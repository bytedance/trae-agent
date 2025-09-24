// Copyright (c) 2025 ByteDance Ltd. and/or its affiliates
// SPDX-License-Identifier: MIT

use super::{
    event::{Event, EventHandler},
    layout::Layout,
    popup_input::PopupInputEditor,
    review_history::ReviewHistoryDisplay,
    settings::{SettingsEditor, UserSettings},
    state::{AgentStatus, AppState},
};
use anyhow::Result;
use crossterm::{
    event::{DisableMouseCapture, EnableMouseCapture, KeyCode, KeyModifiers},
    execute,
    terminal::{EnterAlternateScreen, LeaveAlternateScreen, disable_raw_mode, enable_raw_mode},
};
use ratatui::{
    Terminal,
    backend::{Backend, CrosstermBackend},
    prelude::*,
    text::{Line, Span},
};
use std::sync::Arc;
use std::{collections::HashMap, io, path::PathBuf};
use tokio::sync::Mutex;
use trae_core::{
    agent::base_agent::{Agent, AgentExecution, BaseAgent},
    config::{ModelConfig, ModelProvider},
    llm::LLMClient,
    trae::{AgentUpdate, TraeAgent},
};

const MAX_TOKEN: u32 = 4096;
const TEMPERATURE: f32 = 0.1;

pub struct App {
    state: AppState,
    event_handler: EventHandler,
    agent: Option<Arc<tokio::sync::Mutex<TraeAgent>>>,
    model_config: ModelConfig,
    workspace: PathBuf,
    settings: UserSettings,
    settings_editor: Option<SettingsEditor>,
    popup_input_editor: PopupInputEditor,
    review_history: ReviewHistoryDisplay,
    show_review_history: bool,
}

impl App {
    pub fn new(provider: String, model: String) -> Result<Self> {
        Self::new_with_workspace(provider, model, None)
    }

    pub fn new_with_workspace(provider: String, model: String, workspace: Option<PathBuf>) -> Result<Self> {
        // Load existing settings or create new ones
        let mut settings = UserSettings::load()
            .unwrap_or_else(|_| UserSettings::new(provider.clone(), model.clone()));

        // Override workspace if provided via command line
        let final_workspace = if let Some(ws) = workspace {
            // Convert to absolute path
            let absolute_workspace = if ws.is_absolute() {
                ws
            } else {
                std::env::current_dir()?.join(ws)
            };
            settings.workspace = absolute_workspace.clone();
            absolute_workspace
        } else {
            settings.workspace.clone()
        };

        // Create model configuration from settings
        let api_key = settings.get_api_key().unwrap_or_default();
        let base_url = settings.get_base_url();

        let mut model_provider =
            ModelProvider::new(settings.provider.clone()).with_api_key(api_key);

        if let Some(url) = base_url {
            model_provider = model_provider.with_base_url(url);
        }

        let model_config = ModelConfig::new(settings.model.clone(), model_provider)
            .with_max_tokens(MAX_TOKEN)
            .with_temperature(TEMPERATURE);

        Ok(Self {
            state: AppState::new(),
            event_handler: EventHandler::new(),
            agent: None,
            model_config,
            workspace: final_workspace,
            settings,
            settings_editor: None,
            popup_input_editor: PopupInputEditor::with_title("Multi-line Input".to_string()),
            review_history: ReviewHistoryDisplay::new(),
            show_review_history: false,
        })
    }

    /// Get the current settings
    pub fn get_settings(&self) -> &UserSettings {
        &self.settings
    }

    pub async fn run(&mut self) -> Result<()> {
        // Setup terminal
        enable_raw_mode()?;
        let mut stdout = io::stdout();
        execute!(stdout, EnterAlternateScreen, EnableMouseCapture)?;
        let backend = CrosstermBackend::new(stdout);
        let mut terminal = Terminal::new(backend)?;

        // Clear the screen
        terminal.clear()?;

        // Start the event loop
        self.event_handler.start_event_loop().await;

        // Run the app
        let result = self.run_app(&mut terminal).await;

        // Stop the event handler to prevent further events
        self.event_handler.stop().await;

        // Give a small delay to ensure all background tasks complete
        tokio::time::sleep(tokio::time::Duration::from_millis(100)).await;

        // Flush any remaining output
        use std::io::Write;
        let _ = std::io::stdout().flush();
        let _ = std::io::stderr().flush();

        // Restore terminal
        disable_raw_mode()?;
        execute!(
            terminal.backend_mut(),
            LeaveAlternateScreen,
            DisableMouseCapture
        )?;
        terminal.show_cursor()?;

        // Final flush after terminal restoration
        let _ = std::io::stdout().flush();

        result
    }

