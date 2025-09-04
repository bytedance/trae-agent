// Copyright (c) 2025 ByteDance Ltd. and/or its affiliates
// SPDX-License-Identifier: MIT

use async_trait::async_trait;
use reqwest::Client;
use serde::{Deserialize, Serialize};
use serde_json::Value;
use std::collections::HashMap;
use futures::stream;

use crate::{
    llm::{
        llm_provider::LLMProvider,
        error::{LLMError, LLMResult},
        retry_utils::{retry_with_backoff, RetryConfig},
        llm_basics::{LLMMessage, LLMResponse, LLMUsage, LLMStream, StreamChunk, FinishReason, ContentItem, MessageRole},
    },
    config::ModelConfig,
    tools::{Tool, ToolCall, ToolResult},
};

/// Anthropic request structure
#[derive(Debug, Clone, Serialize)]
struct AnthropicRequest {
    model: String,
    max_tokens: u32,
    messages: Vec<AnthropicMessage>,
    #[serde(skip_serializing_if = "Option::is_none")]
    system: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    tools: Option<Vec<AnthropicTool>>,
    #[serde(skip_serializing_if = "Option::is_none")]
    temperature: Option<f32>,
    #[serde(skip_serializing_if = "Option::is_none")]
    top_p: Option<f32>,
    #[serde(skip_serializing_if = "Option::is_none")]
    stream: Option<bool>,
}

/// Anthropic message structure
#[derive(Debug, Clone, Serialize, Deserialize)]
struct AnthropicMessage {
    role: String,
    content: AnthropicContent,
}

/// Anthropic content can be either string or array of content blocks
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(untagged)]
enum AnthropicContent {
    String(String),
    Array(Vec<AnthropicContentBlock>),
}

/// Anthropic content block
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(tag = "type")]
enum AnthropicContentBlock {
    #[serde(rename = "text")]
    Text { text: String },
    #[serde(rename = "image")]
    Image { source: AnthropicImageSource },
    #[serde(rename = "tool_use")]
    ToolUse {
        id: String,
        name: String,
        input: HashMap<String, Value>,
    },
    #[serde(rename = "tool_result")]
    ToolResult {
        tool_use_id: String,
        content: String,
        #[serde(skip_serializing_if = "Option::is_none")]
        is_error: Option<bool>,
    },
}

/// Anthropic image source
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(tag = "type")]
enum AnthropicImageSource {
    #[serde(rename = "base64")]
    Base64 {
        media_type: String,
        data: String,
    },
}

/// Anthropic tool definition
#[derive(Debug, Clone, Serialize)]
struct AnthropicTool {
    name: String,
    description: String,
    input_schema: Value,
}

/// Anthropic response structure
#[derive(Debug, Clone, Deserialize)]
struct AnthropicResponse {
    id: String,
    #[serde(rename = "type")]
    response_type: String,
    role: String,
    content: Vec<AnthropicResponseContent>,
    model: String,
    stop_reason: Option<String>,
    stop_sequence: Option<String>,
    usage: AnthropicUsage,
}

/// Anthropic response content
#[derive(Debug, Clone, Deserialize)]
#[serde(tag = "type")]
enum AnthropicResponseContent {
    #[serde(rename = "text")]
    Text { text: String },
    #[serde(rename = "tool_use")]
    ToolUse {
        id: String,
        name: String,
        input: HashMap<String, Value>,
    },
}

/// Anthropic usage structure
#[derive(Debug, Clone, Deserialize)]
struct AnthropicUsage {
    input_tokens: i32,
    output_tokens: i32,
    #[serde(default)]
    cache_creation_input_tokens: i32,
    #[serde(default)]
    cache_read_input_tokens: i32,
}

/// Anthropic streaming event structure
#[derive(Debug, Clone, Deserialize)]
struct AnthropicStreamEvent {
    #[serde(rename = "type")]
    event_type: String,
    #[serde(flatten)]
    data: Option<Value>,
}

