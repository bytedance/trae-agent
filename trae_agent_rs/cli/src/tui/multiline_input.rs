// Copyright (c) 2025 ByteDance Ltd. and/or its affiliates
// SPDX-License-Identifier: MIT

use ratatui::{
    prelude::*,
    text::{Line, Span},
    widgets::{Block, Borders, Paragraph, Wrap},
};

/// Multi-line text input widget with advanced editing capabilities
#[derive(Debug, Clone)]
pub struct MultiLineInput {
    /// Lines of text content
    pub lines: Vec<String>,
    /// Current cursor line (0-based)
    pub cursor_line: usize,
    /// Current cursor column (0-based)
    pub cursor_col: usize,
    /// Vertical scroll offset for display
    pub scroll_offset: usize,
    /// Horizontal scroll offset for long lines
    pub horizontal_scroll: usize,
    /// Maximum width for text wrapping
    pub max_width: usize,
    /// Whether to show line numbers
    pub show_line_numbers: bool,
    /// Placeholder text when empty
    pub placeholder: String,
}

impl Default for MultiLineInput {
    fn default() -> Self {
        Self {
            lines: vec![String::new()],
            cursor_line: 0,
            cursor_col: 0,
            scroll_offset: 0,
            horizontal_scroll: 0,
            max_width: 80,
            show_line_numbers: false,
            placeholder: "Type your task here...".to_string(),
        }
    }
}

impl MultiLineInput {
    pub fn new() -> Self {
        Self::default()
    }

    pub fn with_placeholder(mut self, placeholder: String) -> Self {
        self.placeholder = placeholder;
        self
    }

    pub fn with_line_numbers(mut self, show: bool) -> Self {
        self.show_line_numbers = show;
        self
    }

    /// Get the complete text as a single string
    pub fn get_text(&self) -> String {
        self.lines.join("\n")
    }

    /// Set the complete text from a string
    pub fn set_text(&mut self, text: String) {
        self.lines = if text.is_empty() {
            vec![String::new()]
        } else {
            text.lines().map(|s| s.to_string()).collect()
        };
        self.cursor_line = 0;
        self.cursor_col = 0;
        self.scroll_offset = 0;
        self.horizontal_scroll = 0;
    }

    /// Clear all text
    pub fn clear(&mut self) {
        self.lines = vec![String::new()];
        self.cursor_line = 0;
        self.cursor_col = 0;
        self.scroll_offset = 0;
        self.horizontal_scroll = 0;
    }

    /// Check if the input is empty
    pub fn is_empty(&self) -> bool {
        self.lines.len() == 1 && self.lines[0].is_empty()
    }

    /// Insert a character at the current cursor position
    pub fn insert_char(&mut self, c: char) {
        if c == '\n' {
            self.insert_newline();
        } else {
            let current_line = &mut self.lines[self.cursor_line];
            current_line.insert(self.cursor_col, c);
            self.cursor_col += 1;
        }
        self.adjust_scroll();
    }

    /// Insert a newline at the current cursor position
    pub fn insert_newline(&mut self) {
        let current_line = self.lines[self.cursor_line].clone();
        let left = current_line[..self.cursor_col].to_string();
        let right = current_line[self.cursor_col..].to_string();
        
        self.lines[self.cursor_line] = left;
        self.lines.insert(self.cursor_line + 1, right);
        
        self.cursor_line += 1;
        self.cursor_col = 0;
        self.adjust_scroll();
    }

    /// Delete the character before the cursor (backspace)
    pub fn delete_char(&mut self) {
        if self.cursor_col > 0 {
            // Delete character in current line
            self.lines[self.cursor_line].remove(self.cursor_col - 1);
            self.cursor_col -= 1;
        } else if self.cursor_line > 0 {
            // Join with previous line
            let current_line = self.lines.remove(self.cursor_line);
            self.cursor_line -= 1;
            self.cursor_col = self.lines[self.cursor_line].len();
            self.lines[self.cursor_line].push_str(&current_line);
        }
        self.adjust_scroll();
    }

    /// Delete the character at the cursor (delete key)
    pub fn delete_char_forward(&mut self) {
        let current_line = &mut self.lines[self.cursor_line];
        if self.cursor_col < current_line.len() {
            // Delete character in current line
            current_line.remove(self.cursor_col);
        } else if self.cursor_line < self.lines.len() - 1 {
            // Join with next line
            let next_line = self.lines.remove(self.cursor_line + 1);
            self.lines[self.cursor_line].push_str(&next_line);
        }
    }

    /// Move cursor left
    pub fn move_cursor_left(&mut self) {
        if self.cursor_col > 0 {
            self.cursor_col -= 1;
        } else if self.cursor_line > 0 {
            self.cursor_line -= 1;
            self.cursor_col = self.lines[self.cursor_line].len();
        }
        self.adjust_scroll();
    }

