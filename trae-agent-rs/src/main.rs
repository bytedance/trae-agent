use std::fs;
use std::io::{self, Write as IoWrite};
use std::io::Write;
use std::path::{Path, PathBuf};
use std::process::Command;

use anyhow::{bail, Context, Result};
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
    /// Path to YAML config file (default: ./spark_config.yaml or ./trae_config.yaml)
    #[arg(long, global = true)]
    config: Option<PathBuf>,

    /// Working directory to execute commands
    #[arg(long, global = true)]
    working_dir: Option<PathBuf>,

    /// File to record execution trajectory (JSON Lines)
    #[arg(long, global = true)]
    trajectory_file: Option<PathBuf>,

    #[command(subcommand)]
    command: Commands,
}

#[derive(Subcommand, Debug)]
enum Commands {
    /// Run a simple task (prints message for now)
    Run { task: String },
    /// Show parsed configuration
    ShowConfig,
    /// Execute a bash command (uses /usr/bin/bash -lc)
    Bash {
        /// The command string to execute (everything after -- will be joined)
        #[arg(required = true)]
        cmd: Vec<String>,
    },
    /// Edit a file by replacing text
    Edit {
        /// Path to the file to edit
        file: PathBuf,
        /// The text to search for
        search: String,
        /// The replacement text
        replace: String,
        /// Replace only the first occurrence (default: replace all)
        #[arg(long)]
        once: bool,
    },
    /// Interactive REPL
    Interactive,
    /// Terminal coding REPL (Claude Code/Gemini CLI style)
    Code,
}

fn init_tracing() {
    let env_filter = EnvFilter::try_from_default_env().unwrap_or_else(|_| EnvFilter::new("info"));
    tracing_subscriber::fmt()
        .with_env_filter(env_filter)
        .with_max_level(Level::INFO)
        .init();
}

fn load_config(path_opt: Option<PathBuf>) -> Result<Option<Config>> {
    if let Some(p) = path_opt {
        if p.exists() {
            let content = fs::read_to_string(&p)
                .with_context(|| format!("Failed to read config file: {}", p.display()))?;
            let cfg: Config = serde_yaml::from_str(&content)
                .with_context(|| format!("Failed to parse YAML from: {}", p.display()))?;
            return Ok(Some(cfg));
        }
    }

    let candidates = [PathBuf::from("spark_config.yaml"), PathBuf::from("trae_config.yaml")];
    for path in candidates {
        if path.exists() {
            let content = fs::read_to_string(&path)
                .with_context(|| format!("Failed to read config file: {}", path.display()))?;
            let cfg: Config = serde_yaml::from_str(&content)
                .with_context(|| format!("Failed to parse YAML from: {}", path.display()))?;
            return Ok(Some(cfg));
        }
    }

    Ok(None)
}

fn record_trajectory(path_opt: &Option<PathBuf>, entry: serde_json::Value) -> Result<()> {
    if let Some(path) = path_opt {
        let mut file = fs::OpenOptions::new()
            .create(true)
            .append(true)
            .open(path)
            .with_context(|| format!("Failed to open trajectory file: {}", path.display()))?;
        let line = serde_json::to_string(&entry)?;
        file.write_all(line.as_bytes())?;
        file.write_all(b"\n")?;
    }
    Ok(())
}

fn run_bash(working_dir: &Option<PathBuf>, cmd_pieces: &[String]) -> Result<i32> {
    let command_str = cmd_pieces.join(" ");
    info!(command=%command_str, "Executing bash command");

    let mut cmd = Command::new("/usr/bin/bash");
    cmd.arg("-lc").arg(&command_str);

    if let Some(dir) = working_dir {
        cmd.current_dir(dir);
    }

    let status = cmd
        .status()
        .with_context(|| format!("Failed to spawn bash with command: {command_str}"))?;

    Ok(status.code().unwrap_or(-1))
}

fn run_bash_capture(working_dir: &Path, command_str: &str) -> Result<(i32, String)> {
    let output = Command::new("/usr/bin/bash")
        .arg("-lc")
        .arg(command_str)
        .current_dir(working_dir)
        .output()
        .with_context(|| format!("Failed to run bash command: {command_str}"))?;
    let code = output.status.code().unwrap_or(-1);
    let stdout = String::from_utf8_lossy(&output.stdout).to_string();
    Ok((code, stdout))
}

