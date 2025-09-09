// Copyright (c) 2025 ByteDance Ltd. and/or its affiliates
// SPDX-License-Identifier: MIT

use std::collections::VecDeque;

#[derive(Debug, Clone, Default)]
pub struct TokenUsage {
    pub input_tokens: u64,
    pub output_tokens: u64,
    pub total_tokens: u64,
}


#[derive(Debug, Clone, PartialEq)]
pub enum AgentStatus {
    Idle,
    Running,
    Thinking,
    CallingTool,
    Reflecting,
    Completed,
    Error(String),
}

impl Default for AgentStatus {
    fn default() -> Self {
        Self::Idle
    }
}

impl AgentStatus {
    pub fn display(&self) -> String {
        match self {
            AgentStatus::Idle => "Idle".to_string(),
            AgentStatus::Running => "Running".to_string(),
            AgentStatus::Thinking => "Thinking".to_string(),
            AgentStatus::CallingTool => "Calling Tool".to_string(),
            AgentStatus::Reflecting => "Reflecting".to_string(),
            AgentStatus::Completed => "Completed".to_string(),
            AgentStatus::Error(msg) => format!("Error: {}", msg),
        }
    }

    pub fn color(&self) -> ratatui::style::Color {
        use ratatui::style::Color;
        match self {
            AgentStatus::Idle => Color::Gray,
            AgentStatus::Running => Color::Blue,
            AgentStatus::Thinking => Color::Yellow,
            AgentStatus::CallingTool => Color::Cyan,
            AgentStatus::Reflecting => Color::Magenta,
            AgentStatus::Completed => Color::Green,
            AgentStatus::Error(_) => Color::Red,
        }
    }
}

#[derive(Debug)]
pub struct AppState {
    /// Current agent status
    pub agent_status: AgentStatus,
    
    /// Token usage statistics
    pub token_usage: TokenUsage,
    
    /// Agent output lines (main display area)
    pub output_lines: VecDeque<String>,
    
    /// Current input text
    pub input_text: String,
    
    /// Input cursor position
    pub input_cursor: usize,
    
    /// Whether the app should quit
    pub should_quit: bool,
    
    /// Scroll position for output
    pub output_scroll: usize,
    
    /// Maximum lines to keep in output buffer
    pub max_output_lines: usize,
}

impl Default for AppState {
    fn default() -> Self {
        Self {
            agent_status: AgentStatus::default(),
            token_usage: TokenUsage::default(),
            output_lines: VecDeque::new(),
            input_text: String::new(),
            input_cursor: 0,
            should_quit: false,
            output_scroll: 0,
            max_output_lines: 1000,
        }
    }
}

impl AppState {
    pub fn new() -> Self {
        let mut state = Self::default();
        
        // Add welcome message
        state.add_welcome_message();
        
        state
    }
    
    pub fn add_welcome_message(&mut self) {
        let welcome_lines = vec![
            "████████┐██████┐  █████┐ ███████┐    █████┐  ██████┐ ███████┐███┐  ██┐████████┐".to_string(),
            "└──██┌──┘██┌──██┐██┌──██┐██┌────┘   ██┌──██┐██┌────┘ ██┌────┘████┐ ██│└──██┌──┘".to_string(),
            "   ██│   ██████┌┘███████│█████┐     ███████│██│  ██┐ █████┐  ██┌██┐██│   ██│   ".to_string(),
            "   ██│   ██┌──██┐██┌──██│██┌──┘     ██┌──██│██│  └██┐██┌──┘  ██│└████│   ██│   ".to_string(),
            "   ██│   ██│  ██│██│  ██│███████┐   ██│  ██│└██████┌┘███████┐██│ └███│   ██│   ".to_string(),
            "   └─┘   └─┘  └─┘└─┘  └─┘└──────┘   └─┘  └─┘ └─────┘ └──────┘└─┘  └──┘   └─┘   ".to_string(),
            "".to_string(),
            "🤖 Trae Agent - Intelligent coding assistant".to_string(),
            "💡 Version: 0.1.0".to_string(),
            "".to_string(),
            "Welcome to Trae Agent interactive mode!".to_string(),
            "Type your task below and press Enter to start.".to_string(),
            "".to_string(),
        ];
        
        for line in welcome_lines {
            self.add_output_line(line);
        }
    }
    
    pub fn add_output_line(&mut self, line: String) {
        self.output_lines.push_back(line);
        
        // Limit buffer size
        while self.output_lines.len() > self.max_output_lines {
            self.output_lines.pop_front();
        }
        
        // Auto-scroll to bottom
        self.output_scroll = self.output_lines.len().saturating_sub(1);
    }
    
    pub fn clear_input(&mut self) {
        self.input_text.clear();
        self.input_cursor = 0;
    }
    
    pub fn insert_char(&mut self, c: char) {
        self.input_text.insert(self.input_cursor, c);
        self.input_cursor += 1;
    }
    
    pub fn delete_char(&mut self) {
        if self.input_cursor > 0 {
            self.input_cursor -= 1;
            self.input_text.remove(self.input_cursor);
        }
    }
    
    pub fn move_cursor_left(&mut self) {
        if self.input_cursor > 0 {
            self.input_cursor -= 1;
        }
    }
    
    pub fn move_cursor_right(&mut self) {
        if self.input_cursor < self.input_text.len() {
            self.input_cursor += 1;
        }
    }
    
    pub fn scroll_up(&mut self) {
        if self.output_scroll > 0 {
            self.output_scroll -= 1;
        }
    }
    
    pub fn scroll_down(&mut self) {
        if self.output_scroll < self.output_lines.len().saturating_sub(1) {
            self.output_scroll += 1;
        }
    }
    
    pub fn update_token_usage(&mut self, input_tokens: u64, output_tokens: u64) {
        self.token_usage.input_tokens += input_tokens;
        self.token_usage.output_tokens += output_tokens;
        self.token_usage.total_tokens = self.token_usage.input_tokens + self.token_usage.output_tokens;
    }
}
