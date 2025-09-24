// Copyright (c) 2025 ByteDance Ltd. and/or its affiliates
// SPDX-License-Identifier: MIT

use anyhow::Result;
use ratatui::{
    prelude::*,
    text::{Line, Span},
    widgets::{Block, Borders, Clear, List, ListItem, ListState, Paragraph, Wrap},
};
use std::path::PathBuf;
use trae_core::utils::review_history::{ReviewHistory, ReviewRecord, ReviewStatus};

/// Review history display component for the TUI
/// 
/// This component handles the display and interaction with review history records
/// in the terminal user interface, including navigation, selection, and detailed views.
pub struct ReviewHistoryDisplay {
    /// Collection of review records loaded from storage
    pub records: Vec<ReviewRecord>,
    /// State for the list widget to track selection and scrolling
    pub list_state: ListState,
    /// Currently selected record for detailed view
    pub selected_record: Option<ReviewRecord>,
    /// Whether to show detailed view of the selected record
    pub show_details: bool,
    /// Path to the storage directory for review records
    pub storage_path: PathBuf,
    /// Error message to display if loading fails
    pub error_message: Option<String>,
}

impl ReviewHistoryDisplay {
    /// Create a new review history display component
    /// 
    /// # Returns
    /// A new `ReviewHistoryDisplay` instance with default settings
    pub fn new() -> Self {
        Self {
            records: Vec::new(),
            list_state: ListState::default(),
            selected_record: None,
            show_details: false,
            storage_path: ReviewHistory::default_storage_path(),
            error_message: None,
        }
    }

    /// Load review records from storage
    /// 
    /// # Returns
    /// * `Ok(())` if records were loaded successfully
    /// * `Err(anyhow::Error)` if loading failed
    pub fn load_records(&mut self) -> Result<()> {
        let history: ReviewHistory = ReviewHistory::new(self.storage_path.clone());
        
        match history.load_all_records() {
            Ok(records) => {
                self.records = records;
                self.error_message = None;
                
                // Reset selection if no records
                if self.records.is_empty() {
                    self.list_state.select(None);
                    self.selected_record = None;
                } else {
                    // Select first record by default
                    self.list_state.select(Some(0));
                    self.selected_record = Some(self.records[0].clone());
                }
            }
            Err(e) => {
                self.error_message = Some(format!("Failed to load records: {}", e));
                self.records.clear();
                self.list_state.select(None);
                self.selected_record = None;
            }
        }
        
        Ok(())
    }

    /// Handle navigation input for the review history display
    /// 
    /// # Arguments
    /// * `key` - The key code from user input
    pub fn handle_navigation(&mut self, key: crossterm::event::KeyCode) {
        match key {
            crossterm::event::KeyCode::Up => {
                if !self.records.is_empty() {
                    let selected: usize = self.list_state.selected().unwrap_or(0);
                    let new_selected: usize = if selected > 0 { 
                        selected - 1 
                    } else { 
                        self.records.len() - 1 
                    };
                    self.list_state.select(Some(new_selected));
                    self.selected_record = Some(self.records[new_selected].clone());
                }
            }
            crossterm::event::KeyCode::Down => {
                if !self.records.is_empty() {
                    let selected: usize = self.list_state.selected().unwrap_or(0);
                    let new_selected: usize = if selected < self.records.len() - 1 { 
                        selected + 1 
                    } else { 
                        0 
                    };
                    self.list_state.select(Some(new_selected));
                    self.selected_record = Some(self.records[new_selected].clone());
                }
            }
            crossterm::event::KeyCode::Enter => {
                self.show_details = !self.show_details;
            }
            _ => {}
        }
    }

