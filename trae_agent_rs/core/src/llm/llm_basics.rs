// Copyright (c) 2025 ByteDance Ltd. and/or its affiliates
// SPDX-License-Identifier: MIT


use serde::{Deserialize, Serialize};
use std::{fmt, pin::Pin};
use futures::Stream;
use crate::tools::{ToolCall, ToolResult};
use crate::llm::error::LLMResult;

/// Role of a message in the conversation
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "lowercase")]
pub enum MessageRole {
    /// Message from the user/human
    User,
    /// Message from the AI assistant
    Assistant,
    /// Message containing tool/function call results
    Tool,
    /// Legacy function role (for compatibility)
    Function,
    /// Message from developer/system (for some providers)
    Developer,
    /// Message from system
    System
}

impl MessageRole {
    /// Convert to string representation
    pub fn as_str(&self) -> &'static str {
        match self {
            MessageRole::User => "user",
            MessageRole::Assistant => "assistant",
            MessageRole::Tool => "tool",
            MessageRole::Function => "function",
            MessageRole::Developer => "developer",
            MessageRole::System => "system",
        }
    }

    /// Parse from string
    pub fn from_str(s: &str) -> Result<Self, String> {
        match s.to_lowercase().as_str() {
            "user" => Ok(MessageRole::User),
            "assistant" => Ok(MessageRole::Assistant),
            "tool" => Ok(MessageRole::Tool),
            "function" => Ok(MessageRole::Function),
            "developer" => Ok(MessageRole::Developer),
            "system" => Ok(MessageRole::System),
            _ => Err(format!("Invalid message role: {}", s)),
        }
    }
}

impl fmt::Display for MessageRole {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "{}", self.as_str())
    }
}

impl From<MessageRole> for String {
    fn from(role: MessageRole) -> String {
        role.as_str().to_string()
    }
}

/// Content type for text
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct TextContent {
    pub text: String,
}

/// Content type for images with different source types
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct ImageContent {
    #[serde(flatten)]
    pub source: ImageSource,
}

/// Different ways to specify image data
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
#[serde(tag = "type")]
pub enum ImageSource {
    /// Base64 encoded image data
    #[serde(rename = "base64")]
    Base64 {
        media_type: String,
        data: String,
    },
    /// Image URL
    #[serde(rename = "image_url")]
    Url {
        #[serde(rename = "image_url")]
        url: String,
    },
}

/// Content item in a message - can be text or image
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
#[serde(tag = "type")]
pub enum ContentItem {
    #[serde(rename = "text")]
    Text(TextContent),
    #[serde(rename = "image")]
    Image(ImageContent),
}

impl ContentItem {
    /// Create a text content item
    pub fn text(text: impl Into<String>) -> Self {
        ContentItem::Text(TextContent { text: text.into() })
    }

    /// Create an image content item from base64 data
    pub fn image_base64(media_type: impl Into<String>, data: impl Into<String>) -> Self {
        ContentItem::Image(ImageContent {
            source: ImageSource::Base64 {
                media_type: media_type.into(),
                data: data.into(),
            },
        })
    }

    /// Create an image content item from URL
    pub fn image_url(url: impl Into<String>) -> Self {
        ContentItem::Image(ImageContent {
            source: ImageSource::Url {
                url: url.into(),
            },
        })
    }

    /// Get text content if this is a text item
    pub fn as_text(&self) -> Option<&str> {
        match self {
            ContentItem::Text(text) => Some(&text.text),
            _ => None,
        }
    }

    /// Get image content if this is an image item
    pub fn as_image(&self) -> Option<&ImageContent> {
        match self {
            ContentItem::Image(image) => Some(image),
            _ => None,
        }
    }
}

/// Standard message format
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct LLMMessage {
    pub role: MessageRole,
    pub content: Option<Vec<ContentItem>>,
    pub tool_call: Option<ToolCall>,
    pub tool_result: Option<ToolResult>,
}

impl LLMMessage {
    /// Create a new message with text content
    pub fn new_text(role: MessageRole, text: impl Into<String>) -> Self {
        Self {
            role,
            content: Some(vec![ContentItem::text(text)]),
            tool_call: None,
            tool_result: None,
        }
    }

    /// Create a new message with multiple content items
    pub fn new_with_content(role: MessageRole, content: Vec<ContentItem>) -> Self {
        Self {
            role,
            content: Some(content),
            tool_call: None,
            tool_result: None,
        }
    }

    /// Create a new user message with text content
    pub fn user(text: impl Into<String>) -> Self {
        Self::new_text(MessageRole::User, text)
    }

