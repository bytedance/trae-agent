// Copyright (c) 2025 ByteDance Ltd. and/or its affiliates
// SPDX-License-Identifier: MIT

//! OpenAI Compatible client test program
//!
//! This program demonstrates how to use the OpenAI Compatible client with various configurations
//! and test scenarios including basic chat, tool calling, and streaming.
//!
//! Usage:
//! 1. Set your API key: export OPENAI_COMPATIBLE_API_KEY="your-api-key"
//! 2. Set your base URL: export OPENAI_COMPATIBLE_BASE_URL="https://api.your-provider.com/v1"
//! 3. Optional: Set site info: export OPENAI_COMPATIBLE_SITE_URL="your-site.com" and OPENAI_COMPATIBLE_SITE_NAME="Your Site"
//! 4. Optional: Set typewriter delay: export TYPEWRITER_DELAY_MS="15" (default: 15ms, set to 0 to disable)
//! 5. Run: cargo run --example openai_compatible_test

use std::collections::HashMap;
use std::future::Future;
use std::pin::Pin;
use trae_core::{
    config::{ModelConfig, ModelProvider},
    llm::{LLMMessage, LLMClient, MessageRole, ContentItem},
    tools::Tool,
};

/// Simple calculator tool for testing tool calling
#[derive(Debug)]
struct CalculatorTool;

impl Tool for CalculatorTool {
    fn get_name(&self) -> &str {
        "calculator"
    }

    fn get_description(&self) -> &str {
        "Performs basic arithmetic operations (add, subtract, multiply, divide)"
    }

    fn get_input_schema(&self) -> serde_json::Value {
        serde_json::json!({
            "type": "object",
            "properties": {
                "operation": {
                    "type": "string",
                    "enum": ["add", "subtract", "multiply", "divide"],
                    "description": "The arithmetic operation to perform"
                },
                "a": {
                    "type": "number",
                    "description": "First number"
                },
                "b": {
                    "type": "number",
                    "description": "Second number"
                }
            },
            "required": ["operation", "a", "b"]
        })
    }

    fn execute(&mut self, arguments: HashMap<String, serde_json::Value>) -> Pin<Box<dyn Future<Output = Result<String, String>> + Send + '_>> {
        let operation = arguments.get("operation")
            .and_then(|v| v.as_str())
            .unwrap_or("");

        let a = arguments.get("a")
            .and_then(|v| v.as_f64())
            .unwrap_or(0.0);

        let b = arguments.get("b")
            .and_then(|v| v.as_f64())
            .unwrap_or(0.0);

        let result = match operation {
            "add" => Ok((a + b).to_string()),
            "subtract" => Ok((a - b).to_string()),
            "multiply" => Ok((a * b).to_string()),
            "divide" => {
                if b == 0.0 {
                    Err("Division by zero".to_string())
                } else {
                    Ok((a / b).to_string())
                }
            }
            _ => Err(format!("Unknown operation: {}", operation)),
        };

        Box::pin(async move { result })
    }
}

/// Weather tool for testing tool calling
#[derive(Debug)]
struct WeatherTool;

impl Tool for WeatherTool {
    fn get_name(&self) -> &str {
        "get_weather"
    }

    fn get_description(&self) -> &str {
        "Gets the current weather for a given location"
    }

    fn get_input_schema(&self) -> serde_json::Value {
        serde_json::json!({
            "type": "object",
            "properties": {
                "location": {
                    "type": "string",
                    "description": "The city and country (e.g., 'London, UK')"
                }
            },
            "required": ["location"]
        })
    }

    fn execute(&mut self, arguments: HashMap<String, serde_json::Value>) -> Pin<Box<dyn Future<Output = Result<String, String>> + Send + '_>> {
        let location = arguments.get("location")
            .and_then(|v| v.as_str())
            .unwrap_or("Unknown");

        // Mock weather data
        let weather_data = format!(
            "Weather in {}: 22°C, partly cloudy with light winds. Humidity: 65%",
            location
        );

