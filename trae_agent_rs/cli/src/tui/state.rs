// Copyright (c) 2025 ByteDance Ltd. and/or its affiliates
// SPDX-License-Identifier: MIT

use ratatui::{
    prelude::*,
    text::{Line, Span},
};
use std::collections::VecDeque;
use std::time::{SystemTime, UNIX_EPOCH};

use super::multiline_input::MultiLineInput;

#[derive(Debug, Clone, Default)]
pub struct TokenUsage {
    pub input: u64,
    pub output: u64,
}

#[derive(Debug, Clone)]
pub struct StepHistoryEntry {
    pub step_number: u32,
    pub timestamp: f64,
    pub description: String,
    pub status: AgentStatus,
    pub output_lines: Vec<Line<'static>>,
    pub token_usage: Option<TokenUsage>,
}

impl StepHistoryEntry {
    pub fn new(step_number: u32, description: String, status: AgentStatus) -> Self {
        let timestamp = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap_or_default()
            .as_secs_f64();
        
        Self {
            step_number,
            timestamp,
            description,
            status,
            output_lines: Vec::new(),
            token_usage: None,
        }
    }
    
    pub fn add_output_line(&mut self, line: Line<'static>) {
        self.output_lines.push(line);
    }
    
    pub fn formatted_timestamp(&self) -> String {
        let duration = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap_or_default()
            .as_secs_f64() - self.timestamp;
        
        if duration < 60.0 {
            format!("{:.0}s ago", duration)
        } else if duration < 3600.0 {
            format!("{:.0}m ago", duration / 60.0)
        } else {
            format!("{:.1}h ago", duration / 3600.0)
        }
    }
}

impl TokenUsage {
    pub fn total(&self) -> u64 {
        self.input + self.output
    }
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

    /// Multi-line input widget
    pub input: MultiLineInput,

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

    /// Whether to show settings popup
    pub show_settings: bool,

    /// Whether to show popup input
    pub show_popup_input: bool,

    /// Command history for up/down navigation
    pub command_history: Vec<String>,

    /// Current position in command history (None means not navigating history)
    pub history_index: Option<usize>,

    /// Temporary storage for current input when navigating history
    pub temp_input: Option<String>,

    /// Chronological step history for navigation
    pub step_history: Vec<StepHistoryEntry>,

    /// Current step being executed (for tracking)
    pub current_step: Option<u32>,

    /// Whether we're in history view mode
    pub show_step_history: bool,

    /// Current position in step history view (None means viewing current/latest)
    pub history_view_index: Option<usize>,

    /// Scroll position within a specific step's content
    pub step_content_scroll: usize,

    /// Temporary storage for current input when navigating step history
    pub step_history_temp_input: Option<String>,

    /// Temporary storage for current output scroll when navigating step history
    pub step_history_temp_output_scroll: Option<usize>,
}

