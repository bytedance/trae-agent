// Copyright (c) 2025 ByteDance Ltd. and/or its affiliates
// SPDX-License-Identifier: MIT

//! LLM Client wrapper for OpenAI, Anthropic, and other OpenAI compatible LLM providers.
//!
//! This module provides a unified interface for different LLM providers,
//! similar to the Python implementation in trae_agent.utils.llm_clients.llm_client.
//!
//! # Example usage
//!
//! ```rust
//! use trae_core::config::{ModelConfig, ModelProvider};
//! use trae_core::llm::{LLMClient, LLMProvider, LLMMessage};
//!
//! // Create OpenAI provider configuration
//! let model_provider = ModelProvider::new("openai".to_string())
//!     .with_api_key("your-api-key".to_string());
//!
//! // Create model configuration
//! let model_config = ModelConfig::new("gpt-4".to_string(), model_provider);
//!
//! // Create LLM client - automatically detects provider
//! let mut client = LLMClient::new(model_config)?;
//!
//! // Send a chat message
//! let messages = vec![LLMMessage::user("Hello, world!")];
//! let response = client.chat(messages, &client.model_config, None, true).await?;
//! ```

use async_trait::async_trait;
use std::fmt;

use crate::llm::{
    error::{LLMError, LLMResult},
    llm_provider::LLMProvider as LLMProviderTrait,
    LLMMessage, LLMResponse, LLMStream,
    OpenAIClient, AnthropicClient,
    OpenAICompatibleGenericClient,
};
use crate::config::ModelConfig;
use crate::tools::Tool;

/// Supported LLM providers.
///
/// This enum matches the providers supported in the Python version.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum LLMProvider {
    /// OpenAI GPT models
    OpenAI,
    /// Anthropic Claude models
    Anthropic,
    /// Generic OpenAI Compatible providers
    OpenAICompatible,
}

impl LLMProvider {
    /// Create LLMProvider from string
    pub fn from_str(provider: &str) -> LLMResult<Self> {
        match provider.to_lowercase().as_str() {
            "openai" => Ok(LLMProvider::OpenAI),
            "anthropic" => Ok(LLMProvider::Anthropic),
            "openai_compatible" => Ok(LLMProvider::OpenAICompatible),
            _ => Err(LLMError::ConfigError(format!("Unsupported provider: {}", provider)))
        }
    }

    /// Get string representation of the provider
    pub fn as_str(&self) -> &'static str {
        match self {
            LLMProvider::OpenAI => "openai",
            LLMProvider::Anthropic => "anthropic",
            LLMProvider::OpenAICompatible => "openai_compatible",
        }
    }
}

impl fmt::Display for LLMProvider {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "{}", self.as_str())
    }
}

impl From<LLMProvider> for String {
    fn from(provider: LLMProvider) -> String {
        provider.as_str().to_string()
    }
}

/// Client wrapper that handles different LLM providers
///
/// This enum holds the specific client implementation for each provider.
pub enum ClientWrapper {
    OpenAI(OpenAIClient),
    Anthropic(AnthropicClient),
    OpenAICompatible(OpenAICompatibleGenericClient),
}

#[async_trait]
impl LLMProviderTrait for ClientWrapper {
    fn set_chat_history(&mut self, messages: Vec<LLMMessage>) {
        match self {
            ClientWrapper::OpenAI(client) => client.set_chat_history(messages),
            ClientWrapper::Anthropic(client) => client.set_chat_history(messages),
            ClientWrapper::OpenAICompatible(client) => client.set_chat_history(messages),
        }
    }

    async fn chat(
        &mut self,
        messages: Vec<LLMMessage>,
        model_config: &ModelConfig,
        tools: Option<&Vec<Box<dyn Tool>>>,
        reuse_history: Option<bool>,
    ) -> LLMResult<LLMResponse> {
        match self {
            ClientWrapper::OpenAI(client) => client.chat(messages, model_config, tools, reuse_history).await,
            ClientWrapper::Anthropic(client) => client.chat(messages, model_config, tools, reuse_history).await,
            ClientWrapper::OpenAICompatible(client) => client.chat(messages, model_config, tools, reuse_history).await,
        }
    }

