// Copyright (c) 2025 ByteDance Ltd. and/or its affiliates
// SPDX-License-Identifier: MIT

use ratatui::{
    Frame,
    layout::{Alignment, Constraint, Direction, Rect},
    prelude::*,
    text::{Line, Span},
    widgets::{Block, Borders, Clear, List, ListItem, Paragraph, Wrap},
};

use super::state::AppState;

pub struct Layout;

impl Layout {
    /// Create the main layout with 4 sections:
    /// - Top: Agent output (takes remaining space)
    /// - Agent state and token usage (minimal height needed)
    /// - Input box (minimal height needed)
    /// - Shortcuts (minimal height needed)
    pub fn render(frame: &mut Frame, state: &AppState) {
        let size = frame.area();
        // Create main layout chunks with dynamic sizing
        let chunks = ratatui::layout::Layout::default()
            .direction(Direction::Vertical)
            .constraints([
                Constraint::Min(0),    // Output area - takes remaining space
                Constraint::Length(1), // Status area - single line
                Constraint::Length(3), // Input area - 3 lines (content + borders)
                Constraint::Length(4), // Shortcuts area - 4 lines for shortcuts
            ])
            .split(size);

        // Render each section
        Self::render_output_area(frame, chunks[0], state);
        Self::render_status_area(frame, chunks[1], state);
        Self::render_input_area(frame, chunks[2], state);
        Self::render_shortcuts_area(frame, chunks[3]);

        // Render overlays (autocomplete and popups)
        if state.show_autocomplete {
            Self::render_autocomplete(frame, chunks[2], state);
        }

        if state.show_quit_popup {
            Self::render_quit_popup(frame, size);
        }
    }

    fn render_output_area(frame: &mut Frame, area: Rect, state: &AppState) {
        let output_lines = if state.output_lines.is_empty() {
            vec![Line::from(Span::styled(
                "No output yet...",
                Style::default()
                    .fg(Color::DarkGray)
                    .add_modifier(ratatui::style::Modifier::ITALIC),
            ))]
        } else {
            state
                .output_lines
                .iter()
                .skip(state.output_scroll.saturating_sub(area.height as usize))
                .take(area.height as usize)
                .cloned()
                .collect::<Vec<_>>()
        };

        let paragraph = Paragraph::new(output_lines).wrap(Wrap { trim: false });

        frame.render_widget(paragraph, area);
    }

    fn render_status_area(frame: &mut Frame, area: Rect, state: &AppState) {
        // Create a single line status bar with both agent status and token usage
        let status_text = format!(
            "Status: {} │ Tokens: In:{} Out:{} Total:{}",
            state.agent_status.display(),
            state.token_usage.input,
            state.token_usage.output,
            state.token_usage.total()
        );

        let status_paragraph = Paragraph::new(status_text).style(
            Style::default()
                .fg(Color::Gray)
                .add_modifier(ratatui::style::Modifier::DIM),
        );

        frame.render_widget(status_paragraph, area);
    }

    fn render_input_area(frame: &mut Frame, area: Rect, state: &AppState) {
        // Create styled prompt
        let prompt_span = Span::styled(
            "❯ ",
            Style::default()
                .fg(Color::Cyan)
                .add_modifier(ratatui::style::Modifier::BOLD),
        );

        let input_line = if state.input_text.is_empty() {
            // Show placeholder text
            let placeholder_span = Span::styled(
                "Type your task here...",
                Style::default()
                    .fg(Color::DarkGray)
                    .add_modifier(ratatui::style::Modifier::ITALIC),
            );
            Line::from(vec![prompt_span, placeholder_span])
        } else {
            // Show actual input text

            let input_span = Span::styled(&state.input_text, Style::default().fg(Color::White));
            Line::from(vec![prompt_span, input_span])
        };

        let input_paragraph = Paragraph::new(vec![input_line]).block(
            Block::default()
                .borders(Borders::ALL)
                .border_style(Style::default().fg(Color::Cyan))
                .title("Input"),
        );

        frame.render_widget(input_paragraph, area);

        // Position cursor after the prompt (accounting for border)
        let cursor_x = 1
            + 2
            + if state.input_text.is_empty() {
                0
            } else {
                state.input_cursor
            }; // border + "❯ " + cursor position

        frame.set_cursor_position(Position {
            x: area.x + cursor_x as u16,
            y: area.y + 1, // Account for top border
        });
    }

