// Copyright (c) 2025 ByteDance Ltd. and/or its affiliates
// SPDX-License-Identifier: MIT

use ratatui::{
    layout::{Constraint, Direction, Rect},
    prelude::*,
    widgets::{Block, Borders, List, ListItem, Paragraph, Wrap},
    Frame,
};

use super::state::AppState;

pub struct Layout;

impl Layout {
    /// Create the main layout with 4 sections:
    /// - Top 70%: Agent output
    /// - Next 10%: Agent state and token usage
    /// - Next 10%: Input box
    /// - Bottom 10%: Shortcuts
    pub fn render(frame: &mut Frame, state: &AppState) {
        let size = frame.area();
        
        // Create main layout chunks
        let chunks = ratatui::layout::Layout::default()
            .direction(Direction::Vertical)
            .constraints([
                Constraint::Percentage(70), // Output area
                Constraint::Percentage(10), // Status area
                Constraint::Percentage(10), // Input area
                Constraint::Percentage(10), // Shortcuts area
            ])
            .split(size);

        // Render each section
        Self::render_output_area(frame, chunks[0], state);
        Self::render_status_area(frame, chunks[1], state);
        Self::render_input_area(frame, chunks[2], state);
        Self::render_shortcuts_area(frame, chunks[3]);
    }

    fn render_output_area(frame: &mut Frame, area: Rect, state: &AppState) {
        let output_text = if state.output_lines.is_empty() {
            "No output yet...".to_string()
        } else {
            state.output_lines
                .iter()
                .skip(state.output_scroll.saturating_sub(area.height as usize))
                .take(area.height as usize)
                .cloned()
                .collect::<Vec<_>>()
                .join("\n")
        };

        let paragraph = Paragraph::new(output_text)
            .block(
                Block::default()
                    .title("Agent Output")
                    .borders(Borders::ALL)
                    .border_style(Style::default().fg(Color::Cyan))
            )
            .wrap(Wrap { trim: false })
            .style(Style::default().fg(Color::White));

        frame.render_widget(paragraph, area);
    }

    fn render_status_area(frame: &mut Frame, area: Rect, state: &AppState) {
        // Split status area into two parts: agent status and token usage
        let status_chunks = ratatui::layout::Layout::default()
            .direction(Direction::Horizontal)
            .constraints([
                Constraint::Percentage(60), // Agent status
                Constraint::Percentage(40), // Token usage
            ])
            .split(area);

        // Agent status
        let status_text = format!("Status: {}", state.agent_status.display());
        let status_paragraph = Paragraph::new(status_text)
            .block(
                Block::default()
                    .title("Agent Status")
                    .borders(Borders::ALL)
                    .border_style(Style::default().fg(Color::Yellow))
            )
            .style(Style::default().fg(state.agent_status.color()));

        frame.render_widget(status_paragraph, status_chunks[0]);

        // Token usage
        let token_text = format!(
            "Input: {} | Output: {} | Total: {}",
            state.token_usage.input_tokens,
            state.token_usage.output_tokens,
            state.token_usage.total_tokens
        );
        let token_paragraph = Paragraph::new(token_text)
            .block(
                Block::default()
                    .title("Token Usage")
                    .borders(Borders::ALL)
                    .border_style(Style::default().fg(Color::Green))
            )
            .style(Style::default().fg(Color::White));

        frame.render_widget(token_paragraph, status_chunks[1]);
    }

    fn render_input_area(frame: &mut Frame, area: Rect, state: &AppState) {
        let input_paragraph = Paragraph::new(state.input_text.as_str())
            .block(
                Block::default()
                    .title("Enter Task")
                    .borders(Borders::ALL)
                    .border_style(Style::default().fg(Color::Magenta))
            )
            .style(Style::default().fg(Color::White));

        frame.render_widget(input_paragraph, area);

        // Position cursor
        if area.width > 2 {
            frame.set_cursor_position(Position {
                x: area.x + 1 + state.input_cursor as u16,
                y: area.y + 1,
            });
        }
    }

    fn render_shortcuts_area(frame: &mut Frame, area: Rect) {
        let shortcuts = [
            "Enter: Run task",
            "Ctrl+C/Ctrl+Q/Esc: Quit",
            "↑/↓: Scroll output",
            "/help: Show help",
        ];

        let shortcuts_items: Vec<ListItem> = shortcuts
            .iter()
            .map(|s| ListItem::new(*s))
            .collect();

        let shortcuts_list = List::new(shortcuts_items)
            .block(
                Block::default()
                    .title("Shortcuts")
                    .borders(Borders::ALL)
                    .border_style(Style::default().fg(Color::Gray))
            )
            .style(Style::default().fg(Color::Gray));

        frame.render_widget(shortcuts_list, area);
    }
}