    /// Move cursor right
    pub fn move_cursor_right(&mut self) {
        let current_line_len = self.lines[self.cursor_line].len();
        if self.cursor_col < current_line_len {
            self.cursor_col += 1;
        } else if self.cursor_line < self.lines.len() - 1 {
            self.cursor_line += 1;
            self.cursor_col = 0;
        }
        self.adjust_scroll();
    }

    /// Move cursor up
    pub fn move_cursor_up(&mut self) {
        if self.cursor_line > 0 {
            self.cursor_line -= 1;
            let line_len = self.lines[self.cursor_line].len();
            self.cursor_col = self.cursor_col.min(line_len);
        }
        self.adjust_scroll();
    }

    /// Move cursor down
    pub fn move_cursor_down(&mut self) {
        if self.cursor_line < self.lines.len() - 1 {
            self.cursor_line += 1;
            let line_len = self.lines[self.cursor_line].len();
            self.cursor_col = self.cursor_col.min(line_len);
        }
        self.adjust_scroll();
    }

    /// Move cursor to beginning of line
    pub fn move_cursor_to_line_start(&mut self) {
        self.cursor_col = 0;
        self.adjust_scroll();
    }

    /// Move cursor to end of line
    pub fn move_cursor_to_line_end(&mut self) {
        self.cursor_col = self.lines[self.cursor_line].len();
        self.adjust_scroll();
    }

    /// Move cursor to beginning of text
    pub fn move_cursor_to_start(&mut self) {
        self.cursor_line = 0;
        self.cursor_col = 0;
        self.scroll_offset = 0;
        self.horizontal_scroll = 0;
    }

    /// Move cursor to end of text
    pub fn move_cursor_to_end(&mut self) {
        self.cursor_line = self.lines.len() - 1;
        self.cursor_col = self.lines[self.cursor_line].len();
        self.adjust_scroll();
    }

    /// Adjust scroll to keep cursor visible
    fn adjust_scroll(&mut self) {
        // Vertical scrolling
        if self.cursor_line < self.scroll_offset {
            self.scroll_offset = self.cursor_line;
        }
        
        // Basic horizontal scrolling - ensure cursor is not behind the scroll position
        // The viewport-specific adjustment should be called from the UI layer for full visibility
        if self.cursor_col < self.horizontal_scroll {
            self.horizontal_scroll = self.cursor_col;
        }
        
        // Basic forward scrolling - if cursor is way ahead, do a minimal adjustment
        // This helps when viewport adjustment isn't called immediately
        if self.cursor_col > self.horizontal_scroll + self.max_width {
            self.horizontal_scroll = self.cursor_col.saturating_sub(self.max_width / 2);
        }
    }

    /// Adjust scroll for a given viewport height
    pub fn adjust_scroll_for_viewport(&mut self, viewport_height: usize) {
        let visible_lines = viewport_height.saturating_sub(2); // Account for borders
        
        // Ensure cursor is visible vertically
        if self.cursor_line >= self.scroll_offset + visible_lines {
            self.scroll_offset = self.cursor_line.saturating_sub(visible_lines - 1);
        }
        if self.cursor_line < self.scroll_offset {
            self.scroll_offset = self.cursor_line;
        }
    }

    /// Adjust horizontal scroll for a given viewport width
    pub fn adjust_horizontal_scroll_for_viewport(&mut self, viewport_width: usize) {
        let visible_cols = viewport_width.saturating_sub(4); // Account for borders and prompt
        
        // Ensure we have at least 1 visible column
        if visible_cols == 0 {
            return;
        }
        
        // If cursor is beyond the right edge of the visible area, scroll right
        if self.cursor_col >= self.horizontal_scroll + visible_cols {
            self.horizontal_scroll = self.cursor_col.saturating_sub(visible_cols - 1);
        }
        
        // If cursor is before the left edge of the visible area, scroll left
        if self.cursor_col < self.horizontal_scroll {
            self.horizontal_scroll = self.cursor_col;
        }
    }