/// Message start event
#[derive(Debug, Clone, Deserialize)]
struct MessageStartEvent {
    message: AnthropicResponse,
}

/// Content block delta event
#[derive(Debug, Clone, Deserialize)]
struct ContentBlockDeltaEvent {
    index: u32,
    delta: ContentDelta,
}

/// Content delta
#[derive(Debug, Clone, Deserialize)]
#[serde(tag = "type")]
enum ContentDelta {
    #[serde(rename = "text_delta")]
    TextDelta { text: String },
    #[serde(rename = "input_json_delta")]
    InputJsonDelta { partial_json: String },
}

/// Message delta event
#[derive(Debug, Clone, Deserialize)]
struct MessageDeltaEvent {
    delta: MessageDelta,
    usage: Option<AnthropicUsage>,
}

/// Message delta
#[derive(Debug, Clone, Deserialize)]
struct MessageDelta {
    stop_reason: Option<String>,
    stop_sequence: Option<String>,
}

/// Anthropic client implementation
pub struct AnthropicClient {
    client: Client,
    api_key: String,
    base_url: String,
    message_history: Vec<AnthropicMessage>,
    system_message: Option<String>,
}

impl AnthropicClient {
    pub fn new(model_config: &ModelConfig) -> LLMResult<Self> {
        let api_key = model_config
            .model_provider
            .api_key
            .as_ref()
            .ok_or_else(|| LLMError::ConfigError("API key is required".to_string()))?
            .clone();

        let base_url = model_config
            .model_provider
            .base_url
            .as_ref()
            .unwrap_or(&"https://api.anthropic.com/v1".to_string())
            .clone();

        Ok(Self {
            client: Client::new(),
            api_key,
            base_url,
            message_history: Vec::new(),
            system_message: None,
        })
    }

    async fn create_response(&self, request: AnthropicRequest) -> LLMResult<AnthropicResponse> {
        let url = format!("{}/messages", self.base_url);

        let response = self
            .client
            .post(&url)
            .header("x-api-key", &self.api_key)
            .header("Content-Type", "application/json")
            .header("anthropic-version", "2023-06-01")
            .json(&request)
            .send()
            .await
            .map_err(LLMError::HttpError)?;

        if !response.status().is_success() {
            let status_code = response.status().as_u16();
            let error_text = response.text().await.unwrap_or_default();
            return Err(LLMError::ApiError {
                status_code,
                message: error_text,
            });
        }

        response.json().await.map_err(LLMError::HttpError)
    }

    async fn create_stream_response(&self, request: AnthropicRequest) -> LLMResult<LLMStream> {
        let url = format!("{}/messages", self.base_url);

        let response = self
            .client
            .post(&url)
            .header("x-api-key", &self.api_key)
            .header("Content-Type", "application/json")
            .header("anthropic-version", "2023-06-01")
            .header("Accept", "text/event-stream")
            .json(&request)
            .send()
            .await
            .map_err(LLMError::HttpError)?;

        if !response.status().is_success() {
            let status_code = response.status().as_u16();
            let error_text = response.text().await.unwrap_or_default();
            return Err(LLMError::ApiError {
                status_code,
                message: error_text,
            });
        }

        // Read the entire response body for parsing
        let text = response.text().await.map_err(LLMError::HttpError)?;
        let chunks: Vec<_> = text.lines().filter_map(|line| {
            if line.starts_with("data: ") {
                let data = &line[6..];
                if data == "[DONE]" {
                    return None;
                }
                match self.parse_sse_chunk(line) {
                    Ok(Some(chunk)) => Some(Ok(chunk)),
                    Ok(None) => None,
                    Err(e) => Some(Err(e))
                }
            } else {
                None
            }
        }).collect();

        let stream = stream::iter(chunks);
        Ok(Box::pin(stream))
    }