fn edit_file(file: &PathBuf, search: &str, replace: &str, once: bool) -> Result<usize> {
    let content = fs::read_to_string(file)
        .with_context(|| format!("Failed to read file: {}", file.display()))?;
    let (new_content, count) = if once {
        if let Some(pos) = content.find(search) {
            let mut s = String::with_capacity(content.len() - search.len() + replace.len());
            s.push_str(&content[..pos]);
            s.push_str(replace);
            s.push_str(&content[pos + search.len()..]);
            (s, 1)
        } else {
            (content, 0)
        }
    } else {
        let count = content.matches(search).count();
        (content.replace(search, replace), count)
    };

    if count > 0 {
        fs::write(file, new_content)
            .with_context(|| format!("Failed to write file: {}", file.display()))?;
    }

    Ok(count)
}

fn print_interactive_help() {
    println!("Commands:");
    println!("  run <text>                 - run a simple task");
    println!("  bash <cmd...>              - execute a bash command");
    println!("  edit <file> <s> <r> [--once] - replace text in file");
    println!("  show-config                - print parsed config");
    println!("  status                     - show current status");
    println!("  help                       - show this help");
    println!("  exit | quit                - leave interactive mode");
}

fn interactive_loop(
    config: &Option<Config>,
    working_dir: &Option<PathBuf>,
    trajectory_file: &Option<PathBuf>,
) -> Result<()> {
    println!("Entering interactive mode. Type 'help' for commands.");
    let mut line = String::new();
    loop {
        print!("> ");
        io::stdout().flush().ok();
        line.clear();
        if io::stdin().read_line(&mut line)? == 0 {
            break; // EOF
        }
        let input = line.trim();
        if input.is_empty() {
            continue;
        }
        if input == "exit" || input == "quit" {
            break;
        }
        if input == "help" {
            print_interactive_help();
            continue;
        }
        if input == "show-config" {
            match config {
                Some(cfg) => println!("{}", serde_yaml::to_string(cfg)?),
                None => println!("No config loaded"),
            }
            continue;
        }
        if input == "status" {
            println!(
                "working_dir: {}",
                working_dir
                    .as_ref()
                    .map(|p| p.display().to_string())
                    .unwrap_or_else(|| "<none>".into())
            );
            println!("trajectory_file: {}", trajectory_file.as_ref().map(|p| p.display().to_string()).unwrap_or_else(|| "<none>".into()));
            println!("config_loaded: {}", config.is_some());
            continue;
        }

        let mut parts = input.split_whitespace();
        let cmd = parts.next().unwrap();
        match cmd {
            "run" => {
                let task: String = parts.collect::<Vec<_>>().join(" ");
                if task.is_empty() { bail!("usage: run <text>"); }
                println!("Trae (rs) is running task: {task}");
                record_trajectory(trajectory_file, serde_json::json!({
                    "event": "run",
                    "task": task,
                }))?;
            }
            "bash" => {
                let cmd_vec: Vec<String> = parts.map(|s| s.to_string()).collect();
                if cmd_vec.is_empty() { bail!("usage: bash <cmd...>"); }
                let code = run_bash(working_dir, &cmd_vec)?;
                println!("Command exited with status {code}");
                record_trajectory(trajectory_file, serde_json::json!({
                    "event": "bash",
                    "cmd": cmd_vec,
                    "status": code,
                }))?;
            }
            "edit" => {
                let args: Vec<&str> = parts.collect();
                if args.len() < 3 { bail!("usage: edit <file> <search> <replace> [--once]"); }
                let once = args.iter().any(|&a| a == "--once");
                // naive: first three are file/search/replace
                let file = PathBuf::from(args[0]);
                let search = args[1].to_string();
                let replace = args[2].to_string();
                let count = edit_file(&file, &search, &replace, once)?;
                println!("Replacements: {count}");
                record_trajectory(trajectory_file, serde_json::json!({
                    "event": "edit",
                    "file": file,
                    "search": search,
                    "replace": replace,
                    "once": once,
                    "replacements": count,
                }))?;
            }
            other => {
                println!("Unknown command: {other}");
                print_interactive_help();
            }
        }
    }
    println!("Goodbye.");
    Ok(())
}

