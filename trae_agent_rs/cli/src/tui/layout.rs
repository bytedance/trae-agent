// Copyright (c) 2025 ByteDance Ltd. and/or its affiliates
// SPDX-License-Identifier: MIT

use ratatui::{
    Frame,
    layout::{Alignment, Constraint, Direction, Rect},
    prelude::*,
    text::{Line, Span},
    widgets::{Block, Borders, Clear, List, ListItem, Paragraph, Wrap},
};

use super::{popup_input::PopupInputEditor, review_history::ReviewHistoryDisplay, settings::SettingsEditor, state::AppState};

pub struct Layout;

impl Layout {
    /// Create the main layout with 4 sections:
    /// - Top: Agent output (takes remaining space)
    /// - Agent state and token usage (minimal height needed)
    /// - Input box (minimal height needed)
    /// - Shortcuts (minimal height needed)
    pub fn render(
        frame: &mut Frame, 
        state: &mut AppState, 
        settings_editor: &Option<SettingsEditor>,
        popup_input_editor: &mut PopupInputEditor,
        review_history: &mut ReviewHistoryDisplay,
        show_review_history: bool,
    ) {
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

        if state.show_settings {
            Self::render_settings_popup(frame, size, state, settings_editor);
        }

        if state.show_popup_input {
            Self::render_popup_input(frame, size, popup_input_editor);
        }

        if show_review_history {
            review_history.render_popup(frame, size);
        }

        if state.show_step_history {
            Self::render_step_history_popup(frame, size, state);
        }
    }

    fn render_output_area(frame: &mut Frame, area: Rect, state: &mut AppState) {
        let output_lines = if state.output_lines.is_empty() {
            vec![Line::from(Span::styled(
                "No output yet...",
                Style::default()
                    .fg(Color::DarkGray)
                    .add_modifier(ratatui::style::Modifier::ITALIC),
            ))]
        } else {
            state.output_lines.iter().cloned().collect::<Vec<_>>()
        };

        // Calculate scroll parameters
        let total_lines = output_lines.len();
        let visible_height = area.height as usize;
        
        // Clamp scroll position to valid bounds
        state.clamp_scroll(visible_height);
        
        // output_scroll represents the number of lines to skip from the top
        let max_scroll = if total_lines > visible_height {
            total_lines - visible_height
        } else {
            0
        };
        
        let clamped_scroll = std::cmp::min(state.output_scroll, max_scroll);

        // Create scroll indicator for the title
        let scroll_info = if total_lines > visible_height {
            format!(" [{}]", state.get_scroll_info(visible_height))
        } else {
            String::new()
        };

        // Create title with scroll indicator
        let title = format!("Output{}", scroll_info);
        
        // Create the paragraph with proper scrolling
        let visible_lines = if total_lines == 0 {
            // No content case
            output_lines
        } else if total_lines <= visible_height {
            // Content fits entirely in view - no scrolling needed
            output_lines
        } else {
            // Content is larger than view - apply scrolling
            let start = clamped_scroll;
            let end = std::cmp::min(start + visible_height, total_lines);
            if start < total_lines {
                output_lines[start..end].to_vec()
            } else {
                // Fallback if scroll position is invalid
                output_lines
            }
        };
        
        let paragraph = Paragraph::new(visible_lines)
            .wrap(Wrap { trim: false })
            .block(
                Block::default()
                    .borders(Borders::ALL)
                    .title(title)
                    .border_style(Style::default().fg(Color::Gray))
            );

        frame.render_widget(paragraph, area);
    }

    fn render_status_area(frame: &mut Frame, area: Rect, state: &AppState) {
        // Create a single line status bar with both agent status and token usage
        let status_text = format!(
            "Status: {} │ Tokens: ⬆️ {} ⬇️ {}",
            state.agent_status.display(),
            state.token_usage.input,
            state.token_usage.output,
        );

        let status_paragraph = Paragraph::new(status_text).style(
            Style::default()
                .fg(Color::Gray)
                .add_modifier(ratatui::style::Modifier::DIM),
        );

        frame.render_widget(status_paragraph, area);
    }

    fn render_input_area(frame: &mut Frame, area: Rect, state: &mut AppState) {
        // Adjust horizontal scroll before rendering to ensure cursor visibility
        state.adjust_input_horizontal_scroll(area.width as usize);
        
        // Render the multi-line input widget
        state.input.render(frame, area);
    }

