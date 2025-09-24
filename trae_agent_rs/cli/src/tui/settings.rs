// Copyright (c) 2025 ByteDance Ltd. and/or its affiliates
// SPDX-License-Identifier: MIT

use anyhow::Result;
use dirs::config_dir;
use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::fs;
use std::path::PathBuf;
use trae_core::config::{Config, ModelConfig, ModelProvider, TraeAgentConfig};

/// User settings for the CLI application
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct UserSettings {
    pub provider: String,
    pub model: String,
    pub api_key: Option<String>,
    pub base_url: Option<String>,
    #[serde(skip)]
    pub workspace: PathBuf,
    pub max_steps: u32,
}

impl Default for UserSettings {
    fn default() -> Self {
        Self {
            provider: "openai".to_string(),
            model: "gpt-4".to_string(),
            api_key: None,
            base_url: None,
            workspace: std::env::current_dir().unwrap_or_else(|_| PathBuf::from(".")),
            max_steps: 200,
        }
    }
}

impl UserSettings {
    /// Create new settings with provided values
    pub fn new(provider: String, model: String) -> Self {
        Self {
            provider,
            model,
            api_key: None,
            base_url: None,
            workspace: std::env::current_dir().unwrap_or_else(|_| PathBuf::from(".")),
            max_steps: 200,
        }
    }

    /// Create UserSettings from Config
    pub fn from_config(config: &Config) -> Self {
        let model_config = &config.trae_agent_config.model;
        let provider = &model_config.model_provider;

        Self {
            provider: provider.name.clone(),
            model: model_config.model.clone(),
            api_key: provider.api_key.clone(),
            base_url: provider.base_url.clone(),
            workspace: std::env::current_dir().unwrap_or_else(|_| PathBuf::from(".")),
            max_steps: config.trae_agent_config.max_steps,
        }
    }

    /// Convert UserSettings to Config structure
    pub fn to_config(&self) -> Config {
        let provider = ModelProvider {
            name: self.provider.clone(),
            api_key: self.api_key.clone(),
            base_url: self.base_url.clone(),
        };

        let model_config = ModelConfig {
            model: self.model.clone(),
            model_provider: provider,
            temperature: None,
            top_p: None,
            max_tokens: None,
            max_retries: None,
            extra_headers: HashMap::new(),
        };

        let trae_agent_config = TraeAgentConfig {
            tools: vec![
                "bash".to_string(),
                "str_replace_based_edit_tool".to_string(),
            ], // Default tools
            model: model_config,
            max_steps: self.max_steps,
            allow_mcp_servers: vec![],
            mcp_servers_config: HashMap::new(),
        };

        Config { trae_agent_config }
    }

    /// Convert Config to YAML string
    fn config_to_yaml(&self) -> Result<String> {
        let config = self.to_config();
        let model_config = &config.trae_agent_config.model;
        let provider = &model_config.model_provider;

        let yaml_content = format!(
            r#"agents:
  trae_agent:
    model: user_model
    max_steps: {}
    tools:
{}

model_providers:
  {}:
    api_key: {}
    base_url: {}

models:
  user_model:
    model_provider: {}
    model: {}
    temperature: {}
    top_p: {}
    max_tokens: {}
    max_retries: {}

allow_mcp_servers: []
mcp_servers: {{}}
"#,
            config.trae_agent_config.max_steps,
            config
                .trae_agent_config
                .tools
                .iter()
                .map(|tool| format!("      - {}", tool))
                .collect::<Vec<_>>()
                .join("\n"),
            provider.name,
            provider.api_key.as_ref().unwrap_or(&"null".to_string()),
            provider.base_url.as_ref().unwrap_or(&"null".to_string()),
            provider.name,
            model_config.model,
            model_config
                .temperature
                .map(|t| t.to_string())
                .unwrap_or("null".to_string()),
            model_config
                .top_p
                .map(|t| t.to_string())
                .unwrap_or("null".to_string()),
            model_config
                .max_tokens
                .map(|t| t.to_string())
                .unwrap_or("null".to_string()),
            model_config
                .max_retries
                .map(|t| t.to_string())
                .unwrap_or("null".to_string()),
        );

        Ok(yaml_content)
    }

