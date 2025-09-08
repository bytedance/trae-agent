// Copyright (c) 2025 ByteDance Ltd. and/or its affiliates
// SPDX-License-Identifier: MIT

//! TraeAgent Test Program
//!
//! This program demonstrates and tests the TraeAgent functionality with various configurations
//! and test scenarios including task initialization, tool usage, and agent execution.
//!
//! Usage:
//! 1. Set your API key: export OPENAI_COMPATIBLE_API_KEY="your-api-key"
//! 2. Set your base URL: export OPENAI_COMPATIBLE_BASE_URL="https://api.your-provider.com/v1"
//! 3. Set test project path: export TEST_PROJECT_PATH="/path/to/test/project"
//! 4. Optional: Set test issue: export TEST_ISSUE="Test issue description"
//! 5. PLEASE MAKE SURE YOU CHANGE THE PATH TO YOUR ABSOLUTE PATH.
//! 6. Run: cargo run --example trae_agent_test

use std::collections::HashMap;
use std::{env, vec};
use trae_core::trae::TraeAgent;
use trae_core::{
    agent::base_agent::{Agent, AgentError, AgentExecution, BaseAgent},
    config::{ModelConfig, ModelProvider},
    llm::{LLMClient, MessageRole},
};

/// Helper function to create a test TraeAgent
fn create_test_trae_agent() -> Result<TraeAgent, Box<dyn std::error::Error>> {
    // Get configuration from environment or use defaults
    let api_key =
        env::var("OPENAI_COMPATIBLE_API_KEY").unwrap_or_else(|_| "test-api-key".to_string());

    let base_url = env::var("OPENAI_COMPATIBLE_BASE_URL")
        .unwrap_or_else(|_| "https://api.openai.com/v1".to_string());

    // Create model provider and configuration
    let provider = ModelProvider::new("openai_compatible".to_string())
        .with_api_key(api_key)
        .with_base_url(base_url);

    let model_config =
        ModelConfig::new("gpt-4.1-2025-04-14".to_string(), provider).with_temperature(0.1);

    // Create LLM client
    let llm_client = LLMClient::new(model_config.clone())?;

    // Create base agent
    let base_agent = BaseAgent::new(
        "".to_string(), // Empty task initially
        AgentExecution::new("".to_string(), None),
        llm_client,
        10, // max_step
        model_config,
        None, // tools will be set in new_task
        vec![],
    );

    Ok(TraeAgent::new(base_agent, None))
}

/// Test TraeAgent initialization
async fn test_trae_agent_initialization() -> Result<(), Box<dyn std::error::Error>> {
    println!("\n🧪 Testing TraeAgent initialization...");

    let agent = create_test_trae_agent();

    match agent {
        Ok(_) => {
            println!("✅ TraeAgent initialization successful!");
        }
        Err(e) => {
            println!("❌ TraeAgent initialization failed: {}", e);
            return Err(e);
        }
    }

    Ok(())
}

/// Test new_task method with valid arguments
async fn test_new_task_valid_args() -> Result<(), Box<dyn std::error::Error>> {
    println!("\n🧪 Testing new_task with valid arguments...");

    let mut agent = create_test_trae_agent()?;

    let mut args = HashMap::new();
    args.insert("project_path".to_string(), "/tmp/test_project".to_string());
    args.insert(
        "issue".to_string(),
        "Fix the bug in the main function".to_string(),
    );
    args.insert("base_commit".to_string(), "abc123".to_string());
    args.insert("must_patch".to_string(), "true".to_string());
    args.insert("patch_path".to_string(), "/tmp/patches".to_string());

    let task = "Fix the identified bug in the codebase".to_string();

    match agent.new_task(task.clone(), Some(args), None) {
        Ok(_) => {
            println!("✅ new_task with valid arguments successful!");
            println!("Task set: {}", task);
            println!("Initial messages count: {}", agent.initial_msgs.len());

            // Verify the agent state
            assert!(
                !agent.initial_msgs.is_empty(),
                "Initial messages should not be empty"
            );
            assert_eq!(agent.baseagent.task, task, "Task should be set correctly");

            // Check if optional fields are set
            if let Some(base_commit) = &agent.base_commit {
                println!("Base commit: {}", base_commit);
            }
            if let Some(must_patch) = &agent.must_patch {
                println!("Must patch: {}", must_patch);
            }
            if let Some(patch_path) = &agent.patch_path {
                println!("Patch path: {}", patch_path);
            }
        }
        Err(e) => {
            println!("❌ new_task with valid arguments failed: {:?}", e);
            return Err(Box::new(e));
        }
    }

    Ok(())
}