    fn parse_sse_chunk(&self, chunk: &str) -> LLMResult<Option<StreamChunk>> {
        for line in chunk.lines() {
            if line.starts_with("data: ") {
                let data = &line[6..];
                if data == "[DONE]" {
                    return Ok(None);
                }

                let event: AnthropicStreamEvent = serde_json::from_str(data)
                    .map_err(LLMError::JsonError)?;

                match event.event_type.as_str() {
                    "message_start" => {
                        if let Some(data) = event.data {
                            if let Ok(start_event) = serde_json::from_value::<MessageStartEvent>(data) {
                                return Ok(Some(StreamChunk {
                                    content: None,
                                    finish_reason: None,
                                    model: Some(start_event.message.model),
                                    tool_calls: None,
                                    usage: Some(LLMUsage {
                                        input_tokens: start_event.message.usage.input_tokens,
                                        output_tokens: start_event.message.usage.output_tokens,
                                        cache_creation_input_tokens: start_event.message.usage.cache_creation_input_tokens,
                                        cache_read_input_tokens: start_event.message.usage.cache_read_input_tokens,
                                        reasoning_tokens: 0,
                                    }),
                                }));
                            }
                        }
                    }
                    "content_block_delta" => {
                        if let Some(data) = event.data {
                            if let Ok(delta_event) = serde_json::from_value::<ContentBlockDeltaEvent>(data) {
                                match delta_event.delta {
                                    ContentDelta::TextDelta { text } => {
                                        return Ok(Some(StreamChunk {
                                            content: Some(vec![ContentItem::text(text)]),
                                            finish_reason: None,
                                            model: None,
                                            tool_calls: None,
                                            usage: None,
                                        }));
                                    }
                                    _ => continue,
                                }
                            }
                        }
                    }
                    "message_delta" => {
                        if let Some(data) = event.data {
                            if let Ok(delta_event) = serde_json::from_value::<MessageDeltaEvent>(data) {
                                let finish_reason = delta_event.delta.stop_reason.as_ref().map(|reason| {
                                    match reason.as_str() {
                                        "end_turn" => FinishReason::Stop,
                                        "tool_use" => FinishReason::ToolCalls,
                                        "max_tokens" => FinishReason::Stop,
                                        _ => FinishReason::Stop,
                                    }
                                });

                                return Ok(Some(StreamChunk {
                                    content: None,
                                    finish_reason,
                                    model: None,
                                    tool_calls: None,
                                    usage: delta_event.usage.map(|u| LLMUsage {
                                        input_tokens: u.input_tokens,
                                        output_tokens: u.output_tokens,
                                        cache_creation_input_tokens: u.cache_creation_input_tokens,
                                        cache_read_input_tokens: u.cache_read_input_tokens,
                                        reasoning_tokens: 0,
                                    }),
                                }));
                            }
                        }
                    }
                    _ => continue,
                }
            }
        }
        Ok(None)
    }

    fn convert_messages(&self, messages: &[LLMMessage]) -> Vec<AnthropicMessage> {
        let mut result = Vec::new();

        for msg in messages {
            match msg.role {
                MessageRole::System => {
                    // Anthropic handles system messages separately, skip here
                    continue;
                }
                MessageRole::Tool => {
                    if let Some(tool_result) = &msg.tool_result {
                        result.push(self.convert_tool_result(tool_result));
                    }
                }
                _ => {
                    let content = self.convert_content(&msg.content, &msg.tool_call);
                    result.push(AnthropicMessage {
                        role: match msg.role {
                            MessageRole::User => "user".to_string(),
                            MessageRole::Assistant => "assistant".to_string(),
                            _ => "user".to_string(), // fallback
                        },
                        content,
                    });
                }
            }
        }

        result
    }