    /// Get the config file path
    pub fn config_file_path() -> Result<PathBuf> {
        let config_dir =
            config_dir().ok_or_else(|| anyhow::anyhow!("Could not find config directory"))?;

        let trae_config_dir = config_dir.join("trae-agent");

        // Create the directory if it doesn't exist
        if !trae_config_dir.exists() {
            fs::create_dir_all(&trae_config_dir)?;
        }

        Ok(trae_config_dir.join("trae_config.yaml"))
    }

    /// Load settings from config file
    pub fn load() -> Result<Self> {
        // First try to load from trae_config.yaml in current directory
        let local_config = PathBuf::from("trae_config.yaml");
        if local_config.exists() {
            let config = Config::from_yaml(local_config.to_str().unwrap())?;
            return Ok(Self::from_config(&config));
        }

        // Fall back to user config directory
        let config_path = Self::config_file_path()?;

        if !config_path.exists() {
            // Return default settings if config file doesn't exist
            return Ok(Self::default());
        }

        let config = Config::from_yaml(config_path.to_str().unwrap())?;
        Ok(Self::from_config(&config))
    }

    /// Save settings to config file
    pub fn save(&self) -> Result<()> {
        // Check if trae_config.yaml exists in current directory
        let local_config = PathBuf::from("trae_config.yaml");
        if local_config.exists() {
            // Save to local config if it exists
            let content = self.config_to_yaml()?;
            fs::write(&local_config, content)?;
        } else {
            // Save to user config directory
            let config_path = Self::config_file_path()?;
            let content = self.config_to_yaml()?;
            fs::write(&config_path, content)?;
        }
        Ok(())
    }

    /// Get the effective API key (from settings or environment)
    pub fn get_api_key(&self) -> Option<String> {
        // First try the stored API key
        if let Some(ref key) = self.api_key
            && !key.is_empty()
        {
            return Some(key.clone());
        }

        // Fall back to environment variables
        match self.provider.as_str() {
            "openai" => std::env::var("OPENAI_API_KEY")
                .or_else(|_| std::env::var("API_KEY"))
                .ok(),
            "anthropic" => std::env::var("ANTHROPIC_API_KEY").ok(),
            "azure" => std::env::var("AZURE_API_KEY").ok(),
            _ => None,
        }
    }

    /// Get the effective base URL (from settings or default)
    pub fn get_base_url(&self) -> Option<String> {
        // First try the stored base URL
        if let Some(ref url) = self.base_url
            && !url.is_empty()
        {
            return Some(url.clone());
        }

        // Fall back to provider defaults
        match self.provider.as_str() {
            "openai" => Some("https://api.openai.com/v1".to_string()),
            "anthropic" => Some("https://api.anthropic.com".to_string()),
            "azure" => std::env::var("AZURE_BASE_URL").ok(),
            _ => None,
        }
    }

    /// Update provider and reset model to default for that provider
    pub fn set_provider(&mut self, provider: String) {
        self.provider = provider.clone();

        // Set default model for the provider
        self.model = match provider.as_str() {
            "openai" => "gpt-4".to_string(),
            "anthropic" => "claude-3-sonnet-20240229".to_string(),
            "azure" => "gpt-4".to_string(),
            _ => "gpt-4".to_string(),
        };
    }

    /// Get the current workspace (always the current working directory)
    pub fn get_workspace(&self) -> &PathBuf {
        &self.workspace
    }

    /// Update the workspace to the current working directory
    pub fn refresh_workspace(&mut self) {
        self.workspace = std::env::current_dir().unwrap_or_else(|_| PathBuf::from("."));
    }

    /// Get the workspace path formatted with ~ prefix if it starts with home directory
    pub fn get_workspace_display(&self) -> String {
        if let Some(home_dir) = dirs::home_dir()
            && let Ok(stripped) = self.workspace.strip_prefix(&home_dir)
        {
            return format!("~/{}", stripped.display());
        }
        self.workspace.display().to_string()
    }