    /// Render the review history list widget
    /// 
    /// # Arguments
    /// * `frame` - The frame to render to
    /// * `area` - The rectangular area to render within
    pub fn render_list(&mut self, frame: &mut Frame, area: Rect) {
        // Create the list items
        let items: Vec<ListItem> = if self.records.is_empty() {
            if let Some(error) = &self.error_message {
                vec![ListItem::new(Line::from(vec![
                    Span::styled("❌ ", Style::default().fg(Color::Red)),
                    Span::styled(error, Style::default().fg(Color::Red)),
                ]))]
            } else {
                vec![ListItem::new(Line::from(vec![
                    Span::styled("📝 ", Style::default().fg(Color::Yellow)),
                    Span::styled("No review records found", Style::default().fg(Color::Gray)),
                ]))]
            }
        } else {
            self.records
                .iter()
                .map(|record: &ReviewRecord| {
                    let status_icon: &str = match record.status {
                        ReviewStatus::Pending => "⏳",
                        ReviewStatus::InProgress => "🔄",
                        ReviewStatus::Completed => "✅",
                        ReviewStatus::Rejected => "❌",
                        ReviewStatus::Approved => "✅",
                    };

                    let status_color: Color = match record.status {
                        ReviewStatus::Pending => Color::Yellow,
                        ReviewStatus::InProgress => Color::Blue,
                        ReviewStatus::Completed => Color::Green,
                        ReviewStatus::Rejected => Color::Red,
                        ReviewStatus::Approved => Color::Green,
                    };

                    let rating_text: String = if let Some(rating) = record.rating {
                        format!(" ({}⭐)", rating)
                    } else {
                        String::new()
                    };

                    ListItem::new(Line::from(vec![
                        Span::styled(format!("{} ", status_icon), Style::default().fg(status_color)),
                        Span::styled(&record.task_description, Style::default().fg(Color::White)),
                        Span::styled(rating_text, Style::default().fg(Color::Yellow)),
                        Span::styled(
                            format!(" - {}", record.reviewer),
                            Style::default().fg(Color::Gray),
                        ),
                    ]))
                })
                .collect()
        };

        // Create the list widget
        let list: List = List::new(items)
            .block(
                Block::default()
                    .title("📋 Review History")
                    .borders(Borders::ALL)
                    .border_style(Style::default().fg(Color::Cyan)),
            )
            .highlight_style(
                Style::default()
                    .bg(Color::DarkGray)
                    .add_modifier(Modifier::BOLD),
            )
            .highlight_symbol("▶ ");

        frame.render_stateful_widget(list, area, &mut self.list_state);
    }

    /// Render the detailed view of a selected record
    /// 
    /// # Arguments
    /// * `frame` - The frame to render to
    /// * `area` - The rectangular area to render within
    pub fn render_details(&self, frame: &mut Frame, area: Rect) {
        if let Some(record) = &self.selected_record {
            // Create detailed content
            let mut lines: Vec<Line> = Vec::new();

            // Title
            lines.push(Line::from(vec![
                Span::styled("📋 Task: ", Style::default().fg(Color::Cyan).add_modifier(Modifier::BOLD)),
                Span::styled(&record.task_description, Style::default().fg(Color::White)),
            ]));
            lines.push(Line::from(""));

            // Basic info
            lines.push(Line::from(vec![
                Span::styled("👤 Reviewer: ", Style::default().fg(Color::Green)),
                Span::styled(&record.reviewer, Style::default().fg(Color::White)),
            ]));

            let status_text: String = format!("{:?}", record.status);
            let status_color: Color = match record.status {
                ReviewStatus::Pending => Color::Yellow,
                ReviewStatus::InProgress => Color::Blue,
                ReviewStatus::Completed => Color::Green,
                ReviewStatus::Rejected => Color::Red,
                ReviewStatus::Approved => Color::Green,
            };
            lines.push(Line::from(vec![
                Span::styled("📊 Status: ", Style::default().fg(Color::Green)),
                Span::styled(status_text, Style::default().fg(status_color)),
            ]));

            if let Some(rating) = record.rating {
                lines.push(Line::from(vec![
                    Span::styled("⭐ Rating: ", Style::default().fg(Color::Green)),
                    Span::styled(format!("{}/5", rating), Style::default().fg(Color::Yellow)),
                ]));
            }

            if let Some(duration) = record.duration_seconds {
                let hours: u64 = duration / 3600;
                let minutes: u64 = (duration % 3600) / 60;
                let duration_text: String = if hours > 0 {
                    format!("{}h {}m", hours, minutes)
                } else {
                    format!("{}m", minutes)
                };
                lines.push(Line::from(vec![
                    Span::styled("⏱️  Duration: ", Style::default().fg(Color::Green)),
                    Span::styled(duration_text, Style::default().fg(Color::White)),
                ]));
            }

            lines.push(Line::from(""));

            // Tags
            if !record.tags.is_empty() {
                lines.push(Line::from(vec![
                    Span::styled("🏷️  Tags: ", Style::default().fg(Color::Green)),
                    Span::styled(record.tags.join(", "), Style::default().fg(Color::Magenta)),
                ]));
                lines.push(Line::from(""));
            }

            // Files reviewed
            if !record.files_reviewed.is_empty() {
                lines.push(Line::from(vec![
                    Span::styled("📁 Files Reviewed:", Style::default().fg(Color::Green).add_modifier(Modifier::BOLD)),
                ]));
                for file in &record.files_reviewed {
                    lines.push(Line::from(vec![
                        Span::styled("  • ", Style::default().fg(Color::Gray)),
                        Span::styled(file, Style::default().fg(Color::White)),
                    ]));
                }
                lines.push(Line::from(""));
            }

            // Comments
            if !record.comments.is_empty() {
                lines.push(Line::from(vec![
                    Span::styled("💬 Comments:", Style::default().fg(Color::Green).add_modifier(Modifier::BOLD)),
                ]));
                for comment in &record.comments {
                    let comment_icon: &str = match comment.comment_type {
                        trae_core::utils::review_history::CommentType::General => "💬",
                        trae_core::utils::review_history::CommentType::Suggestion => "💡",
                        trae_core::utils::review_history::CommentType::Issue => "⚠️",
                        trae_core::utils::review_history::CommentType::Praise => "👍",
                        trae_core::utils::review_history::CommentType::Question => "❓",
                    };

                    lines.push(Line::from(vec![
                        Span::styled(format!("  {} ", comment_icon), Style::default().fg(Color::Yellow)),
                        Span::styled(&comment.author, Style::default().fg(Color::Cyan)),
                        Span::styled(": ", Style::default().fg(Color::Gray)),
                        Span::styled(&comment.content, Style::default().fg(Color::White)),
                    ]));

                    if let Some(file_path) = &comment.file_path {
                        let location_text: String = if let Some(line_num) = comment.line_number {
                            format!("    📍 {}:{}", file_path, line_num)
                        } else {
                            format!("    📍 {}", file_path)
                        };
                        lines.push(Line::from(vec![
                            Span::styled(location_text, Style::default().fg(Color::Gray)),
                        ]));
                    }
                    lines.push(Line::from(""));
                }
            }

            // Timestamps
            lines.push(Line::from(vec![
                Span::styled("📅 Created: ", Style::default().fg(Color::Gray)),
                Span::styled(&record.created_at, Style::default().fg(Color::White)),
            ]));
            lines.push(Line::from(vec![
                Span::styled("📅 Updated: ", Style::default().fg(Color::Gray)),
                Span::styled(&record.updated_at, Style::default().fg(Color::White)),
            ]));

            let paragraph: Paragraph = Paragraph::new(lines)
                .block(
                    Block::default()
                        .title("📄 Review Details")
                        .borders(Borders::ALL)
                        .border_style(Style::default().fg(Color::Green)),
                )
                .wrap(Wrap { trim: true });

            frame.render_widget(paragraph, area);
        } else {
            let paragraph: Paragraph = Paragraph::new("No record selected")
                .block(
                    Block::default()
                        .title("📄 Review Details")
                        .borders(Borders::ALL)
                        .border_style(Style::default().fg(Color::Gray)),
                )
                .style(Style::default().fg(Color::Gray));

            frame.render_widget(paragraph, area);
        }
    }

