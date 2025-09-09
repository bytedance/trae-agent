// Copyright (c) 2025 ByteDance Ltd. and/or its affiliates
// SPDX-License-Identifier: MIT

use anyhow::Result;
use crossterm::{
    event::{DisableMouseCapture, EnableMouseCapture, KeyCode, KeyModifiers},
    execute,
    terminal::{disable_raw_mode, enable_raw_mode, EnterAlternateScreen, LeaveAlternateScreen},
};
use ratatui::{
    backend::{Backend, CrosstermBackend},
    Terminal,
};
use std::{collections::HashMap, io, path::PathBuf};
use trae_core::{
    agent::base_agent::{Agent, AgentExecution, BaseAgent},
    config::{ModelConfig, ModelProvider},
    llm::LLMClient,
    trae::TraeAgent,
};

use super::{
    event::{Event, EventHandler},
    layout::Layout,
    state::{AgentStatus, AppState},
};

pub struct App {
    state: AppState,
    event_handler: EventHandler,
    agent: Option<TraeAgent>,
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

        let model_provider = ModelProvider::new(provider.clone()).with_api_key(api_key);

        let model_provider = if let Some(url) = base_url {
            model_provider.with_base_url(url)
        } else {
            model_provider
        };

        let model_config = ModelConfig::new(model, model_provider)
            .with_max_tokens(4096)
            .with_temperature(0.1);

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

        // Start event loop
        self.event_handler.start_event_loop().await;

        // Main application loop
        let result = self.run_app(&mut terminal).await;

        // Cleanup terminal
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
                    Event::TokenUsageUpdate { input, output } => {
                        self.state.update_token_usage(input, output);
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
        match key_event.code {
            KeyCode::Char('c') if key_event.modifiers.contains(KeyModifiers::CONTROL) => {
                self.state.should_quit = true;
            }
            KeyCode::Char('q') if key_event.modifiers.contains(KeyModifiers::CONTROL) => {
                self.state.should_quit = true;
            }
            KeyCode::Esc => {
                self.state.should_quit = true;
            }
            KeyCode::Enter => {
                if !self.state.input_text.trim().is_empty() {
                    let task = self.state.input_text.clone();
                    self.state.clear_input();
                    self.handle_task(task).await?;
                }
            }
            KeyCode::Char(c) => {
                self.state.insert_char(c);
            }
            KeyCode::Backspace => {
                self.state.delete_char();
            }
            KeyCode::Left => {
                self.state.move_cursor_left();
            }
            KeyCode::Right => {
                self.state.move_cursor_right();
            }
            KeyCode::Up => {
                self.state.scroll_up();
            }
            KeyCode::Down => {
                self.state.scroll_down();
            }
            _ => {}
        }

        Ok(())
    }

    async fn handle_task(&mut self, task: String) -> Result<()> {
        // Add task to output
        self.state.add_output_line(format!("🚀 Running task: {}", task));
        self.state.agent_status = AgentStatus::Running;

        // Check for special commands
        if task.trim() == "/help" {
            self.show_help();
            return Ok(());
        }

        if task.trim() == "/quit" || task.trim() == "/exit" {
            self.state.should_quit = true;
            return Ok(());
        }

        // Create agent if not exists
        if self.agent.is_none() {
            match self.create_agent().await {
                Ok(agent) => {
                    self.agent = Some(agent);
                }
                Err(e) => {
                    self.state.add_output_line(format!("❌ Failed to create agent: {}", e));
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

        Ok(TraeAgent::new(base_agent, Some(self.workspace.to_string_lossy().to_string())))
    }

    async fn run_agent_task(&mut self, task: String) -> Result<()> {
        self.state.agent_status = AgentStatus::Thinking;

        // Setup task arguments
        let mut args = HashMap::new();
        args.insert("project_path".to_string(), self.workspace.to_string_lossy().to_string());
        args.insert("issue".to_string(), task.clone());

        // Initialize the task
        let agent = self.agent.as_mut().unwrap();
        match agent.new_task(task, Some(args), None) {
            Ok(_) => {
                self.state.add_output_line("✅ Task initialized successfully".to_string());
            }
            Err(e) => {
                self.state.add_output_line(format!("❌ Failed to initialize task: {:?}", e));
                self.state.agent_status = AgentStatus::Error(format!("{:?}", e));
                return Ok(());
            }
        }

        // Run the agent in the background
        let event_sender = self.event_handler.sender();
        
        tokio::spawn(async move {
            // Note: The actual agent execution would need to be implemented here
            // This is a placeholder for the agent execution logic
            
            let _ = event_sender.send(Event::AgentStatusUpdate(AgentStatus::CallingTool));
            let _ = event_sender.send(Event::AgentOutput("🔧 Agent is processing your request...".to_string()));
            
            // Simulate some processing time
            tokio::time::sleep(std::time::Duration::from_secs(2)).await;
            
            let _ = event_sender.send(Event::AgentOutput("💡 Task execution completed (placeholder)".to_string()));
            let _ = event_sender.send(Event::AgentStatusUpdate(AgentStatus::Completed));
            let _ = event_sender.send(Event::TokenUsageUpdate { input: 100, output: 50 });
        });

        Ok(())
    }

    fn show_help(&mut self) {
        let help_text = vec![
            "".to_string(),
            "🆘 Trae Agent Help".to_string(),
            "".to_string(),
            "Commands:".to_string(),
            "  /help - Show this help message".to_string(),
            "  /quit or /exit - Exit the application".to_string(),
            "".to_string(),
            "Keyboard shortcuts:".to_string(),
            "  Enter - Execute the current task".to_string(),
            "  Ctrl+C, Ctrl+Q, Esc - Quit the application".to_string(),
            "  ↑/↓ - Scroll through output".to_string(),
            "  ←/→ - Move cursor in input field".to_string(),
            "  Backspace - Delete character".to_string(),
            "".to_string(),
            "Usage:".to_string(),
            "  Type your coding task in the input field and press Enter.".to_string(),
            "  The agent will analyze your request and execute appropriate actions.".to_string(),
            "".to_string(),
        ];

        for line in help_text {
            self.state.add_output_line(line);
        }
    }
}
