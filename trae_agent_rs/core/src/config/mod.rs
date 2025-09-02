// Copyright (c) 2025 ByteDance Ltd. and/or its affiliates
// SPDX-License-Identifier: MIT

use serde::{Deserialize, Serialize};
use std::collections::HashMap;

/// Model provider configuration
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ModelProvider {
    pub name: String,
    pub api_key: Option<String>,
    pub base_url: Option<String>,
}

/// Model configuration for LLM clients
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ModelConfig {
    pub model: String,
    pub model_provider: ModelProvider,
    pub temperature: Option<f32>,
    pub top_p: Option<f32>,
    pub max_tokens: Option<u32>,
    pub max_retries: Option<u32>,
    #[serde(default)]
    pub extra_headers: HashMap<String, String>,
}

impl ModelProvider {
    pub fn new(name: String) -> Self {
        Self {
            name,
            api_key: None,
            base_url: None,
        }
    }
    
    pub fn with_api_key(mut self, api_key: String) -> Self {
        self.api_key = Some(api_key);
        self
    }
    
    pub fn with_base_url(mut self, base_url: String) -> Self {
        self.base_url = Some(base_url);
        self
    }
}

impl ModelConfig {
    pub fn new(model: String, provider: ModelProvider) -> Self {
        Self {
            model,
            model_provider: provider,
            temperature: None,
            top_p: None,
            max_tokens: None,
            max_retries: None,
            extra_headers: HashMap::new(),
        }
    }
    
    pub fn with_temperature(mut self, temperature: f32) -> Self {
        self.temperature = Some(temperature);
        self
    }
    
    pub fn with_top_p(mut self, top_p: f32) -> Self {
        self.top_p = Some(top_p);
        self
    }
    
    pub fn with_max_tokens(mut self, max_tokens: u32) -> Self {
        self.max_tokens = Some(max_tokens);
        self
    }
    
    pub fn with_max_retries(mut self, max_retries: u32) -> Self {
        self.max_retries = Some(max_retries);
        self
    }
    
    pub fn with_extra_header(mut self, key: String, value: String) -> Self {
        self.extra_headers.insert(key, value);
        self
    }
}