    /// Create a new assistant message with text content
    pub fn assistant(text: impl Into<String>) -> Self {
        Self::new_text(MessageRole::Assistant, text)
    }

    /// Create a new tool message with text content
    pub fn tool(text: impl Into<String>) -> Self {
        Self::new_text(MessageRole::Tool, text)
    }

    /// Create a new user message with multiple content items
    pub fn user_with_content(content: Vec<ContentItem>) -> Self {
        Self::new_with_content(MessageRole::User, content)
    }

    /// Create a new assistant message with multiple content items
    pub fn assistant_with_content(content: Vec<ContentItem>) -> Self {
        Self::new_with_content(MessageRole::Assistant, content)
    }

    /// Get the text content from the message (first text item)
    pub fn get_text(&self) -> Option<&str> {
        self.content.as_ref()?.iter()
            .find_map(|item| item.as_text())
    }

    /// Get all text content items concatenated
    pub fn get_all_text(&self) -> String {
        self.content.as_ref()
            .map(|items| {
                items.iter()
                    .filter_map(|item| item.as_text())
                    .collect::<Vec<_>>()
                    .join(" ")
            })
            .unwrap_or_default()
    }
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

    pub fn new(
        input_token:i32,
        output_token:i32,
        cache_creation_input_tokens:i32,
        cache_read_input_tokens:i32,
        reasoing_tokens:i32)
    -> Self{
        LLMUsage {
            input_tokens: input_token,
            output_tokens: output_token,
            cache_creation_input_tokens: cache_creation_input_tokens,
            cache_read_input_tokens: cache_read_input_tokens,
            reasoning_tokens: reasoing_tokens,
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
    pub content: Vec<ContentItem>,
    pub usage: Option<LLMUsage>,
    pub model: Option<String>,
    pub finish_reason: FinishReason,
    pub tool_calls: Option<Vec<ToolCall>>,
}

impl LLMResponse {
    /// Create a new response with text content
    pub fn new_text(
        content: impl Into<String>,
        usage: Option<LLMUsage>,
        model: Option<String>,
        finish_reason: FinishReason,
        tool_calls: Option<Vec<ToolCall>>,
    ) -> Self {
        let content_str = content.into();
        let content_vec = if content_str.is_empty() {
            vec![]
        } else {
            vec![ContentItem::text(content_str)]
        };

        LLMResponse {
            content: content_vec,
            usage,
            model,
            finish_reason,
            tool_calls
        }
    }

    /// Create a new response with multiple content items
    pub fn new_with_content(
        content: Vec<ContentItem>,
        usage: Option<LLMUsage>,
        model: Option<String>,
        finish_reason: FinishReason,
        tool_calls: Option<Vec<ToolCall>>,
    ) -> Self {
        LLMResponse {
            content,
            usage,
            model,
            finish_reason,
            tool_calls
        }
    }

    /// Get the text content from the response (first text item)
    pub fn get_text(&self) -> Option<&str> {
        self.content.iter()
            .find_map(|item| item.as_text())
    }

    /// Get all text content items concatenated
    pub fn get_all_text(&self) -> String {
        self.content.iter()
            .filter_map(|item| item.as_text())
            .collect::<Vec<_>>()
            .join(" ")
    }
}

/// Stream chunk for streaming responses
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct StreamChunk {
    pub content: Option<Vec<ContentItem>>,
    pub finish_reason: Option<FinishReason>,
    pub model: Option<String>,
    pub tool_calls: Option<Vec<ToolCall>>,
    pub usage: Option<LLMUsage>,
}

impl StreamChunk {
    /// Create a new stream chunk with text content
    pub fn new_text(
        content: Option<String>,
        finish_reason: Option<FinishReason>,
        model: Option<String>,
        tool_calls: Option<Vec<ToolCall>>,
        usage: Option<LLMUsage>
    ) -> Self {
        let content_vec = content.map(|c| vec![ContentItem::text(c)]);

        StreamChunk {
            content: content_vec,
            finish_reason,
            model,
            tool_calls,
            usage,
        }
    }

    /// Create a new stream chunk with multiple content items
    pub fn new_with_content(
        content: Option<Vec<ContentItem>>,
        finish_reason: Option<FinishReason>,
        model: Option<String>,
        tool_calls: Option<Vec<ToolCall>>,
        usage: Option<LLMUsage>
    ) -> Self {
        StreamChunk {
            content,
            finish_reason,
            model,
            tool_calls,
            usage,
        }
    }

    /// Get the text content from the chunk (first text item)
    pub fn get_text(&self) -> Option<&str> {
        self.content.as_ref()?.iter()
            .find_map(|item| item.as_text())
    }
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
            role: MessageRole::User,
            content: Some(vec![ContentItem::text("Hello")]),
            tool_call: None,
            tool_result: None,
        };

        let json = serde_json::to_string(&message).unwrap();
        let deserialized: LLMMessage = serde_json::from_str(&json).unwrap();

        assert_eq!(message.role, deserialized.role);
        assert_eq!(message.content, deserialized.content);
    }

