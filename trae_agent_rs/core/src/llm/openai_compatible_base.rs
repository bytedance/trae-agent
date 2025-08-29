// Copyright (c) 2025 ByteDance Ltd. and/or its affiliates
// SPDX-License-Identifier: MIT

use async_trait::async_trait;
use reqwest::Client;
use serde::{Deserialize, Serialize};
use serde_json::json;
use std::collections::HashMap;
use std::time::Duration;

use crate::llm::llm_provider::LLMProvider;
use crate::config::ModelConfig;
use crate::llm::error::{LLMError, LLMResult};
use crate::llm::retry_utils::retry_with_backoff;
use crate::llm::{LLMMessage, LLMResponse, LLMUsage};
use crate::tools::{Tool, ToolCall, ToolResult};

/// Provider configuration trait for OpenAI-compatible clients
pub trait ProviderConfig {
    fn get_service_name(&self) -> &str;
    fn get_provider_name(&self) -> &str;
    fn get_extra_headers(&self) -> HashMap<String, String>;
    fn supports_tool_calling(&self, model_name: &str) -> bool;
}

/// OpenAI-compatible request structure
#[derive(Debug, Serialize)]
struct OpenAIRequest {
    model: String,
    messages: Vec<OpenAIMessage>,
    #[serde(skip_serializing_if = "Option::is_none")]
    tools: Option<Vec<serde_json::Value>>,
    #[serde(skip_serializing_if = "Option::is_none")]
    temperature: Option<f32>,
    #[serde(skip_serializing_if = "Option::is_none")]
    top_p: Option<f32>,
    #[serde(skip_serializing_if = "Option::is_none")]
    max_tokens: Option<u32>,
}

#[derive(Debug, Serialize, Deserialize)]
struct OpenAIMessage {
    role: String,
    content: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    tool_calls: Option<Vec<OpenAIToolCall>>,
}

#[derive(Debug, Serialize, Deserialize)]
struct OpenAIToolCall {
    id: String,
    #[serde(rename = "type")]
    call_type: String,
    function: OpenAIFunction,
}

#[derive(Debug, Serialize, Deserialize)]
struct OpenAIFunction {
    name: String,
    arguments: String,
}

/// OpenAI-compatible response structure
#[derive(Debug, Deserialize)]
struct OpenAIResponse {
    choices: Vec<OpenAIChoice>,
    usage: Option<OpenAIUsage>,
    model: Option<String>,
}

#[derive(Debug, Deserialize)]
struct OpenAIChoice {
    message: OpenAIResponseMessage,
    finish_reason: Option<String>,
}

#[derive(Debug, Deserialize)]
struct OpenAIResponseMessage {
    role: String,
    content: Option<String>,
    tool_calls: Option<Vec<OpenAIToolCall>>,
}

#[derive(Debug, Deserialize)]
struct OpenAIUsage {
    prompt_tokens: i32,
    completion_tokens: i32,
    total_tokens: i32,
}

/// Generic OpenAI-compatible client
pub struct OpenAICompatibleClient<P: ProviderConfig> {
    client: Client,
    config: ModelConfig,
    provider: P,
    chat_history: Vec<LLMMessage>,
}

impl<P: ProviderConfig> OpenAICompatibleClient<P> {
    pub fn new(config: &ModelConfig, provider: P) -> LLMResult<Self> {
        let client = Client::builder()
            .timeout(Duration::from_secs(30))
            .build()
            .map_err(|e| LLMError::ConfigError(e.to_string()))?;
        
        Ok(Self {
            client,
            config: config.clone(),
            provider,
            chat_history: Vec::new(),
        })
    }

    async fn make_api_call(&self, request: OpenAIRequest) -> LLMResult<OpenAIResponse> {
         let base_url = self.config.model_provider.base_url
             .as_ref()
             .ok_or_else(|| LLMError::ConfigError("Base URL not configured".to_string()))?;
         
         let url = format!("{}/chat/completions", base_url);
         
         let mut headers = reqwest::header::HeaderMap::new();
         let api_key = self.config.model_provider.api_key
             .as_ref()
             .ok_or_else(|| LLMError::AuthError("API key not configured".to_string()))?;
         headers.insert(
             reqwest::header::AUTHORIZATION,
             format!("Bearer {}", api_key)
                 .parse()
                 .map_err(|e| LLMError::AuthError(format!("Invalid API key: {}", e)))?,
         );
        headers.insert(
            reqwest::header::CONTENT_TYPE,
            "application/json".parse().unwrap(),
        );
        
        // Add provider-specific headers
        for (key, value) in self.provider.get_extra_headers() {
            let header_name = reqwest::header::HeaderName::from_str(&key).unwrap();
            let header_value = reqwest::header::HeaderValue::from_str(&value).unwrap();
            headers.insert(header_name, header_value);
        }
        
        // Add extra headers from config
         for (key, value) in &self.config.extra_headers {
             headers.insert(
                 key.parse().map_err(|e| LLMError::HttpError(format!("Invalid header key: {}", e)))?,
                 value.parse().map_err(|e| LLMError::HttpError(format!("Invalid header value: {}", e)))?,
             );
         }

         let response = retry_with_backoff(
             || async {
                 self.client
                     .post(&url)
                     .headers(headers.clone())
                     .json(&request)
                     .send()
                     .await
             },
             &crate::llm::retry_utils::RetryConfig::default(),
             self.config.max_retries,
         )
         .await?;

         if !response.status().is_success() {
             let status = response.status();
             let error_text = response.text().await.unwrap_or_default();
             return Err(LLMError::ApiError {
                 status_code: status.as_u16(),
                 message: error_text,
             });
         }

         let response_text = response.text().await?;
         
         serde_json::from_str::<OpenAIResponse>(&response_text)
             .map_err(LLMError::JsonError)
    }

