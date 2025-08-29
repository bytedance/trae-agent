// Copyright (c) 2025 ByteDance Ltd. and/or its affiliates
// SPDX-License-Identifier: MIT

use thiserror::Error;

/// Errors that can occur when interacting with LLM clients
#[derive(Error, Debug)]
pub enum LLMError {
    #[error("HTTP request failed: {0}")]
    HttpError(#[from] reqwest::Error),
    
    #[error("JSON serialization/deserialization error: {0}")]
    JsonError(#[from] serde_json::Error),
    
    #[error("Invalid configuration: {0}")]
    ConfigError(String),
    
    #[error("Authentication failed: {0}")]
    AuthError(String),
    
    #[error("Rate limit exceeded: {0}")]
    RateLimitError(String),
    
    #[error("API error: {status_code} - {message}")]
    ApiError {
        status_code: u16,
        message: String,
    },
    
    #[error("Tool calling not supported for model: {0}")]
    ToolCallNotSupported(String),
    
    #[error("Invalid tool call: {0}")]
    InvalidToolCall(String),
    
    #[error("Timeout error: {0}")]
    TimeoutError(String),
    
    #[error("Unknown error: {0}")]
    Unknown(String),
}

pub type LLMResult<T> = Result<T, LLMError>;