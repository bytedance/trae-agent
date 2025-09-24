// Copyright (c) 2025 ByteDance Ltd. and/or its affiliates
// SPDX-License-Identifier: MIT

use std::collections::HashMap;
use trae_core::utils::review_history::{
    ReviewHistory, ReviewRecord, ReviewStatus, ReviewComment, CommentType, ReviewHistoryError,
};

fn main() -> Result<(), ReviewHistoryError> {
    println!("🚀 Review History Demo - Creating sample records...");

    let storage_path = ReviewHistory::default_storage_path();
    println!("📁 Storage path: {}", storage_path.display());

    let history = ReviewHistory::new(storage_path.clone());

    // Create sample review records
    let records = vec![
        ReviewRecord {
            id: "review_001".to_string(),
            timestamp: "2025-01-20T09:00:00Z".to_string(),
            task_description: "Implement user authentication system".to_string(),
            reviewer: "Alice Johnson".to_string(),
            status: ReviewStatus::Completed,
            rating: Some(5),
            files_reviewed: vec![
                "src/auth/mod.rs".to_string(),
                "src/auth/login.rs".to_string(),
                "src/auth/middleware.rs".to_string(),
            ],
            comments: vec![
                ReviewComment {
                    id: "comment_001".to_string(),
                    timestamp: "2025-01-20T10:30:00Z".to_string(),
                    author: "Alice Johnson".to_string(),
                    content: "Excellent implementation! The authentication flow is well-structured and secure.".to_string(),
                    comment_type: CommentType::Praise,
                    file_path: Some("src/auth/mod.rs".to_string()),
                    line_number: Some(45),
                },
                ReviewComment {
                    id: "comment_002".to_string(),
                    timestamp: "2025-01-20T10:35:00Z".to_string(),
                    author: "Alice Johnson".to_string(),
                    content: "Consider adding rate limiting to prevent brute force attacks.".to_string(),
                    comment_type: CommentType::Suggestion,
                    file_path: Some("src/auth/login.rs".to_string()),
                    line_number: Some(78),
                },
            ],
            tags: vec!["authentication".to_string(), "security".to_string(), "backend".to_string()],
            duration_seconds: Some(3600), // 1 hour
            created_at: "2025-01-20T09:00:00Z".to_string(),
            updated_at: "2025-01-20T11:00:00Z".to_string(),
        },
        ReviewRecord {
            id: "review_002".to_string(),
            timestamp: "2025-01-20T14:00:00Z".to_string(),
            task_description: "Add dark mode support to UI components".to_string(),
            reviewer: "Bob Smith".to_string(),
            status: ReviewStatus::InProgress,
            rating: None,
            files_reviewed: vec![
                "src/components/theme.rs".to_string(),
                "src/styles/dark.css".to_string(),
            ],
            comments: vec![
                ReviewComment {
                    id: "comment_003".to_string(),
                    timestamp: "2025-01-20T14:15:00Z".to_string(),
                    author: "Bob Smith".to_string(),
                    content: "The theme switching logic looks good, but we need to test it across all components.".to_string(),
                    comment_type: CommentType::General,
                    file_path: Some("src/components/theme.rs".to_string()),
                    line_number: Some(23),
                },
            ],
            tags: vec!["ui".to_string(), "frontend".to_string(), "theme".to_string()],
            duration_seconds: Some(1800), // 30 minutes
            created_at: "2025-01-20T14:00:00Z".to_string(),
            updated_at: "2025-01-20T14:30:00Z".to_string(),
        },
        ReviewRecord {
            id: "review_003".to_string(),
            timestamp: "2025-01-20T15:30:00Z".to_string(),
            task_description: "Optimize database queries for better performance".to_string(),
            reviewer: "Carol Davis".to_string(),
            status: ReviewStatus::Rejected,
            rating: Some(2),
            files_reviewed: vec![
                "src/database/queries.rs".to_string(),
                "src/models/user.rs".to_string(),
            ],
            comments: vec![
                ReviewComment {
                    id: "comment_004".to_string(),
                    timestamp: "2025-01-20T16:20:00Z".to_string(),
                    author: "Carol Davis".to_string(),
                    content: "The N+1 query problem still exists in the user loading logic.".to_string(),
                    comment_type: CommentType::Issue,
                    file_path: Some("src/models/user.rs".to_string()),
                    line_number: Some(156),
                },
                ReviewComment {
                    id: "comment_005".to_string(),
                    timestamp: "2025-01-20T16:25:00Z".to_string(),
                    author: "Carol Davis".to_string(),
                    content: "Please implement proper indexing and consider using eager loading.".to_string(),
                    comment_type: CommentType::Suggestion,
                    file_path: Some("src/database/queries.rs".to_string()),
                    line_number: Some(89),
                },
            ],
            tags: vec!["database".to_string(), "performance".to_string(), "optimization".to_string()],
            duration_seconds: Some(2700), // 45 minutes
            created_at: "2025-01-20T15:30:00Z".to_string(),
            updated_at: "2025-01-20T16:30:00Z".to_string(),
        },
        ReviewRecord {
            id: "review_004".to_string(),
            timestamp: "2025-01-21T08:00:00Z".to_string(),
            task_description: "Add comprehensive unit tests for API endpoints".to_string(),
            reviewer: "David Wilson".to_string(),
            status: ReviewStatus::Approved,
            rating: Some(4),
            files_reviewed: vec![
                "tests/api/auth_test.rs".to_string(),
                "tests/api/user_test.rs".to_string(),
                "tests/api/common.rs".to_string(),
            ],
            comments: vec![
                ReviewComment {
                    id: "comment_006".to_string(),
                    timestamp: "2025-01-21T09:15:00Z".to_string(),
                    author: "David Wilson".to_string(),
                    content: "Great test coverage! The edge cases are well handled.".to_string(),
                    comment_type: CommentType::Praise,
                    file_path: Some("tests/api/auth_test.rs".to_string()),
                    line_number: Some(45),
                },
                ReviewComment {
                    id: "comment_007".to_string(),
                    timestamp: "2025-01-21T09:20:00Z".to_string(),
                    author: "David Wilson".to_string(),
                    content: "Consider adding integration tests for the complete user flow.".to_string(),
                    comment_type: CommentType::Question,
                    file_path: None,
                    line_number: None,
                },
            ],
            tags: vec!["testing".to_string(), "api".to_string(), "quality".to_string()],
            duration_seconds: Some(5400), // 1.5 hours
            created_at: "2025-01-21T08:00:00Z".to_string(),
            updated_at: "2025-01-21T10:00:00Z".to_string(),
        },
        ReviewRecord {
            id: "review_005".to_string(),
            timestamp: "2025-01-21T11:00:00Z".to_string(),
            task_description: "Implement real-time notifications system".to_string(),
            reviewer: "Eve Brown".to_string(),
            status: ReviewStatus::Pending,
            rating: None,
            files_reviewed: vec![
                "src/notifications/mod.rs".to_string(),
                "src/websocket/handler.rs".to_string(),
            ],
            comments: vec![],
            tags: vec!["notifications".to_string(), "websocket".to_string(), "realtime".to_string()],
            duration_seconds: None,
            created_at: "2025-01-21T11:00:00Z".to_string(),
            updated_at: "2025-01-21T11:00:00Z".to_string(),
        },
    ];

    // Save all records
    for (i, record) in records.iter().enumerate() {
        match history.save_record(record) {
            Ok(_) => println!("✅ Saved record {}: {}", i + 1, record.task_description),
            Err(e) => println!("❌ Failed to save record {}: {}", i + 1, e),
        }
    }

    println!("\n📊 Demo Summary:");
    println!("   • Created {} sample review records", records.len());
    println!("   • Records saved to: {}", storage_path.display());
    println!("   • Status distribution:");
    
    let mut status_counts = HashMap::new();
    for record in &records {
        let status_str = format!("{:?}", record.status);
        *status_counts.entry(status_str).or_insert(0) += 1;
    }
    
    for (status, count) in status_counts {
        let icon = match status.as_str() {
            "Pending" => "⏳",
            "InProgress" => "🔄",
            "Completed" => "✅",
            "Rejected" => "❌",
            "Approved" => "✅",
            _ => "❓",
        };
        println!("     {} {}: {}", icon, status, count);
    }

    println!("\n🎯 You can now test the review history feature in the CLI:");
    println!("   1. Run: cargo run --bin trae-cli");
    println!("   2. Type: /review");
    println!("   3. Navigate with ↑/↓ keys");
    println!("   4. Press Enter to view details");
    println!("   5. Press Esc to close");

    Ok(())
}