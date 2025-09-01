// Copyright (c) 2025 ByteDance Ltd. and/or its affiliates
// SPDX-License-Identifier: MIT

use async_trait::async_trait;
use reqwest::Client;
use serde::{Deserialize, Serialize};
use serde_json::Value;
use std::collections::HashMap;


use crate::{
    llm::{
        llm_provider::LLMProvider,
        error::{LLMError, LLMResult},
        retry_utils::{retry_with_backoff, RetryConfig},
        LLMMessage, LLMResponse, LLMUsage, LLMStream, StreamChunk, FinishReason,
    },
    config::ModelConfig,
};
use crate::tools::{Tool, ToolCall, ToolResult, ToolSchema};

#[derive(Debug, Clone, Serialize)]
struct OpenAIResponsesRequest {
    model: String,
    messages: Vec<OpenAIMessage>,
    #[serde(skip_serializing_if = "Option::is_none")]
    tools: Option<Vec<ToolSchema>>,
    #[serde(skip_serializing_if = "Option::is_none")]
    temperature: Option<f32>,
    #[serde(skip_serializing_if = "Option::is_none")]
    top_p: Option<f32>,
    #[serde(skip_serializing_if = "Option::is_none")]
    max_tokens: Option<u32>,
    #[serde(skip_serializing_if = "Option::is_none")]
    stream: Option<bool>,
}

#[derive(Debug, Serialize, Deserialize, Clone)]
struct OpenAIMessage {
    role: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    content: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    tool_calls: Option<Vec<OpenAIToolCall>>,
    #[serde(skip_serializing_if = "Option::is_none")]
    tool_call_id: Option<String>,
}

#[derive(Debug, Serialize, Deserialize, Clone)]
struct OpenAIToolCall {
    id: String,
    #[serde(rename = "type")]
    tool_type: String,
    function: OpenAIFunction,
}

#[derive(Debug, Serialize, Deserialize, Clone)]
struct OpenAIFunction {
    name: String,
    arguments: String,
}

#[derive(Debug, Deserialize)]
struct OpenAIResponse {
    choices: Vec<OpenAIChoice>,
    model: String,
    usage: Option<OpenAIUsage>,
}

#[derive(Debug, Deserialize)]
struct OpenAIChoice {
    message: OpenAIResponseMessage,
    finish_reason: Option<FinishReason>,
}

#[derive(Debug, Deserialize)]
struct OpenAIResponseMessage {
    role: String,
    content: Option<String>,
    tool_calls: Option<Vec<OpenAIToolCall>>,
}

#[derive(Debug, Deserialize)]
struct OpenAIUsage {
    prompt_tokens: Option<i32>,
    completion_tokens: Option<i32>,
}

#[derive(Debug, Deserialize)]
struct OpenAIStreamResponse {
    choices: Vec<OpenAIStreamChoice>,
    model: Option<String>,
    usage: Option<OpenAIUsage>,
}

#[derive(Debug, Deserialize)]
struct OpenAIStreamChoice {
    delta: OpenAIStreamDelta,
    finish_reason: Option<FinishReason>,
}

#[derive(Debug, Deserialize)]
struct OpenAIStreamDelta {
    content: Option<String>,
    tool_calls: Option<Vec<OpenAIToolCall>>,
}

pub struct OpenAIClient {
    client: Client,
    api_key: String,
    base_url: String,
    message_history: Vec<OpenAIMessage>,
}

impl OpenAIClient {
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
            .unwrap_or(&"https://api.openai.com/v1".to_string())
            .clone();