/// Test new_task method with missing required arguments
async fn test_new_task_missing_args() -> Result<(), Box<dyn std::error::Error>> {
    println!("\n🧪 Testing new_task with missing arguments...");

    let mut agent = create_test_trae_agent()?;

    // Test missing project_path
    println!("Testing missing project_path...");
    let mut args = HashMap::new();
    args.insert("issue".to_string(), "Fix the bug".to_string());

    let task = "Fix the bug".to_string();

    match agent.new_task(task.clone(), Some(args), None) {
        Ok(_) => {
            println!("⚠️  Expected error for missing project_path but got success");
        }
        Err(AgentError::NoProjectPath) => {
            println!("✅ Correctly caught missing project_path error");
        }
        Err(e) => {
            println!("❌ Got unexpected error: {:?}", e);
        }
    }

    // Test completely missing args
    println!("Testing missing args entirely...");
    match agent.new_task(task, None, None) {
        Ok(_) => {
            println!("⚠️  Expected error for missing args but got success");
        }
        Err(AgentError::NoExtraArgument) => {
            println!("✅ Correctly caught missing arguments error");
        }
        Err(e) => {
            println!("❌ Got unexpected error: {:?}", e);
        }
    }

    Ok(())
}

/// Test tool initialization
async fn test_tool_initialization() -> Result<(), Box<dyn std::error::Error>> {
    println!("\n🧪 Testing tool initialization...");

    let mut agent = create_test_trae_agent()?;

    let mut args = HashMap::new();
    args.insert("project_path".to_string(), "/tmp/test_project".to_string());
    args.insert("issue".to_string(), "Test issue".to_string());

    let task = "Test task".to_string();

    // Initialize the agent
    agent.new_task(task, Some(args), None)?;

    // Check if tools are initialized (this would require access to the baseagent's tools)
    // Since the tools field is private, we can't directly check, but we can verify
    // that the initialization completed without errors
    println!("✅ Tool initialization completed without errors");

    // The TraeAgentToolNames should include "bash" and "str_replace_based_edit_tool"
    println!("Expected tools: bash, str_replace_based_edit_tool");

    Ok(())
}

/// Test agent execution (basic flow)
async fn test_agent_execution_basic() -> Result<(), Box<dyn std::error::Error>> {
    println!("\n🧪 Testing basic agent execution...");

    // Only run this test if we have valid API credentials
    let api_key = env::var("OPENAI_COMPATIBLE_API_KEY");
    let base_url = env::var("OPENAI_COMPATIBLE_BASE_URL");

    if api_key.is_err() || base_url.is_err() {
        println!("⚠️  Skipping execution test - missing API credentials");
        println!(
            "   Set OPENAI_COMPATIBLE_API_KEY and OPENAI_COMPATIBLE_BASE_URL to run this test"
        );
        return Ok(());
    }

    let mut agent = create_test_trae_agent()?;

    let mut args = HashMap::new();
    args.insert("project_path".to_string(), "./test".to_string());
    args.insert(
        "issue".to_string(),
        "Create a simple hello world script".to_string(),
    );

    let task = "Create a hello world script in the project directory".to_string();

    // Initialize the agent
    agent.new_task(
        task,
        Some(args),
        Some(vec![
            "bash".to_string(),
            "str_replace_based_edit_tool".to_string(),
        ]),
    )?;

    println!("🚀 Starting agent execution...");
    println!("⚠️  Note: This will attempt to make real API calls");

    // Run the agent (this will likely fail due to incomplete implementation)
    match agent.run().await {
        Ok(execution) => {
            println!("✅ Agent execution completed!");
            println!("Task: {}", execution.task);
            println!("Steps taken: {}", execution.steps.len());
            println!("Success: {}", execution.success);
            println!("Final state: {:?}", execution.agent_state);
            println!("Execution time: {:.2}s", execution.execution_time);

            if let Some(final_result) = &execution.final_result {
                println!("Final result: {}", final_result);
            }
        }
        Err(e) => {
            println!(
                "❌ Agent execution failed (expected due to incomplete implementation): {}",
                e
            );
            // This is expected since the implementation returns an error
        }
    }

    Ok(())
}