    fn convert_content(&self, content: &Option<Vec<ContentItem>>, tool_call: &Option<ToolCall>) -> AnthropicContent {
        let mut blocks = Vec::new();

        // Add content items
        if let Some(content_vec) = content {
            for item in content_vec {
                match item {
                    ContentItem::Text(text_content) => {
                        blocks.push(AnthropicContentBlock::Text {
                            text: text_content.text.clone(),
                        });
                    }
                    ContentItem::Image(image_content) => {
                        match &image_content.source {
                            crate::llm::llm_basics::ImageSource::Base64 { media_type, data } => {
                                blocks.push(AnthropicContentBlock::Image {
                                    source: AnthropicImageSource::Base64 {
                                        media_type: media_type.clone(),
                                        data: data.clone(),
                                    },
                                });
                            }
                            crate::llm::llm_basics::ImageSource::Url { .. } => {
                                // Anthropic doesn't support image URLs directly, would need conversion
                                // For now, skip or add as text description
                            }
                        }
                    }
                }
            }
        }

        // Add tool call if present
        if let Some(tc) = tool_call {
            blocks.push(AnthropicContentBlock::ToolUse {
                id: tc.call_id.clone(),
                name: tc.name.clone(),
                input: tc.arguments.clone(),
            });
        }

        // If only one text block, use string format
        if blocks.len() == 1 {
            if let AnthropicContentBlock::Text { text } = &blocks[0] {
                return AnthropicContent::String(text.clone());
            }
        }

        AnthropicContent::Array(blocks)
    }

    fn convert_tool_result(&self, tool_result: &ToolResult) -> AnthropicMessage {
        let content = AnthropicContent::Array(vec![AnthropicContentBlock::ToolResult {
            tool_use_id: tool_result.call_id.clone(),
            content: if tool_result.success {
                tool_result.result.clone().unwrap_or_default()
            } else {
                tool_result.error.clone().unwrap_or_default()
            },
            is_error: Some(!tool_result.success),
        }]);

        AnthropicMessage {
            role: "user".to_string(), // Tool results are sent as user messages in Anthropic
            content,
        }
    }

    fn extract_system_message(&mut self, messages: &[LLMMessage]) {
        for msg in messages {
            if msg.role == MessageRole::System {
                if let Some(text) = msg.get_text() {
                    self.system_message = Some(text.to_string());
                    break;
                }
            }
        }
    }
}

#[async_trait]
impl LLMProvider for AnthropicClient {
    fn set_chat_history(&mut self, messages: Vec<LLMMessage>) {
        self.extract_system_message(&messages);
        self.message_history = self.convert_messages(&messages);
    }

    async fn chat(
        &mut self,
        messages: Vec<LLMMessage>,
        model_config: &ModelConfig,
        tools: Option<&Vec<Box<dyn Tool>>>,
        reuse_history: Option<bool>,
    ) -> LLMResult<LLMResponse> {
        self.extract_system_message(&messages);
        let parsed_messages = self.convert_messages(&messages);

        let mut all_messages = Vec::new();
        if reuse_history.unwrap_or(true) {
            all_messages.extend(self.message_history.clone());
        }
        all_messages.extend(parsed_messages);

        let tool_schemas = tools.as_ref().map(|tools| {
            tools
                .iter()
                .map(|tool| AnthropicTool {
                    name: tool.get_name().to_string(),
                    description: tool.get_description().to_string(),
                    input_schema: tool.get_input_schema(),
                })
                .collect()
        });

        let request = AnthropicRequest {
            model: model_config.model.clone(),
            max_tokens: model_config.max_tokens.unwrap_or(4096),
            messages: all_messages,
            system: self.system_message.clone(),
            tools: tool_schemas,
            temperature: model_config.temperature,
            top_p: model_config.top_p,
            stream: None,
        };

        let retry_config = RetryConfig {
            max_retries: model_config.max_retries.unwrap_or(3),
            ..Default::default()
        };

        let response = retry_with_backoff(
            || self.create_response(request.clone()),
            retry_config,
            "Anthropic",
        )
        .await?;

        // Parse response
        let mut content_items = Vec::new();
        let mut tool_calls = Vec::new();

        for content in &response.content {
            match content {
                AnthropicResponseContent::Text { text } => {
                    content_items.push(ContentItem::text(text.clone()));
                }
                AnthropicResponseContent::ToolUse { id, name, input } => {
                    tool_calls.push(ToolCall {
                        name: name.clone(),
                        call_id: id.clone(),
                        arguments: input.clone(),
                        id: Some(id.clone()),
                    });
                }
            }
        }

        let usage = LLMUsage {
            input_tokens: response.usage.input_tokens,
            output_tokens: response.usage.output_tokens,
            cache_creation_input_tokens: response.usage.cache_creation_input_tokens,
            cache_read_input_tokens: response.usage.cache_read_input_tokens,
            reasoning_tokens: 0,
        };

        let finish_reason = match response.stop_reason.as_deref() {
            Some("end_turn") => FinishReason::Stop,
            Some("tool_use") => FinishReason::ToolCalls,
            Some("max_tokens") => FinishReason::Stop,
            _ => FinishReason::Stop,
        };

        // Add the assistant's response to chat history
        let first_tool_call = tool_calls.first();
        let assistant_content = self.convert_content(&Some(content_items.clone()), &first_tool_call.cloned());
        let assistant_message = AnthropicMessage {
            role: "assistant".to_string(),
            content: assistant_content,
        };
        self.message_history.push(assistant_message);

        Ok(LLMResponse {
            content: content_items,
            usage: Some(usage),
            model: Some(response.model),
            finish_reason,
            tool_calls: if tool_calls.is_empty() { None } else { Some(tool_calls) },
        })
    }

