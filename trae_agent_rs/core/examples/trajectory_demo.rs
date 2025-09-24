// Copyright (c) 2025 ByteDance Ltd. and/or its affiliates
// SPDX-License-Identifier: MIT

//! Trajectory Demo Program
//!
//! This program demonstrates the trajectory saving functionality by creating
//! a TraeAgent and simulating its execution to generate a trajectory JSON file.
//!
//! Usage: cargo run --example trajectory_demo

use std::collections::HashMap;
use trae_core::trae::TraeAgent;
use trae_core::{
    agent::base_agent::{Agent, AgentExecution, BaseAgent},
    config::{ModelConfig, ModelProvider},
    llm::LLMClient,
};

/// Create a test TraeAgent for demonstration
fn create_demo_trae_agent() -> Result<TraeAgent, Box<dyn std::error::Error>> {
    // Create model provider and configuration (using dummy values)
    let provider = ModelProvider::new("openai_compatible".to_string())
        .with_api_key("demo-api-key".to_string())
        .with_base_url("https://api.demo.com/v1".to_string());

    let model_config = ModelConfig::new("gpt-4".to_string(), provider).with_temperature(0.1);

    // Create LLM client
    let llm_client = LLMClient::new(model_config.clone())?;

    // Create base agent
    let base_agent = BaseAgent::new(
        "".to_string(), // Empty task initially
        AgentExecution::new("".to_string(), None),
        llm_client,
        5, // max_step
        model_config,
        None, // tools will be set in new_task
        vec![],
    );

    // Create TraeAgent with a specific trajectory path
    Ok(TraeAgent::new(
        base_agent,
        Some("./demo_trajectory.json".to_string()),
    ))
}

#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    println!("🎬 Trajectory Demo - Demonstrating trajectory saving functionality");
    println!("==================================================================");

    // Create the agent
    let mut agent = create_demo_trae_agent()?;
    println!("✅ TraeAgent created successfully");

    // Set up a task
    let mut args = HashMap::new();
    args.insert("project_path".to_string(), "./demo_project".to_string());
    args.insert(
        "issue".to_string(),
        "Demo issue: Create a simple hello world script".to_string(),
    );

    let task = "Demo task: Create a hello world script in the project directory".to_string();

    // Initialize the agent with the task
    agent.new_task(
        task,
        Some(args),
        Some(vec![
            "bash".to_string(),
            "str_replace_based_edit_tool".to_string(),
        ]),
    )?;
    println!("✅ Task initialized successfully");

    println!(
        "\n🚀 Starting agent execution (this will fail due to no real API, but will save trajectory)..."
    );

    // Run the agent (this will fail due to no real API, but should still save trajectory)
    match agent.run().await {
        Ok(execution) => {
            println!("✅ Agent execution completed!");
            println!("Task: {}", execution.task);
            println!("Steps taken: {}", execution.steps.len());
            println!("Success: {}", execution.success);
            println!("Execution time: {:.2}s", execution.execution_time);

            if let Some(final_result) = &execution.final_result {
                println!("Final result: {}", final_result);
            }
        }
        Err(e) => {
            println!("❌ Agent execution failed (expected): {}", e);
            println!("   This is expected since we're using dummy API credentials");
        }
    }

    // Check if trajectory file was created
    println!("\n📁 Checking for trajectory file...");
    if std::path::Path::new("./demo_trajectory.json").exists() {
        println!("✅ Trajectory file created: ./demo_trajectory.json");

        // Read and display the trajectory content
        match std::fs::read_to_string("./demo_trajectory.json") {
            Ok(content) => {
                println!("\n📄 Trajectory file content:");
                println!("{}", content);

                // Validate JSON format
                match serde_json::from_str::<serde_json::Value>(&content) {
                    Ok(json) => {
                        println!("\n✅ Trajectory file is valid JSON");

                        // Show key information
                        if let Some(task) = json.get("task") {
                            println!("📋 Task: {}", task);
                        }
                        if let Some(success) = json.get("success") {
                            println!("🎯 Success: {}", success);
                        }
                        if let Some(total_steps) = json.get("total_steps") {
                            println!("📊 Total steps: {}", total_steps);
                        }
                        if let Some(error_count) = json.get("error_count") {
                            println!("❌ Error count: {}", error_count);
                        }
                        if let Some(llm_interactions) = json.get("llm_interaction") {
                            if let Some(interactions_array) = llm_interactions.as_array() {
                                println!("💬 LLM interactions: {}", interactions_array.len());
                            }
                        }
                    }
                    Err(e) => {
                        println!("❌ Trajectory file is not valid JSON: {}", e);
                    }
                }
            }
            Err(e) => {
                println!("❌ Could not read trajectory file: {}", e);
            }
        }
    } else {
        println!("❌ Trajectory file was not created");
        println!("   This might indicate an issue with the trajectory saving mechanism");
    }

    println!("\n🎉 Trajectory demo completed!");
    println!(
        "📝 Note: The trajectory file demonstrates the structure even when agent execution fails"
    );

    Ok(())
}
