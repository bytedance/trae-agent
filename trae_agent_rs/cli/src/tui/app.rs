// Copyright (c) 2025 ByteDance Ltd. and/or its affiliates
// SPDX-License-Identifier: MIT

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
use tokio::sync::Mutex;
use std::{collections::HashMap, io, path::PathBuf};
use trae_core::{
    agent::base_agent::{Agent, AgentExecution, BaseAgent}, config::{ModelConfig, ModelProvider}, llm::LLMClient, trae::{TraeAgent, AgentUpdate}
};
use std::sync::Arc;
use super::{
    event::{Event, EventHandler},
    layout::Layout,
    state::{AgentStatus, AppState},
};

const MAX_TOKEN: u32 = 4096; 
const TEMPERATURE: f32 = 0.1;

pub struct App {
    state: AppState,
    event_handler: EventHandler,
    agent: Option<Arc<tokio::sync::Mutex<TraeAgent>>>,
    model_config: ModelConfig,
    workspace: PathBuf,
}

impl App {
    pub fn new(provider: String, model: String, workspace: PathBuf) -> Result<Self> {
        // Create model configuration
        let api_key = match provider.as_str() {
            "openai" => std::env::var("OPENAI_API_KEY")
                .or_else(|_| std::env::var("API_KEY"))
                .unwrap_or_default(),
            "anthropic" => std::env::var("ANTHROPIC_API_KEY").unwrap_or_default(),
            "azure" => std::env::var("AZURE_API_KEY").unwrap_or_default(),
            _ => {
                return Err(anyhow::anyhow!(
                    "Unknown provider: {}. Supported providers: openai, anthropic, azure",
                    provider
                ));
            }
        };

        let base_url = match provider.as_str() {
            "openai" => Some("https://api.openai.com/v1".to_string()),
            "anthropic" => Some("https://api.anthropic.com".to_string()),
            "azure" => std::env::var("AZURE_BASE_URL").ok(),
            _ => None,
        };

        let mut model_provider = ModelProvider::new(provider.clone())
                .with_api_key(api_key);

        model_provider.base_url = base_url.clone();

        let model_config = ModelConfig::new(model, model_provider)
            .with_max_tokens(MAX_TOKEN)
            .with_temperature(TEMPERATURE);

        Ok(Self {
            state: AppState::new(),
            event_handler: EventHandler::new(),
            agent: None,
            model_config,
            workspace,
        })
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

        // Restore terminal
        disable_raw_mode()?;
        execute!(
            terminal.backend_mut(),
            LeaveAlternateScreen,
            DisableMouseCapture
        )?;
        terminal.show_cursor()?;

        result
    }

    async fn run_app<B: Backend>(&mut self, terminal: &mut Terminal<B>) -> Result<()> {
        loop {
            // Draw the UI
            terminal.draw(|frame| {
                Layout::render(frame, &self.state);
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
                        self.state.add_output_line(output);
                    }
                    Event::AgentStatusUpdate(status) => {
                        self.state.agent_status = status;
                    }
                    Event::TokenUsageUpdate(token_usage) => {
                        self.state.token_usage = token_usage;
                    }
                    Event::AgentStepUpdate { step, description } => {
                        self.state.add_output_line(format!("Step {}: {}", step, description));
                    }
                    Event::AgentError(error) => {
                        self.state.add_output_line(format!("Error: {}", error));
                        self.state.agent_status = AgentStatus::Error(error);
                    }
                    Event::TaskCompleted(summary) => {
                        self.state.add_output_line(format!("Task completed: {}", summary));
                        self.state.agent_status = AgentStatus::Idle;
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
                if !self.state.input_text.trim().is_empty() {
                    let task = self.state.input_text.clone();
                    self.state.clear_input();
                    self.state.hide_autocomplete();
                    self.handle_task(task).await?;
                }
            }
            KeyCode::Char(c) => {
                self.state.insert_char(c);
                self.state.update_autocomplete();
            }
            KeyCode::Backspace => {
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
                if !self.state.show_autocomplete {
                    self.state.scroll_up();
                }
            }
            KeyCode::Down => {
                if !self.state.show_autocomplete {
                    self.state.scroll_down();
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
        Ok(TraeAgent::new(
            base_agent,
            Some(self.workspace.to_string_lossy().to_string()),
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
        let (agent_update_sender, mut agent_update_receiver) = tokio::sync::mpsc::unbounded_channel::<AgentUpdate>();
        
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
                        let _ = event_sender.send(Event::TaskCompleted("Task completed successfully".to_string()));
                    }
                    Err(e) => {
                        let _ = event_sender.send(Event::AgentError(format!("Agent execution failed: {}", e)));
                    }
                }

                // Send final token usage (TODO: implement proper LLM usage tracking)
                let _ = event_sender.send(Event::TokenUsageUpdate(crate::tui::state::TokenUsage { input: 100, output: 50 }));
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