fn print_code_help() {
    println!("Terminal Coding Tool (code mode) commands:");
    println!("  help                    - show this help");
    println!("  ls [path]               - list directory");
    println!("  open <file>             - show file with line numbers");
    println!("  grep <pattern> [path]   - search text (uses ripgrep if available)");
    println!("  run <cmd...>            - run shell command (bash -lc)");
    println!("  edit <file> <s> <r> [--once] - replace text in file");
    println!("  diff [path]             - git diff (optional path)");
    println!("  commit <message>        - git add -A && git commit -m <message>");
    println!("  status                  - git status -s");
    println!("  pwd                     - print current working dir");
    println!("  cd <path>               - change working dir for subsequent commands");
    println!("  exit | quit             - leave code mode");
}

fn show_file_with_numbers(path: &Path) -> Result<()> {
    let content = fs::read_to_string(path)
        .with_context(|| format!("Failed to read file: {}", path.display()))?;
    for (idx, line) in content.lines().enumerate() {
        println!("{:>6} | {}", idx + 1, line);
    }
    Ok(())
}

fn list_directory(path: &Path) -> Result<()> {
    let entries = fs::read_dir(path).with_context(|| format!("Cannot read dir: {}", path.display()))?;
    for entry in entries {
        let entry = entry?;
        let meta = entry.metadata()?;
        let name = entry.file_name().to_string_lossy().to_string();
        if meta.is_dir() {
            println!("{}/", name);
        } else if meta.is_file() {
            println!("{}", name);
        } else {
            println!("{}", name);
        }
    }
    Ok(())
}

fn code_loop(mut current_dir: PathBuf, trajectory_file: &Option<PathBuf>) -> Result<()> {
    println!("Entering code mode. Type 'help' for commands.");
    let mut line = String::new();
    loop {
        print!("code:{}$ ", current_dir.display());
        io::stdout().flush().ok();
        line.clear();
        if io::stdin().read_line(&mut line)? == 0 {
            break;
        }
        let input = line.trim();
        if input.is_empty() {
            continue;
        }
        let mut parts = input.split_whitespace();
        let cmd = parts.next().unwrap();
        match cmd {
            "help" => print_code_help(),
            "exit" | "quit" => break,
            "pwd" => println!("{}", current_dir.display()),
            "cd" => {
                let target = parts.next().unwrap_or(".");
                let new_dir = PathBuf::from(target);
                let abs = if new_dir.is_absolute() { new_dir } else { current_dir.join(new_dir) };
                if abs.is_dir() {
                    current_dir = abs.canonicalize().unwrap_or(abs);
                } else {
                    eprintln!("Not a directory: {}", abs.display());
                }
            }
            "ls" => {
                let p = parts.next().map(PathBuf::from).unwrap_or_else(|| current_dir.clone());
                let abs = if p.is_absolute() { p } else { current_dir.join(p) };
                if let Err(e) = list_directory(&abs) { eprintln!("{}", e); }
            }
            "open" => {
                let Some(file) = parts.next() else { eprintln!("usage: open <file>"); continue; };
                let p = PathBuf::from(file);
                let abs = if p.is_absolute() { p } else { current_dir.join(p) };
                if let Err(e) = show_file_with_numbers(&abs) { eprintln!("{}", e); }
            }
            "grep" => {
                let Some(pattern) = parts.next() else { eprintln!("usage: grep <pattern> [path]"); continue; };
                let path = parts.next().unwrap_or(".");
                let abs = if Path::new(path).is_absolute() { PathBuf::from(path) } else { current_dir.join(path) };
                // Prefer ripgrep
                let cmd = format!("(command -v rg >/dev/null 2>&1 && rg -n --no-heading --color never -S '{}' '{}') || grep -RIn --binary-files=without-match '{}' '{}' | cat", pattern, abs.display(), pattern, abs.display());
                match run_bash_capture(&current_dir, &cmd) {
                    Ok((_code, out)) => print!("{}", out),
                    Err(e) => eprintln!("{}", e),
                }
            }
            "run" => {
                let rest = parts.collect::<Vec<_>>().join(" ");
                if rest.is_empty() { eprintln!("usage: run <cmd...>"); continue; }
                match run_bash_capture(&current_dir, &rest) {
                    Ok((code, out)) => { print!("{}", out); println!("[exit {}]", code); record_trajectory(trajectory_file, serde_json::json!({"event":"code.run","cmd":rest,"status":code}))?; }
                    Err(e) => eprintln!("{}", e),
                }
            }
            "edit" => {
                let args: Vec<&str> = parts.collect();
                if args.len() < 3 { eprintln!("usage: edit <file> <search> <replace> [--once]"); continue; }
                let once = args.iter().any(|&a| a == "--once");
                let file = PathBuf::from(args[0]);
                let abs = if file.is_absolute() { file } else { current_dir.join(file) };
                match edit_file(&abs, args[1], args[2], once) {
                    Ok(count) => { println!("Replacements: {}", count); record_trajectory(trajectory_file, serde_json::json!({"event":"code.edit","file":abs,"search":args[1],"replace":args[2],"once":once,"replacements":count}))?; }
                    Err(e) => eprintln!("{}", e),
                }
            }
            "diff" => {
                let path_opt = parts.next();
                let cmd = if let Some(p) = path_opt { format!("git -c color.ui=always diff -- '{}' | cat", p) } else { "git -c color.ui=always diff | cat".to_string() };
                match run_bash_capture(&current_dir, &cmd) {
                    Ok((_c, out)) => print!("{}", out),
                    Err(e) => eprintln!("{}", e),
                }
            }
            "commit" => {
                let msg = parts.collect::<Vec<_>>().join(" ");
                if msg.is_empty() { eprintln!("usage: commit <message>"); continue; }
                let cmd = format!("git add -A && git commit -m '{}' | cat", msg.replace("'", "'\\''"));
                match run_bash_capture(&current_dir, &cmd) {
                    Ok((_c, out)) => { print!("{}", out); record_trajectory(trajectory_file, serde_json::json!({"event":"code.commit","message":msg}))?; }
                    Err(e) => eprintln!("{}", e),
                }
            }
            "status" => {
                match run_bash_capture(&current_dir, "git status -s | cat") { Ok((_c, out)) => print!("{}", out), Err(e) => eprintln!("{}", e) }
            }
            unknown => {
                eprintln!("Unknown command: {}", unknown);
                print_code_help();
            }
        }
    }
    println!("Goodbye.");
    Ok(())
}

