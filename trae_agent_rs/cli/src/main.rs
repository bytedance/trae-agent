// Copyright (c) 2025 ByteDance Ltd. and/or its affiliates
// SPDX-License-Identifier: MIT

use anyhow::Result;
use clap::{Parser, Subcommand};
use owo_colors::OwoColorize;
use std::path::PathBuf;
use trae_cli::get_trae_agent_logo;
use trae_core::{ModelConfig, ModelProvider};

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
    name = "trae",
    about = "Trae Agent - Intelligent coding assistant",
    version = env!("CARGO_PKG_VERSION"),
    author = "ByteDance"
)]
struct Cli {
    #[command(subcommand)]
    command: Commands,

    /// Enable verbose logging
    #[arg(short, long, global = true)]
    verbose: bool,

    /// Configuration file path
    #[arg(short, long, global = true)]
    config: Option<PathBuf>,
}

#[derive(Subcommand)]
enum Commands {
    /// Start an interactive coding session
    Chat {
        /// Initial message or task description
        #[arg(short, long)]
        message: Option<String>,

        /// Working directory for the agent
        #[arg(short, long, default_value = ".")]
        workspace: PathBuf,

        /// Model provider to use (openai, anthropic, etc.)
        #[arg(short, long, default_value = "openai")]
        provider: String,

        /// Model name to use
        #[arg(long, default_value = "gpt-4")]
        model: String,
    },

    /// Execute a single task without interactive mode
    Run {
        /// Task description
        task: String,

        /// Working directory for the agent
        #[arg(short, long, default_value = ".")]
        workspace: PathBuf,

        /// Model provider to use (openai, anthropic, etc.)
        #[arg(short, long, default_value = "openai")]
        provider: String,

        /// Model name to use
        #[arg(long, default_value = "gpt-4")]
        model: String,
    },

    /// Show configuration information
    Config {
        #[command(subcommand)]
        action: ConfigCommands,
    },
}

#[derive(Subcommand)]
enum ConfigCommands {
    /// Show current configuration
    Show,
    /// Set configuration values
    Set {
        /// Configuration key
        key: String,
        /// Configuration value
        value: String,
    },
}

#[tokio::main]
async fn main() -> Result<()> {
    let cli = Cli::parse();

    // Initialize logging
    env_logger::Builder::new()
        .filter_level(if cli.verbose {
            log::LevelFilter::Debug
        } else {
            log::LevelFilter::Info
        })
        .init();

    match cli.command {
        Commands::Chat {
            message,
            workspace,
            provider,
            model,
        } => {
            handle_chat(message, workspace, provider, model).await?;
        }
        Commands::Run {
            task,
            workspace,
            provider,
            model,
        } => {
            handle_run(task, workspace, provider, model).await?;
        }
        Commands::Config { action } => {
            handle_config(action).await?;
        }
    }

    Ok(())
}

async fn handle_chat(
    message: Option<String>,
    workspace: PathBuf,
    provider: String,
    model: String,
) -> Result<()> {
    show_welcome_message();

    println!("🚀 Starting interactive session...");
    println!(
        "📁 Workspace: {}",
        workspace.display().to_string().bright_blue()
    );
    println!(
        "🎯 Provider: {}, Model: {}",
        provider.bright_green(),
        model.bright_yellow()
    );

    if let Some(msg) = message {
        println!("💬 Initial message: {}", msg.bright_white());
        // TODO: Initialize agent and process the initial message
    }

    println!();
    println!(
        "{}",
        "💡 Interactive mode not yet implemented.".bright_yellow()
    );
    println!("This will start an interactive coding session where you can:");
    println!("  {} Chat with the AI assistant", "•".bright_cyan());
    println!("  {} Get help with coding tasks", "•".bright_cyan());
    println!("  {} Have the agent make code changes", "•".bright_cyan());
    println!("  {} Use various tools and utilities", "•".bright_cyan());

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
        _ => {
            eprintln!(
                "❌ Unknown provider: {}. Supported providers: openai, anthropic, azure",
                provider
            );
            std::process::exit(1);
        }
    };

    let base_url = match provider.as_str() {
        "openai" => Some("https://api.openai.com/v1".to_string()),
        "anthropic" => Some("https://api.anthropic.com".to_string()),
        "azure" => std::env::var("AZURE_BASE_URL").ok(),
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

    println!();
    println!(
        "{}",
        "💡 Task execution not yet implemented.".bright_yellow()
    );
    println!("This will:");
    println!("  {} Initialize the appropriate agent", "•".bright_cyan());
    println!(
        "  {} Process the task using the configured model",
        "•".bright_cyan()
    );
    println!("  {} Execute any necessary actions", "•".bright_cyan());
    println!("  {} Provide results and feedback", "•".bright_cyan());

    Ok(())
}

async fn handle_config(action: ConfigCommands) -> Result<()> {
    match action {
        ConfigCommands::Show => {
            println!(
                "{} {}",
                "📋".bright_cyan(),
                "Current Configuration:".bright_white()
            );

            if std::env::var("API_KEY").is_ok() {
                println!("  {}: {}", "API_KEY".bright_cyan(), "***".bright_green());
            } else {
                println!("  {}: {}", "API_KEY".bright_cyan(), "not set".bright_red());
            }

            if std::env::var("ANTHROPIC_API_KEY").is_ok() {
                println!(
                    "  {}: {}",
                    "ANTHROPIC_API_KEY".bright_cyan(),
                    "***".bright_green()
                );
            } else {
                println!(
                    "  {}: {}",
                    "ANTHROPIC_API_KEY".bright_cyan(),
                    "not set".bright_red()
                );
            }

            if std::env::var("AZURE_API_KEY").is_ok() {
                println!(
                    "  {}: {}",
                    "AZURE_API_KEY".bright_cyan(),
                    "***".bright_green()
                );
            } else {
                println!(
                    "  {}: {}",
                    "AZURE_API_KEY".bright_cyan(),
                    "not set".bright_red()
                );
            }

            println!();
            println!(
                "{} Environment variables you can set:",
                "💡".bright_yellow()
            );
            println!(
                "  {} - for OpenAI models",
                "API_KEY or OPENAI_API_KEY".bright_blue()
            );
            println!(
                "  {} - for Anthropic/Claude models",
                "ANTHROPIC_API_KEY".bright_blue()
            );
            println!(
                "  {} - for Azure OpenAI models",
                "AZURE_API_KEY".bright_blue()
            );
        }
        ConfigCommands::Set { key, value: _ } => {
            println!(
                "{} Configuration setting not yet implemented.",
                "💡".bright_yellow()
            );
            println!(
                "To set {}, use environment variables for now.",
                key.bright_cyan()
            );
            println!(
                "Example: {}",
                format!("export {}=your_key_here", key).bright_green()
            );
        }
    }

    Ok(())
}
