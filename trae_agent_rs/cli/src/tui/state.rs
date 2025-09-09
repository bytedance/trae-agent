// Copyright (c) 2025 ByteDance Ltd. and/or its affiliates
// SPDX-License-Identifier: MIT

use std::collections::VecDeque;
use ratatui::{
    prelude::*,
    text::{Line, Span},
};

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
    pub output_lines: VecDeque<Line<'static>>,
    
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
    
    /// Whether to show quit confirmation popup
    pub show_quit_popup: bool,
    
    /// Auto-completion suggestions for commands
    pub autocomplete_suggestions: Vec<String>,
    
    /// Currently selected autocomplete suggestion index
    pub autocomplete_selected: usize,
    
    /// Whether autocomplete is visible
    pub show_autocomplete: bool,
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
            show_quit_popup: false,
            autocomplete_suggestions: Vec::new(),
            autocomplete_selected: 0,
            show_autocomplete: false,
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
        // Create colorful logo lines
        let logo_lines = Self::create_colored_logo();
        
        for line in logo_lines {
            self.output_lines.push_back(line);
        }
        
        // Add colored header
        self.add_output_line_styled(Line::from(vec![
            Span::styled("🤖 ", Style::default().fg(Color::Yellow)),
            Span::styled("Trae Agent", Style::default().fg(Color::Cyan).add_modifier(ratatui::style::Modifier::BOLD)),
            Span::styled(" - Intelligent coding assistant", Style::default().fg(Color::White)),
        ]));
        
        self.add_output_line_styled(Line::from(vec![
            Span::styled("💡 Version: ", Style::default().fg(Color::Yellow)),
            Span::styled("0.1.0", Style::default().fg(Color::Green).add_modifier(ratatui::style::Modifier::BOLD)),
        ]));
        
        self.add_output_line_styled(Line::from(""));
        
        self.add_output_line_styled(Line::from(vec![
            Span::styled("Welcome to ", Style::default().fg(Color::Gray)),
            Span::styled("Trae Agent", Style::default().fg(Color::Cyan).add_modifier(ratatui::style::Modifier::BOLD)),
            Span::styled(" interactive mode!", Style::default().fg(Color::Gray)),
        ]));
        
        self.add_output_line_styled(Line::from(
            Span::styled("Type your task below and press Enter to start.", Style::default().fg(Color::DarkGray).add_modifier(ratatui::style::Modifier::ITALIC))
        ));
        
        self.add_output_line_styled(Line::from(""));
    }
    
    fn create_colored_logo() -> Vec<Line<'static>> {
        let logo_raw = [
            "████████┐██████┐  █████┐ ███████┐    █████┐  ██████┐ ███████┐███┐  ██┐████████┐",
            "└──██┌──┘██┌──██┐██┌──██┐██┌────┘   ██┌──██┐██┌────┘ ██┌────┘████┐ ██│└──██┌──┘",
            "   ██│   ██████┌┘███████│█████┐     ███████│██│  ██┐ █████┐  ██┌██┐██│   ██│   ",
            "   ██│   ██┌──██┐██┌──██│██┌──┘     ██┌──██│██│  └██┐██┌──┘  ██│└████│   ██│   ",
            "   ██│   ██│  ██│██│  ██│███████┐   ██│  ██│└██████┌┘███████┐██│ └███│   ██│   ",
            "   └─┘   └─┘  └─┘└─┘  └─┘└──────┘   └─┘  └─┘ └─────┘ └──────┘└─┘  └──┘   └─┘   ",
        ];
        
        let mut colored_lines = Vec::new();
        // First push an empty line to colored_lines
        colored_lines.push(Line::from(""));
        
        // Define colors exactly as in show_welcome_message()
        let gradient_start = (0x02, 0x74, 0x3B); // 0x02743B
        let gradient_end = (0x32, 0xF0, 0x8C); // 0x32F08C
        let shadow_color = (0x5C, 0xF5, 0xA8); // 0x5CF5A8
        
        for line in logo_raw.iter() {
            let mut spans = Vec::new();
            let line_length = line.chars().filter(|c| *c == '█').count();
            let mut main_char_index = 0;
            
            for ch in line.chars() {
                let style = if ch == '█' {
                    // Calculate gradient position (0.0 to 1.0) - exactly as in original
                    let position = if line_length > 1 {
                        main_char_index as f32 / (line_length - 1) as f32
                    } else {
                        0.0
                    };
                    
                    // Interpolate between gradient colors - exactly as in original
                    let r = (gradient_start.0 as f32
                        + (gradient_end.0 as f32 - gradient_start.0 as f32) * position)
                        as u8;
                    let g = (gradient_start.1 as f32
                        + (gradient_end.1 as f32 - gradient_start.1 as f32) * position)
                        as u8;
                    let b = (gradient_start.2 as f32
                        + (gradient_end.2 as f32 - gradient_start.2 as f32) * position)
                        as u8;
                    
                    main_char_index += 1;
                    Style::default().fg(Color::Rgb(r, g, b))
                } else if ch == '└'
                    || ch == '┌'
                    || ch == '┐'
                    || ch == '┘'
                    || ch == '─'
                    || ch == '│'
                    || ch == '┬'
                    || ch == '┴'
                    || ch == '├'
                    || ch == '┤'
                    || ch == '┼'
                {
                    // Shadow characters - exactly as in original
                    Style::default().fg(Color::Rgb(shadow_color.0, shadow_color.1, shadow_color.2))
                } else {
                    // Regular characters (spaces, etc.) - exactly as in original
                    Style::default().fg(Color::White)
                };
                
                spans.push(Span::styled(ch.to_string(), style));
            }
            
            colored_lines.push(Line::from(spans));
        }
        
        // Add empty line after logo
        colored_lines.push(Line::from(""));
        
        colored_lines
    }
    
    pub fn add_output_line(&mut self, line: String) {
        self.add_output_line_styled(Line::from(Span::styled(line, Style::default().fg(Color::White))));
    }
    
    pub fn add_output_line_styled(&mut self, line: Line<'static>) {
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
        self.hide_autocomplete();
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
    
    pub fn is_task_running(&self) -> bool {
        matches!(self.agent_status, 
            AgentStatus::Running | 
            AgentStatus::Thinking | 
            AgentStatus::CallingTool | 
            AgentStatus::Reflecting
        )
    }
    
    pub fn show_quit_confirmation(&mut self) {
        self.show_quit_popup = true;
    }
    
    pub fn hide_quit_confirmation(&mut self) {
        self.show_quit_popup = false;
    }
    
    pub fn confirm_quit(&mut self) {
        self.should_quit = true;
        self.show_quit_popup = false;
    }
    
    pub fn update_autocomplete(&mut self) {
        if self.input_text.starts_with('/') {
            // Only show supported commands
            let commands = vec![
                "/help".to_string(),
                "/quit".to_string(),
                "/exit".to_string(),
            ];
            
            let input_lower = self.input_text.to_lowercase();
            self.autocomplete_suggestions = commands
                .into_iter()
                .filter(|cmd| cmd.starts_with(&input_lower))
                .collect();
            
            self.show_autocomplete = !self.autocomplete_suggestions.is_empty();
            self.autocomplete_selected = 0;
        } else {
            self.hide_autocomplete();
        }
    }
    
    pub fn hide_autocomplete(&mut self) {
        self.show_autocomplete = false;
        self.autocomplete_suggestions.clear();
        self.autocomplete_selected = 0;
    }
    
    pub fn select_next_suggestion(&mut self) {
        if !self.autocomplete_suggestions.is_empty() {
            self.autocomplete_selected = (self.autocomplete_selected + 1) % self.autocomplete_suggestions.len();
        }
    }
    
    pub fn select_prev_suggestion(&mut self) {
        if !self.autocomplete_suggestions.is_empty() {
            self.autocomplete_selected = if self.autocomplete_selected == 0 {
                self.autocomplete_suggestions.len() - 1
            } else {
                self.autocomplete_selected - 1
            };
        }
    }
    
    pub fn apply_selected_suggestion(&mut self) {
        if let Some(suggestion) = self.autocomplete_suggestions.get(self.autocomplete_selected) {
            self.input_text = suggestion.clone();
            self.input_cursor = self.input_text.len();
            self.hide_autocomplete();
        }
    }
}
