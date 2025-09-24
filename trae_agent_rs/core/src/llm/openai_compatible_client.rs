// Copyright (c) 2025 ByteDance Ltd. and/or its affiliates
// SPDX-License-Identifier: MIT

use async_trait::async_trait;
use reqwest::Client;
use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::time::Duration;

use crate::config::ModelConfig;
use crate::llm::error::{LLMError, LLMResult};
use crate::llm::llm_basics::{ContentItem, LLMMessage, LLMResponse, LLMUsage};
use crate::llm::llm_provider::LLMProvider;
use crate::llm::retry_utils::retry_with_backoff;
use crate::tools::{Tool, ToolCall};

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
    max_completion_tokens: Option<u32>,
    #[serde(skip_serializing_if = "Option::is_none")]
    stream: Option<bool>,
}

#[derive(Debug, Serialize, Deserialize, Clone)]
struct OpenAIMessage {
    role: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    content: Option<serde_json::Value>,
    #[serde(skip_serializing_if = "Option::is_none")]
    tool_calls: Option<Vec<OpenAIToolCall>>,
}

#[derive(Debug, Serialize, Deserialize, Clone)]
struct OpenAIToolCall {
    id: String,
    #[serde(rename = "type")]
    call_type: String,
    function: OpenAIFunction,
}

#[derive(Debug, Serialize, Deserialize, Clone)]
struct OpenAIFunction {
    name: String,
    arguments: String,
}

/// OpenAI-compatible response structure
#[derive(Debug, Deserialize, Clone)]
struct OpenAIResponse {
    choices: Vec<OpenAIChoice>,
    usage: Option<OpenAIUsage>,
    model: Option<String>,
}

#[derive(Debug, Deserialize, Clone)]
struct OpenAIChoice {
    message: OpenAIResponseMessage,
    finish_reason: Option<String>,
}

#[derive(Debug, Deserialize, Clone)]
struct OpenAIResponseMessage {
    role: String,
    content: Option<String>,
    tool_calls: Option<Vec<OpenAIToolCall>>,
}

#[derive(Debug, Deserialize, Clone)]
#[allow(dead_code)]
struct OpenAIUsage {
    prompt_tokens: i32,
    completion_tokens: i32,
    total_tokens: i32,
}

/// OpenAI-compatible streaming response structures
#[derive(Debug, Deserialize, Clone)]
struct OpenAIStreamResponse {
    choices: Vec<OpenAIStreamChoice>,
    model: Option<String>,
    usage: Option<OpenAIUsage>,
}

#[derive(Debug, Deserialize, Clone)]
struct OpenAIStreamChoice {
    delta: OpenAIStreamDelta,
    finish_reason: Option<String>,
}

#[derive(Debug, Deserialize, Clone)]
struct OpenAIStreamDelta {
    content: Option<String>,
    tool_calls: Option<Vec<OpenAIToolCall>>,
}

/// Generic OpenAI-compatible client
pub struct OpenAICompatibleClient {
    client: Client,
    config: ModelConfig,
    chat_history: Vec<OpenAIMessage>,
}

impl OpenAICompatibleClient {
    pub fn new(config: &ModelConfig) -> LLMResult<Self> {
        let client = Client::builder()
            .timeout(Duration::from_secs(30))
            .build()
            .map_err(|e| LLMError::ConfigError(e.to_string()))?;

        Ok(Self {
            client,
            config: config.clone(),
            chat_history: Vec::new(),
        })
    }

