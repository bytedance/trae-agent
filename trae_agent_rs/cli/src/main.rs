// Copyright (c) 2025 ByteDance Ltd. and/or its affiliates
// SPDX-License-Identifier: MIT

use anyhow::Result;
use clap::Parser;
use owo_colors::OwoColorize;
use std::{collections::HashMap, path::PathBuf};
use trae_cli::{get_trae_agent_logo, tui::App};
use trae_core::{
    agent::base_agent::{Agent, AgentExecution, BaseAgent},
    config::{ModelConfig, ModelProvider},
    llm::LLMClient,
    trae::TraeAgent,
};

fn show_welcome_message() {
    // Title to display
    let text = get_trae_agent_logo();

    println!("{}", text);

    println!();
    println!(
        "🤖 {} - Intelligent coding assistant",
        "Trae Agent".bright_cyan()
    );
    println!("💡 Version: {}", env!("CARGO_PKG_VERSION").bright_green());
    println!();
}

#[derive(Parser)]
#[command(
    name = "trae-agent",
    about = "Trae Agent - Intelligent coding assistant",
    version = env!("CARGO_PKG_VERSION"),
    author = "ByteDance"
)]
struct Cli {
    /// Start interactive mode (default behavior)
    #[arg(short, long)]
    interactive: bool,

    /// Run a single task without interactive mode
    #[arg(short, long)]
    run: Option<String>,

    /// Enable verbose logging
    #[arg(short, long, global = true)]
    verbose: bool,

    /// Configuration file path
    #[arg(short, long, global = true)]
    config: Option<PathBuf>,

    /// Working directory for the agent
    #[arg(short, long, global = true, default_value = ".")]
    workspace: PathBuf,

    /// Model provider to use (openai, anthropic, etc.)
    #[arg(short, long, global = true, default_value = "openai")]
    provider: String,

    /// Model name to use
    #[arg(long, global = true, default_value = "gpt-4")]
    model: String,
}

#[tokio::main]
async fn main() -> Result<()> {
    let cli = Cli::parse();

    // Initialize logging
    env_logger::Builder::new()
        .filter_level(if cli.verbose {
            log::LevelFilter::Debug
        } else {
            log::LevelFilter::Error  // Only show errors by default, suppress warnings and info
        })
        .init();

    // Check if we have a run command
    if let Some(task) = cli.run {
        // Single run mode
        handle_run(task, cli.workspace, cli.provider, cli.model).await?;
    } else {
        // Interactive mode (default)
        handle_interactive(cli.workspace, cli.provider, cli.model).await?;
    }

    Ok(())
}

async fn handle_interactive(workspace: PathBuf, provider: String, model: String) -> Result<()> {
    println!("🚀 Starting interactive session...");

    // Create the TUI application with the specified workspace
    let mut app = App::new_with_workspace(provider, model, Some(workspace))?;
    let settings = app.get_settings();

    println!(
        "📁 Workspace: {}",
        settings.workspace.display().to_string().bright_blue()
    );
    println!(
        "🎯 Provider: {}, Model: {}",
        settings.provider.bright_green(),
        settings.model.bright_yellow()
    );

    // Run the TUI application
    app.run().await?;

    Ok(())
}

