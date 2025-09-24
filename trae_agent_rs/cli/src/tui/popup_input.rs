// Copyright (c) 2025 ByteDance Ltd. and/or its affiliates
// SPDX-License-Identifier: MIT

use super::multiline_input::MultiLineInput;

/// Popup input editor for multiline text editing
#[derive(Debug, Clone)]
pub struct PopupInputEditor {
    /// The multiline input widget
    pub input: MultiLineInput,
    /// Whether the popup is currently active
    pub is_active: bool,
    /// Title of the popup
    pub title: String,
    /// Instructions text
    pub instructions: String,
}

impl Default for PopupInputEditor {
    fn default() -> Self {
        Self::new()
    }
}

impl PopupInputEditor {
    /// Create a new popup input editor
    pub fn new() -> Self {
        Self {
            input: MultiLineInput::new(),
            is_active: false,
            title: "Multi-line Input".to_string(),
            instructions: "Enter: Submit • Esc: Cancel • Shift+Enter: New line • ↑↓←→: Navigate".to_string(),
        }
    }

    /// Create a new popup input editor with custom title
    pub fn with_title(title: String) -> Self {
        Self {
            input: MultiLineInput::new(),
            is_active: false,
            title,
            instructions: "Enter: Submit • Esc: Cancel • Shift+Enter: New line • ↑↓←→: Navigate".to_string(),
        }
    }

    /// Create a new popup input editor with custom title and instructions
    pub fn with_title_and_instructions(title: String, instructions: String) -> Self {
        Self {
            input: MultiLineInput::new(),
            is_active: false,
            title,
            instructions,
        }
    }

    /// Activate the popup with optional initial text
    pub fn activate(&mut self, initial_text: Option<String>) {
        self.is_active = true;
        if let Some(text) = initial_text {
            self.input.set_text(text);
        } else {
            self.input.clear();
        }
    }

    /// Deactivate the popup
    pub fn deactivate(&mut self) {
        self.is_active = false;
        self.input.clear();
    }

    /// Get the current text content
    pub fn get_text(&self) -> String {
        self.input.get_text()
    }

    /// Set the text content
    pub fn set_text(&mut self, text: String) {
        self.input.set_text(text);
    }

    /// Clear the input
    pub fn clear(&mut self) {
        self.input.clear();
    }

    /// Check if the input is empty
    pub fn is_empty(&self) -> bool {
        self.input.is_empty()
    }

    /// Insert a character at the current cursor position
    pub fn insert_char(&mut self, c: char) {
        self.input.insert_char(c);
    }

    /// Delete the character before the cursor
    pub fn delete_char(&mut self) {
        self.input.delete_char();
    }

    /// Move cursor left
    pub fn move_cursor_left(&mut self) {
        self.input.move_cursor_left();
    }

    /// Move cursor right
    pub fn move_cursor_right(&mut self) {
        self.input.move_cursor_right();
    }

    /// Move cursor up
    pub fn move_cursor_up(&mut self) {
        self.input.move_cursor_up();
    }

    /// Move cursor down
    pub fn move_cursor_down(&mut self) {
        self.input.move_cursor_down();
    }

    /// Move cursor to the start of the current line
    pub fn move_cursor_to_line_start(&mut self) {
        self.input.move_cursor_to_line_start();
    }

    /// Move cursor to the end of the current line
    pub fn move_cursor_to_line_end(&mut self) {
        self.input.move_cursor_to_line_end();
    }

    /// Insert a newline at the current cursor position
    pub fn insert_newline(&mut self) {
        self.input.insert_newline();
    }

    /// Get the cursor position for rendering
    pub fn get_cursor_position(&self) -> (usize, usize) {
        (self.input.cursor_line, self.input.cursor_col)
    }

    /// Get the lines for rendering
    pub fn get_lines(&self) -> &Vec<String> {
        &self.input.lines
    }

    /// Get the scroll offset for rendering
    pub fn get_scroll_offset(&self) -> usize {
        self.input.scroll_offset
    }

    /// Get the horizontal scroll for rendering
    pub fn get_horizontal_scroll(&self) -> usize {
        self.input.horizontal_scroll
    }

    /// Update scroll based on popup dimensions
    pub fn update_scroll(&mut self, popup_height: usize) {
        // Reserve space for title, borders, and instructions
        let content_height = popup_height.saturating_sub(4); // 2 for borders, 1 for title, 1 for instructions
        
        // Ensure cursor is visible
        if self.input.cursor_line < self.input.scroll_offset {
            self.input.scroll_offset = self.input.cursor_line;
        } else if self.input.cursor_line >= self.input.scroll_offset + content_height {
            self.input.scroll_offset = self.input.cursor_line.saturating_sub(content_height.saturating_sub(1));
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_popup_input_creation() {
        let editor = PopupInputEditor::new();
        assert!(!editor.is_active);
        assert_eq!(editor.title, "Multi-line Input");
        assert!(editor.is_empty());
    }

    #[test]
    fn test_popup_input_with_title() {
        let editor = PopupInputEditor::with_title("Custom Title".to_string());
        assert_eq!(editor.title, "Custom Title");
        assert!(!editor.is_active);
    }

    #[test]
    fn test_popup_activation() {
        let mut editor = PopupInputEditor::new();
        editor.activate(Some("Initial text".to_string()));
        assert!(editor.is_active);
        assert_eq!(editor.get_text(), "Initial text");
    }

    #[test]
    fn test_popup_deactivation() {
        let mut editor = PopupInputEditor::new();
        editor.activate(Some("Some text".to_string()));
        editor.deactivate();
        assert!(!editor.is_active);
        assert!(editor.is_empty());
    }

    #[test]
    fn test_text_operations() {
        let mut editor = PopupInputEditor::new();
        editor.activate(None);
        
        editor.insert_char('H');
        editor.insert_char('i');
        assert_eq!(editor.get_text(), "Hi");
        
        editor.insert_newline();
        editor.insert_char('!');
        assert_eq!(editor.get_text(), "Hi\n!");
        
        editor.clear();
        assert!(editor.is_empty());
    }
}