    async fn run_app<B: Backend>(&mut self, terminal: &mut Terminal<B>) -> Result<()> {
        loop {
            // Draw the UI
            terminal.draw(|frame| {
                Layout::render(frame, &mut self.state, &self.settings_editor, &mut self.popup_input_editor, &mut self.review_history, self.show_review_history);
            })?;

            // Handle events
            if let Some(event) = self.event_handler.next().await {
                match event {
                    Event::Quit => {
                        self.state.should_quit = true;
                        break;
                    }
                    Event::Key(key_event) => {
                        self.handle_key_event(key_event).await?;
                    }
                    Event::AgentOutput(output) => {
                        self.state.add_output_line(output.clone());
                        
                        // Also add to current step history
                        let styled_line = Line::from(Span::styled(output, Style::default().fg(Color::White)));
                        self.state.add_output_to_current_step(styled_line);
                    }
                    Event::AgentStatusUpdate(status) => {
                        self.state.agent_status = status.clone();
                        self.state.update_current_step_status(status);
                    }
                    Event::TokenUsageUpdate(token_usage) => {
                        self.state.token_usage = token_usage;
                    }
                    Event::AgentStepUpdate { step, description } => {
                        // Complete previous step if exists
                        if self.state.current_step.is_some() && self.state.current_step != Some(step) {
                            self.state.complete_current_step();
                        }
                        
                        // Start new step tracking
                        self.state.start_new_step(step, description.clone());
                        
                        // Add to regular output
                        let step_line = format!("Step {}: {}", step, description);
                        self.state.add_output_line(step_line.clone());
                        
                        // Also add to current step history
                        let styled_line = Line::from(vec![
                            Span::styled("🔄 ", Style::default().fg(Color::Yellow)),
                            Span::styled(step_line, Style::default().fg(Color::Cyan)),
                        ]);
                        self.state.add_output_to_current_step(styled_line);
                    }
                    Event::AgentError(error) => {
                        let error_msg = format!("Error: {}", error);
                        self.state.add_output_line(error_msg.clone());
                        self.state.agent_status = AgentStatus::Error(error.clone());
                        
                        // Add error to current step history
                        let styled_line = Line::from(vec![
                            Span::styled("❌ ", Style::default().fg(Color::Red)),
                            Span::styled(error_msg, Style::default().fg(Color::Red)),
                        ]);
                        self.state.add_output_to_current_step(styled_line);
                        self.state.update_current_step_status(AgentStatus::Error(error));
                    }
                    Event::TaskCompleted(summary) => {
                        let completion_msg = format!("Task completed: {}", summary);
                        self.state.add_output_line(completion_msg.clone());
                        self.state.agent_status = AgentStatus::Idle;
                        
                        // Add completion to current step history and complete the step
                        let styled_line = Line::from(vec![
                            Span::styled("✅ ", Style::default().fg(Color::Green)),
                            Span::styled(completion_msg, Style::default().fg(Color::Green)),
                        ]);
                        self.state.add_output_to_current_step(styled_line);
                        self.state.complete_current_step();
                    }
                    Event::Tick => {
                        // Regular update tick - can be used for periodic updates
                    }
                }
            }

            if self.state.should_quit {
                break;
            }
        }

        Ok(())
    }