    async fn chat_stream(
        &mut self,
        messages: Vec<LLMMessage>,
        model_config: &ModelConfig,
        tools: Option<&Vec<Box<dyn Tool>>>,
        reuse_history: Option<bool>,
    ) -> LLMResult<LLMStream> {
        match self {
            ClientWrapper::OpenAI(client) => client.chat_stream(messages, model_config, tools, reuse_history).await,
            ClientWrapper::Anthropic(client) => client.chat_stream(messages, model_config, tools, reuse_history).await,
            ClientWrapper::OpenAICompatible(client) => client.chat_stream(messages, model_config, tools, reuse_history).await,
        }
    }

    fn get_provider_name(&self) -> &str {
        match self {
            ClientWrapper::OpenAI(client) => client.get_provider_name(),
            ClientWrapper::Anthropic(client) => client.get_provider_name(),
            ClientWrapper::OpenAICompatible(client) => client.get_provider_name(),
        }
    }
}

/// Main LLM client that supports multiple providers.
///
/// This is the primary interface for LLM interactions, providing a unified API
/// across different providers. It automatically selects the appropriate client
/// implementation based on the provider specified in the model configuration.
pub struct LLMClient {
    /// The provider type for this client
    pub provider: LLMProvider,
    /// The model configuration
    pub model_config: ModelConfig,
    /// The wrapped client implementation
    client: ClientWrapper,
}

impl LLMClient {
    /// Create a new LLM client with the given model configuration.
    ///
    /// This method automatically detects the provider from the model configuration
    /// and instantiates the appropriate client implementation.
    ///
    /// # Arguments
    ///
    /// * `model_config` - The model configuration containing provider details
    ///
    /// # Returns
    ///
    /// Returns a `Result` containing the initialized `LLMClient` or an error if
    /// the provider is unsupported or configuration is invalid.
    ///
    /// # Example
    ///
    /// ```rust
    /// use trae_core::config::{ModelConfig, ModelProvider};
    /// use trae_core::llm::LLMClient;
    ///
    /// let model_provider = ModelProvider::new("openai".to_string())
    ///     .with_api_key("sk-...".to_string());
    /// let model_config = ModelConfig::new("gpt-4".to_string(), model_provider);
    ///
    /// let client = LLMClient::new(model_config)?;
    /// ```
    pub fn new(model_config: ModelConfig) -> LLMResult<Self> {
        let provider = LLMProvider::from_str(&model_config.model_provider.name)?;

        let client = match provider {
            LLMProvider::OpenAI => {
                let openai_client = OpenAIClient::new(&model_config)?;
                ClientWrapper::OpenAI(openai_client)
            },
            LLMProvider::Anthropic => {
                let anthropic_client = AnthropicClient::new(&model_config)?;
                ClientWrapper::Anthropic(anthropic_client)
            },
            LLMProvider::OpenAICompatible => {
                let openai_compatible_client = OpenAICompatibleGenericClient::with_config(model_config.clone())?;
                ClientWrapper::OpenAICompatible(openai_compatible_client)
            },
        };

        Ok(Self {
            provider,
            model_config,
            client,
        })
    }

    /// Set the chat history for the underlying client.
    ///
    /// This method allows you to set a persistent chat history that will be
    /// included in subsequent chat calls when `reuse_history` is true.
    ///
    /// # Arguments
    ///
    /// * `messages` - Vector of `LLMMessage` representing the chat history
    pub fn set_chat_history(&mut self, messages: Vec<LLMMessage>) {
        self.client.set_chat_history(messages);
    }

    /// Send chat messages to the LLM.
    ///
    /// This is the main method for interacting with the LLM. It sends a sequence
    /// of messages and returns the LLM's response.
    ///
    /// # Arguments
    ///
    /// * `messages` - Vector of messages to send to the LLM
    /// * `model_config` - Model configuration to use for this request
    /// * `tools` - Optional vector of tools the LLM can call
    /// * `reuse_history` - Whether to include previously set chat history
    ///
    /// # Returns
    ///
    /// Returns a `Result` containing the `LLMResponse` from the provider.
    ///
    /// # Example
    ///
    /// ```rust
    /// use trae_core::llm::{LLMClient, LLMMessage};
    ///
    /// let messages = vec![LLMMessage::user("What is the capital of France?")];
    /// let response = client.chat(messages, &client.model_config, None, true).await?;
    /// println!("Response: {}", response.get_text().unwrap_or("No text response"));
    /// ```
    pub async fn chat(
        &mut self,
        messages: Vec<LLMMessage>,
        model_config: &ModelConfig,
        tools: Option<&Vec<Box<dyn Tool>>>,
        reuse_history: bool,
    ) -> LLMResult<LLMResponse> {
        self.client.chat(messages, model_config, tools, Some(reuse_history)).await
    }