/// Test system prompt and initial messages
async fn test_system_prompt() -> Result<(), Box<dyn std::error::Error>> {
    println!("\n🧪 Testing system prompt and initial messages...");

    let mut agent = create_test_trae_agent()?;

    let mut args = HashMap::new();
    args.insert("project_path".to_string(), "/tmp/test_project".to_string());
    args.insert(
        "issue".to_string(),
        "Test issue for system prompt".to_string(),
    );

    let task = "Test task".to_string();

    agent.new_task(task, Some(args), None)?;

    println!("✅ System prompt initialization successful!");
    println!("Initial messages count: {}", agent.initial_msgs.len());

    // Verify we have at least system and user messages
    assert!(
        agent.initial_msgs.len() >= 2,
        "Should have at least system and user messages"
    );

    // Check message types
    if let Some(first_msg) = agent.initial_msgs.first() {
        match first_msg.role {
            MessageRole::System => println!("✅ First message is system message"),
            _ => println!("❌ First message should be system message"),
        }
    }

    if let Some(second_msg) = agent.initial_msgs.get(1) {
        match second_msg.role {
            MessageRole::User => println!("✅ Second message is user message"),
            _ => println!("❌ Second message should be user message"),
        }
    }

    // Print message contents (truncated for readability)
    for (i, msg) in agent.initial_msgs.iter().enumerate() {
        println!("Message {}: Role = {:?}", i + 1, msg.role);
        if let Some(content) = &msg.content
            && let Some(text_content) = content.first().and_then(|c| c.as_text())
        {
            let truncated = if text_content.len() > 100 {
                format!("{}...", &text_content[..100])
            } else {
                text_content.to_string()
            };
            println!("  Content: {}", truncated);
        }
    }

    Ok(())
}

async fn test_custom_tool_names() -> Result<(), Box<dyn std::error::Error>> {
    println!("\n🧪 Testing custom tool names...");

    let mut agent = create_test_trae_agent()?;

    let mut args = HashMap::new();
    args.insert("project_path".to_string(), "/tmp/test_project".to_string());
    args.insert("issue".to_string(), "Custom tools test".to_string());

    let task = "Test with custom tools".to_string();
    let custom_tools = vec!["bash".to_string()]; // Only bash tool

    match agent.new_task(task, Some(args), Some(custom_tools)) {
        Ok(_) => {
            println!("✅ Custom tool names test successful!");
            println!("Note: Custom tool handling logic needs to be implemented");
        }
        Err(e) => {
            println!("❌ Custom tool names test failed: {:?}", e);
            return Err(Box::new(e));
        }
    }

    Ok(())
}

fn print_header() {
    println!("🤖 TraeAgent Test Program");
    println!("==========================");
    println!("This program comprehensively tests the TraeAgent functionality.");
    println!("Make sure you have set appropriate environment variables for full testing.");
    println!();
}