    async fn handle_key_event(&mut self, key_event: crossterm::event::KeyEvent) -> Result<()> {
        // Handle popup interactions first
        if self.state.show_quit_popup {
            return self.handle_quit_popup_key(key_event).await;
        }

        if self.state.show_settings {
            return self.handle_settings_popup_key(key_event).await;
        }

        if self.state.show_popup_input {
            return self.handle_popup_input_key(key_event).await;
        }

        if self.show_review_history {
            return self.handle_review_history_key(key_event).await;
        }

        if self.state.show_step_history {
            return self.handle_step_history_key(key_event).await;
        }

        // Handle autocomplete interactions
        if self.state.show_autocomplete {
            match key_event.code {
                KeyCode::Tab | KeyCode::Enter => {
                    self.state.apply_selected_suggestion();
                    return Ok(());
                }
                KeyCode::Up => {
                    self.state.select_prev_suggestion();
                    return Ok(());
                }
                KeyCode::Down => {
                    self.state.select_next_suggestion();
                    return Ok(());
                }
                KeyCode::Esc => {
                    self.state.hide_autocomplete();
                    return Ok(());
                }
                _ => {
                    // Continue with normal key handling, but update autocomplete
                }
            }
        }

        // Normal key handling
        match key_event.code {
            KeyCode::Char('c') if key_event.modifiers.contains(KeyModifiers::CONTROL) => {
                // Always allow Ctrl+C to quit immediately for better UX
                self.state.should_quit = true;
            }
            KeyCode::Char('q') if key_event.modifiers.contains(KeyModifiers::CONTROL) => {
                self.handle_quit_request();
            }
            KeyCode::Esc => {
                if self.state.show_autocomplete {
                    self.state.hide_autocomplete();
                } else {
                    self.handle_quit_request();
                }
            }
            KeyCode::Enter => {
                // Check for Shift+Enter to insert newline
                if key_event.modifiers.contains(KeyModifiers::SHIFT) {
                    // Shift+Enter inserts a new line
                    self.state.insert_newline();
                    self.state.update_autocomplete();
                } else {
                    // Regular Enter submits the task
                    if !self.state.get_input_text().trim().is_empty() {
                        let task = self.state.get_input_text();
                        // Add command to history before clearing input
                        self.state.add_to_history(task.clone());
                        self.state.clear_input();
                        self.state.hide_autocomplete();
                        self.handle_task(task).await?;
                    }
                }
            }
            KeyCode::Char(c) => {
                // Reset history navigation when user types
                self.state.reset_history_navigation();
                
                // Handle special key combinations
                if key_event.modifiers.contains(KeyModifiers::CONTROL) {
                    match c {
                        'a' => self.state.move_cursor_to_line_start(),
                        'e' => self.state.move_cursor_to_line_end(),
                        'h' => self.state.toggle_step_history_view(),
                        'u' => {
                            // Ctrl+U: Scroll up (alternative scroll-up binding)
                            if !self.state.show_autocomplete {
                                self.state.scroll_page_up(5);
                            }
                        },
                        'd' => {
                            // Ctrl+D: Scroll down (alternative scroll-down binding)
                            if !self.state.show_autocomplete {
                                self.state.scroll_page_down(5);
                            }
                        },
                        'k' => {
                            // Ctrl+K: Scroll up one line (vim-like)
                            if !self.state.show_autocomplete {
                                self.state.scroll_up();
                            }
                        },
                        'j' => {
                            // Ctrl+J: Scroll down one line (vim-like)
                            if !self.state.show_autocomplete {
                                self.state.scroll_down();
                            }
                        },
                        _ => {
                            self.state.insert_char(c);
                            self.state.update_autocomplete();
                        }
                    }
                } else {
                    self.state.insert_char(c);
                    self.state.update_autocomplete();
                }
            }
            KeyCode::Backspace => {
                // Reset history navigation when user edits
                self.state.reset_history_navigation();
                self.state.delete_char();
                self.state.update_autocomplete();
            }
            KeyCode::Left => {
                self.state.move_cursor_left();
            }
            KeyCode::Right => {
                self.state.move_cursor_right();
            }
            KeyCode::Up => {
                if self.state.show_autocomplete {
                    self.state.select_prev_suggestion();
                } else if key_event.modifiers.contains(KeyModifiers::CONTROL) {
                    // Ctrl+Up: Jump to first (oldest) command in history
                    self.state.history_jump_to_first();
                } else if key_event.modifiers.contains(KeyModifiers::SHIFT) {
                    // Shift+Up: Scroll output up (enhanced scroll-up functionality)
                    self.state.scroll_up();
                } else {
                    // Regular Up: Navigate to previous command in history
                    self.state.history_previous();
                }
            }
            KeyCode::Down => {
                if self.state.show_autocomplete {
                    self.state.select_next_suggestion();
                } else if key_event.modifiers.contains(KeyModifiers::CONTROL) {
                    // Ctrl+Down: Jump to last (newest) command in history
                    self.state.history_jump_to_last();
                } else if key_event.modifiers.contains(KeyModifiers::SHIFT) {
                    // Shift+Down: Scroll output down (enhanced scroll-down functionality)
                    self.state.scroll_down();
                } else {
                    // Regular Down: Navigate to next command in history
                    self.state.history_next();
                }
            }
            KeyCode::PageUp => {
                if !self.state.show_autocomplete {
                    // Use a heuristic page size; layout height is unavailable here, so use 10
                    self.state.scroll_page_up(10);
                }
            }
            KeyCode::PageDown => {
                if !self.state.show_autocomplete {
                    self.state.scroll_page_down(10);
                }
            }
            KeyCode::Home => {
                if key_event.modifiers.contains(KeyModifiers::CONTROL) {
                    // Ctrl+Home: scroll output to top
                    if !self.state.show_autocomplete {
                        self.state.scroll_to_top();
                    }
                } else {
                    // Home: move cursor to line start
                    self.state.move_cursor_to_line_start();
                }
            }
            KeyCode::End => {
                if key_event.modifiers.contains(KeyModifiers::CONTROL) {
                    // Ctrl+End: scroll output to bottom
                    if !self.state.show_autocomplete {
                        self.state.scroll_to_bottom();
                    }
                } else {
                    // End: move cursor to line end
                    self.state.move_cursor_to_line_end();
                }
            }
            KeyCode::Tab => {
                if self.state.show_autocomplete {
                    self.state.apply_selected_suggestion();
                }
            }
            _ => {}
        }

        Ok(())
    }