        Box::pin(async move { Ok(weather_data) })
    }
}

async fn test_basic_chat(client: &mut LLMClient, model_config: &ModelConfig) -> Result<(), Box<dyn std::error::Error>> {
    println!("\n🧪 Testing basic chat functionality...");

    let messages = vec![
        LLMMessage {
            role: MessageRole::User,
            content: Some(vec![ContentItem::text("Hello! Can you tell me a short joke?".to_string())]),
            tool_call: None,
            tool_result: None,
        }
    ];

    match client.chat(messages, model_config, None, false).await {
        Ok(response) => {
            println!("✅ Basic chat test successful!");
            println!("Model: {:?}", response.model);
            println!("Finish reason: {:?}", response.finish_reason);
            if let Some(usage) = &response.usage {
                println!("Usage: {}", usage);
            }
            if !response.content.is_empty() {
                if let Some(text) = response.content[0].as_text() {
                    println!("Response: {}", text);
                }
            }
        }
        Err(e) => {
            println!("❌ Basic chat test failed: {}", e);
            return Err(e.into());
        }
    }

    Ok(())
}

async fn test_tool_calling(client: &mut LLMClient, model_config: &ModelConfig) -> Result<(), Box<dyn std::error::Error>> {
    println!("\n🔧 Testing tool calling functionality...");

    let tools: Vec<Box<dyn Tool>> = vec![
        Box::new(CalculatorTool),
        Box::new(WeatherTool),
    ];

    let messages = vec![
        LLMMessage {
            role: MessageRole::User,
            content: Some(vec![ContentItem::text("What's 15 + 27? Also, what's the weather like in Tokyo, Japan?".to_string())]),
            tool_call: None,
            tool_result: None,
        }
    ];

    match client.chat(messages, model_config, Some(tools), false).await {
        Ok(response) => {
            println!("✅ Tool calling test successful!");
            println!("Model: {:?}", response.model);
            println!("Finish reason: {:?}", response.finish_reason);

            if let Some(tool_calls) = &response.tool_calls {
                println!("Tool calls made: {}", tool_calls.len());
                for (i, call) in tool_calls.iter().enumerate() {
                    println!("  Tool call {}: {}", i + 1, call);

                    // Execute the tool call using the new async interface
                    let result = if call.name == "calculator" {
                        CalculatorTool.execute(call.arguments.clone()).await
                    } else if call.name == "get_weather" {
                        WeatherTool.execute(call.arguments.clone()).await
                    } else {
                        Err("Unknown tool".to_string())
                    };

                    match result {
                        Ok(output) => println!("  Tool result: success=true, result={}", output),
                        Err(error) => println!("  Tool result: success=false, error={}", error),
                    }
                }
            } else {
                println!("No tool calls were made (model might not support tools or didn't decide to use them)");
            }

            if !response.content.is_empty() {
                if let Some(text) = response.content[0].as_text() {
                    println!("Response: {}", text);
                }
            }
        }
        Err(e) => {
            println!("❌ Tool calling test failed: {}", e);
            return Err(e.into());
        }
    }

    Ok(())
}