impl Default for AppState {
    fn default() -> Self {
        Self {
            agent_status: AgentStatus::default(),
            token_usage: TokenUsage::default(),
            output_lines: VecDeque::new(),
            input: MultiLineInput::new().with_placeholder("Type your task here...".to_string()),
            should_quit: false,
            output_scroll: 0,
            max_output_lines: 1000,
            show_quit_popup: false,
            autocomplete_suggestions: Vec::new(),
            autocomplete_selected: 0,
            show_autocomplete: false,
            show_settings: false,
            show_popup_input: false,
            command_history: Vec::new(),
            history_index: None,
            temp_input: None,
            step_history: Vec::new(),
            current_step: None,
            show_step_history: false,
            history_view_index: None,
            step_content_scroll: 0,
            step_history_temp_input: None,
            step_history_temp_output_scroll: None,
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
            Span::styled(
                "Trae Agent",
                Style::default()
                    .fg(Color::Cyan)
                    .add_modifier(ratatui::style::Modifier::BOLD),
            ),
            Span::styled(
                " - Intelligent coding assistant",
                Style::default().fg(Color::White),
            ),
        ]));

        self.add_output_line_styled(Line::from(vec![
            Span::styled("💡 Version: ", Style::default().fg(Color::Yellow)),
            Span::styled(
                "0.1.0",
                Style::default()
                    .fg(Color::Green)
                    .add_modifier(ratatui::style::Modifier::BOLD),
            ),
        ]));

        self.add_output_line_styled(Line::from(""));

        self.add_output_line_styled(Line::from(vec![
            Span::styled("Welcome to ", Style::default().fg(Color::Gray)),
            Span::styled(
                "Trae Agent",
                Style::default()
                    .fg(Color::Cyan)
                    .add_modifier(ratatui::style::Modifier::BOLD),
            ),
            Span::styled(" interactive mode!", Style::default().fg(Color::Gray)),
        ]));

        self.add_output_line_styled(Line::from(Span::styled(
            "Type your task below and press Enter to start.",
            Style::default()
                .fg(Color::DarkGray)
                .add_modifier(ratatui::style::Modifier::ITALIC),
        )));

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
        self.add_output_line_styled(Line::from(Span::styled(
            line,
            Style::default().fg(Color::White),
        )));
    }

    pub fn add_output_line_styled(&mut self, line: Line<'static>) {
        self.output_lines.push_back(line);

        // Limit buffer size
        while self.output_lines.len() > self.max_output_lines {
            self.output_lines.pop_front();
        }

        // Auto-scroll to bottom (set to max value, layout will clamp appropriately)
        self.output_scroll = usize::MAX;
    }

    pub fn clear_input(&mut self) {
        self.input.clear();
        self.hide_autocomplete();
    }

    pub fn insert_char(&mut self, c: char) {
        self.input.insert_char(c);
    }

    pub fn delete_char(&mut self) {
        self.input.delete_char();
    }

    pub fn move_cursor_left(&mut self) {
        self.input.move_cursor_left();
    }

    pub fn move_cursor_right(&mut self) {
        self.input.move_cursor_right();
    }

    pub fn move_cursor_up(&mut self) {
        self.input.move_cursor_up();
    }

    pub fn move_cursor_down(&mut self) {
        self.input.move_cursor_down();
    }

    pub fn move_cursor_to_line_start(&mut self) {
        self.input.move_cursor_to_line_start();
    }

    pub fn move_cursor_to_line_end(&mut self) {
        self.input.move_cursor_to_line_end();
    }

    pub fn insert_newline(&mut self) {
        self.input.insert_newline();
    }

    pub fn get_input_text(&self) -> String {
        self.input.get_text()
    }

    pub fn is_input_empty(&self) -> bool {
        self.input.is_empty()
    }

    pub fn scroll_up(&mut self) {
        if self.output_scroll > 0 {
            self.output_scroll -= 1;
        }
    }

    pub fn scroll_down(&mut self) {
        // Only scroll down if there's content to scroll
        if self.output_lines.len() > 0 {
            self.output_scroll += 1;
        }
    }

    /// Enhanced scroll up with multiple lines
    pub fn scroll_up_lines(&mut self, lines: usize) {
        if self.output_scroll >= lines {
            self.output_scroll -= lines;
        } else {
            self.output_scroll = 0;
        }
    }

    /// Enhanced scroll down with multiple lines
    pub fn scroll_down_lines(&mut self, lines: usize) {
        if self.output_lines.len() > 0 {
            self.output_scroll += lines;
        }
    }

    /// Smooth scroll up with acceleration
    pub fn smooth_scroll_up(&mut self, acceleration: usize) {
        let scroll_amount = std::cmp::max(1, acceleration);
        self.scroll_up_lines(scroll_amount);
    }

    /// Smooth scroll down with acceleration
    pub fn smooth_scroll_down(&mut self, acceleration: usize) {
        let scroll_amount = std::cmp::max(1, acceleration);
        self.scroll_down_lines(scroll_amount);
    }

    pub fn scroll_page_up(&mut self, page_size: usize) {
        self.output_scroll = self.output_scroll.saturating_sub(page_size);
    }

    pub fn scroll_page_down(&mut self, page_size: usize) {
        self.output_scroll += page_size;
    }

    pub fn scroll_to_top(&mut self) {
        self.output_scroll = 0;
    }

    pub fn scroll_to_bottom(&mut self) {
        // Set scroll to a very large number - the layout will clamp it appropriately
        self.output_scroll = usize::MAX;
    }

    /// Clamp scroll position to valid bounds given the viewport height
    pub fn clamp_scroll(&mut self, viewport_height: usize) {
        let total_lines = self.output_lines.len();
        let max_scroll = if total_lines > viewport_height {
            total_lines - viewport_height
        } else {
            0
        };
        self.output_scroll = std::cmp::min(self.output_scroll, max_scroll);
    }

    /// Get scroll position as a percentage (0-100)
    pub fn get_scroll_percentage(&self, viewport_height: usize) -> u8 {
        let total_lines = self.output_lines.len();
        if total_lines <= viewport_height {
            return 100; // At bottom when all content fits
        }
        
        let max_scroll = total_lines - viewport_height;
        if max_scroll == 0 {
            return 100;
        }
        
        let percentage = (self.output_scroll as f64 / max_scroll as f64) * 100.0;
        percentage.round() as u8
    }

    /// Check if we're at the top of the output
    pub fn is_at_top(&self) -> bool {
        self.output_scroll == 0
    }

    /// Check if we're at the bottom of the output
    pub fn is_at_bottom(&self, viewport_height: usize) -> bool {
        let total_lines = self.output_lines.len();
        if total_lines <= viewport_height {
            return true;
        }
        
        let max_scroll = total_lines - viewport_height;
        self.output_scroll >= max_scroll
    }

    /// Get scroll position info for display
    pub fn get_scroll_info(&self, viewport_height: usize) -> String {
        let total_lines = self.output_lines.len();
        if total_lines <= viewport_height {
            return "All".to_string();
        }
        
        let percentage = self.get_scroll_percentage(viewport_height);
        if self.is_at_top() {
            "Top".to_string()
        } else if self.is_at_bottom(viewport_height) {
            "Bot".to_string()
        } else {
            format!("{}%", percentage)
        }
    }

    pub fn update_token_usage(&mut self, input_tokens: u64, output_tokens: u64) {
        self.token_usage.input += input_tokens;
        self.token_usage.output += output_tokens;
    }

    pub fn is_task_running(&self) -> bool {
        matches!(
            self.agent_status,
            AgentStatus::Running
                | AgentStatus::Thinking
                | AgentStatus::CallingTool
                | AgentStatus::Reflecting
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
        let input_text = self.input.get_text();
        if input_text.starts_with('/') {
            // Only show supported commands
            let commands = vec![
                "/help".to_string(),
                "/settings".to_string(),
                "/review".to_string(),
                "/quit".to_string(),
                "/exit".to_string(),
            ];

            let input_lower = input_text.to_lowercase();
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
            self.autocomplete_selected =
                (self.autocomplete_selected + 1) % self.autocomplete_suggestions.len();
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
        if let Some(suggestion) = self
            .autocomplete_suggestions
            .get(self.autocomplete_selected)
        {
            self.input.set_text(suggestion.clone());
            self.hide_autocomplete();
        }
    }

    /// Show settings popup
    pub fn show_settings_popup(&mut self) {
        self.show_settings = true;
    }

    /// Hide settings popup
    pub fn hide_settings_popup(&mut self) {
        self.show_settings = false;
    }

    pub fn show_popup_input(&mut self) {
        self.show_popup_input = true;
    }

    pub fn hide_popup_input(&mut self) {
        self.show_popup_input = false;
    }

    /// Adjust horizontal scroll for the input field based on viewport width
    pub fn adjust_input_horizontal_scroll(&mut self, viewport_width: usize) {
        self.input.adjust_horizontal_scroll_for_viewport(viewport_width);
    }

    /// Add a command to history when it's submitted
    pub fn add_to_history(&mut self, command: String) {
        if !command.trim().is_empty() && !self.command_history.contains(&command) {
            self.command_history.push(command);
            // Keep history size reasonable (last 100 commands)
            if self.command_history.len() > 100 {
                self.command_history.remove(0);
            }
        }
        // Reset history navigation state
        self.history_index = None;
        self.temp_input = None;
    }

    /// Navigate to previous command in history (up arrow)
    pub fn history_previous(&mut self) {
        if self.command_history.is_empty() {
            return;
        }

        // If not currently navigating history, save current input
        if self.history_index.is_none() {
            let current_input = self.get_input_text();
            if !current_input.trim().is_empty() {
                self.temp_input = Some(current_input);
            }
            self.history_index = Some(self.command_history.len() - 1);
        } else if let Some(index) = self.history_index {
            if index > 0 {
                self.history_index = Some(index - 1);
            }
        }

        // Set input to the selected history item and position cursor at end
        if let Some(index) = self.history_index {
            if let Some(command) = self.command_history.get(index) {
                self.input.set_text(command.clone());
                // Position cursor at the end of the recalled command for immediate editing
                self.input.move_cursor_to_end();
            }
        }
    }

    /// Navigate to next command in history (down arrow)
    pub fn history_next(&mut self) {
        if let Some(index) = self.history_index {
            if index < self.command_history.len() - 1 {
                self.history_index = Some(index + 1);
                if let Some(command) = self.command_history.get(index + 1) {
                    self.input.set_text(command.clone());
                    // Position cursor at the end of the recalled command for immediate editing
                    self.input.move_cursor_to_end();
                }
            } else {
                // Reached the end of history, restore temp input or clear
                self.history_index = None;
                if let Some(temp) = self.temp_input.take() {
                    self.input.set_text(temp);
                    // Position cursor at the end of restored input
                    self.input.move_cursor_to_end();
                } else {
                    self.input.clear();
                }
            }
        }
    }

    /// Check if we're currently navigating through history
    pub fn is_navigating_history(&self) -> bool {
        self.history_index.is_some()
    }

    /// Reset history navigation state (called when user types)
    pub fn reset_history_navigation(&mut self) {
        self.history_index = None;
        self.temp_input = None;
    }

    /// Get the current history position for display purposes
    pub fn get_history_position(&self) -> Option<(usize, usize)> {
        if let Some(index) = self.history_index {
            Some((index + 1, self.command_history.len()))
        } else {
            None
        }
    }

    /// Check if there are any commands in history
    pub fn has_history(&self) -> bool {
        !self.command_history.is_empty()
    }

    /// Jump to the first (oldest) command in history
    pub fn history_jump_to_first(&mut self) {
        if self.command_history.is_empty() {
            return;
        }

        // Save current input if not already navigating
        if !self.is_navigating_history() {
            let current_input = self.get_input_text();
            if !current_input.trim().is_empty() {
                self.temp_input = Some(current_input);
            }
        }

        // Jump to first (oldest) command
        self.history_index = Some(0);
        if let Some(command) = self.command_history.get(0) {
            self.input.set_text(command.clone());
            self.input.move_cursor_to_end();
        }
    }

    /// Jump to the last (newest) command in history
    pub fn history_jump_to_last(&mut self) {
        if self.command_history.is_empty() {
            return;
        }

        // Save current input if not already navigating
        if !self.is_navigating_history() {
            let current_input = self.get_input_text();
            if !current_input.trim().is_empty() {
                self.temp_input = Some(current_input);
            }
        }

        // Jump to last (newest) command
        let last_index = self.command_history.len() - 1;
        self.history_index = Some(last_index);
        if let Some(command) = self.command_history.get(last_index) {
            self.input.set_text(command.clone());
            self.input.move_cursor_to_end();
        }
    }

    // Step History Management Methods
    
    pub fn start_new_step(&mut self, step_number: u32, description: String) {
        let entry = StepHistoryEntry::new(step_number, description, self.agent_status.clone());
        self.step_history.push(entry);
        self.current_step = Some(step_number);
    }
    
    pub fn add_output_to_current_step(&mut self, line: Line<'static>) {
        if let Some(current_step) = self.current_step {
            if let Some(entry) = self.step_history.iter_mut()
                .find(|e| e.step_number == current_step) {
                entry.add_output_line(line);
            }
        }
    }
    
    pub fn update_current_step_status(&mut self, status: AgentStatus) {
        if let Some(current_step) = self.current_step {
            if let Some(entry) = self.step_history.iter_mut()
                .find(|e| e.step_number == current_step) {
                entry.status = status;
            }
        }
    }
    
    pub fn complete_current_step(&mut self) {
        if let Some(current_step) = self.current_step {
            if let Some(entry) = self.step_history.iter_mut()
                .find(|e| e.step_number == current_step) {
                entry.status = AgentStatus::Completed;
            }
        }
        self.current_step = None;
    }
    
    // Step History Navigation Methods
    
    pub fn toggle_step_history_view(&mut self) {
        self.show_step_history = !self.show_step_history;
        if self.show_step_history {
            // Save current context before entering history view
            self.step_history_temp_input = Some(self.get_input_text());
            self.step_history_temp_output_scroll = Some(self.output_scroll);
            
            // When showing history, start at the latest step
            if !self.step_history.is_empty() {
                self.history_view_index = Some(self.step_history.len() - 1);
            }
        } else {
            // Restore context when exiting history view
            if let Some(saved_input) = self.step_history_temp_input.take() {
                self.input.set_text(saved_input);
            }
            if let Some(saved_scroll) = self.step_history_temp_output_scroll.take() {
                self.output_scroll = saved_scroll;
            }
            
            self.history_view_index = None;
            self.step_content_scroll = 0;
        }
    }
    
    pub fn navigate_step_history_previous(&mut self) {
        if self.step_history.is_empty() {
            return;
        }
        
        match self.history_view_index {
            None => {
                // Start from the latest step
                self.history_view_index = Some(self.step_history.len() - 1);
            }
            Some(index) => {
                if index > 0 {
                    self.history_view_index = Some(index - 1);
                }
            }
        }
        self.step_content_scroll = 0;
    }
    
    pub fn navigate_step_history_next(&mut self) {
        if self.step_history.is_empty() {
            return;
        }
        
        if let Some(index) = self.history_view_index {
            if index < self.step_history.len() - 1 {
                self.history_view_index = Some(index + 1);
            } else {
                // Go back to current view
                self.history_view_index = None;
            }
            self.step_content_scroll = 0;
        }
    }
    
    pub fn navigate_step_history_first(&mut self) {
        if !self.step_history.is_empty() {
            self.history_view_index = Some(0);
            self.step_content_scroll = 0;
        }
    }
    
    pub fn navigate_step_history_last(&mut self) {
        if !self.step_history.is_empty() {
            self.history_view_index = Some(self.step_history.len() - 1);
            self.step_content_scroll = 0;
        }
    }
    
    pub fn scroll_step_content_up(&mut self) {
        if self.step_content_scroll > 0 {
            self.step_content_scroll -= 1;
        }
    }
    
    pub fn scroll_step_content_down(&mut self, max_lines: usize) {
        if let Some(step) = self.get_current_viewed_step() {
            let content_lines = step.output_lines.len();
            if content_lines > max_lines && self.step_content_scroll < content_lines - max_lines {
                self.step_content_scroll += 1;
            }
        }
    }
    
    pub fn get_current_viewed_step(&self) -> Option<&StepHistoryEntry> {
        if let Some(index) = self.history_view_index {
            self.step_history.get(index)
        } else {
            // Return the latest step if not viewing history
            self.step_history.last()
        }
    }
    
    pub fn get_step_history_position(&self) -> Option<(usize, usize)> {
        if self.step_history.is_empty() {
            return None;
        }
        
        let current = self.history_view_index.unwrap_or(self.step_history.len() - 1);
        Some((current + 1, self.step_history.len()))
    }
    
    pub fn is_navigating_step_history(&self) -> bool {
        self.show_step_history && self.history_view_index.is_some()
    }
    
    pub fn clear_step_history(&mut self) {
        self.step_history.clear();
        self.current_step = None;
        self.history_view_index = None;
        self.step_content_scroll = 0;
        self.show_step_history = false;
    }
}