fn main() -> Result<()> {
    init_tracing();
    let cli = Cli::parse();

    let config = load_config(cli.config.clone())?;
    match cli.command {
        Commands::Run { task } => {
            info!(task=%task, "Running task (MVP placeholder)");
            println!("Trae (rs) is running task: {task}");
            record_trajectory(&cli.trajectory_file, serde_json::json!({
                "event": "run",
                "task": task,
            }))?;
        }
        Commands::ShowConfig => match &config {
            Some(cfg) => {
                println!("{}", serde_yaml::to_string(cfg)?);
            }
            None => {
                println!("No config file found (looked for spark_config.yaml / trae_config.yaml or --config)");
            }
        },
        Commands::Bash { cmd } => {
            let code = run_bash(&cli.working_dir, &cmd)?;
            println!("Command exited with status {code}");
            record_trajectory(&cli.trajectory_file, serde_json::json!({
                "event": "bash",
                "cmd": cmd,
                "status": code,
            }))?;
        }
        Commands::Edit { file, search, replace, once } => {
            let count = edit_file(&file, &search, &replace, once)?;
            println!("Replacements: {count}");
            record_trajectory(&cli.trajectory_file, serde_json::json!({
                "event": "edit",
                "file": file,
                "search": search,
                "replace": replace,
                "once": once,
                "replacements": count,
            }))?;
        }
        Commands::Interactive => {
            interactive_loop(&config, &cli.working_dir, &cli.trajectory_file)?;
        }
        Commands::Code => {
            let cwd = cli.working_dir.clone().unwrap_or_else(|| std::env::current_dir().unwrap_or_else(|_| PathBuf::from(".")));
            code_loop(cwd, &cli.trajectory_file)?;
        }
    }

    Ok(())
}
