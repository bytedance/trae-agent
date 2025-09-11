// Copyright (c) 2025 ByteDance Ltd. and/or its affiliates
// SPDX-License-Identifier: MIT

use anyhow::Result;
use serde::{Deserialize, Serialize};
use std::path::PathBuf;
use std::fs;
use dirs::config_dir;

/// User settings for the CLI application
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct UserSettings {
    pub provider: String,
    pub model: String,
    pub api_key: Option<String>,
    pub base_url: Option<String>,
    pub workspace: PathBuf,
}

impl Default for UserSettings {
    fn default() -> Self {
        Self {
            provider: "openai".to_string(),
            model: "gpt-4".to_string(),
            api_key: None,
            base_url: None,
            workspace: PathBuf::from("."),
        }
    }
}

impl UserSettings {
    /// Create new settings with provided values
    pub fn new(provider: String, model: String, workspace: PathBuf) -> Self {
        Self {
            provider,
            model,
            api_key: None,
            base_url: None,
            workspace,
        }
    }

    /// Get the config file path
    pub fn config_file_path() -> Result<PathBuf> {
        let config_dir = config_dir()
            .ok_or_else(|| anyhow::anyhow!("Could not find config directory"))?;
        
        let trae_config_dir = config_dir.join("trae-agent");
        
        // Create the directory if it doesn't exist
        if !trae_config_dir.exists() {
            fs::create_dir_all(&trae_config_dir)?;
        }
        
        Ok(trae_config_dir.join("settings.json"))
    }

    /// Load settings from config file
    pub fn load() -> Result<Self> {
        // First try to load from trae_config.json in current directory
        let local_config = PathBuf::from("trae_config.json");
        if local_config.exists() {
            let content = fs::read_to_string(&local_config)?;
            return Ok(serde_json::from_str(&content)?);
        }
        
        // Fall back to user config directory
        let config_path = Self::config_file_path()?;
        
        if !config_path.exists() {
            // Return default settings if config file doesn't exist
            return Ok(Self::default());
        }
        
        let content = fs::read_to_string(&config_path)?;
        let settings: UserSettings = serde_json::from_str(&content)?;
        
        Ok(settings)
    }

    /// Save settings to config file
    pub fn save(&self) -> Result<()> {
        // Check if trae_config.json exists in current directory
        let local_config = PathBuf::from("trae_config.json");
        if local_config.exists() {
            // Save to local config if it exists
            let content = serde_json::to_string_pretty(self)?;
            fs::write(&local_config, content)?;
        } else {
            // Save to user config directory
            let config_path = Self::config_file_path()?;
            let content = serde_json::to_string_pretty(self)?;
            fs::write(&config_path, content)?;
        }
        Ok(())
    }

    /// Get the effective API key (from settings or environment)
    pub fn get_api_key(&self) -> Option<String> {
        // First try the stored API key
        if let Some(ref key) = self.api_key {
            if !key.is_empty() {
                return Some(key.clone());
            }
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
        if let Some(ref url) = self.base_url {
            if !url.is_empty() {
                return Some(url.clone());
            }
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

    /// Get the number of editable fields
    pub fn field_count() -> usize {
        5 // provider, model, api_key, base_url, workspace
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
            },
            3 => self.settings.base_url.clone().unwrap_or("(default)".to_string()),
            4 => self.settings.workspace.display().to_string(),
            _ => String::new(),
        }
    }

    /// Start editing a field
    pub fn start_editing(&mut self, index: usize) {
        self.editing_field = Some(index);
        self.temp_input = match index {
            0 => self.settings.provider.clone(),
            1 => self.settings.model.clone(),
            2 => self.settings.api_key.clone().unwrap_or_default(),
            3 => self.settings.base_url.clone().unwrap_or_default(),
            4 => self.settings.workspace.display().to_string(),
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
                },
                3 => {
                    if self.temp_input.is_empty() {
                        self.settings.base_url = None;
                    } else {
                        self.settings.base_url = Some(self.temp_input.clone());
                    }
                },
                4 => {
                    self.settings.workspace = PathBuf::from(&self.temp_input);
                },
                _ => {},
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
}