async fn test_streaming(client: &mut LLMClient, model_config: &ModelConfig) -> Result<(), Box<dyn std::error::Error>> {
    println!("\n📡 Testing streaming functionality...");

    let messages = vec![
        LLMMessage {
            role: MessageRole::User,
            content: Some(vec![ContentItem::text("Tell me a short story about a robot learning to cook.".to_string())]),
            tool_call: None,
            tool_result: None,
        }
    ];

    match client.chat_stream(messages, model_config, None, false).await {
        Ok(mut stream) => {
            println!("✅ Streaming test initiated successfully!");
            println!("🤖 Assistant: ");

            use futures::StreamExt;
            use std::io::{self, Write};
            use tokio::time::{sleep, Duration};

            // Get typewriter delay from environment variable (default: 15ms)
            let typewriter_delay = std::env::var("TYPEWRITER_DELAY_MS")
                .ok()
                .and_then(|s| s.parse::<u64>().ok())
                .unwrap_or(15);

            let mut chunk_count = 0;

            while let Some(chunk_result) = stream.next().await {
                match chunk_result {
                    Ok(chunk) => {
                        chunk_count += 1;

                        if let Some(content) = &chunk.content {
                            if !content.is_empty() {
                                if let Some(text) = content[0].as_text() {
                                    print!("{}", text);
                                    // Flush stdout to ensure real-time output
                                    io::stdout().flush().unwrap();
                                    // Typewriter effect delay (configurable via TYPEWRITER_DELAY_MS env var)
                                    if typewriter_delay > 0 {
                                        sleep(Duration::from_millis(typewriter_delay)).await;
                                    }
                                }
                            }
                        }

                        if let Some(finish_reason) = &chunk.finish_reason {
                            println!("\n\n🏁 Stream finished with reason: {:?}", finish_reason);
                            break;
                        }
                    }
                    Err(e) => {
                        println!("\n❌ Streaming error: {}", e);
                        return Err(e.into());
                    }
                }
            }

            println!("✅ Streaming test completed! Received {} chunks", chunk_count);
        }
        Err(e) => {
            println!("❌ Streaming test failed: {}", e);
            return Err(e.into());
        }
    }

    Ok(())
}

async fn test_error_handling() -> Result<(), Box<dyn std::error::Error>> {
    println!("\n⚠️  Testing error handling...");

    // Test with invalid base URL that will fail quickly (non-existent domain)
    // Using .invalid TLD ensures DNS resolution fails quickly without retries
    // Alternative: use "http://localhost:99999" for immediate connection refused
    let provider = ModelProvider::new("openai_compatible".to_string())
        .with_api_key("test-key".to_string())
        .with_base_url("https://non-existent-domain-12345.invalid".to_string());

    let config = ModelConfig::new("gpt-4o-2024-11-20".to_string(), provider)
        .with_temperature(0.7)
        .with_max_tokens(100)
        .with_max_retries(1); // Reduce retries for faster error testing

    match LLMClient::new(config) {
        Ok(mut client) => {
            let messages = vec![
                LLMMessage {
                    role: MessageRole::User,
                    content: Some(vec![ContentItem::text("Hello".to_string())]),
                    tool_call: None,
                    tool_result: None,
                }
            ];

            let model_config = ModelConfig::new("gpt-4o-2024-11-20".to_string(),
                ModelProvider::new("openai_compatible".to_string())
                    .with_api_key("test-key".to_string())
                    .with_base_url("https://non-existent-domain-12345.invalid".to_string()))
                .with_max_retries(1); // Reduce retries for faster error testing

            println!("🔍 Attempting connection to invalid URL (this should fail quickly)...");
            match client.chat(messages, &model_config, None, false).await {
                Ok(_) => {
                    println!("⚠️  Expected error but got success - this might indicate a problem");
                }
                Err(e) => {
                    println!("✅ Error handling test successful - caught expected error: {}", e);
                }
            }
        }
        Err(e) => {
            println!("✅ Error handling test successful - caught config error: {}", e);
        }
    }

    Ok(())
}

fn print_header() {
    println!("🤖 OpenAI Compatible Client Test Program");
    println!("==========================================");
    println!("This program tests the OpenAI Compatible client functionality.");
    println!("Make sure you have set your OPENAI_COMPATIBLE_API_KEY and OPENAI_COMPATIBLE_BASE_URL environment variables.");
    println!();
}

