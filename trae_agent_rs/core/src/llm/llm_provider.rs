// Copyright (c) 2025 ByteDance Ltd. and/or its affiliates
// SPDX-License-Identifier: MIT

use async_trait::async_trait;
use crate::llm::{LLMMessage, LLMResponse, LLMStream, error::LLMResult};
use crate::config::ModelConfig;
use crate::tools::Tool;

/// Base trait for all LLM clients
#[async_trait]
pub trait LLMProvider: Send + Sync {
    /// Set the chat history for the client
    fn set_chat_history(&mut self, messages: Vec<LLMMessage>);

    /// Send chat messages to the LLM with optional tool support
    async fn chat(
        // i am not so sure why here need to use mut instead of & cuz it will cause every 
        // agent calling this api has to be &mut
        &mut self,
        messages: Vec<LLMMessage>,
        model_config: &ModelConfig,
        tools: Option<&Vec<Box<dyn Tool>>>,
        reuse_history: Option<bool>,
    ) -> LLMResult<LLMResponse>;

    /// Send chat messages to the LLM with streaming response
    async fn chat_stream(
        &mut self,
        messages: Vec<LLMMessage>,
        model_config: &ModelConfig,
        tools: Option<Vec<Box<dyn Tool>>>,
        reuse_history: Option<bool>,
    ) -> LLMResult<LLMStream>;

    /// Get the provider name for this client
    fn get_provider_name(&self) -> &str;
}