    async fn chat_stream(
        &mut self,
        messages: Vec<LLMMessage>,
        model_config: &ModelConfig,
        tools: Option<&Vec<Box<dyn Tool>>>,
        reuse_history: Option<bool>,
    ) -> LLMResult<LLMStream> {
        // Note: For streaming responses, chat history is not automatically updated.
        // The caller should accumulate the complete response from the stream and
        // manually add it to chat history using set_chat_history() if needed.
        self.extract_system_message(&messages);
        let parsed_messages = self.convert_messages(&messages);

        let mut all_messages = Vec::new();
        if reuse_history.unwrap_or(true) {
            all_messages.extend(self.message_history.clone());
        }
        all_messages.extend(parsed_messages);

        let tool_schemas = tools.as_ref().map(|tools| {
            tools
                .iter()
                .map(|tool| AnthropicTool {
                    name: tool.get_name().to_string(),
                    description: tool.get_description().to_string(),
                    input_schema: tool.get_input_schema(),
                })
                .collect()
        });

        let request = AnthropicRequest {
            model: model_config.model.clone(),
            max_tokens: model_config.max_tokens.unwrap_or(4096),
            messages: all_messages,
            system: self.system_message.clone(),
            tools: tool_schemas,
            temperature: model_config.temperature,
            top_p: model_config.top_p,
            stream: Some(true),
        };

        self.create_stream_response(request).await
    }