fn print_configuration_info() {
    println!("📋 Configuration:");

    if let Ok(api_key) = std::env::var("OPENAI_COMPATIBLE_API_KEY") {
        println!("✅ API Key: {}...{}", &api_key[..8.min(api_key.len())],
            if api_key.len() > 8 { &api_key[api_key.len()-4..] } else { "" });
    } else {
        println!("❌ API Key: Not set (set OPENAI_COMPATIBLE_API_KEY environment variable)");
    }

    if let Ok(base_url) = std::env::var("OPENAI_COMPATIBLE_BASE_URL") {
        println!("✅ Base URL: {}", base_url);
    } else {
        println!("❌ Base URL: Not set (set OPENAI_COMPATIBLE_BASE_URL environment variable)");
    }

    if let Ok(site_url) = std::env::var("OPENAI_COMPATIBLE_SITE_URL") {
        println!("✅ Site URL: {}", site_url);
    } else {
        println!("ℹ️  Site URL: Not set (optional - set OPENAI_COMPATIBLE_SITE_URL)");
    }

    if let Ok(site_name) = std::env::var("OPENAI_COMPATIBLE_SITE_NAME") {
        println!("✅ Site Name: {}", site_name);
    } else {
        println!("ℹ️  Site Name: Not set (optional - set OPENAI_COMPATIBLE_SITE_NAME)");
    }

    let typewriter_delay = std::env::var("TYPEWRITER_DELAY_MS")
        .ok()
        .and_then(|s| s.parse::<u64>().ok())
        .unwrap_or(15);
    println!("⚡ Typewriter Delay: {}ms (set TYPEWRITER_DELAY_MS to customize, 0 to disable)", typewriter_delay);

    println!();
}

#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    print_header();
    print_configuration_info();

    // Get API key and base URL from environment
    let api_key = std::env::var("OPENAI_COMPATIBLE_API_KEY")
        .map_err(|_| "OPENAI_COMPATIBLE_API_KEY environment variable not set")?;

    let base_url = std::env::var("OPENAI_COMPATIBLE_BASE_URL")
        .map_err(|_| "OPENAI_COMPATIBLE_BASE_URL environment variable not set")?;

    // Create model provider and configuration
    let provider = ModelProvider::new("openai_compatible".to_string())
        .with_api_key(api_key)
        .with_base_url(base_url);

    let model_config = ModelConfig::new("gpt-4o-2024-11-20".to_string(), provider)
        .with_temperature(0.7)
        .with_max_tokens(500);

    // Create LLM client
    let mut client = LLMClient::new(model_config.clone())?;

    println!("🚀 Starting tests with model: {}", model_config.model);
    println!("Provider: {}", client.get_provider_name());

    // Run all tests
    let mut test_results = Vec::new();

    // Test 1: Basic chat
    match test_basic_chat(&mut client, &model_config).await {
        Ok(_) => test_results.push(("Basic Chat", true)),
        Err(e) => {
            eprintln!("Basic chat test failed: {}", e);
            test_results.push(("Basic Chat", false));
        }
    }

    // Test 2: Tool calling (try it and see if the model supports it)
    match test_tool_calling(&mut client, &model_config).await {
        Ok(_) => test_results.push(("Tool Calling", true)),
        Err(e) => {
            eprintln!("Tool calling test failed: {}", e);
            test_results.push(("Tool Calling", false));
        }
    }

    // Test 3: Streaming
    match test_streaming(&mut client, &model_config).await {
        Ok(_) => test_results.push(("Streaming", true)),
        Err(e) => {
            eprintln!("Streaming test failed: {}", e);
            test_results.push(("Streaming", false));
        }
    }

    // Test 4: Error handling
    match test_error_handling().await {
        Ok(_) => test_results.push(("Error Handling", true)),
        Err(e) => {
            eprintln!("Error handling test failed: {}", e);
            test_results.push(("Error Handling", false));
        }
    }

    // Print summary
    println!("\n📊 Test Summary");
    println!("================");
    let mut passed = 0;
    let total = test_results.len();

    for (test_name, success) in test_results {
        let status = if success { "✅ PASS" } else { "❌ FAIL" };
        println!("{}: {}", test_name, status);
        if success {
            passed += 1;
        }
    }

    println!("\nOverall: {}/{} tests passed", passed, total);

    if passed == total {
        println!("🎉 All tests passed!");
    } else {
        println!("⚠️  Some tests failed. Check the output above for details.");
    }

    Ok(())
}