    /// Render the review history popup overlay
    /// 
    /// # Arguments
    /// * `frame` - The frame to render to
    /// * `area` - The rectangular area to render within
    pub fn render_popup(&mut self, frame: &mut Frame, area: Rect) {
        // Calculate popup size (80% of screen)
        let popup_width: u16 = (area.width * 80) / 100;
        let popup_height: u16 = (area.height * 80) / 100;
        let popup_x: u16 = (area.width - popup_width) / 2;
        let popup_y: u16 = (area.height - popup_height) / 2;

        let popup_area: Rect = Rect {
            x: popup_x,
            y: popup_y,
            width: popup_width,
            height: popup_height,
        };

        // Clear the background
        frame.render_widget(Clear, popup_area);

        // Split the popup into list and details
        let chunks: std::rc::Rc<[Rect]> = Layout::default()
            .direction(Direction::Horizontal)
            .constraints([Constraint::Percentage(40), Constraint::Percentage(60)])
            .split(popup_area);

        // Render list and details
        self.render_list(frame, chunks[0]);
        self.render_details(frame, chunks[1]);

        // Add help text at the bottom
        let help_area: Rect = Rect {
            x: popup_area.x,
            y: popup_area.y + popup_area.height - 3,
            width: popup_area.width,
            height: 3,
        };

        let help_text: &str = if self.show_details {
            "↑/↓: Navigate • Enter: Toggle Details • Esc: Close • R: Refresh"
        } else {
            "↑/↓: Navigate • Enter: Show Details • Esc: Close • R: Refresh"
        };

        let help_paragraph: Paragraph = Paragraph::new(help_text)
            .block(
                Block::default()
                    .borders(Borders::TOP)
                    .border_style(Style::default().fg(Color::Gray)),
            )
            .style(Style::default().fg(Color::Gray))
            .alignment(Alignment::Center);

        frame.render_widget(help_paragraph, help_area);
    }

    /// Get the number of records currently loaded
    /// 
    /// # Returns
    /// The count of review records
    pub fn record_count(&self) -> usize {
        self.records.len()
    }

    /// Check if there are any records loaded
    /// 
    /// # Returns
    /// `true` if records exist, `false` otherwise
    pub fn has_records(&self) -> bool {
        !self.records.is_empty()
    }
}

impl Default for ReviewHistoryDisplay {
    /// Create a default instance of ReviewHistoryDisplay
    /// 
    /// # Returns
    /// A new `ReviewHistoryDisplay` instance with default settings
    fn default() -> Self {
        Self::new()
    }
}