    fn handle_quit_request(&mut self) {
        if self.state.is_task_running() {
            self.state.show_quit_confirmation();
        } else {
            self.state.should_quit = true;
        }
    }

    async fn handle_quit_popup_key(&mut self, key_event: crossterm::event::KeyEvent) -> Result<()> {
        match key_event.code {
            KeyCode::Char('y') | KeyCode::Char('Y') => {
                self.state.confirm_quit();
            }
            KeyCode::Char('n') | KeyCode::Char('N') | KeyCode::Esc => {
                self.state.hide_quit_confirmation();
            }
            KeyCode::Enter => {
                // Default to not quitting
                self.state.hide_quit_confirmation();
            }
            _ => {}
        }
        Ok(())
    }

    async fn handle_settings_popup_key(
        &mut self,
        key_event: crossterm::event::KeyEvent,
    ) -> Result<()> {
        if let Some(ref mut editor) = self.settings_editor {
            match key_event.code {
                KeyCode::Esc => {
                    if editor.editing_field.is_some() {
                        // Cancel editing if in edit mode
                        editor.cancel_editing();
                    } else {
                        // Close popup if not editing
                        self.state.hide_settings_popup();
                        self.settings_editor = None;
                    }
                }
                KeyCode::Enter => {
                    if editor.editing_field.is_some() {
                        // Confirm editing
                        if let Err(e) = editor.confirm_editing() {
                            eprintln!("Failed to update field: {}", e);
                        }
                    } else {
                        // Start editing the selected field
                        editor.start_editing(editor.selected_field);
                    }
                }
                KeyCode::Char('s') if editor.editing_field.is_none() => {
                    // Save settings and update app configuration
                    let new_settings = editor.get_settings();
                    if let Err(e) = new_settings.save() {
                        eprintln!("Failed to save settings: {}", e);
                    } else {
                        // Update app configuration
                        self.settings = new_settings.clone();
                        self.workspace = new_settings.workspace.clone();

                        // Recreate model config with new settings
                        let api_key = new_settings.get_api_key().unwrap_or_default();
                        let base_url = new_settings.get_base_url();

                        let mut model_provider =
                            ModelProvider::new(new_settings.provider.clone()).with_api_key(api_key);

                        if let Some(url) = base_url {
                            model_provider = model_provider.with_base_url(url);
                        }

                        self.model_config =
                            ModelConfig::new(new_settings.model.clone(), model_provider)
                                .with_max_tokens(MAX_TOKEN)
                                .with_temperature(TEMPERATURE);

                        // Reset agent to use new configuration
                        self.agent = None;
                    }

                    self.state.hide_settings_popup();
                    self.settings_editor = None;
                }
                KeyCode::Tab if editor.editing_field.is_none() => {
                    editor.next_field();
                }
                KeyCode::BackTab if editor.editing_field.is_none() => {
                    editor.prev_field();
                }
                KeyCode::Up if editor.editing_field.is_none() => {
                    editor.prev_field();
                }
                KeyCode::Down if editor.editing_field.is_none() => {
                    editor.next_field();
                }
                KeyCode::Backspace if editor.editing_field.is_some() => {
                    editor.delete_char();
                }
                KeyCode::Char(c) if editor.editing_field.is_some() => {
                    editor.insert_char(c);
                }
                _ => {}
            }
        }
        Ok(())
    }