    fn render_shortcuts_area(frame: &mut Frame, area: Rect) {
        let shortcuts = vec![
            Line::from(vec![
                Span::styled("Enter", Style::default().fg(Color::Yellow)),
                Span::raw(": Submit │ "),
                Span::styled("Shift+Enter", Style::default().fg(Color::Yellow)),
                Span::raw(": New line │ "),
                Span::styled("↑/↓", Style::default().fg(Color::Yellow)),
                Span::raw(": History │ "),
                Span::styled("Tab", Style::default().fg(Color::Yellow)),
                Span::raw(": Autocomplete"),
            ]),
            Line::from(vec![
                Span::styled("Shift+↑/↓", Style::default().fg(Color::Yellow)),
                Span::raw(": Scroll │ "),
                Span::styled("Ctrl+K/J", Style::default().fg(Color::Yellow)),
                Span::raw(": Scroll line │ "),
                Span::styled("Ctrl+U/D", Style::default().fg(Color::Yellow)),
                Span::raw(": Scroll page │ "),
                Span::styled("PgUp/PgDn", Style::default().fg(Color::Yellow)),
                Span::raw(": Page scroll"),
            ]),
            Line::from(vec![
                Span::styled("Ctrl+Home/End", Style::default().fg(Color::Yellow)),
                Span::raw(": Top/Bottom │ "),
                Span::styled("Ctrl+H", Style::default().fg(Color::Yellow)),
                Span::raw(": History │ "),
                Span::styled("Ctrl+Q", Style::default().fg(Color::Yellow)),
                Span::raw(": Quit"),
            ]),
        ];

        let shortcuts_paragraph = Paragraph::new(shortcuts);
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

    fn render_settings_popup(
        frame: &mut Frame,
        area: Rect,
        _state: &AppState,
        settings_editor: &Option<SettingsEditor>,
    ) {
        // Calculate popup size (larger than quit popup for form fields)
        let popup_width = 80;
        let popup_height = 18;
        let x = (area.width.saturating_sub(popup_width)) / 2;
        let y = (area.height.saturating_sub(popup_height)) / 2;
        let popup_area = Rect::new(x, y, popup_width, popup_height);

        // Clear the area behind the popup
        frame.render_widget(Clear, popup_area);

        // Create the popup content with form fields
        let popup_block = Block::default()
            .title("Settings")
            .borders(Borders::ALL)
            .border_style(Style::default().fg(Color::Green))
            .style(Style::default().bg(Color::Black));

        // Split popup into sections for each field
        let inner_area = popup_block.inner(popup_area);
        let field_chunks = ratatui::layout::Layout::default()
            .direction(Direction::Vertical)
            .constraints([
                Constraint::Length(2), // Provider
                Constraint::Length(2), // Model
                Constraint::Length(2), // API Key
                Constraint::Length(2), // Base URL
                Constraint::Length(2), // Workspace
                Constraint::Length(1), // Instructions
                Constraint::Min(0),    // Remaining space
            ])
            .split(inner_area);

        // Render the popup border
        frame.render_widget(popup_block, popup_area);

        // Get actual settings values from editor
        if let Some(editor) = settings_editor {
            let current_field = editor.get_current_field();

            // Render each field
            for i in 0..SettingsEditor::field_count() {
                if i < field_chunks.len() - 2 {
                    let is_selected = i == current_field;
                    let is_editing = editor.editing_field == Some(i);
                    let is_editable = editor.is_field_editable(i);

                    let label = SettingsEditor::field_name(i);
                    let value = editor.field_value(i);

                    let display_value = if is_editing {
                        // Show current input when editing
                        &editor.temp_input
                    } else {
                        &value
                    };

                    let field_text = if is_editing {
                        format!("{}: {}|", label, display_value) // Add cursor indicator
                    } else {
                        format!("{}: {}", label, display_value)
                    };

                    let style = if is_editing {
                        Style::default().fg(Color::Green).bg(Color::DarkGray)
                    } else if is_selected && !is_editable {
                        Style::default().fg(Color::Gray).bg(Color::DarkGray)
                    } else if is_selected {
                        Style::default().fg(Color::Yellow).bg(Color::DarkGray)
                    } else if !is_editable {
                        Style::default().fg(Color::Gray)
                    } else {
                        Style::default().fg(Color::White)
                    };

                    let field_paragraph = Paragraph::new(field_text).style(style);
                    frame.render_widget(field_paragraph, field_chunks[i]);
                }
            }
        }

        // Render instructions
        let instructions = if let Some(editor) = settings_editor {
            if editor.editing_field.is_some() {
                "Enter: Confirm • Esc: Cancel"
            } else {
                "Tab/↑↓: Navigate • Enter: Edit (Workspace is read-only) • s: Save • Esc: Close"
            }
        } else {
            "Tab/↑↓: Navigate • Enter: Edit (Workspace is read-only) • s: Save • Esc: Close"
        };
        let instructions_paragraph = Paragraph::new(instructions)
            .style(Style::default().fg(Color::Gray))
            .alignment(Alignment::Center);
        frame.render_widget(instructions_paragraph, field_chunks[5]);
    }

    fn render_popup_input(
        frame: &mut Frame,
        area: Rect,
        popup_input_editor: &mut PopupInputEditor,
    ) {
        // Calculate popup size (larger than settings popup for multiline input)
        let popup_width = std::cmp::min(100, area.width.saturating_sub(4));
        let popup_height = std::cmp::min(25, area.height.saturating_sub(4));
        let x = (area.width.saturating_sub(popup_width)) / 2;
        let y = (area.height.saturating_sub(popup_height)) / 2;
        let popup_area = Rect::new(x, y, popup_width, popup_height);

        // Update scroll to ensure proper display of multi-line content
        popup_input_editor.update_scroll(popup_height as usize);

        // Clear the area behind the popup
        frame.render_widget(Clear, popup_area);

        // Create the popup block
        let popup_block = Block::default()
            .title(popup_input_editor.title.clone())
            .borders(Borders::ALL)
            .border_style(Style::default().fg(Color::Blue))
            .style(Style::default().bg(Color::Black));

        // Split popup into sections
        let inner_area = popup_block.inner(popup_area);
        let popup_chunks = ratatui::layout::Layout::default()
            .direction(Direction::Vertical)
            .constraints([
                Constraint::Min(0),    // Text content area
                Constraint::Length(1), // Instructions
            ])
            .split(inner_area);

        // Render the popup border
        frame.render_widget(popup_block, popup_area);

        // Render text content
        let lines = popup_input_editor.get_lines();
        let scroll_offset = popup_input_editor.get_scroll_offset();
        let horizontal_scroll = popup_input_editor.get_horizontal_scroll();
        let (cursor_line, cursor_col) = popup_input_editor.get_cursor_position();

        let content_height = popup_chunks[0].height as usize;
        let content_width = popup_chunks[0].width as usize;

        // Create display lines with cursor
        let mut display_lines = Vec::new();
        let visible_start = scroll_offset;
        let visible_end = std::cmp::min(lines.len(), visible_start + content_height);

        for (line_idx, line) in lines.iter().enumerate().skip(visible_start).take(content_height) {
            if line_idx >= visible_end {
                break;
            }

            let mut display_line = if line.len() > horizontal_scroll {
                line.chars().skip(horizontal_scroll).take(content_width).collect::<String>()
            } else {
                String::new()
            };

            // Add cursor if this is the cursor line
            if line_idx == cursor_line {
                let cursor_pos_in_line = if cursor_col >= horizontal_scroll {
                    cursor_col.saturating_sub(horizontal_scroll)
                } else {
                    0
                };

                if cursor_pos_in_line <= display_line.len() {
                    // Insert cursor character
                    if cursor_pos_in_line == display_line.len() {
                        display_line.push('│');
                    } else {
                        display_line.insert(cursor_pos_in_line, '│');
                    }
                }
            }

            display_lines.push(Line::from(display_line));
        }

        // Fill remaining lines if needed
        while display_lines.len() < content_height {
            display_lines.push(Line::from(""));
        }

        let content_paragraph = Paragraph::new(display_lines)
            .style(Style::default().fg(Color::White))
            .wrap(Wrap { trim: false });
        frame.render_widget(content_paragraph, popup_chunks[0]);

        // Render instructions
        let instructions_paragraph = Paragraph::new(popup_input_editor.instructions.clone())
            .style(Style::default().fg(Color::Gray))
            .wrap(Wrap { trim: false });
        frame.render_widget(instructions_paragraph, popup_chunks[1]);
    }

    fn render_step_history_popup(frame: &mut Frame, area: Rect, state: &AppState) {
        // Clear the background
        frame.render_widget(Clear, area);

        // Create popup area (80% of screen)
        let popup_width = (area.width as f32 * 0.8) as u16;
        let popup_height = (area.height as f32 * 0.8) as u16;
        let popup_x = (area.width.saturating_sub(popup_width)) / 2;
        let popup_y = (area.height.saturating_sub(popup_height)) / 2;
        
        let popup_area = Rect {
            x: popup_x,
            y: popup_y,
            width: popup_width,
            height: popup_height,
        };

        // Create main block
        let block = Block::default()
            .title("Step History (Ctrl+H to close)")
            .borders(Borders::ALL)
            .style(Style::default().fg(Color::White));
        frame.render_widget(block, popup_area);

        // Create inner area for content
        let inner_area = popup_area.inner(ratatui::layout::Margin { horizontal: 1, vertical: 1 });

        // Split into two panels: step list (left) and step content (right)
        let panels = ratatui::layout::Layout::default()
            .direction(Direction::Horizontal)
            .constraints([
                Constraint::Percentage(30), // Step list
                Constraint::Percentage(70), // Step content
            ])
            .split(inner_area);

        // Render step list
        Self::render_step_list(frame, panels[0], state);
        
        // Render step content
        Self::render_step_content(frame, panels[1], state);
    }

    fn render_step_list(frame: &mut Frame, area: Rect, state: &AppState) {
        let block = Block::default()
            .title("Steps")
            .borders(Borders::ALL)
            .style(Style::default().fg(Color::Blue));

        let inner_area = area.inner(ratatui::layout::Margin { horizontal: 1, vertical: 1 });

        if state.step_history.is_empty() {
            let no_steps = Paragraph::new("No steps recorded yet")
                .style(Style::default().fg(Color::Gray))
                .alignment(Alignment::Center);
            frame.render_widget(block, area);
            frame.render_widget(no_steps, inner_area);
            return;
        }

        // Create list items for each step
        let items: Vec<ListItem> = state.step_history
            .iter()
            .enumerate()
            .map(|(idx, step)| {
                let is_selected = state.history_view_index == Some(idx);
                let status_icon = match step.status {
                    super::state::AgentStatus::Running => "🔄",
                    super::state::AgentStatus::Idle => "✅",
                    super::state::AgentStatus::Thinking => "🤔",
                    super::state::AgentStatus::CallingTool => "🔧",
                    super::state::AgentStatus::Reflecting => "💭",
                    super::state::AgentStatus::Completed => "✅",
                    super::state::AgentStatus::Error(_) => "❌",
                };
                
                let style = if is_selected {
                    Style::default().bg(Color::Blue).fg(Color::White)
                } else {
                    Style::default().fg(Color::White)
                };

                let content = format!("{} Step {}: {}", 
                    status_icon, 
                    step.step_number, 
                    step.description.chars().take(40).collect::<String>()
                );
                
                ListItem::new(content).style(style)
            })
            .collect();

        let list = List::new(items)
            .style(Style::default().fg(Color::White));

        frame.render_widget(block, area);
        frame.render_widget(list, inner_area);
    }

    fn render_step_content(frame: &mut Frame, area: Rect, state: &AppState) {
        let block = Block::default()
            .title("Step Details")
            .borders(Borders::ALL)
            .style(Style::default().fg(Color::Green));

        let inner_area = area.inner(ratatui::layout::Margin { horizontal: 1, vertical: 1 });

        if let Some(step) = state.get_current_viewed_step() {
            // Create header with step info
            let header_height = 3;
            let content_area = Rect {
                x: inner_area.x,
                y: inner_area.y + header_height,
                width: inner_area.width,
                height: inner_area.height.saturating_sub(header_height),
            };
            
            let header_area = Rect {
                x: inner_area.x,
                y: inner_area.y,
                width: inner_area.width,
                height: header_height,
            };

            // Render header
            let header_lines = vec![
                Line::from(vec![
                    Span::styled("Step: ", Style::default().fg(Color::Yellow)),
                    Span::styled(step.step_number.to_string(), Style::default().fg(Color::White)),
                ]),
                Line::from(vec![
                    Span::styled("Time: ", Style::default().fg(Color::Yellow)),
                    Span::styled(step.formatted_timestamp(), Style::default().fg(Color::White)),
                ]),
                Line::from(vec![
                    Span::styled("Description: ", Style::default().fg(Color::Yellow)),
                    Span::styled(&step.description, Style::default().fg(Color::White)),
                ]),
            ];
            
            let header_paragraph = Paragraph::new(header_lines);
            frame.render_widget(header_paragraph, header_area);

            // Render step content with scrolling
            let visible_height = content_area.height as usize;
            let total_lines = step.output_lines.len();
            let scroll_offset = state.step_content_scroll;
            
            let visible_lines = if total_lines == 0 {
                vec![Line::from("No output for this step")]
            } else if total_lines <= visible_height {
                step.output_lines.clone()
            } else {
                let start = scroll_offset.min(total_lines.saturating_sub(visible_height));
                let end = (start + visible_height).min(total_lines);
                step.output_lines[start..end].to_vec()
            };

            let content_paragraph = Paragraph::new(visible_lines)
                .wrap(Wrap { trim: false });
            frame.render_widget(content_paragraph, content_area);
        } else {
            let no_selection = Paragraph::new("Select a step to view details")
                .style(Style::default().fg(Color::Gray))
                .alignment(Alignment::Center);
            frame.render_widget(no_selection, inner_area);
        }

        frame.render_widget(block, area);
    }
}
