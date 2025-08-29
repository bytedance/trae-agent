// Copyright (c) 2025 ByteDance Ltd. and/or its affiliates
// SPDX-License-Identifier: MIT

use std::collections::HashMap;
use crate::llm::openai_compatible_base::{OpenAICompatibleClient, ProviderConfig};
use crate::llm::config::ModelConfig;
use crate::llm::error::LLMResult;

/// OpenRouter provider configuration
pub struct OpenRouterProvider;

impl ProviderConfig for OpenRouterProvider {
    fn get_service_name(&self) -> &str {
        "OpenRouter"
    }

    fn get_provider_name(&self) -> &str {
        "openrouter"
    }

    fn get_extra_headers(&self) -> HashMap<String, String> {
        let mut headers = HashMap::new();
        
        if let Ok(site_url) = std::env::var("OPENROUTER_SITE_URL") {
            headers.insert("HTTP-Referer".to_string(), site_url);
        }
        
        if let Ok(site_name) = std::env::var("OPENROUTER_SITE_NAME") {
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

/// OpenRouter client
pub type OpenRouterClient = OpenAICompatibleClient<OpenRouterProvider>;

impl OpenRouterClient {
    pub fn with_config(mut model_config: ModelConfig) -> LLMResult<Self> {
        // Set default base URL if not provided
        if model_config.model_provider.base_url.is_none() {
            model_config.model_provider.base_url = Some("https://openrouter.ai/api/v1".to_string());
        }
        OpenAICompatibleClient::new(&model_config, OpenRouterProvider)
    }
}