    async fn handle_popup_input_key(&mut self, key_event: crossterm::event::KeyEvent) -> Result<()> {
        match key_event.code {
            KeyCode::Esc => {
                self.state.hide_popup_input();
            }
            KeyCode::Enter if key_event.modifiers.contains(KeyModifiers::SHIFT) => {
                // Shift+Enter adds a new line
                self.popup_input_editor.insert_char('\n');
            }
            KeyCode::Enter => {
                // Regular Enter submits the input
                let content = self.popup_input_editor.get_text();
                self.state.input.set_text(content);
                self.state.hide_popup_input();
            }
            KeyCode::Backspace => {
                self.popup_input_editor.delete_char();
            }
            KeyCode::Left => {
                self.popup_input_editor.move_cursor_left();
            }
            KeyCode::Right => {
                self.popup_input_editor.move_cursor_right();
            }
            KeyCode::Up => {
                self.popup_input_editor.move_cursor_up();
            }
            KeyCode::Down => {
                self.popup_input_editor.move_cursor_down();
            }
            KeyCode::Home => {
                self.popup_input_editor.move_cursor_to_line_start();
            }
            KeyCode::End => {
                self.popup_input_editor.move_cursor_to_line_end();
            }
            KeyCode::Char(c) => {
                self.popup_input_editor.insert_char(c);
            }
            _ => {}
        }
        Ok(())
    }

    async fn handle_review_history_key(
        &mut self,
        key_event: crossterm::event::KeyEvent,
    ) -> Result<()> {
        match key_event.code {
            KeyCode::Esc => {
                self.show_review_history = false;
            }
            KeyCode::Char('r') | KeyCode::Char('R') => {
                if let Err(e) = self.review_history.load_records() {
                    self.state.add_output_line_styled(Line::from(vec![
                        Span::styled("❌ ", Style::default().fg(Color::Red)),
                        Span::styled("Failed to refresh review history: ", Style::default().fg(Color::Red)),
                        Span::styled(e.to_string(), Style::default().fg(Color::Yellow)),
                    ]));
                }
            }
            _ => {
                self.review_history.handle_navigation(key_event.code);
            }
        }
        Ok(())
    }

    async fn handle_step_history_key(
        &mut self,
        key_event: crossterm::event::KeyEvent,
    ) -> Result<()> {
        match key_event.code {
            KeyCode::Esc | KeyCode::Char('h') if key_event.modifiers.contains(KeyModifiers::CONTROL) => {
                self.state.toggle_step_history_view();
            }
            KeyCode::Up => {
                if key_event.modifiers.contains(KeyModifiers::CONTROL) {
                    // Ctrl+Up: Scroll content up within current step
                    self.state.scroll_step_content_up();
                } else {
                    // Up: Navigate to previous step
                    self.state.navigate_step_history_previous();
                }
            }
            KeyCode::Down => {
                if key_event.modifiers.contains(KeyModifiers::CONTROL) {
                     // Ctrl+Down: Scroll content down within current step
                     self.state.scroll_step_content_down(20); // Use reasonable page size
                 } else {
                    // Down: Navigate to next step
                    self.state.navigate_step_history_next();
                }
            }
            KeyCode::Home => {
                if key_event.modifiers.contains(KeyModifiers::CONTROL) {
                    // Ctrl+Home: Go to first step
                    self.state.navigate_step_history_first();
                } else {
                    // Home: Scroll to top of current step content
                    self.state.step_content_scroll = 0;
                }
            }
            KeyCode::End => {
                if key_event.modifiers.contains(KeyModifiers::CONTROL) {
                    // Ctrl+End: Go to last step
                    self.state.navigate_step_history_last();
                } else {
                    // End: Scroll to bottom of current step content
                    if let Some(step) = self.state.get_current_viewed_step() {
                        let max_scroll = step.output_lines.len().saturating_sub(1);
                        self.state.step_content_scroll = max_scroll;
                    }
                }
            }
            KeyCode::PageUp => {
                // Page Up: Navigate to previous step (same as Up for now)
                self.state.navigate_step_history_previous();
            }
            KeyCode::PageDown => {
                // Page Down: Navigate to next step (same as Down for now)
                self.state.navigate_step_history_next();
            }
            _ => {}
        }
        Ok(())
    }