    fn render_shortcuts_area(frame: &mut Frame, area: Rect) {
        let shortcuts_lines = vec![
            // Main shortcuts with highlighting
            Line::from(vec![
                Span::styled(
                    "Enter",
                    Style::default()
                        .fg(Color::Yellow)
                        .add_modifier(ratatui::style::Modifier::BOLD),
                ),
                Span::styled(": Run │ ", Style::default().fg(Color::Gray)),
                Span::styled(
                    "Ctrl+C/Q/Esc",
                    Style::default()
                        .fg(Color::Red)
                        .add_modifier(ratatui::style::Modifier::BOLD),
                ),
                Span::styled(": Quit │ ", Style::default().fg(Color::Gray)),
                Span::styled(
                    "↑/↓",
                    Style::default()
                        .fg(Color::Blue)
                        .add_modifier(ratatui::style::Modifier::BOLD),
                ),
                Span::styled(": Scroll │ ", Style::default().fg(Color::Gray)),
                Span::styled(
                    "/help",
                    Style::default()
                        .fg(Color::Green)
                        .add_modifier(ratatui::style::Modifier::BOLD),
                ),
                Span::styled(": Help", Style::default().fg(Color::Gray)),
            ]),
            Line::from(""),
            // Commands line
            Line::from(vec![
                Span::styled("Commands: ", Style::default().fg(Color::DarkGray)),
                Span::styled("/help", Style::default().fg(Color::Green)),
                Span::styled(", ", Style::default().fg(Color::DarkGray)),
                Span::styled("/quit", Style::default().fg(Color::Red)),
                Span::styled(", ", Style::default().fg(Color::DarkGray)),
                Span::styled("/exit", Style::default().fg(Color::Red)),
            ]),
            Line::from(""),
        ];

        let shortcuts_paragraph = Paragraph::new(shortcuts_lines);
        frame.render_widget(shortcuts_paragraph, area);
    }

    fn render_autocomplete(frame: &mut Frame, input_area: Rect, state: &AppState) {
        if state.autocomplete_suggestions.is_empty() {
            return;
        }

        // Position autocomplete above the input area
        let autocomplete_height = std::cmp::min(state.autocomplete_suggestions.len() as u16 + 2, 6);
        let autocomplete_area = Rect {
            x: input_area.x,
            y: input_area.y.saturating_sub(autocomplete_height),
            width: std::cmp::min(input_area.width, 30),
            height: autocomplete_height,
        };

        // Create list items
        let items: Vec<ListItem> = state
            .autocomplete_suggestions
            .iter()
            .enumerate()
            .map(|(i, suggestion)| {
                let style = if i == state.autocomplete_selected {
                    Style::default()
                        .bg(Color::Blue)
                        .fg(Color::White)
                        .add_modifier(ratatui::style::Modifier::BOLD)
                } else {
                    Style::default().fg(Color::Gray)
                };
                ListItem::new(suggestion.as_str()).style(style)
            })
            .collect();

        let autocomplete_list = List::new(items)
            .block(
                Block::default()
                    .borders(Borders::ALL)
                    .border_style(Style::default().fg(Color::Cyan))
                    .title("Commands"),
            )
            .style(Style::default().bg(Color::Black));

        frame.render_widget(autocomplete_list, autocomplete_area);
    }

    fn render_quit_popup(frame: &mut Frame, area: Rect) {
        // Calculate popup size and position (centered)
        let popup_width = 50;
        let popup_height = 7;
        let popup_area = Rect {
            x: (area.width.saturating_sub(popup_width)) / 2,
            y: (area.height.saturating_sub(popup_height)) / 2,
            width: popup_width,
            height: popup_height,
        };

        // Clear the area behind the popup
        frame.render_widget(Clear, popup_area);

        // Create the popup content
        let popup_text = [
            "",
            "A task is currently running.",
            "",
            "Are you sure you want to quit?",
            "",
            "Press 'Y' to confirm, 'N' or Esc to cancel",
        ];

        let popup_content = popup_text.join("\n");

        let popup_block = Block::default()
            .title("Confirm Quit")
            .borders(Borders::ALL)
            .border_style(Style::default().fg(Color::Red))
            .style(Style::default().bg(Color::Black));

        let popup_paragraph = Paragraph::new(popup_content)
            .block(popup_block)
            .alignment(Alignment::Center)
            .style(Style::default().fg(Color::Yellow));

        frame.render_widget(popup_paragraph, popup_area);
    }
}
