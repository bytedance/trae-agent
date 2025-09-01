// Copyright (c) 2025 ByteDance Ltd. and/or its affiliates
// SPDX-License-Identifier: MIT

use std::collections::HashMap;
use crate::llm::openai_compatible_base::{OpenAICompatibleClient, ProviderConfig};
use crate::config::ModelConfig;
use crate::llm::error::LLMResult;

/// OpenAI compatible provider configuration
pub struct OpenAICompatibleProvider;

impl ProviderConfig for OpenAICompatibleProvider {
    fn get_service_name(&self) -> &str {
        "OpenAI Compatible"
    }

    fn get_provider_name(&self) -> &str {
        "openai_compatible"
    }

    fn get_extra_headers(&self) -> HashMap<String, String> {
        let mut headers = HashMap::new();
        
        // Add common OpenAI compatible headers if available
        if let Ok(site_url) = std::env::var("OPENAI_COMPATIBLE_SITE_URL") {
            headers.insert("HTTP-Referer".to_string(), site_url);
        }
        
        if let Ok(site_name) = std::env::var("OPENAI_COMPATIBLE_SITE_NAME") {
            headers.insert("X-Title".to_string(), site_name);
        }
        
        headers
    }

    fn supports_tool_calling(&self, model_name: &str) -> bool {
        let model_lower = model_name.to_lowercase();
        let tool_capable_patterns = [
            "gpt-4", "gpt-3.5-turbo", "claude-3", "claude-2",
            "gemini", "mistral", "llama-3", "command-r",
        ];
        
        tool_capable_patterns.iter().any(|pattern| model_lower.contains(pattern))
    }
}

/// OpenAI compatible client
pub type OpenAICompatibleGenericClient = OpenAICompatibleClient<OpenAICompatibleProvider>;

impl OpenAICompatibleGenericClient {
    pub fn with_config(model_config: ModelConfig) -> LLMResult<Self> {
        // Set default base URL if not provided (this is just an example, should be set by user)
        if model_config.model_provider.base_url.is_none() {
            // No default URL - user must provide one
            return Err(crate::llm::error::LLMError::ConfigError(
                "Base URL must be provided for OpenAI compatible client".to_string()
            ));
        }
        OpenAICompatibleClient::new(&model_config, OpenAICompatibleProvider)
    }
}
