// Copyright (c) 2025 ByteDance Ltd. and/or its affiliates
// SPDX-License-Identifier: MIT

use backoff::ExponentialBackoff;
use log::{debug, warn};
use std::time::Duration;
use crate::llm::error::{LLMError, LLMResult};

/// Retry configuration for LLM API calls
#[derive(Debug, Clone)]
pub struct RetryConfig {
    pub max_retries: u32,
    pub initial_interval: Duration,
    pub max_interval: Duration,
    pub multiplier: f64,
}

impl Default for RetryConfig {
    fn default() -> Self {
        Self {
            max_retries: 3,
            initial_interval: Duration::from_millis(1000),
            max_interval: Duration::from_secs(60),
            multiplier: 2.0,
        }
    }
}

/// Retry a function with exponential backoff
pub async fn retry_with_backoff<F, Fut, T>(
    mut operation: F,
    config: RetryConfig,
    provider_name: &str,
) -> LLMResult<T>
where
    F: FnMut() -> Fut,
    Fut: std::future::Future<Output = LLMResult<T>>,
{
    let backoff = ExponentialBackoff {
        initial_interval: config.initial_interval,
        max_interval: config.max_interval,
        multiplier: config.multiplier,
        max_elapsed_time: Some(Duration::from_secs(300)), // 5 minutes max
        ..Default::default()
    };

    let mut attempt = 0u32;
    
    loop {
        match operation().await {
            Ok(result) => {
                if attempt > 0 {
                    debug!("[{}] Succeeded after {} retries", provider_name, attempt);
                }
                return Ok(result);
            }
            Err(err) => {
                attempt += 1;
                
                let should_retry = match &err {
                    LLMError::HttpError(reqwest_err) => should_retry_http_error(reqwest_err),
                    LLMError::RateLimitError(_) => true,
                    LLMError::TimeoutError(_) => true,
                    LLMError::ApiError { status_code, .. } => should_retry_status_code(*status_code),
                    _ => false,
                };
                
                if !should_retry || attempt >= config.max_retries {
                    return Err(err);
                }
                
                let delay = backoff.initial_interval.mul_f64(config.multiplier.powi((attempt - 1) as i32));
                let delay = delay.min(backoff.max_interval);
                
                warn!(
                    "[{}] Attempt {} failed, retrying in {:?}: {}",
                    provider_name, attempt, delay, err
                );
                
                tokio::time::sleep(delay).await;
            }
        }
    }
}

/// Check if an HTTP error should be retried
fn should_retry_http_error(err: &reqwest::Error) -> bool {
    if err.is_timeout() || err.is_connect() {
        return true;
    }
    
    if let Some(status) = err.status() {
        should_retry_status_code(status.as_u16())
    } else {
        // Network errors without status codes are usually retryable
        true
    }
}

/// Check if an HTTP status code should be retried
fn should_retry_status_code(status_code: u16) -> bool {
    match status_code {
        // Server errors are generally retryable
        500..=599 => true,
        // Rate limiting
        429 => true,
        // Client errors are generally not retryable
        400..=499 => false,
        // Success codes shouldn't reach here, but don't retry
        200..=299 => false,
        // Other codes, be conservative and don't retry
        _ => false,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_should_retry_status_code() {
        assert!(should_retry_status_code(500));
        assert!(should_retry_status_code(502));
        assert!(should_retry_status_code(429));
        assert!(!should_retry_status_code(400));
        assert!(!should_retry_status_code(401));
        assert!(!should_retry_status_code(404));
        assert!(!should_retry_status_code(200));
    }
}