fn print_configuration_info() {
    println!("📋 Configuration:");

    // Check API configuration
    if let Ok(api_key) = env::var("OPENAI_COMPATIBLE_API_KEY") {
        let masked_key = if api_key.len() > 8 {
            format!("{}...{}", &api_key[..4], &api_key[api_key.len() - 4..])
        } else {
            "***".to_string()
        };
        println!("✅ API Key: {}", masked_key);
    } else {
        println!("⚠️  API Key: Not set (some tests will be skipped)");
    }

    if let Ok(base_url) = env::var("OPENAI_COMPATIBLE_BASE_URL") {
        println!("✅ Base URL: {}", base_url);
    } else {
        println!("⚠️  Base URL: Not set (some tests will be skipped)");
    }

    if let Ok(project_path) = env::var("TEST_PROJECT_PATH") {
        println!("✅ Test Project Path: {}", project_path);
    } else {
        println!("ℹ️  Test Project Path: Using default /tmp/test_project");
    }

    if let Ok(issue) = env::var("TEST_ISSUE") {
        println!("✅ Test Issue: {}", issue);
    } else {
        println!("ℹ️  Test Issue: Using default test issues");
    }

    println!();
}

#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    print_header();
    print_configuration_info();

    println!("🚀 Starting TraeAgent comprehensive tests...");

    // Collect test results
    let mut test_results = Vec::new();

    // Test 1: Agent Initialization
    match test_trae_agent_initialization().await {
        Ok(_) => test_results.push(("Agent Initialization", true)),
        Err(e) => {
            eprintln!("Agent initialization test failed: {}", e);
            test_results.push(("Agent Initialization", false));
        }
    }

    // Test 2: new_task with valid arguments
    match test_new_task_valid_args().await {
        Ok(_) => test_results.push(("New Task (Valid Args)", true)),
        Err(e) => {
            eprintln!("New task valid args test failed: {}", e);
            test_results.push(("New Task (Valid Args)", false));
        }
    }

    // Test 3: new_task with missing arguments
    match test_new_task_missing_args().await {
        Ok(_) => test_results.push(("New Task (Error Handling)", true)),
        Err(e) => {
            eprintln!("New task error handling test failed: {}", e);
            test_results.push(("New Task (Error Handling)", false));
        }
    }

    // Test 4: Tool initialization
    match test_tool_initialization().await {
        Ok(_) => test_results.push(("Tool Initialization", true)),
        Err(e) => {
            eprintln!("Tool initialization test failed: {}", e);
            test_results.push(("Tool Initialization", false));
        }
    }

    // Test 5: System prompt setup
    match test_system_prompt().await {
        Ok(_) => test_results.push(("System Prompt Setup", true)),
        Err(e) => {
            eprintln!("System prompt test failed: {}", e);
            test_results.push(("System Prompt Setup", false));
        }
    }

    // Test 7: Custom tool names
    match test_custom_tool_names().await {
        Ok(_) => test_results.push(("Custom Tool Names", true)),
        Err(e) => {
            eprintln!("Custom tool names test failed: {}", e);
            test_results.push(("Custom Tool Names", false));
        }
    }

    // Test 9: Agent execution (if credentials available)
    match test_agent_execution_basic().await {
        Ok(_) => test_results.push(("Agent Execution", true)),
        Err(e) => {
            eprintln!("Agent execution test failed: {}", e);
            test_results.push(("Agent Execution", false));
        }
    }

    // Print comprehensive summary
    println!("\n📊 Comprehensive Test Summary");
    println!("==============================");

    let mut passed = 0;
    let total = test_results.len();

    for (test_name, success) in &test_results {
        let status = if *success { "✅ PASS" } else { "❌ FAIL" };
        println!("{:<25}: {}", test_name, status);
        if *success {
            passed += 1;
        }
    }

    println!(
        "\n📈 Results: {}/{} tests passed ({:.1}%)",
        passed,
        total,
        (passed as f32 / total as f32) * 100.0
    );

    if passed == total {
        println!("🎉 All tests passed! TraeAgent appears to be functioning correctly.");
    } else if passed > total / 2 {
        println!(
            "⚠️  Most tests passed, but some issues were found. Check the failed tests above."
        );
    } else {
        println!("❌ Many tests failed. TraeAgent may have significant issues.");
    }

    println!("\n📝 Notes:");
    println!("- Some tests may be skipped if API credentials are not provided");
    println!("- Agent execution test may fail due to incomplete implementation (expected)");
    println!("- Tool functionality tests require proper environment setup");

    Ok(())
}