        Ok(Self {
            client: Client::new(),
            api_key,
            base_url,
            message_history: Vec::new(),
        })
    }

    async fn create_response(&self, request: OpenAIResponsesRequest) -> LLMResult<OpenAIResponse> {
        let url = format!("{}/responses", self.base_url);
        
        let response = self
            .client
            .post(&url)
            .header("Authorization", format!("Bearer {}", self.api_key))
            .header("Content-Type", "application/json")
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

    async fn create_stream_response(&self, request: OpenAIResponsesRequest) -> LLMResult<LLMStream> {
        let url = format!("{}/responses", self.base_url);
        
        let response = self
            .client
            .post(&url)
            .header("Authorization", format!("Bearer {}", self.api_key))
            .header("Content-Type", "application/json")
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

        use futures::stream;
        
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
                
                match serde_json::from_str::<OpenAIStreamResponse>(data) {
                    Ok(response) => {
                        if let Some(choice) = response.choices.first() {
                            return Ok(Some(StreamChunk {
                                content: choice.delta.content.as_ref().map(|c| vec![HashMap::from([("text".to_string(), c.clone())])]),
                                finish_reason: choice.finish_reason.as_ref().map(|fr| match fr {
                                    FinishReason::Stop => FinishReason::Stop,
                                    FinishReason::ToolCalls => FinishReason::ToolCalls,
                                    _ => FinishReason::Stop,
                                }),
                                model: response.model.clone(),
                                tool_calls: choice.delta.tool_calls.as_ref().map(|calls| {
                                    calls.iter().map(|call| {
                                        let arguments: HashMap<String, Value> = 
                                            serde_json::from_str(&call.function.arguments)
                                                .unwrap_or_default();
                                        ToolCall {
                                            name: call.function.name.clone(),
                                            call_id: call.id.clone(),
                                            arguments,
                                            id: Some(call.id.clone()),
                                        }
                                    }).collect()
                                }),
                                usage: response.usage.map(|u| LLMUsage {
                                    input_tokens: u.prompt_tokens.unwrap_or(0),
                                    output_tokens: u.completion_tokens.unwrap_or(0),
                                    cache_creation_input_tokens: 0,
                                    cache_read_input_tokens: 0,
                                    reasoning_tokens: 0,
                                }),
                            }));
                        }
                    },
                    Err(_) => continue,
                }
            }
        }
        Ok(None)
    }

    fn parse_messages(&self, messages: &[LLMMessage]) -> Vec<OpenAIMessage> {
        messages.iter().map(|msg| {
            match msg.role.as_str() {
                "tool" => self.parse_tool_result(msg.tool_result.as_ref().unwrap()),
                _ => OpenAIMessage {
                    role: msg.role.clone(),
                    content: msg.content.as_ref().and_then(|content_vec| {
                        content_vec.first().and_then(|content_map| content_map.get("text")).cloned()
                    }),
                    tool_calls: msg.tool_call.as_ref().map(|tc| vec![OpenAIToolCall {
                        id: tc.call_id.clone(),
                        tool_type: "function".to_string(),
                        function: OpenAIFunction {
                            name: tc.name.clone(),
                            arguments: serde_json::to_string(&tc.arguments).unwrap_or_default(),
                        },
                    }]),
                    tool_call_id: None,
                }
            }
        }).collect()
    }

    fn parse_tool_result(&self, tool_result: &ToolResult) -> OpenAIMessage {
        let content_str = if tool_result.success {
            tool_result.result.clone().unwrap_or_default()
        } else {
            tool_result.error.clone().unwrap_or_default()
        };
        OpenAIMessage {
            role: "tool".to_string(),
            content: Some(content_str),
            tool_calls: None,
            tool_call_id: Some(tool_result.call_id.clone()),
        }
    }
}

#[async_trait]
impl LLMProvider for OpenAIClient {
    fn set_chat_history(&mut self, messages: Vec<LLMMessage>) {
        self.message_history = self.parse_messages(&messages);
    }