async fn handle_run(
    task: String,
    workspace: PathBuf,
    provider: String,
    model: String,
) -> Result<()> {
    show_welcome_message();

    println!("🚀 Executing task: {}", task.bright_white());
    println!(
        "📁 Workspace: {}",
        workspace.display().to_string().bright_blue()
    );
    println!(
        "🎯 Provider: {}, Model: {}",
        provider.bright_green(),
        model.bright_yellow()
    );

    // Create model configuration
    let api_key = match provider.as_str() {
        "openai" => std::env::var("OPENAI_API_KEY")
            .or_else(|_| std::env::var("API_KEY"))
            .unwrap_or_default(),
        "anthropic" => std::env::var("ANTHROPIC_API_KEY").unwrap_or_default(),
        "azure" => std::env::var("AZURE_API_KEY").unwrap_or_default(),
        "openai_compatible" => std::env::var("OPENAI_COMPATIBLE_API_KEY")
            .or_else(|_| std::env::var("API_KEY"))
            .unwrap_or_default(),
        "openrouter" => std::env::var("OPENROUTER_API_KEY")
            .or_else(|_| std::env::var("OPENAI_COMPATIBLE_API_KEY"))
            .or_else(|_| std::env::var("API_KEY"))
            .unwrap_or_default(),
        _ => {
            eprintln!(
                "❌ Unknown provider: {}. Supported providers: openai, anthropic, azure, openai_compatible, openrouter",
                provider
            );
            std::process::exit(1);
        }
    };

    if api_key.is_empty() {
        eprintln!("❌ API key not found. Please set the appropriate environment variable:");
        match provider.as_str() {
            "openai" => eprintln!("   export OPENAI_API_KEY=your_key_here"),
            "anthropic" => eprintln!("   export ANTHROPIC_API_KEY=your_key_here"),
            "azure" => eprintln!("   export AZURE_API_KEY=your_key_here"),
            "openai_compatible" => eprintln!("   export OPENAI_COMPATIBLE_API_KEY=your_key_here"),
            "openrouter" => eprintln!("   export OPENROUTER_API_KEY=your_key_here (or OPENAI_COMPATIBLE_API_KEY)"),
            _ => {}
        }
        std::process::exit(1);
    }

    let base_url = match provider.as_str() {
        "openai" => Some("https://api.openai.com/v1".to_string()),
        "anthropic" => Some("https://api.anthropic.com".to_string()),
        "azure" => std::env::var("AZURE_BASE_URL").ok(),
        "openai_compatible" => std::env::var("OPENAI_COMPATIBLE_BASE_URL").ok(),
        "openrouter" => Some("https://openrouter.ai/api/v1".to_string()),
        _ => None,
    };

    let model_provider = ModelProvider::new(provider.clone()).with_api_key(api_key);

    let model_provider = if let Some(url) = base_url {
        model_provider.with_base_url(url)
    } else {
        model_provider
    };

    let model_config = ModelConfig::new(model, model_provider)
        .with_max_tokens(4096)
        .with_temperature(0.1);

    println!("⚙️ Model config: {:?}", model_config);

    // Create and initialize the agent
    if let Err(e) = create_and_run_agent(model_config, workspace, task).await {
        eprintln!("❌ Task failed: {}", e);
        std::process::exit(1);
    }

    Ok(())
}

async fn create_and_run_agent(
    model_config: ModelConfig,
    workspace: PathBuf,
    task: String,
) -> Result<()> {
    println!("🔧 Creating agent...");

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

    // Create TraeAgent with proper trajectory file path
    let trajectory_path = workspace.join("trajectory.json");
    let mut agent = TraeAgent::new(base_agent, Some(trajectory_path.to_string_lossy().to_string()));

    println!("🎯 Initializing task...");

    // Setup task arguments
    let mut args = HashMap::new();
    args.insert(
        "project_path".to_string(),
        workspace.to_string_lossy().to_string(),
    );
    args.insert("issue".to_string(), task.clone());

    // Initialize the task
    agent
        .new_task(task, Some(args), None)
        .map_err(|e| anyhow::anyhow!("Failed to initialize task: {:?}", e))?;

    println!("🚀 Running agent...");

    // Run the agent
    let result = agent
        .run()
        .await
        .map_err(|e| anyhow::anyhow!("Agent execution failed: {}", e))?;

    println!("📋 Execution result: {:?}", result);

    // Check if the task actually succeeded
    if result.success {
        println!("✅ Task completed successfully!");
    } else {
        let error_msg = result.final_result.unwrap_or_else(|| "Unknown error".to_string());
        return Err(anyhow::anyhow!("❌ Task failed: {}", error_msg));
    }

    Ok(())
}