    /// Send chat messages to the LLM with streaming response.
    ///
    /// This method is similar to `chat` but returns a stream of response chunks
    /// instead of waiting for the complete response.
    ///
    /// # Arguments
    ///
    /// * `messages` - Vector of messages to send to the LLM
    /// * `model_config` - Model configuration to use for this request
    /// * `tools` - Optional vector of tools the LLM can call
    /// * `reuse_history` - Whether to include previously set chat history
    ///
    /// # Returns
    ///
    /// Returns a `Result` containing an `LLMStream` of response chunks.
    pub async fn chat_stream(
        &mut self,
        messages: Vec<LLMMessage>,
        model_config: &ModelConfig,
        tools: Option<&Vec<Box<dyn Tool>>>,
        reuse_history: bool,
    ) -> LLMResult<LLMStream> {
        self.client.chat_stream(messages, model_config, tools, Some(reuse_history)).await
    }

    /// Get the provider name for this client.
    ///
    /// # Returns
    ///
    /// Returns a string slice containing the provider name.
    pub fn get_provider_name(&self) -> &str {
        self.client.get_provider_name()
    }

    /// Get the provider enum for this client.
    ///
    /// # Returns
    ///
    /// Returns a reference to the `LLMProvider` enum variant.
    pub fn get_provider(&self) -> &LLMProvider {
        &self.provider
    }

    /// Get the model configuration for this client.
    ///
    /// # Returns
    ///
    /// Returns a reference to the `ModelConfig`.
    pub fn get_model_config(&self) -> &ModelConfig {
        &self.model_config
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::config::ModelProvider;

    #[test]
    fn test_llm_provider_from_str() {
        assert_eq!(LLMProvider::from_str("openai").unwrap(), LLMProvider::OpenAI);
        assert_eq!(LLMProvider::from_str("ANTHROPIC").unwrap(), LLMProvider::Anthropic);
        assert_eq!(LLMProvider::from_str("openai_compatible").unwrap(), LLMProvider::OpenAICompatible);

        assert!(LLMProvider::from_str("invalid").is_err());
    }

    #[test]
    fn test_llm_provider_as_str() {
        assert_eq!(LLMProvider::OpenAI.as_str(), "openai");
        assert_eq!(LLMProvider::Anthropic.as_str(), "anthropic");
        assert_eq!(LLMProvider::OpenAICompatible.as_str(), "openai_compatible");
    }

    #[test]
    fn test_llm_provider_display() {
        assert_eq!(format!("{}", LLMProvider::OpenAI), "openai");
        assert_eq!(format!("{}", LLMProvider::Anthropic), "anthropic");
    }

    #[test]
    fn test_llm_provider_to_string() {
        let provider_str: String = LLMProvider::OpenAI.into();
        assert_eq!(provider_str, "openai");
    }

    #[test]
    fn test_llm_client_creation_openai() {
        let model_provider = ModelProvider::new("openai".to_string())
            .with_api_key("test_key".to_string());
        let model_config = ModelConfig::new("gpt-4".to_string(), model_provider);

        let client = LLMClient::new(model_config);
        assert!(client.is_ok());

        let client = client.unwrap();
        assert_eq!(client.get_provider(), &LLMProvider::OpenAI);
        assert_eq!(client.get_provider_name(), "openai");
    }

    #[test]
    fn test_llm_client_creation_invalid_provider() {
        let model_provider = ModelProvider::new("invalid_provider".to_string());
        let model_config = ModelConfig::new("some-model".to_string(), model_provider);

        let client = LLMClient::new(model_config);
        assert!(client.is_err());

        if let Err(e) = client {
            assert!(e.to_string().contains("Unsupported provider"));
        }
    }

    #[test]
    fn test_llm_client_accessors() {
        let model_provider = ModelProvider::new("openai".to_string())
            .with_api_key("test_key".to_string());
        let model_config = ModelConfig::new("gpt-4".to_string(), model_provider);

        let client = LLMClient::new(model_config.clone()).unwrap();

        assert_eq!(client.get_provider(), &LLMProvider::OpenAI);
        assert_eq!(client.get_model_config().model, "gpt-4");
        assert_eq!(client.get_model_config().model_provider.name, "openai");
    }
}
