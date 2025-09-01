// Copyright (c) 2025 ByteDance Ltd. and/or its affiliates
// SPDX-License-Identifier: MIT

use serde::{Deserialize, Serialize};
use std::{collections::HashMap, fmt, pin::Pin};
use futures::Stream;
use crate::tools::{ToolCall, ToolResult};

// Module declarations
pub mod error;
pub mod llm_provider;
pub mod retry_utils;
pub mod openai_client;
pub mod openai_compatible_base;
pub mod openai_compatible_client;

// Re-exports
pub use error::{LLMError, LLMResult};
pub use llm_provider::{LLMProvider};
pub use openai_client::OpenAIClient;
pub use openai_compatible_base::{OpenAICompatibleClient, ProviderConfig};
pub use openai_compatible_client::{OpenAICompatibleGenericClient, OpenAICompatibleProvider};


/// Standard message format
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct LLMMessage {
    pub role: String,
    pub content: Option<Vec<HashMap<String, String>>>,
    pub tool_call: Option<ToolCall>,
    pub tool_result: Option<ToolResult>,
}

/// LLM usage format
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct LLMUsage {
    pub input_tokens: i32,
    pub output_tokens: i32,
    #[serde(default)]
    pub cache_creation_input_tokens: i32,
    #[serde(default)]
    pub cache_read_input_tokens: i32,
    #[serde(default)]
    pub reasoning_tokens: i32,
}

impl LLMUsage {
    /// Add two LLMUsage instances together
    pub fn add(&self, other: &LLMUsage) -> LLMUsage {
        LLMUsage {
            input_tokens: self.input_tokens + other.input_tokens,
            output_tokens: self.output_tokens + other.output_tokens,
            cache_creation_input_tokens: self.cache_creation_input_tokens + other.cache_creation_input_tokens,
            cache_read_input_tokens: self.cache_read_input_tokens + other.cache_read_input_tokens,
            reasoning_tokens: self.reasoning_tokens + other.reasoning_tokens,
        }
    }
}

impl std::ops::Add for LLMUsage {
    type Output = LLMUsage;

    fn add(self, other: LLMUsage) -> LLMUsage {
        LLMUsage {
            input_tokens: self.input_tokens + other.input_tokens,
            output_tokens: self.output_tokens + other.output_tokens,
            cache_creation_input_tokens: self.cache_creation_input_tokens + other.cache_creation_input_tokens,
            cache_read_input_tokens: self.cache_read_input_tokens + other.cache_read_input_tokens,
            reasoning_tokens: self.reasoning_tokens + other.reasoning_tokens,
        }
    }
}

impl std::ops::Add for &LLMUsage {
    type Output = LLMUsage;

    fn add(self, other: &LLMUsage) -> LLMUsage {
        LLMUsage {
            input_tokens: self.input_tokens + other.input_tokens,
            output_tokens: self.output_tokens + other.output_tokens,
            cache_creation_input_tokens: self.cache_creation_input_tokens + other.cache_creation_input_tokens,
            cache_read_input_tokens: self.cache_read_input_tokens + other.cache_read_input_tokens,
            reasoning_tokens: self.reasoning_tokens + other.reasoning_tokens,
        }
    }
}

impl fmt::Display for LLMUsage {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(
            f,
            "LLMUsage(input_tokens={}, output_tokens={}, cache_creation_input_tokens={}, cache_read_input_tokens={}, reasoning_tokens={})",
            self.input_tokens,
            self.output_tokens,
            self.cache_creation_input_tokens,
            self.cache_read_input_tokens,
            self.reasoning_tokens
        )
    }
}

///Enum of finish reason
#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum FinishReason {
    Stop,
    ToolCalls,
    Error,
    ContentFilter,
}

/// Standard LLM response format
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct LLMResponse {
    pub content: Vec<HashMap<String, String>>,
    pub usage: Option<LLMUsage>,
    pub model: Option<String>,
    pub finish_reason: FinishReason,
    pub tool_calls: Option<Vec<ToolCall>>,
}

/// Stream chunk for streaming responses
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct StreamChunk {
    pub content: Option<Vec<HashMap<String, String>>>,
    pub finish_reason: Option<FinishReason>,
    pub model: Option<String>,
    pub tool_calls: Option<Vec<ToolCall>>,
    pub usage: Option<LLMUsage>,
}

/// Type alias for streaming response
pub type LLMStream = Pin<Box<dyn Stream<Item = LLMResult<StreamChunk>> + Send>>;

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_llm_usage_add() {
        let usage1 = LLMUsage {
            input_tokens: 10,
            output_tokens: 20,
            cache_creation_input_tokens: 5,
            cache_read_input_tokens: 3,
            reasoning_tokens: 2,
        };

        let usage2 = LLMUsage {
            input_tokens: 15,
            output_tokens: 25,
            cache_creation_input_tokens: 7,
            cache_read_input_tokens: 4,
            reasoning_tokens: 3,
        };

        let result = usage1 + usage2;
        assert_eq!(result.input_tokens, 25);
        assert_eq!(result.output_tokens, 45);
        assert_eq!(result.cache_creation_input_tokens, 12);
        assert_eq!(result.cache_read_input_tokens, 7);
        assert_eq!(result.reasoning_tokens, 5);
    }

    #[test]
    fn test_serialization() {
        let message = LLMMessage {
            role: "user".to_string(),
            content: Some(vec![HashMap::from([("text".to_string(), "Hello".to_string())])]),
            tool_call: None,
            tool_result: None,
        };

        let json = serde_json::to_string(&message).unwrap();
        let deserialized: LLMMessage = serde_json::from_str(&json).unwrap();

        assert_eq!(message.role, deserialized.role);
        assert_eq!(message.content, deserialized.content);
    }
}