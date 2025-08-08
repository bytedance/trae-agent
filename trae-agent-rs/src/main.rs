use std::fs;
use std::path::PathBuf;

use anyhow::{Context, Result};
use clap::{Parser, Subcommand};
use serde::{Deserialize, Serialize};
use tracing::{info, Level};
use tracing_subscriber::EnvFilter;

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
struct ModelProvider {
    #[serde(default)]
    provider: String,
    #[serde(default)]
    api_key: Option<String>,
    #[serde(default)]
    base_url: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
struct AgentsConfig {
    #[serde(default)]
    enable_lakeview: bool,
    #[serde(default)]
    model: String,
    #[serde(default)]
    max_steps: Option<u32>,
    #[serde(default)]
    tools: Vec<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
struct Config {
    #[serde(default)]
    agents: Option<std::collections::HashMap<String, AgentsConfig>>,
    #[serde(default)]
    model_providers: Option<std::collections::HashMap<String, ModelProvider>>,
}

#[derive(Parser, Debug)]
#[command(name = "trae-agent-rs", version, about = "Rust MVP of Trae Agent")] 
struct Cli {
    /// Path to YAML config file (default: ./trae_config.yaml)
    #[arg(long, global = true)]
    config: Option<PathBuf>,

    #[command(subcommand)]
    command: Commands,
}

#[derive(Subcommand, Debug)]
enum Commands {
    /// Run a simple task (prints message for now)
    Run { task: String },
    /// Show parsed configuration
    ShowConfig,
}

fn init_tracing() {
    let env_filter = EnvFilter::try_from_default_env()
        .unwrap_or_else(|_| EnvFilter::new("info"));
    tracing_subscriber::fmt()
        .with_env_filter(env_filter)
        .with_max_level(Level::INFO)
        .init();
}

fn load_config(path_opt: Option<PathBuf>) -> Result<Option<Config>> {
    let path = path_opt.unwrap_or_else(|| PathBuf::from("trae_config.yaml"));
    if !path.exists() {
        return Ok(None);
    }
    let content = fs::read_to_string(&path)
        .with_context(|| format!("Failed to read config file: {}", path.display()))?;
    let cfg: Config = serde_yaml::from_str(&content)
        .with_context(|| format!("Failed to parse YAML from: {}", path.display()))?;
    Ok(Some(cfg))
}

fn main() -> Result<()> {
    init_tracing();
    let cli = Cli::parse();

    let config = load_config(cli.config.clone())?;
    match cli.command {
        Commands::Run { task } => {
            info!(task=%task, "Running task (MVP placeholder)");
            println!("Trae (rs) is running task: {task}");
        }
        Commands::ShowConfig => {
            match &config {
                Some(cfg) => {
                    println!("{}", serde_yaml::to_string(cfg)?);
                }
                None => {
                    println!("No config file found (looked for trae_config.yaml or --config)");
                }
            }
        }
    }

    Ok(())
}