    async fn chat(
        &mut self,
        messages: Vec<LLMMessage>,
        model_config: &ModelConfig,
        tools: Option<Vec<Box<dyn Tool>>>,
        reuse_history: Option<bool>,
    ) -> LLMResult<LLMResponse> {
        let parsed_messages = self.parse_messages(&messages);
        
        let mut all_messages = Vec::new();
        if reuse_history.unwrap_or(true) {
            all_messages.extend(self.message_history.clone());
        }
        all_messages.extend(parsed_messages);

        let tool_schemas = tools.as_ref().map(|tools| {
            tools
                .iter()
                .map(|tool| ToolSchema::from_tool(tool.as_ref()))
                .collect()
        });

        let request = OpenAIResponsesRequest {
            model: model_config.model.clone(),
            messages: all_messages,
            tools: tool_schemas,
            temperature: model_config.temperature,
            top_p: model_config.top_p,
            max_tokens: model_config.max_tokens,
            stream: None,
        };

        let retry_config = RetryConfig {
            max_retries: model_config.max_retries.unwrap_or(3),
            ..Default::default()
        };

        let response = retry_with_backoff(
            || self.create_response(request.clone()),
            retry_config,
            "OpenAI",
        )
        .await?;

        let choice = response.choices.into_iter().next()
            .ok_or_else(|| LLMError::ApiError {
                status_code: 500,
                message: "No choices in response".to_string(),
            })?;

        let mut tool_calls = Vec::new();
        if let Some(response_tool_calls) = &choice.message.tool_calls {
            for tool_call in response_tool_calls {
                let arguments: HashMap<String, Value> = serde_json::from_str(&tool_call.function.arguments)
                    .unwrap_or_default();
                
                tool_calls.push(ToolCall {
                    name: tool_call.function.name.clone(),
                    call_id: tool_call.id.clone(),
                    arguments,
                    id: Some(tool_call.id.clone()),
                });
            }
        }

        let usage = response.usage.map(|u| LLMUsage {
            input_tokens: u.prompt_tokens.unwrap_or(0),
            output_tokens: u.completion_tokens.unwrap_or(0),
            cache_creation_input_tokens: 0,
            cache_read_input_tokens: 0,
            reasoning_tokens: 0,
        });

        Ok(LLMResponse {
            content: choice.message.content.as_ref().map(|c| vec![HashMap::from([("text".to_string(), c.clone())])]).unwrap_or_default(),
            tool_calls: if tool_calls.is_empty() { None } else { Some(tool_calls) },
            finish_reason: match choice.finish_reason.unwrap_or(FinishReason::Stop) {
                FinishReason::Stop => FinishReason::Stop,
                FinishReason::ToolCalls => FinishReason::ToolCalls,
                _ => FinishReason::Stop,
            },
            model: Some(response.model),
            usage,
        })
    }

    async fn chat_stream(
        &mut self,
        messages: Vec<LLMMessage>,
        model_config: &ModelConfig,
        tools: Option<Vec<Box<dyn Tool>>>,
        reuse_history: Option<bool>,
    ) -> LLMResult<LLMStream> {
        let parsed_messages = self.parse_messages(&messages);
        
        let mut all_messages = Vec::new();
        if reuse_history.unwrap_or(true) {
            all_messages.extend(self.message_history.clone());
        }
        all_messages.extend(parsed_messages);

        let tool_schemas = tools.as_ref().map(|tools| {
            tools
                .iter()
                .map(|tool| ToolSchema::from_tool(tool.as_ref()))
                .collect()
        });

        let request = OpenAIResponsesRequest {
            model: model_config.model.clone(),
            messages: all_messages,
            tools: tool_schemas,
            temperature: model_config.temperature,
            top_p: model_config.top_p,
            max_tokens: model_config.max_tokens,
            stream: Some(true),
        };

        self.create_stream_response(request).await
    }

    fn get_provider_name(&self) -> &str {
        "openai"
    }

    fn supports_tool_calling(&self, model_name: &str) -> bool {
        let model_lower = model_name.to_lowercase();
        model_lower.contains("gpt-4") || model_lower.contains("gpt-3.5-turbo")
    }
}