    async fn make_api_call(&self, request: OpenAIRequest) -> LLMResult<OpenAIResponse> {
        let base_url = self
            .config
            .model_provider
            .base_url
            .as_ref()
            .ok_or_else(|| LLMError::ConfigError("Base URL not configured".to_string()))?;

        let url = if base_url.ends_with("/chat/completions") {
            base_url.clone()
        } else if base_url.ends_with("/") {
            format!("{}chat/completions", base_url)
        } else {
            format!("{}/chat/completions", base_url)
        };

        let mut headers = reqwest::header::HeaderMap::new();
        let api_key = self
            .config
            .model_provider
            .api_key
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

        // Add provider-specific headers from environment variables
        if let Ok(site_url) = std::env::var("OPENAI_COMPATIBLE_SITE_URL")
            && let Ok(header_value) = site_url.parse::<reqwest::header::HeaderValue>()
        {
            headers.insert(
                "HTTP-Referer"
                    .parse::<reqwest::header::HeaderName>()
                    .unwrap(),
                header_value,
            );
        }

        if let Ok(site_name) = std::env::var("OPENAI_COMPATIBLE_SITE_NAME")
            && let Ok(header_value) = site_name.parse::<reqwest::header::HeaderValue>()
        {
            headers.insert(
                "X-Title".parse::<reqwest::header::HeaderName>().unwrap(),
                header_value,
            );
        }

        // Add extra headers from config
        for (key, value) in &self.config.extra_headers {
            headers.insert(
                key.parse::<reqwest::header::HeaderName>()
                    .map_err(|e| LLMError::ConfigError(format!("Invalid header key: {}", e)))?,
                value
                    .parse::<reqwest::header::HeaderValue>()
                    .map_err(|e| LLMError::ConfigError(format!("Invalid header value: {}", e)))?,
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
                    .map_err(LLMError::HttpError)
            },
            crate::llm::retry_utils::RetryConfig::default(),
            "openai_compatible",
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

        serde_json::from_str::<OpenAIResponse>(&response_text).map_err(|e| {
            eprintln!("Failed to parse response: {}", response_text);
            if response_text.trim().is_empty() {
                LLMError::ApiError {
                    status_code: 200,
                    message: "Empty response body received from API".to_string(),
                }
            } else {
                LLMError::ApiError {
                    status_code: 200,
                    message: format!("Invalid JSON response: {}. Response body: {}", e, response_text.chars().take(500).collect::<String>()),
                }
            }
        })
    }

    async fn make_streaming_api_call(
        &self,
        request: OpenAIRequest,
    ) -> LLMResult<reqwest::Response> {
        let base_url = self
            .config
            .model_provider
            .base_url
            .as_ref()
            .ok_or_else(|| LLMError::ConfigError("Base URL not configured".to_string()))?;

        let url = if base_url.ends_with("/chat/completions") {
            base_url.clone()
        } else if base_url.ends_with("/") {
            format!("{}chat/completions", base_url)
        } else {
            format!("{}/chat/completions", base_url)
        };

        let mut headers = reqwest::header::HeaderMap::new();
        let api_key = self
            .config
            .model_provider
            .api_key
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

        // Add provider-specific headers from environment variables
        if let Ok(site_url) = std::env::var("OPENAI_COMPATIBLE_SITE_URL")
            && let Ok(header_value) = site_url.parse::<reqwest::header::HeaderValue>()
        {
            headers.insert(
                "HTTP-Referer"
                    .parse::<reqwest::header::HeaderName>()
                    .unwrap(),
                header_value,
            );
        }

        if let Ok(site_name) = std::env::var("OPENAI_COMPATIBLE_SITE_NAME")
            && let Ok(header_value) = site_name.parse::<reqwest::header::HeaderValue>()
        {
            headers.insert(
                "X-Title".parse::<reqwest::header::HeaderName>().unwrap(),
                header_value,
            );
        }

        // Add extra headers from config
        for (key, value) in &self.config.extra_headers {
            headers.insert(
                key.parse::<reqwest::header::HeaderName>()
                    .map_err(|e| LLMError::ConfigError(format!("Invalid header key: {}", e)))?,
                value
                    .parse::<reqwest::header::HeaderValue>()
                    .map_err(|e| LLMError::ConfigError(format!("Invalid header value: {}", e)))?,
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
                    .map_err(LLMError::HttpError)
            },
            crate::llm::retry_utils::RetryConfig::default(),
            "openai_compatible",
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

        Ok(response)
    }

    fn parse_sse_chunk(&self, chunk: &str) -> LLMResult<Option<crate::llm::StreamChunk>> {
        for line in chunk.lines() {
            if line.starts_with("data: ")
                && let Some(data) = line.strip_prefix("data: ")
            {
                if data == "[DONE]" {
                    return Ok(None);
                }

                match serde_json::from_str::<OpenAIStreamResponse>(data) {
                    Ok(response) => {
                        if let Some(choice) = response.choices.first() {
                            return Ok(Some(crate::llm::StreamChunk {
                                content: choice
                                    .delta
                                    .content
                                    .as_ref()
                                    .map(|c| vec![ContentItem::text(c.clone())]),
                                finish_reason: choice.finish_reason.as_ref().map(|fr| {
                                    match fr.as_str() {
                                        "stop" => crate::llm::FinishReason::Stop,
                                        "tool_calls" => crate::llm::FinishReason::ToolCalls,
                                        "content_filter" => crate::llm::FinishReason::ContentFilter,
                                        _ => crate::llm::FinishReason::Stop,
                                    }
                                }),
                                model: response.model.clone(),
                                tool_calls: choice.delta.tool_calls.as_ref().map(|calls| {
                                    calls
                                        .iter()
                                        .map(|call| {
                                            let arguments: HashMap<String, serde_json::Value> =
                                                serde_json::from_str(&call.function.arguments)
                                                    .unwrap_or_default();
                                            ToolCall {
                                                name: call.function.name.clone(),
                                                call_id: call.id.clone(),
                                                arguments,
                                                id: Some(call.id.clone()),
                                            }
                                        })
                                        .collect()
                                }),
                                usage: response.usage.map(|u| crate::llm::llm_basics::LLMUsage {
                                    input_tokens: u.prompt_tokens,
                                    output_tokens: u.completion_tokens,
                                    cache_creation_input_tokens: 0,
                                    cache_read_input_tokens: 0,
                                    reasoning_tokens: 0,
                                }),
                            }));
                        }
                    }
                    Err(_) => continue,
                }
            }
        }
        Ok(None)
    }

    fn supports_tool_calling(&self, model_name: &str) -> bool {
        let model_lower = model_name.to_lowercase();
        let tool_capable_patterns = [
            "gpt-4",
            "gpt-3.5-turbo",
            "claude-3",
            "claude-2",
            "gemini",
            "mistral",
            "llama-3",
            "command-r",
        ];

        tool_capable_patterns
            .iter()
            .any(|pattern| model_lower.contains(pattern))
    }

    fn convert_messages(&self, messages: &[LLMMessage]) -> Vec<OpenAIMessage> {
        messages
            .iter()
            .map(|msg| {
                let content = msg.content.as_ref().map(|content_vec| {
                    if content_vec.len() == 1 {
                        // Single content item - could be simple text string or complex object
                        match &content_vec[0] {
                            ContentItem::Text(text_content) => {
                                serde_json::Value::String(text_content.text.clone())
                            }
                            ContentItem::Image(_) => {
                                // For images, create array format for OpenAI compatible
                                self.convert_content_to_openai_array(content_vec)
                            }
                        }
                    } else if content_vec.is_empty() {
                        serde_json::Value::String(String::new())
                    } else {
                        // Multiple content items - always use array format
                        self.convert_content_to_openai_array(content_vec)
                    }
                });

                let tool_calls = msg.tool_call.as_ref().map(|tc| {
                    vec![OpenAIToolCall {
                        id: tc.id.clone().unwrap_or_else(|| tc.call_id.clone()),
                        call_type: "function".to_string(),
                        function: OpenAIFunction {
                            name: tc.name.clone(),
                            arguments: serde_json::to_string(&tc.arguments).unwrap_or_default(),
                        },
                    }]
                });

                OpenAIMessage {
                    role: msg.role.as_str().to_string(),
                    content,
                    tool_calls,
                }
            })
            .collect()
    }

    fn convert_content_to_openai_array(&self, content_vec: &[ContentItem]) -> serde_json::Value {
        let content_array: Vec<serde_json::Value> = content_vec
            .iter()
            .map(|item| match item {
                ContentItem::Text(text_content) => {
                    serde_json::json!({
                        "type": "text",
                        "text": text_content.text
                    })
                }
                ContentItem::Image(image_content) => match &image_content.source {
                    crate::llm::llm_basics::ImageSource::Base64 { media_type, data } => {
                        serde_json::json!({
                            "type": "image_url",
                            "image_url": {
                                "url": format!("data:{};base64,{}", media_type, data)
                            }
                        })
                    }
                    crate::llm::llm_basics::ImageSource::Url { url } => {
                        serde_json::json!({
                            "type": "image_url",
                            "image_url": {
                                "url": url
                            }
                        })
                    }
                },
            })
            .collect();

        serde_json::Value::Array(content_array)
    }

    fn parse_response(&self, response: OpenAIResponse) -> LLMResult<LLMResponse> {
        let choice = response
            .choices
            .into_iter()
            .next()
            .ok_or_else(|| LLMError::ApiError {
                status_code: 500,
                message: "No choices in response".to_string(),
            })?;

        let content = choice.message.content.unwrap_or_default();

        let tool_calls = choice.message.tool_calls.map(|calls| {
            calls
                .into_iter()
                .map(|call| {
                    let arguments: HashMap<String, serde_json::Value> =
                        serde_json::from_str(&call.function.arguments)
                            .unwrap_or_else(|_| HashMap::new());

                    ToolCall {
                        id: Some(call.id.clone()),
                        call_id: call.id,
                        name: call.function.name,
                        arguments,
                    }
                })
                .collect()
        });

        let usage = response.usage.map(|u| LLMUsage {
            input_tokens: u.prompt_tokens,
            output_tokens: u.completion_tokens,
            cache_creation_input_tokens: 0,
            cache_read_input_tokens: 0,
            reasoning_tokens: 0,
        });

        // Convert content string to Vec<ContentItem>
        let content_vec = if content.is_empty() {
            vec![]
        } else {
            vec![ContentItem::text(content)]
        };

        // Convert finish_reason string to FinishReason enum
        let finish_reason = match choice.finish_reason.as_deref() {
            Some("stop") => crate::llm::FinishReason::Stop,
            Some("tool_calls") => crate::llm::FinishReason::ToolCalls,
            Some("content_filter") => crate::llm::FinishReason::ContentFilter,
            _ => crate::llm::FinishReason::Stop,
        };

        Ok(LLMResponse {
            content: content_vec,
            usage,
            model: response.model,
            finish_reason,
            tool_calls,
        })
    }
}

#[async_trait]
impl LLMProvider for OpenAICompatibleClient {
    fn set_chat_history(&mut self, messages: Vec<LLMMessage>) {
        self.chat_history = self.convert_messages(&messages);
    }

    async fn chat(
        &mut self,
        messages: Vec<LLMMessage>,
        model_config: &ModelConfig,
        tools: Option<&Vec<Box<dyn Tool>>>,
        reuse_history: Option<bool>,
    ) -> LLMResult<LLMResponse> {
        let parsed_messages = self.convert_messages(&messages);

        let mut all_messages = Vec::new();
        if reuse_history.unwrap_or(true) {
            all_messages.extend(self.chat_history.clone());
        }
        all_messages.extend(parsed_messages);

        let tool_schemas = if self.supports_tool_calling(&model_config.model) {
            tools.map(|tools| {
                tools
                    .iter()
                    .map(|tool| {
                        serde_json::json!({
                            "type": "function",
                            "function": {
                                "name": tool.get_name(),
                                "description": tool.get_description(),
                                "parameters": tool.get_input_schema()
                            }
                        })
                    })
                    .collect::<Vec<_>>()
            })
        } else {
            None
        };

        let request = OpenAIRequest {
            model: model_config.model.clone(),
            messages: all_messages,
            tools: tool_schemas,
            temperature: model_config.temperature,
            top_p: model_config.top_p,
            max_completion_tokens: model_config.max_tokens,
            stream: None, // Non-streaming for regular chat
        };

        let response = self.make_api_call(request).await?;
        let llm_response = self.parse_response(response.clone())?;

        // Add the assistant's response to chat history
        if let Some(choice) = response.choices.first() {
            let assistant_message = OpenAIMessage {
                role: choice.message.role.clone(),
                content: choice
                    .message
                    .content
                    .as_ref()
                    .map(|c| serde_json::Value::String(c.clone())),
                tool_calls: choice.message.tool_calls.clone(),
            };
            self.chat_history.push(assistant_message);
        }

        Ok(llm_response)
    }

    fn get_provider_name(&self) -> &str {
        "openai_compatible"
    }

    async fn chat_stream(
        &mut self,
        messages: Vec<LLMMessage>,
        model_config: &ModelConfig,
        tools: Option<&Vec<Box<dyn Tool>>>,
        reuse_history: Option<bool>,
    ) -> LLMResult<crate::llm::LLMStream> {
        // Note: For streaming responses, chat history is not automatically updated.
        // The caller should accumulate the complete response from the stream and
        // manually add it to chat history using set_chat_history() if needed.
        let parsed_messages = self.convert_messages(&messages);

        let mut all_messages = Vec::new();
        if reuse_history.unwrap_or(true) {
            all_messages.extend(self.chat_history.clone());
        }
        all_messages.extend(parsed_messages);

        let tool_schemas = if self.supports_tool_calling(&model_config.model) {
            tools.map(|tools| {
                tools
                    .iter()
                    .map(|tool| {
                        serde_json::json!({
                            "type": "function",
                            "function": {
                                "name": tool.get_name(),
                                "description": tool.get_description(),
                                "parameters": tool.get_input_schema()
                            }
                        })
                    })
                    .collect::<Vec<_>>()
            })
        } else {
            None
        };

        let request = OpenAIRequest {
            model: model_config.model.clone(),
            messages: all_messages,
            tools: tool_schemas,
            temperature: model_config.temperature,
            top_p: model_config.top_p,
            max_completion_tokens: model_config.max_tokens,
            stream: Some(true), // Enable streaming
        };

        let response = self.make_streaming_api_call(request).await?;

        use futures::stream;

        // Read the entire response body first
        let response_text = response.text().await.map_err(LLMError::HttpError)?;

        // Parse lines and collect chunks
        let mut chunks = Vec::new();

        for line in response_text.lines() {
            if line.trim().is_empty() {
                continue;
            }

            if line.starts_with("data: ")
                && let Some(data) = line.strip_prefix("data: ")
            {
                if data == "[DONE]" {
                    break;
                }

                match self.parse_sse_chunk(line) {
                    Ok(Some(chunk)) => chunks.push(Ok(chunk)),
                    Ok(None) => continue,
                    Err(e) => chunks.push(Err(e)),
                }
            } else if line.starts_with(": ") {
                // Comment line (keepalive), ignore per SSE spec
                continue;
            }
        }

        let chunk_stream = stream::iter(chunks);
        Ok(Box::pin(chunk_stream))
    }
}

/// OpenAI compatible client
pub type OpenAICompatibleGenericClient = OpenAICompatibleClient;

impl OpenAICompatibleGenericClient {
    pub fn with_config(model_config: ModelConfig) -> LLMResult<Self> {
        // Set default base URL if not provided (this is just an example, should be set by user)
        if model_config.model_provider.base_url.is_none() {
            // No default URL - user must provide one
            return Err(crate::llm::error::LLMError::ConfigError(
                "Base URL must be provided for OpenAI compatible client".to_string(),
            ));
        }
        OpenAICompatibleClient::new(&model_config)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::config::ModelProvider;

    #[test]
    fn test_parse_sse_chunk() {
        let model_provider = ModelProvider::new("test".to_string())
            .with_api_key("test_key".to_string())
            .with_base_url("https://api.test.com/v1".to_string());
        let config = ModelConfig::new("test-model".to_string(), model_provider);

        let client = OpenAICompatibleClient::new(&config).unwrap();

        // Test parsing a valid SSE chunk
        let chunk_data = r#"data: {"choices":[{"delta":{"content":"Hello"},"finish_reason":null}],"model":"test-model"}"#;
        let result = client.parse_sse_chunk(chunk_data).unwrap();

        assert!(result.is_some());
        let chunk = result.unwrap();
        assert!(chunk.content.is_some());
        assert_eq!(chunk.content.as_ref().unwrap()[0].as_text(), Some("Hello"));

        // Test parsing [DONE] marker
        let done_data = "data: [DONE]";
        let result = client.parse_sse_chunk(done_data).unwrap();
        assert!(result.is_none());

        // Test invalid JSON
        let invalid_data = "data: {invalid json}";
        let result = client.parse_sse_chunk(invalid_data).unwrap();
        assert!(result.is_none());
    }

    #[test]
    fn test_streaming_request_structure() {
        let request = OpenAIRequest {
            model: "test-model".to_string(),
            messages: vec![],
            tools: None,
            temperature: Some(0.7),
            top_p: None,
            max_completion_tokens: Some(100),
            stream: Some(true),
        };

        let json = serde_json::to_string(&request).unwrap();
        assert!(json.contains("\"stream\":true"));
        assert!(json.contains("\"model\":\"test-model\""));
    }
}
