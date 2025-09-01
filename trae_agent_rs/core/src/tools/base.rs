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
    
    /// Execute the tool with the given arguments
    async fn execute(&self, arguments: HashMap<String, Value>) -> Pin<Box<dyn Future<Output = Result<String, String>> + Send + '_>>;
}