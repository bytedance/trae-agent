// Copyright (c) 2025 ByteDance Ltd. and/or its affiliates
// SPDX-License-Identifier: MIT

#[cfg(test)]
mod tests {
    use crate::tui::state::AppState;

    #[test]
    fn test_scroll_up_functionality() {
        let mut state = AppState::default(); // Use default to avoid welcome message
        
        // Add some test output lines
        for i in 0..20 {
            state.add_output_line(format!("Line {}", i));
        }
        
        // After adding lines, scroll is set to usize::MAX (auto-scroll to bottom)
        // Let's clamp it to a reasonable value first
        let viewport_height = 10;
        state.clamp_scroll(viewport_height);
        
        // Now test scroll up
        let initial_scroll = state.output_scroll;
        state.scroll_up();
        assert_eq!(state.output_scroll, initial_scroll.saturating_sub(1));
        
        // Test scroll to top
        state.scroll_to_top();
        assert_eq!(state.output_scroll, 0);
        assert!(state.is_at_top());
        
        // Test scroll down
        state.scroll_down();
        assert_eq!(state.output_scroll, 1);
        assert!(!state.is_at_top());
        
        // Test scroll up when already at top (should stay at 0)
        state.scroll_to_top();
        state.scroll_up();
        assert_eq!(state.output_scroll, 0);
        assert!(state.is_at_top());
    }

    #[test]
    fn test_enhanced_scroll_functions() {
        let mut state = AppState::default();
        
        // Add test content
        for i in 0..30 {
            state.add_output_line(format!("Test line {}", i));
        }
        
        // Test scroll_up_lines
        state.output_scroll = 10;
        state.scroll_up_lines(5);
        assert_eq!(state.output_scroll, 5);
        
        // Test scroll_down_lines
        state.scroll_down_lines(3);
        assert_eq!(state.output_scroll, 8);
        
        // Test smooth scroll up
        state.smooth_scroll_up(2);
        assert_eq!(state.output_scroll, 6);
        
        // Test smooth scroll down
        state.smooth_scroll_down(4);
        assert_eq!(state.output_scroll, 10);
    }

    #[test]
    fn test_scroll_position_indicators() {
        let mut state = AppState::default();
        let viewport_height = 10;
        
        // Add test content
        for i in 0..25 {
            state.add_output_line(format!("Content line {}", i));
        }
        
        // Test at top
        state.output_scroll = 0;
        assert!(state.is_at_top());
        assert_eq!(state.get_scroll_info(viewport_height), "Top");
        
        // Test in middle
        state.output_scroll = 7;
        assert!(!state.is_at_top());
        assert!(!state.is_at_bottom(viewport_height));
        let percentage = state.get_scroll_percentage(viewport_height);
        assert!(percentage > 0 && percentage < 100);
        
        // Test at bottom
        state.output_scroll = 15; // 25 - 10 = 15 max scroll
        state.clamp_scroll(viewport_height);
        assert!(state.is_at_bottom(viewport_height));
        assert_eq!(state.get_scroll_info(viewport_height), "Bot");
    }

    #[test]
    fn test_scroll_bounds_checking() {
        let mut state = AppState::default();
        
        // Test with empty state first
        state.scroll_up();
        assert_eq!(state.output_scroll, 0);
        
        state.scroll_up_lines(10);
        assert_eq!(state.output_scroll, 0);
        
        // Add limited content
        for i in 0..5 {
            state.add_output_line(format!("Line {}", i));
        }
        
        // After adding content, scroll to top first
        state.scroll_to_top();
        
        // Try to scroll up when already at top
        state.scroll_up();
        assert_eq!(state.output_scroll, 0);
        
        // Try to scroll up multiple lines when already at top
        state.scroll_up_lines(10);
        assert_eq!(state.output_scroll, 0);
        
        // Test clamping with viewport larger than content
        let viewport_height = 10;
        state.output_scroll = 5;
        state.clamp_scroll(viewport_height);
        assert_eq!(state.output_scroll, 0);
        assert!(state.is_at_bottom(viewport_height));
    }

    #[test]
    fn test_scroll_with_empty_content() {
        let mut state = AppState::default();
        let viewport_height = 10;
        
        // Test with no content
        assert!(state.is_at_top());
        assert!(state.is_at_bottom(viewport_height));
        assert_eq!(state.get_scroll_info(viewport_height), "All");
        
        // Try scrolling with no content
        state.scroll_up();
        state.scroll_down();
        assert_eq!(state.output_scroll, 0);
    }
}