    async fn handle_task(&mut self, task: String) -> Result<()> {
        // Check for special commands first (before showing "Running task")
        if task.trim() == "/help" {
            self.show_help();
            return Ok(());
        }

        if task.trim() == "/quit" || task.trim() == "/exit" {
            self.state.should_quit = true;
            return Ok(());
        }

        if task.trim() == "/settings" {
            self.state.show_settings_popup();
            self.settings_editor = Some(SettingsEditor::new(self.settings.clone()));
            return Ok(());
        }

        if task.trim() == "/input" || task.trim() == "/popup" {
            self.state.show_popup_input();
            self.popup_input_editor.activate(Some(self.state.get_input_text()));
            return Ok(());
        }

        if task.trim() == "/review" || task.trim() == "/reviews" {
            self.show_review_history = true;
            if let Err(e) = self.review_history.load_records() {
                self.state.add_output_line_styled(Line::from(vec![
                    Span::styled("❌ ", Style::default().fg(Color::Red)),
                    Span::styled("Failed to load review history: ", Style::default().fg(Color::Red)),
                    Span::styled(e.to_string(), Style::default().fg(Color::Yellow)),
                ]));
            }
            return Ok(());
        }

        // Check for unsupported commands starting with "/"
        if task.trim().starts_with('/') {
            let command = task.trim().to_string();
            self.state.add_output_line_styled(Line::from(vec![
                Span::styled("❌ ", Style::default().fg(Color::Red)),
                Span::styled("Unknown command: ", Style::default().fg(Color::Red)),
                Span::styled(
                    command,
                    Style::default()
                        .fg(Color::Yellow)
                        .add_modifier(ratatui::style::Modifier::BOLD),
                ),
            ]));

            self.state.add_output_line_styled(Line::from(vec![
                Span::styled("💡 ", Style::default().fg(Color::Yellow)),
                Span::styled("Available commands: ", Style::default().fg(Color::Gray)),
                Span::styled("/help", Style::default().fg(Color::Green)),
                Span::styled(", ", Style::default().fg(Color::Gray)),
                Span::styled("/settings", Style::default().fg(Color::Green)),
                Span::styled(", ", Style::default().fg(Color::Gray)),
                Span::styled("/review", Style::default().fg(Color::Green)),
                Span::styled(", ", Style::default().fg(Color::Gray)),
                Span::styled("/quit", Style::default().fg(Color::Red)),
                Span::styled(", ", Style::default().fg(Color::Gray)),
                Span::styled("/exit", Style::default().fg(Color::Red)),
            ]));
            return Ok(());
        }

        // Add task to output with styling (only for actual tasks)
        self.state.add_output_line_styled(Line::from(vec![
            Span::styled("🚀 ", Style::default().fg(Color::Yellow)),
            Span::styled("Running task: ", Style::default().fg(Color::Cyan)),
            Span::styled(
                task.clone(),
                Style::default()
                    .fg(Color::White)
                    .add_modifier(ratatui::style::Modifier::BOLD),
            ),
        ]));
        self.state.agent_status = AgentStatus::Running;

        // Create agent if not exists
        if self.agent.is_none() {
            match self.create_agent().await {
                Ok(agent) => {
                    self.agent = Some(Arc::new(Mutex::new(agent)));
                }
                Err(e) => {
                    self.state
                        .add_output_line(format!("❌ Failed to create agent: {}", e));
                    self.state.agent_status = AgentStatus::Error(e.to_string());
                    return Ok(());
                }
            }
        }

        // Run the task
        if self.agent.is_some() {
            self.run_agent_task(task).await?;
        }

        Ok(())
    }

    async fn create_agent(&self) -> Result<TraeAgent> {
        let llm_client = LLMClient::new(self.model_config.clone())?;

        let base_agent = BaseAgent::new(
            "".to_string(), // Empty task initially
            AgentExecution::new("".to_string(), None),
            llm_client,
            10, // max_step
            self.model_config.clone(),
            None, // tools will be set in new_task
            vec![],
        );
        // Create proper trajectory file path
        let trajectory_path = self.workspace.join("trajectory.json");
        Ok(TraeAgent::new(
            base_agent,
            Some(trajectory_path.to_string_lossy().to_string()),
        ))
    }

