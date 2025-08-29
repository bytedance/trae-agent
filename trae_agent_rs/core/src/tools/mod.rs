use std::{collections::HashMap, fmt};
use serde::{Deserialize, Serialize};

pub mod base;
pub use base::Tool;

/// Tool call arguments type alias
pub type ToolCallArguments = HashMap<String, serde_json::Value>;

/// Represents a tool call result
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ToolResult {
    pub call_id: String,
    pub name: String, // Gemini specific field
    pub success: bool,
    pub result: Option<String>,
    pub error: Option<String>,
    pub id: Option<String>, // OpenAI-specific field
}

/// Represents a parsed tool call
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ToolCall {
    pub name: String,
    pub call_id: String,
    #[serde(default)]
    pub arguments: ToolCallArguments,
    pub id: Option<String>,
}

impl fmt::Display for ToolCall {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(
            f,
            "ToolCall(name={}, arguments={:?}, call_id={}, id={:?})",
            self.name, self.arguments, self.call_id, self.id
        )
    }
}

/// Tool schema for API calls
#[derive(Debug, Clone, serde::Serialize, serde::Deserialize)]
pub struct ToolSchema {
    pub name: String,
    pub description: String,
    pub parameters: serde_json::Value,
    #[serde(rename = "type")]
    pub tool_type: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub strict: Option<bool>,
}

impl ToolSchema {
    pub fn from_tool(tool: &dyn Tool) -> Self {
        Self {
            name: tool.get_name().to_string(),
            description: tool.get_description().to_string(),
            parameters: tool.get_input_schema(),
            tool_type: "function".to_string(),
            strict: Some(true),
        }
    }
}