    #[test]
    fn test_content_types() {
        // Test text content
        let text_content = ContentItem::text("Hello world");
        assert_eq!(text_content.as_text(), Some("Hello world"));
        assert!(text_content.as_image().is_none());

        // Test image content with URL
        let image_url = ContentItem::image_url("https://example.com/image.jpg");
        assert!(image_url.as_text().is_none());
        assert!(image_url.as_image().is_some());

        // Test image content with base64
        let image_b64 = ContentItem::image_base64("image/jpeg", "base64data");
        assert!(image_b64.as_text().is_none());
        assert!(image_b64.as_image().is_some());

        // Test message with mixed content
        let message = LLMMessage::new_with_content(MessageRole::User, vec![
            ContentItem::text("What is in this image?"),
            ContentItem::image_url("https://example.com/image.jpg")
        ]);

        assert_eq!(message.get_text(), Some("What is in this image?"));
        assert_eq!(message.content.as_ref().unwrap().len(), 2);
    }

    #[test]
    fn test_response_helpers() {
        let response = LLMResponse::new_text(
            "Hello!",
            None,
            Some("gpt-4".to_string()),
            FinishReason::Stop,
            None,
        );

        assert_eq!(response.get_text(), Some("Hello!"));
        assert_eq!(response.get_all_text(), "Hello!");
        assert_eq!(response.content.len(), 1);

        // Test empty response
        let empty_response = LLMResponse::new_text(
            "",
            None,
            None,
            FinishReason::Stop,
            None,
        );

        assert!(empty_response.content.is_empty());
        assert_eq!(empty_response.get_text(), None);
    }

    #[test]
    fn test_message_role() {
        // Test enum variants
        assert_eq!(MessageRole::User.as_str(), "user");
        assert_eq!(MessageRole::Assistant.as_str(), "assistant");
        assert_eq!(MessageRole::Tool.as_str(), "tool");
        assert_eq!(MessageRole::Function.as_str(), "function");
        assert_eq!(MessageRole::Developer.as_str(), "developer");

        // Test from_str parsing
        assert_eq!(MessageRole::from_str("user").unwrap(), MessageRole::User);
        assert_eq!(MessageRole::from_str("ASSISTANT").unwrap(), MessageRole::Assistant);
        assert_eq!(MessageRole::from_str("Tool").unwrap(), MessageRole::Tool);
        assert!(MessageRole::from_str("invalid").is_err());

        // Test Display trait
        assert_eq!(format!("{}", MessageRole::User), "user");
        assert_eq!(format!("{}", MessageRole::Assistant), "assistant");

        // Test conversion to String
        let role_str: String = MessageRole::User.into();
        assert_eq!(role_str, "user");

        // Test serialization preserves role names
        let message = LLMMessage::user("Hello");
        let json = serde_json::to_string(&message).unwrap();
        assert!(json.contains("\"role\":\"user\""));
    }

    #[test]
    fn test_message_convenience_methods() {
        // Test convenience constructors
        let user_msg = LLMMessage::user("Hello");
        assert_eq!(user_msg.role, MessageRole::User);
        assert_eq!(user_msg.get_text(), Some("Hello"));

        let assistant_msg = LLMMessage::assistant("Hi there!");
        assert_eq!(assistant_msg.role, MessageRole::Assistant);
        assert_eq!(assistant_msg.get_text(), Some("Hi there!"));

        let tool_msg = LLMMessage::tool("Result");
        assert_eq!(tool_msg.role, MessageRole::Tool);
        assert_eq!(tool_msg.get_text(), Some("Result"));

        // Test multi-content convenience methods
        let user_multimodal = LLMMessage::user_with_content(vec![
            ContentItem::text("What's in this image?"),
            ContentItem::image_url("https://example.com/image.jpg")
        ]);
        assert_eq!(user_multimodal.role, MessageRole::User);
        assert_eq!(user_multimodal.content.as_ref().unwrap().len(), 2);

        let assistant_multimodal = LLMMessage::assistant_with_content(vec![
            ContentItem::text("I can see a landscape.")
        ]);
        assert_eq!(assistant_multimodal.role, MessageRole::Assistant);
        assert_eq!(assistant_multimodal.get_text(), Some("I can see a landscape."));
    }
}