    async fn run_agent_task(&mut self, task: String) -> Result<()> {
        // Update status to show we're starting
        self.state.agent_status = AgentStatus::Thinking;

        // Setup task arguments
        let mut args = HashMap::new();
        args.insert(
            "project_path".to_string(),
            self.workspace.to_string_lossy().to_string(),
        );
        args.insert("issue".to_string(), task.clone());

        // Get agent reference
        let agent_arc = self.agent.as_ref().expect("agent missing").clone();

        // Initialize the task (do this in a separate scope to release the lock quickly)
        let init_result = {
            let mut agent = agent_arc.lock().await;
            agent.new_task(task.clone(), Some(args), None)
        };

        match init_result {
            Ok(_) => {
                self.state.add_output_line_styled(Line::from(vec![
                    Span::styled("✅ ", Style::default().fg(Color::Green)),
                    Span::styled(
                        "Task initialized successfully",
                        Style::default().fg(Color::Green),
                    ),
                ]));
            }
            Err(e) => {
                self.state.add_output_line_styled(Line::from(vec![
                    Span::styled("❌ ", Style::default().fg(Color::Red)),
                    Span::styled(
                        "Failed to initialize task: ",
                        Style::default().fg(Color::Red),
                    ),
                    Span::styled(format!("{:?}", e), Style::default().fg(Color::White)),
                ]));
                self.state.agent_status = AgentStatus::Error(format!("{:?}", e));
                return Ok(());
            }
        }

        // Create a channel for agent updates
        let (agent_update_sender, mut agent_update_receiver) =
            tokio::sync::mpsc::unbounded_channel::<AgentUpdate>();

        // Set up the agent with the update sender (in a separate scope)
        {
            let mut agent_guard = agent_arc.lock().await;
            agent_guard.set_update_sender(agent_update_sender);
        }

        // Update status to running
        self.state.agent_status = AgentStatus::Running;

        // Get event sender
        let event_sender = self.event_handler.sender().clone();

        // Spawn task to handle agent updates
        let event_sender_clone = event_sender.clone();
        tokio::spawn(async move {
            while let Some(update) = agent_update_receiver.recv().await {
                let event = match update {
                    AgentUpdate::StatusUpdate(_status) => {
                        Event::AgentStatusUpdate(AgentStatus::CallingTool) // Map status appropriately
                    }
                    AgentUpdate::Output(output) => Event::AgentOutput(output),
                    AgentUpdate::TokenUsage { input, output } => {
                        Event::TokenUsageUpdate(crate::tui::state::TokenUsage { input, output })
                    }
                    AgentUpdate::StepUpdate { step, description } => {
                        Event::AgentStepUpdate { step, description }
                    }
                    AgentUpdate::Error(error) => Event::AgentError(error),
                    AgentUpdate::TaskCompleted(summary) => Event::TaskCompleted(summary),
                };
                let _ = event_sender_clone.send(event);
            }
        });

        // Run the agent in the background
        tokio::spawn({
            let agent_arc = agent_arc.clone();
            let event_sender = event_sender.clone();
            async move {
                // Send initial status update
                let _ = event_sender.send(Event::AgentStatusUpdate(AgentStatus::Running));

                // Run the agent
                let result = {
                    let mut agent_guard = agent_arc.lock().await;
                    agent_guard.run().await
                };

                // Handle completion or error
                match result {
                    Ok(_) => {
                        let _ = event_sender.send(Event::TaskCompleted(
                            "Task completed successfully".to_string(),
                        ));
                    }
                    Err(e) => {
                        let _ = event_sender
                            .send(Event::AgentError(format!("Agent execution failed: {}", e)));
                    }
                }

                // Send final token usage (TODO: implement proper LLM usage tracking)
                let _ = event_sender.send(Event::TokenUsageUpdate(crate::tui::state::TokenUsage {
                    input: 100,
                    output: 50,
                }));
            }
        });

        Ok(())
    }