    fn convert_messages(&self, messages: &[LLMMessage]) -> Vec<OpenAIMessage> {
        messages.iter().map(|msg| {
            let content = msg.content
                .as_ref()
                .and_then(|c| c.get("text"))
                .cloned()
                .unwrap_or_default();
            
            let tool_calls = msg.tool_call.as_ref().map(|tc| {
                vec![OpenAIToolCall {
                    id: tc.id.clone(),
                    call_type: "function".to_string(),
                    function: OpenAIFunction {
                        name: tc.name.clone(),
                        arguments: serde_json::to_string(&tc.arguments).unwrap_or_default(),
                    },
                }]
            });
            
            OpenAIMessage {
                role: msg.role.clone(),
                content,
                tool_calls,
            }
        }).collect()
    }

    fn parse_response(&self, response: OpenAIResponse) -> LLMResult<LLMResponse> {
        let choice = response.choices.into_iter().next()
            .ok_or_else(|| LLMError::ApiError { status_code: 500, message: "No choices in response".to_string() })?;
        
        let content = choice.message.content.unwrap_or_default();
        
        let tool_calls = choice.message.tool_calls.map(|calls| {
            calls.into_iter().map(|call| {
                let arguments: HashMap<String, serde_json::Value> = serde_json::from_str(&call.function.arguments)
                    .unwrap_or_else(|_| HashMap::new());
                
                ToolCall {
                    id: Some(call.id.clone()),
                    call_id: call.id,
                    name: call.function.name,
                    arguments,
                }
            }).collect()
        });
        
        let usage = response.usage.map(|u| LLMUsage {
            input_tokens: u.prompt_tokens,
            output_tokens: u.completion_tokens,
            cache_creation_input_tokens: 0,
            cache_read_input_tokens: 0,
            reasoning_tokens: 0,
        });
        
        Ok(LLMResponse {
            content,
            usage,
            model: response.model,
            finish_reason: choice.finish_reason,
            tool_calls,
        })
    }
}

#[async_trait]
impl<P: ProviderConfig + Send + Sync> LLMProvider for OpenAICompatibleClient<P> {
    fn set_chat_history(&mut self, messages: Vec<LLMMessage>) {
        self.chat_history = messages;
    }

    async fn chat(
        &mut self,
        messages: Vec<LLMMessage>,
        model_config: &ModelConfig,
        tools: Option<Vec<Box<dyn Tool>>>,
        reuse_history: Option<bool>,
    ) -> LLMResult<LLMResponse> {
        if reuse_history.unwrap_or(true) {
            self.chat_history.clear();
        }
        self.chat_history.extend(messages);
        
        let openai_messages = self.convert_messages(&self.chat_history);
        
        let tool_schemas = if self.provider.supports_tool_calling(&model_config.model) {
            tools.map(|tools| {
                tools.iter().map(|tool| {
                    serde_json::json!({
                        "type": "function",
                        "function": {
                            "name": tool.get_name(),
                            "description": tool.get_description(),
                            "parameters": tool.get_input_schema()
                        }
                    })
                }).collect::<Vec<_>>()
            })
        } else {
            None
        };
        
        let request = OpenAIRequest {
            model: model_config.model.clone(),
            messages: openai_messages,
            tools: tool_schemas,
            temperature: model_config.temperature,
            top_p: model_config.top_p,
            max_tokens: model_config.max_tokens,
        };
        
        let response = self.make_api_call(request).await?;
        self.parse_response(response)
    }

    fn get_provider_name(&self) -> &str {
        self.provider.get_provider_name()
    }

    fn supports_tool_calling(&self, model_name: &str) -> bool {
        self.provider.supports_tool_calling(model_name)
    }
}