    /// Validate the current settings
    pub fn validate(&self) -> Result<()> {
        // Check if API key is available
        if self.get_api_key().is_none() {
            return Err(anyhow::anyhow!(
                "No API key found for provider '{}'. Please set it in settings or environment variables.",
                self.provider
            ));
        }

        // Check if workspace exists
        if !self.workspace.exists() {
            return Err(anyhow::anyhow!(
                "Workspace directory '{}' does not exist.",
                self.workspace.display()
            ));
        }

        Ok(())
    }
}

/// Settings editing state for the UI
#[derive(Debug, Clone)]
pub struct SettingsEditor {
    pub settings: UserSettings,
    pub selected_field: usize,
    pub editing_field: Option<usize>,
    pub temp_input: String,
    pub show_password: bool,
}

impl SettingsEditor {
    pub fn new(settings: UserSettings) -> Self {
        Self {
            settings,
            selected_field: 0,
            editing_field: None,
            temp_input: String::new(),
            show_password: false,
        }
    }

    /// Get the number of editable fields (including read-only workspace)
    pub fn field_count() -> usize {
        5 // provider, model, api_key, base_url, workspace (read-only)
    }

    /// Get the number of editable fields (excluding read-only workspace)
    pub fn editable_field_count() -> usize {
        4 // provider, model, api_key, base_url
    }