    fn show_help(&mut self) {
        // Add styled help content
        self.state.add_output_line_styled(Line::from(""));

        self.state.add_output_line_styled(Line::from(vec![
            Span::styled("🆘 ", Style::default().fg(Color::Yellow)),
            Span::styled(
                "Trae Agent Help",
                Style::default()
                    .fg(Color::Cyan)
                    .add_modifier(ratatui::style::Modifier::BOLD),
            ),
        ]));

        self.state.add_output_line_styled(Line::from(""));

        self.state.add_output_line_styled(Line::from(Span::styled(
            "Commands:",
            Style::default()
                .fg(Color::Green)
                .add_modifier(ratatui::style::Modifier::BOLD),
        )));

        self.state.add_output_line_styled(Line::from(vec![
            Span::styled("  ", Style::default()),
            Span::styled("/help", Style::default().fg(Color::Yellow)),
            Span::styled(
                " - Show this help message",
                Style::default().fg(Color::Gray),
            ),
        ]));

        self.state.add_output_line_styled(Line::from(vec![
            Span::styled("  ", Style::default()),
            Span::styled("/settings", Style::default().fg(Color::Green)),
            Span::styled(
                " - Configure API key, base URL, and workspace",
                Style::default().fg(Color::Gray),
            ),
        ]));

        self.state.add_output_line_styled(Line::from(vec![
            Span::styled("  ", Style::default()),
            Span::styled("/input", Style::default().fg(Color::Magenta)),
            Span::styled(" or ", Style::default().fg(Color::Gray)),
            Span::styled("/popup", Style::default().fg(Color::Magenta)),
            Span::styled(
                " - Open popup multi-line input editor",
                Style::default().fg(Color::Gray),
            ),
        ]));

        self.state.add_output_line_styled(Line::from(vec![
            Span::styled("  ", Style::default()),
            Span::styled("/review", Style::default().fg(Color::Cyan)),
            Span::styled(
                " - View review history records",
                Style::default().fg(Color::Gray),
            ),
        ]));

        self.state.add_output_line_styled(Line::from(vec![
            Span::styled("  ", Style::default()),
            Span::styled("/test-scroll", Style::default().fg(Color::Cyan)),
            Span::styled(
                " - Generate test content to test scrolling",
                Style::default().fg(Color::Gray),
            ),
        ]));

        self.state.add_output_line_styled(Line::from(vec![
            Span::styled("  ", Style::default()),
            Span::styled("/quit", Style::default().fg(Color::Red)),
            Span::styled(" or ", Style::default().fg(Color::Gray)),
            Span::styled("/exit", Style::default().fg(Color::Red)),
            Span::styled(" - Exit the application", Style::default().fg(Color::Gray)),
        ]));
        self.state.add_output_line_styled(Line::from(""));

        self.state.add_output_line_styled(Line::from(Span::styled(
            "Keyboard shortcuts:",
            Style::default()
                .fg(Color::Blue)
                .add_modifier(ratatui::style::Modifier::BOLD),
        )));
        let shortcuts = [
            ("Enter", "Execute the current task"),
            ("Ctrl+C, Ctrl+Q, Esc", "Quit the application"),
            ("↑/↓", "Scroll through output"),
            ("←/→", "Move cursor in input field"),
            ("Backspace", "Delete character"),
        ];
        for (key, desc) in shortcuts {
            self.state.add_output_line_styled(Line::from(vec![
                Span::styled("  ", Style::default()),
                Span::styled(key, Style::default().fg(Color::Yellow)),
                Span::styled(" - ", Style::default().fg(Color::Gray)),
                Span::styled(desc, Style::default().fg(Color::Gray)),
            ]));
        }

        self.state.add_output_line_styled(Line::from(""));

        self.state.add_output_line_styled(Line::from(Span::styled(
            "Usage:",
            Style::default()
                .fg(Color::Magenta)
                .add_modifier(ratatui::style::Modifier::BOLD),
        )));

        self.state.add_output_line_styled(Line::from(vec![
            Span::styled(
                "  Type your coding task in the input field and press ",
                Style::default().fg(Color::Gray),
            ),
            Span::styled("Enter", Style::default().fg(Color::Yellow)),
            Span::styled(".", Style::default().fg(Color::Gray)),
        ]));

        self.state.add_output_line_styled(Line::from(Span::styled(
            "  The agent will analyze your request and execute appropriate actions.",
            Style::default().fg(Color::Gray),
        )));

        self.state.add_output_line_styled(Line::from(""));
    }
}
