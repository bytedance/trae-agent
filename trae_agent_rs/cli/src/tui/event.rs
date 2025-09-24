// Copyright (c) 2025 ByteDance Ltd. and/or its affiliates
// SPDX-License-Identifier: MIT

use crossterm::event::{self, KeyCode, KeyEvent, KeyModifiers};
use std::time::Duration;
use tokio::sync::mpsc;
use tokio::task::JoinHandle;

use crate::tui::state::{AgentStatus, TokenUsage};

#[derive(Debug, Clone)]
pub enum Event {
    Key(KeyEvent),
    Tick,
    Quit,
    AgentOutput(String),
    AgentStatusUpdate(AgentStatus),
    TokenUsageUpdate(TokenUsage),
    AgentStepUpdate { step: u32, description: String },
    AgentError(String),
    TaskCompleted(String),
}

pub struct EventHandler {
    event_tx: mpsc::UnboundedSender<Event>,
    event_rx: mpsc::UnboundedReceiver<Event>,
    event_loop_handle: Option<JoinHandle<()>>,
}

impl EventHandler {
    pub fn new() -> Self {
        let (event_tx, event_rx) = mpsc::unbounded_channel();
        Self {
            event_tx,
            event_rx,
            event_loop_handle: None,
        }
    }

    pub fn sender(&self) -> mpsc::UnboundedSender<Event> {
        self.event_tx.clone()
    }

    pub async fn next(&mut self) -> Option<Event> {
        self.event_rx.recv().await
    }

    pub async fn start_event_loop(&mut self) {
        let tx = self.event_tx.clone();

        let handle = tokio::spawn(async move {
            // Terminal event polling
            let mut interval = tokio::time::interval(Duration::from_millis(100));

            loop {
                tokio::select! {
                    _ = interval.tick() => {
                        // Check for terminal events
                        if event::poll(Duration::from_millis(0)).unwrap_or(false)
                            && let Ok(event::Event::Key(key_event)) = event::read()
                            && tx.send(Event::Key(key_event)).is_err() {
                            break;
                        }
                        // Send tick event
                        if tx.send(Event::Tick).is_err() {
                            break;
                        }
                    }
                }
            }
        });

        self.event_loop_handle = Some(handle);
    }

    pub async fn stop(&mut self) {
        if let Some(handle) = self.event_loop_handle.take() {
            handle.abort();
            let _ = handle.await;
        }
    }
}

impl Default for EventHandler {
    fn default() -> Self {
        Self::new()
    }
}

pub fn handle_key_event(key_event: KeyEvent) -> Option<Event> {
    match key_event.code {
        KeyCode::Char('c') if key_event.modifiers.contains(KeyModifiers::CONTROL) => {
            Some(Event::Quit)
        }
        KeyCode::Char('q') if key_event.modifiers.contains(KeyModifiers::CONTROL) => {
            Some(Event::Quit)
        }
        KeyCode::Esc => Some(Event::Quit),
        _ => Some(Event::Key(key_event)),
    }
}
