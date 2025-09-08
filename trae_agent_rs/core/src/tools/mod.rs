use serde::{Deserialize, Serialize};
use std::{collections::HashMap, fmt};

pub mod base;
pub mod bash;
pub mod edit;
pub use base::Tool;

/// Tool call arguments type alias
pub type ToolCallArguments = HashMap<String, serde_json::Value>;

/// Represents a tool call result
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct ToolResult {
    pub call_id: String,
    pub name: String, // Gemini specific field
    pub success: bool,
    pub result: Option<String>,
    pub error: Option<String>,
    pub id: Option<String>, // OpenAI-specific field
}

impl ToolResult {
    pub fn new(call_id: String, name: String) -> Self {
        ToolResult {
            call_id,
            name,
            success: false,
            result: None,
            error: None,
            id: None,
        }
    }
}

/// Represents a parsed tool call
#[derive(Default, Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct ToolCall {
    pub name: String,
    pub call_id: String,
    #[serde(default)]
    pub arguments: ToolCallArguments,
    pub id: Option<String>,
}

// don't implement new for tool call cause tool call actually depends on the argument which
// may cause problem when developer randomly call the Tool Call

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

#[derive(Debug, Default)]
pub struct ToolExecResult {
    pub output: Option<String>,
    pub error: Option<String>,
    pub error_code: Option<i32>,
}