    fn get_provider_name(&self) -> &str {
        "anthropic"
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::config::ModelProvider;

    #[test]
    fn test_anthropic_client_creation() {
        let model_provider = ModelProvider::new("anthropic".to_string())
            .with_api_key("test_key".to_string())
            .with_base_url("https://api.anthropic.com/v1".to_string());
        let config = ModelConfig::new("claude-3-sonnet-20240229".to_string(), model_provider);

        let client = AnthropicClient::new(&config);
        assert!(client.is_ok());

        let client = client.unwrap();
        assert_eq!(client.get_provider_name(), "anthropic");
    }

    #[test]
    fn test_anthropic_client_creation_without_api_key() {
        let model_provider = ModelProvider::new("anthropic".to_string())
            .with_base_url("https://api.anthropic.com/v1".to_string());
        let config = ModelConfig::new("claude-3-sonnet-20240229".to_string(), model_provider);

        let client = AnthropicClient::new(&config);
        assert!(client.is_err());

        if let Err(LLMError::ConfigError(msg)) = client {
            assert_eq!(msg, "API key is required");
        } else {
            panic!("Expected ConfigError");
        }
    }

    #[test]
    fn test_content_conversion() {
        let model_provider = ModelProvider::new("anthropic".to_string())
            .with_api_key("test_key".to_string());
        let config = ModelConfig::new("claude-3-sonnet-20240229".to_string(), model_provider);
        let client = AnthropicClient::new(&config).unwrap();

        // Test simple text content
        let content = vec![ContentItem::text("Hello world")];
        let result = client.convert_content(&Some(content), &None);

        match result {
            AnthropicContent::String(text) => assert_eq!(text, "Hello world"),
            _ => panic!("Expected string content"),
        }

        // Test multiple content items
        let content = vec![
            ContentItem::text("Hello"),
            ContentItem::text("world"),
        ];
        let result = client.convert_content(&Some(content), &None);

        match result {
            AnthropicContent::Array(blocks) => {
                assert_eq!(blocks.len(), 2);
                match &blocks[0] {
                    AnthropicContentBlock::Text { text } => assert_eq!(text, "Hello"),
                    _ => panic!("Expected text block"),
                }
            }
            _ => panic!("Expected array content"),
        }
    }

    #[test]
    fn test_message_conversion() {
        let model_provider = ModelProvider::new("anthropic".to_string())
            .with_api_key("test_key".to_string());
        let config = ModelConfig::new("claude-3-sonnet-20240229".to_string(), model_provider);
        let client = AnthropicClient::new(&config).unwrap();

        let messages = vec![
            LLMMessage::user("Hello"),
            LLMMessage::assistant("Hi there!"),
        ];

        let converted = client.convert_messages(&messages);
        assert_eq!(converted.len(), 2);

        assert_eq!(converted[0].role, "user");
        match &converted[0].content {
            AnthropicContent::String(text) => assert_eq!(text, "Hello"),
            _ => panic!("Expected string content"),
        }

        assert_eq!(converted[1].role, "assistant");
        match &converted[1].content {
            AnthropicContent::String(text) => assert_eq!(text, "Hi there!"),
            _ => panic!("Expected string content"),
        }
    }

    #[test]
    fn test_system_message_extraction() {
        let model_provider = ModelProvider::new("anthropic".to_string())
            .with_api_key("test_key".to_string());
        let config = ModelConfig::new("claude-3-sonnet-20240229".to_string(), model_provider);
        let mut client = AnthropicClient::new(&config).unwrap();

        let messages = vec![
            LLMMessage::new_text(MessageRole::System, "You are a helpful assistant"),
            LLMMessage::user("Hello"),
        ];

        client.extract_system_message(&messages);
        assert_eq!(client.system_message, Some("You are a helpful assistant".to_string()));

        let converted = client.convert_messages(&messages);
        // System message should be filtered out from regular messages
        assert_eq!(converted.len(), 1);
        assert_eq!(converted[0].role, "user");
    }

    #[test]
    fn test_tool_result_conversion() {
        let model_provider = ModelProvider::new("anthropic".to_string())
            .with_api_key("test_key".to_string());
        let config = ModelConfig::new("claude-3-sonnet-20240229".to_string(), model_provider);
        let client = AnthropicClient::new(&config).unwrap();

        let mut tool_result = ToolResult::new("call_123".to_string(), "test_tool".to_string());
        tool_result.success = true;
        tool_result.result = Some("Success result".to_string());

        let converted = client.convert_tool_result(&tool_result);
        assert_eq!(converted.role, "user");

        match converted.content {
            AnthropicContent::Array(blocks) => {
                assert_eq!(blocks.len(), 1);
                match &blocks[0] {
                    AnthropicContentBlock::ToolResult { tool_use_id, content, is_error } => {
                        assert_eq!(tool_use_id, "call_123");
                        assert_eq!(content, "Success result");
                        assert_eq!(*is_error, Some(false));
                    }
                    _ => panic!("Expected tool result block"),
                }
            }
            _ => panic!("Expected array content"),
        }
    }
}