    /// Get the field name for display
    pub fn field_name(index: usize) -> &'static str {
        match index {
            0 => "Provider",
            1 => "Model",
            2 => "API Key",
            3 => "Base URL",
            4 => "Workspace",
            _ => "Unknown",
        }
    }

    /// Get the current value of a field
    pub fn field_value(&self, index: usize) -> String {
        match index {
            0 => self.settings.provider.clone(),
            1 => self.settings.model.clone(),
            2 => {
                if let Some(ref key) = self.settings.api_key {
                    if self.show_password {
                        key.clone()
                    } else {
                        "*".repeat(key.len().min(20))
                    }
                } else {
                    "(not set)".to_string()
                }
            }
            3 => self
                .settings
                .base_url
                .clone()
                .unwrap_or("(default)".to_string()),
            4 => self.settings.get_workspace_display(),
            _ => String::new(),
        }
    }

    /// Start editing a field (workspace is read-only)
    pub fn start_editing(&mut self, index: usize) {
        // Don't allow editing workspace (index 4)
        if index == 4 {
            return;
        }

        self.editing_field = Some(index);
        self.temp_input = match index {
            0 => self.settings.provider.clone(),
            1 => self.settings.model.clone(),
            2 => self.settings.api_key.clone().unwrap_or_default(),
            3 => self.settings.base_url.clone().unwrap_or_default(),
            _ => String::new(),
        };
    }

    /// Cancel editing
    pub fn cancel_editing(&mut self) {
        self.editing_field = None;
        self.temp_input.clear();
    }

    /// Confirm editing and update the field
    pub fn confirm_editing(&mut self) -> Result<()> {
        if let Some(index) = self.editing_field {
            match index {
                0 => self.settings.set_provider(self.temp_input.clone()),
                1 => self.settings.model = self.temp_input.clone(),
                2 => {
                    if self.temp_input.is_empty() {
                        self.settings.api_key = None;
                    } else {
                        self.settings.api_key = Some(self.temp_input.clone());
                    }
                }
                3 => {
                    if self.temp_input.is_empty() {
                        self.settings.base_url = None;
                    } else {
                        self.settings.base_url = Some(self.temp_input.clone());
                    }
                }
                _ => {}
            }
            self.cancel_editing();
        }
        Ok(())
    }

    /// Move selection up
    pub fn move_up(&mut self) {
        if self.selected_field > 0 {
            self.selected_field -= 1;
        }
    }

    /// Move selection down
    pub fn move_down(&mut self) {
        if self.selected_field < Self::field_count() - 1 {
            self.selected_field += 1;
        }
    }

    /// Toggle password visibility
    pub fn toggle_password_visibility(&mut self) {
        self.show_password = !self.show_password;
    }

    /// Move to the previous field
    pub fn prev_field(&mut self) {
        if self.selected_field > 0 {
            self.selected_field -= 1;
        } else {
            self.selected_field = Self::field_count() - 1;
        }
    }

    /// Move to the next field
    pub fn next_field(&mut self) {
        self.selected_field = (self.selected_field + 1) % Self::field_count();
    }

    /// Delete a character from the current input
    pub fn delete_char(&mut self) {
        if !self.temp_input.is_empty() {
            self.temp_input.pop();
        }
    }

    /// Insert a character into the current input
    pub fn insert_char(&mut self, c: char) {
        self.temp_input.push(c);
    }

    /// Get the current settings
    pub fn get_settings(&self) -> &UserSettings {
        &self.settings
    }

    /// Get the currently selected field index
    pub fn get_current_field(&self) -> usize {
        self.selected_field
    }

    /// Check if a field is editable (workspace is read-only)
    pub fn is_field_editable(&self, index: usize) -> bool {
        index != 4 // workspace is not editable
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_config_conversion() {
        let settings = UserSettings {
            provider: "openai".to_string(),
            model: "gpt-4".to_string(),
            api_key: Some("test-key".to_string()),
            base_url: Some("https://api.openai.com/v1".to_string()),
            workspace: std::env::current_dir().unwrap_or_else(|_| PathBuf::from(".")),
            max_steps: 200,
        };

        let config = settings.to_config();
        let converted_settings = UserSettings::from_config(&config);

        assert_eq!(converted_settings.provider, "openai");
        assert_eq!(converted_settings.model, "gpt-4");
        assert_eq!(converted_settings.api_key, Some("test-key".to_string()));
        assert_eq!(
            converted_settings.base_url,
            Some("https://api.openai.com/v1".to_string())
        );
        // Workspace is always current directory, so we just verify it's set
        assert!(
            converted_settings.workspace.is_absolute()
                || converted_settings.workspace == PathBuf::from(".")
        );
    }

    #[test]
    fn test_yaml_generation() {
        let settings = UserSettings {
            provider: "anthropic".to_string(),
            model: "claude-3-sonnet".to_string(),
            api_key: Some("test-anthropic-key".to_string()),
            base_url: None,
            workspace: std::env::current_dir().unwrap_or_else(|_| PathBuf::from(".")),
            max_steps: 200,
        };

        let yaml_content = settings.config_to_yaml().unwrap();
        assert!(yaml_content.contains("anthropic"));
        assert!(yaml_content.contains("claude-3-sonnet"));
        assert!(yaml_content.contains("test-anthropic-key"));
        assert!(yaml_content.contains("model_providers:"));
        assert!(yaml_content.contains("agents:"));
    }

    #[test]
    fn test_workspace_display_with_tilde() {
        // Test workspace display with home directory prefix
        if let Some(home_dir) = dirs::home_dir() {
            let workspace_in_home = home_dir.join("Projects").join("test");
            let settings = UserSettings {
                provider: "openai".to_string(),
                model: "gpt-4".to_string(),
                api_key: None,
                base_url: None,
                workspace: workspace_in_home,
                max_steps: 200,
            };

            let display = settings.get_workspace_display();
            assert!(
                display.starts_with("~/"),
                "Display should start with ~/: {}",
                display
            );
            assert!(
                display.contains("Projects/test"),
                "Display should contain the path: {}",
                display
            );
        }

        // Test workspace display with non-home directory
        let settings = UserSettings {
            provider: "openai".to_string(),
            model: "gpt-4".to_string(),
            api_key: None,
            base_url: None,
            workspace: PathBuf::from("/tmp/test"),
            max_steps: 200,
        };

        let display = settings.get_workspace_display();
        assert_eq!(display, "/tmp/test");
    }
}
