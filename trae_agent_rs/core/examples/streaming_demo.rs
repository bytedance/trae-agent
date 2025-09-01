// Copyright (c) 2025 ByteDance Ltd. and/or its affiliates
// SPDX-License-Identifier: MIT

//! Streaming implementation demonstration
//! 
//! This example demonstrates the streaming functionality implemented for OpenAI-compatible clients.
//! It shows how Server-Sent Events (SSE) are parsed and converted into stream chunks.

// Note: Imports are shown for demonstration purposes in the usage example

fn demonstrate_sse_parsing() {
    println!("🔧 Demonstrating SSE Parsing Implementation");
    println!("===========================================");
    
    // Example SSE stream data that would come from OpenRouter or similar providers
    let sample_sse_stream = r#"data: {"choices":[{"delta":{"content":"Hello"},"finish_reason":null}],"model":"gpt-4"}

data: {"choices":[{"delta":{"content":" there!"},"finish_reason":null}],"model":"gpt-4"}

data: {"choices":[{"delta":{"content":" How"},"finish_reason":null}],"model":"gpt-4"}

data: {"choices":[{"delta":{"content":" can"},"finish_reason":null}],"model":"gpt-4"}

data: {"choices":[{"delta":{"content":" I"},"finish_reason":null}],"model":"gpt-4"}

data: {"choices":[{"delta":{"content":" help"},"finish_reason":null}],"model":"gpt-4"}

data: {"choices":[{"delta":{"content":" you"},"finish_reason":null}],"model":"gpt-4"}

data: {"choices":[{"delta":{"content":"?"},"finish_reason":"stop"}],"model":"gpt-4"}

data: [DONE]
"#;

    println!("📝 Sample SSE Stream Data:");
    println!("{}", sample_sse_stream);
    
    println!("\n📊 Parsed Stream Chunks:");
    let mut content_parts = Vec::new();
    
    for line in sample_sse_stream.lines() {
        if line.starts_with("data: ") {
            let data = &line[6..];
            if data == "[DONE]" {
                println!("🏁 Stream completed with [DONE] marker");
                break;
            }
            
            // Simulate parsing (in real implementation this would use parse_sse_chunk)
            if let Ok(parsed) = serde_json::from_str::<serde_json::Value>(data) {
                if let Some(choices) = parsed.get("choices").and_then(|c| c.as_array()) {
                    if let Some(first_choice) = choices.first() {
                        if let Some(delta) = first_choice.get("delta") {
                            if let Some(content) = delta.get("content").and_then(|c| c.as_str()) {
                                content_parts.push(content.to_string());
                                println!("📦 Chunk: {:?}", content);
                            }
                            if let Some(finish_reason) = first_choice.get("finish_reason").and_then(|fr| fr.as_str()) {
                                println!("🔚 Finish reason: {}", finish_reason);
                            }
                        }
                    }
                }
            }
        } else if line.starts_with(": ") {
            println!("💬 Comment (keepalive): {}", &line[2..]);
        }
    }
    
    let complete_message = content_parts.join("");
    println!("\n✨ Complete assembled message: \"{}\"", complete_message);
}

fn demonstrate_implementation_features() {
    println!("\n🚀 Streaming Implementation Features");
    println!("===================================");
    
    println!("✅ OpenAI-compatible SSE parsing");
    println!("✅ Proper handling of [DONE] markers");
    println!("✅ Support for comment lines (keepalive)");
    println!("✅ Tool calls in streaming responses");
    println!("✅ Usage information in final chunks");
    println!("✅ Error handling for malformed JSON");
    println!("✅ Stream cancellation support via connection abort");
    
    println!("\n📋 Implementation Details:");
    println!("- Follows OpenRouter API streaming specification");
    println!("- Uses Server-Sent Events (SSE) format");
    println!("- Parses 'data: ' prefixed lines");
    println!("- Ignores comment lines starting with ': '");
    println!("- Handles incremental content delivery");
    println!("- Supports tool calling in streaming mode");
    println!("- Compatible with any OpenAI-compatible API");
}

fn show_usage_example() {
    println!("\n💡 Usage Example");
    println!("================");
    
    println!("```rust");
    println!("use trae_core::{{");
    println!("    config::{{ModelConfig, ModelProvider}},");
    println!("    llm::{{LLMMessage, LLMProvider, OpenAICompatibleGenericClient}},");
    println!("}};");
    println!("use futures::StreamExt;");
    println!();
    println!("async fn streaming_chat_example() -> Result<(), Box<dyn std::error::Error>> {{");
    println!("    // Configure your OpenAI-compatible provider");
    println!("    let provider = ModelProvider::new(\"openai_compatible\".to_string())");
    println!("        .with_api_key(\"your-api-key\".to_string())");
    println!("        .with_base_url(\"https://openrouter.ai/api/v1\".to_string());");
    println!();
    println!("    let model_config = ModelConfig::new(\"gpt-4o-2024-11-20\".to_string(), provider)");
    println!("        .with_temperature(0.7)");
    println!("        .with_max_tokens(500);");
    println!();
    println!("    let mut client = OpenAICompatibleGenericClient::with_config(model_config.clone())?;");
    println!();
    println!("    let messages = vec![");
    println!("        LLMMessage {{");
    println!("            role: \"user\".to_string(),");
    println!("            content: Some(vec![HashMap::from([(");
    println!("                \"text\".to_string(), ");
    println!("                \"Tell me about streaming APIs\".to_string()");
    println!("            )])]),");
    println!("            tool_call: None,");
    println!("            tool_result: None,");
    println!("        }}");
    println!("    ];");
    println!();
    println!("    // Start streaming");
    println!("    let mut stream = client.chat_stream(messages, &model_config, None, Some(false)).await?;");
    println!();
    println!("    // Process stream chunks");
    println!("    while let Some(chunk_result) = stream.next().await {{");
    println!("        match chunk_result {{");
    println!("            Ok(chunk) => {{");
    println!("                if let Some(content) = &chunk.content {{");
    println!("                    if let Some(text) = content[0].get(\"text\") {{");
    println!("                        print!(\"{{}}\", text); // Print incrementally");
    println!("                    }}");
    println!("                }}");
    println!("                if let Some(finish_reason) = &chunk.finish_reason {{");
    println!("                    println!(\"\\nStream completed: {{:?}}\", finish_reason);");
    println!("                    break;");
    println!("                }}");
    println!("            }}");
    println!("            Err(e) => {{");
    println!("                eprintln!(\"Streaming error: {{}}\", e);");
    println!("                break;");
    println!("            }}");
    println!("        }}");
    println!("    }}");
    println!();
    println!("    Ok(())");
    println!("}}");
    println!("```");
}

fn main() {
    println!("🤖 OpenAI-Compatible Streaming Implementation Demo");
    println!("==================================================");
    println!();
    println!("This demo showcases the streaming functionality implemented for");
    println!("OpenAI-compatible clients, following the OpenRouter API specification.");
    println!();
    
    demonstrate_sse_parsing();
    demonstrate_implementation_features();
    show_usage_example();
    
    println!("\n🎉 Streaming implementation is complete!");
    println!("You can now use the OpenAI-compatible client with streaming support");
    println!("for real-time responses from any OpenAI-compatible API provider.");
}
