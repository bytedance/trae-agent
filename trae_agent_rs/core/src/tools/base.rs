// Copyright (c) 2025 ByteDance Ltd. and/or its affiliates
// SPDX-License-Identifier: MIT

use serde_json::Value;
use std::collections::HashMap;
use std::future::Future;
use std::pin::Pin;

/// Base trait for all tools that can be used by LLM clients
pub trait Tool: Send + Sync {
    /// Get the name of the tool
    fn get_name(&self) -> &str;

    /// Get the description of the tool
    fn get_description(&self) -> &str;

    /// Get the input schema for the tool parameters
    fn get_input_schema(&self) -> Value;

    // Get descriptive message for a tool call
    fn get_descriptive_message(&self, arguments: &HashMap<String, Value>) -> String;

    /// Check if the tool needs approval before execution
    fn needs_approval(&self, arguments: &HashMap<String, Value>) -> bool;

    /// Execute the tool with the given arguments
    fn execute(
        &mut self,
        arguments: HashMap<String, Value>,
    ) -> Pin<Box<dyn Future<Output = Result<String, String>> + Send + '_>>;

    fn reset(&mut self);
}

pub trait Reset {
    // tools that allow to reset
    fn reset(&mut self);
}