    /// Render the multi-line input widget
    pub fn render(&self, frame: &mut Frame, area: Rect) -> (u16, u16) {
        let visible_lines = area.height.saturating_sub(2) as usize; // Account for borders
        let visible_cols = area.width.saturating_sub(4) as usize; // Account for borders and prompt
        
        let mut display_lines = Vec::new();
        
        if self.is_empty() {
            // Show placeholder
            let placeholder_line = Line::from(vec![
                Span::styled(
                    "❯ ",
                    Style::default()
                        .fg(Color::Cyan)
                        .add_modifier(ratatui::style::Modifier::BOLD),
                ),
                Span::styled(
                    &self.placeholder,
                    Style::default()
                        .fg(Color::DarkGray)
                        .add_modifier(ratatui::style::Modifier::ITALIC),
                ),
            ]);
            display_lines.push(placeholder_line);
        } else {
            // Show actual content
            let end_line = (self.scroll_offset + visible_lines).min(self.lines.len());
            
            for (i, line) in self.lines[self.scroll_offset..end_line].iter().enumerate() {
                let line_number = self.scroll_offset + i;
                let is_cursor_line = line_number == self.cursor_line;
                
                let prompt = if i == 0 {
                    "❯ "
                } else {
                    "  "
                };
                
                let prompt_span = Span::styled(
                    prompt,
                    Style::default()
                        .fg(Color::Cyan)
                        .add_modifier(ratatui::style::Modifier::BOLD),
                );
                
                // Handle horizontal scrolling
                let display_text = if line.len() > self.horizontal_scroll {
                    let end_col = (self.horizontal_scroll + visible_cols).min(line.len());
                    &line[self.horizontal_scroll..end_col]
                } else {
                    ""
                };
                
                let text_span = Span::styled(
                    display_text,
                    Style::default().fg(if is_cursor_line { Color::White } else { Color::Gray }),
                );
                
                display_lines.push(Line::from(vec![prompt_span, text_span]));
            }
        }
        
        let input_paragraph = Paragraph::new(display_lines)
            .block(
                Block::default()
                    .borders(Borders::ALL)
                    .border_style(Style::default().fg(Color::Cyan))
                    .title("Input (Enter to submit, Shift+Enter for new line)"),
            )
            .wrap(Wrap { trim: false });
        
        frame.render_widget(input_paragraph, area);
        
        // Calculate cursor position for rendering
        let cursor_x = if self.is_empty() {
            1 + 2 // border + "❯ "
        } else {
            let visible_cursor_col = self.cursor_col.saturating_sub(self.horizontal_scroll);
            1 + 2 + visible_cursor_col as u16 // border + "❯ " + cursor position
        };
        
        let cursor_y = if self.is_empty() {
            1 // border
        } else {
            1 + (self.cursor_line.saturating_sub(self.scroll_offset)) as u16
        };
        
        (cursor_x, cursor_y)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_basic_text_insertion() {
        let mut input = MultiLineInput::new();
        
        // Test inserting characters
        input.insert_char('H');
        input.insert_char('e');
        input.insert_char('l');
        input.insert_char('l');
        input.insert_char('o');
        
        assert_eq!(input.get_text(), "Hello");
        assert_eq!(input.cursor_line, 0);
        assert_eq!(input.cursor_col, 5);
    }

    #[test]
    fn test_multiline_insertion() {
        let mut input = MultiLineInput::new();
        
        // Insert first line
        input.insert_char('L');
        input.insert_char('i');
        input.insert_char('n');
        input.insert_char('e');
        input.insert_char(' ');
        input.insert_char('1');
        
        // Insert newline
        input.insert_newline();
        
        // Insert second line
        input.insert_char('L');
        input.insert_char('i');
        input.insert_char('n');
        input.insert_char('e');
        input.insert_char(' ');
        input.insert_char('2');
        
        assert_eq!(input.get_text(), "Line 1\nLine 2");
        assert_eq!(input.cursor_line, 1);
        assert_eq!(input.cursor_col, 6);
    }

    #[test]
    fn test_cursor_navigation() {
        let mut input = MultiLineInput::new();
        
        // Setup multi-line text
        input.set_text("First line\nSecond line\nThird line".to_string());
        
        // Initially at line 0, moving up should stay at line 0
        input.move_cursor_up();
        assert_eq!(input.cursor_line, 0);
        
        // Move down to line 1
        input.move_cursor_down();
        assert_eq!(input.cursor_line, 1);
        
        // Move down to line 2
        input.move_cursor_down();
        assert_eq!(input.cursor_line, 2);
        
        // Move up to line 1
        input.move_cursor_up();
        assert_eq!(input.cursor_line, 1);
        
        // Move up to line 0
        input.move_cursor_up();
        assert_eq!(input.cursor_line, 0);
    }

    #[test]
    fn test_line_navigation() {
        let mut input = MultiLineInput::new();
        input.set_text("Hello World".to_string());
        
        // Move to middle
        input.cursor_col = 6;
        
        // Test line start/end
        input.move_cursor_to_line_start();
        assert_eq!(input.cursor_col, 0);
        
        input.move_cursor_to_line_end();
        assert_eq!(input.cursor_col, 11);
    }

    #[test]
    fn test_deletion() {
        let mut input = MultiLineInput::new();
        input.set_text("Hello World".to_string());
        input.cursor_col = 5; // Position after "Hello"
        
        // Delete character before cursor
        input.delete_char();
        assert_eq!(input.get_text(), "Hell World");
        assert_eq!(input.cursor_col, 4);
    }

    #[test]
    fn test_clear() {
        let mut input = MultiLineInput::new();
        input.set_text("Some text\nMore text".to_string());
        
        input.clear();
        assert_eq!(input.get_text(), "");
        assert_eq!(input.cursor_line, 0);
        assert_eq!(input.cursor_col, 0);
    }

    #[test]
    fn test_empty_check() {
        let mut input = MultiLineInput::new();
        assert!(input.is_empty());
        
        input.insert_char('a');
        assert!(!input.is_empty());
        
        input.clear();
        assert!(input.is_empty());
    }
}