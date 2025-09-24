#[cfg(test)]
mod tests {
    use super::super::state::{AppState, StepHistoryEntry, AgentStatus};
    use ratatui::text::Line;

    #[test]
    fn test_step_history_basic_operations() {
        let mut state = AppState::default();
        
        // Test starting a new step
        state.start_new_step(1, "Test step 1".to_string());
        assert_eq!(state.current_step, Some(1));
        assert_eq!(state.step_history.len(), 1);
        assert_eq!(state.step_history[0].description, "Test step 1");
        assert_eq!(state.step_history[0].step_number, 1);
        
        // Test adding output to current step
        let line = Line::from("Test output line");
        state.add_output_to_current_step(line.clone());
        assert_eq!(state.step_history[0].output_lines.len(), 1);
        
        // Test updating step status
        state.update_current_step_status(AgentStatus::Running);
        assert!(matches!(state.step_history[0].status, AgentStatus::Running));
        
        // Test completing current step
        state.complete_current_step();
        assert!(matches!(state.step_history[0].status, AgentStatus::Completed));
        assert_eq!(state.current_step, None);
        
        // Test starting another step
        state.start_new_step(2, "Test step 2".to_string());
        assert_eq!(state.current_step, Some(2));
        assert_eq!(state.step_history.len(), 2);
        assert_eq!(state.step_history[1].step_number, 2);
    }
    
    #[test]
    fn test_step_history_navigation() {
        let mut state = AppState::default();
        
        // Create some test steps
        for i in 1..=5 {
            state.start_new_step(i, format!("Step {}", i));
            let line = Line::from(format!("Output for step {}", i));
            state.add_output_to_current_step(line);
            state.complete_current_step();
        }
        
        // Test toggling history view
        assert!(!state.show_step_history);
        state.toggle_step_history_view();
        assert!(state.show_step_history);
        
        // Test navigation
        assert_eq!(state.history_view_index, Some(4)); // Should start at last step (0-indexed)
        
        state.navigate_step_history_previous();
        assert_eq!(state.history_view_index, Some(3));
        
        state.navigate_step_history_next();
        assert_eq!(state.history_view_index, Some(4));
        
        state.navigate_step_history_first();
        assert_eq!(state.history_view_index, Some(0));
        
        state.navigate_step_history_last();
        assert_eq!(state.history_view_index, Some(4));
        
        // Test getting current viewed step
        let current_step = state.get_current_viewed_step();
        assert!(current_step.is_some());
        assert_eq!(current_step.unwrap().step_number, 5);
        
        // Test position info
        if let Some((current, total)) = state.get_step_history_position() {
            assert_eq!(current, 5);
            assert_eq!(total, 5);
        }
    }
    
    #[test]
    fn test_step_content_scrolling() {
        let mut state = AppState::default();
        
        // Create a step with multiple output lines
        state.start_new_step(1, "Test step".to_string());
        for i in 1..=20 {
            let line = Line::from(format!("Line {}", i));
            state.add_output_to_current_step(line);
        }
        state.complete_current_step();
        
        state.toggle_step_history_view();
        
        // Test scrolling
        assert_eq!(state.step_content_scroll, 0);
        
        state.scroll_step_content_down(10); // max_lines = 10
        assert_eq!(state.step_content_scroll, 1); // Should increment by 1
        
        state.scroll_step_content_up();
        assert_eq!(state.step_content_scroll, 0);
        
        // Test scroll bounds
        for _ in 0..20 {
            state.scroll_step_content_up();
        }
        assert_eq!(state.step_content_scroll, 0); // Should not go below 0
    }
    
    #[test]
    fn test_step_history_entry_timestamp_formatting() {
        let entry = StepHistoryEntry::new(1, "Test step".to_string(), AgentStatus::Completed);
        let formatted = entry.formatted_timestamp();
        
        // Should format as relative time (e.g., "0s ago", "2m ago", etc.)
        assert!(formatted.len() >= 5); // Minimum is "0s ago" (5 characters)
        assert!(formatted.contains("ago"));
    }
    
    #[test]
    fn test_clear_step_history() {
        let mut state = AppState::default();
        
        // Create some steps
        for i in 1..=3 {
            state.start_new_step(i, format!("Step {}", i));
            state.complete_current_step();
        }
        
        assert_eq!(state.step_history.len(), 3);
        
        state.clear_step_history();
        assert_eq!(state.step_history.len(), 0);
        assert_eq!(state.current_step, None);
        assert_eq!(state.history_view_index, None);
        assert_eq!(state.step_content_scroll, 0);
    }

    #[test]
    fn test_context_preservation_during_step_history_navigation() {
        let mut state = AppState::default();
        
        // Set up some initial state
        state.input.set_text("test input".to_string());
        state.output_scroll = 5;
        
        // Add some step history
        state.start_new_step(1, "Step 1".to_string());
        state.start_new_step(2, "Step 2".to_string());
        
        // Enter step history view
        state.toggle_step_history_view();
        
        // Verify context is saved and we're in history view
        assert!(state.show_step_history);
        assert!(state.is_navigating_step_history());
        assert_eq!(state.step_history_temp_input, Some("test input".to_string()));
        assert_eq!(state.step_history_temp_output_scroll, Some(5));
        
        // Modify input and scroll while in history view (this should not affect saved context)
        state.input.set_text("modified input".to_string());
        state.output_scroll = 10;
        
        // Exit step history view
        state.toggle_step_history_view();
        
        // Verify context is restored
        assert!(!state.show_step_history);
        assert!(!state.is_navigating_step_history());
        assert_eq!(state.get_input_text(), "test input");
        assert_eq!(state.output_scroll, 5);
        assert_eq!(state.step_history_temp_input, None);
        assert_eq!(state.step_history_temp_output_scroll, None);
    }

    #[test]
    fn test_step_history_navigation_state_check() {
        let mut state = AppState::default();
        
        // Initially not navigating
        assert!(!state.is_navigating_step_history());
        
        // Add some steps
        state.start_new_step(1, "Step 1".to_string());
        
        // Still not navigating until we enter history view
        assert!(!state.is_navigating_step_history());
        
        // Enter history view
        state.toggle_step_history_view();
        
        // Now we should be navigating
        assert!(state.is_navigating_step_history());
        
        // Exit history view
        state.toggle_step_history_view();
        
        // No longer navigating
        assert!(!state.is_navigating_step_history());
    }
}