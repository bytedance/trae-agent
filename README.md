# Spark CLI

Spark CLI is an LLM-based agent CLI for general purpose software engineering tasks. It provides a modular, research-friendly architecture and a powerful command-line interface for executing complex workflows with multiple tool providers.

This repository is a fork/refactor of the original Trae Agent project. The branding and docs are updated to Spark CLI, while some file names and command names remain the same for compatibility (e.g., `trae-cli`, `trae_config.yaml`).

## ✨ Features

- **Multi-LLM Support**: OpenAI, Anthropic, Google Gemini, OpenRouter, Ollama, Doubao
- **Rich Tool Ecosystem**: File editing, bash execution, structured thinking, task completion
- **Interactive Mode**: Conversational REPL for iterative development
- **Trajectory Recording**: Detailed logging of steps, tool calls, and metadata
- **Flexible Configuration**: YAML-based config with env var support
- **Research-friendly**: Transparent, modular, easy to extend and ablate

## 🚀 Installation

### Requirements
- Python 3.12+
- UV (`https://docs.astral.sh/uv/`)
- API key for chosen providers (OpenAI, Anthropic, Google Gemini, OpenRouter, etc.)

### Setup (Python CLI)

```bash
git clone <your-fork-url>.git
cd Spark_agent
uv sync --all-extras
source .venv/bin/activate
```

> Note: The current Python CLI entrypoint is still named `trae-cli` and the default config file is `trae_config.yaml`. These will be renamed in a future update.

### Optional: Rust MVP (binary crate)
A minimal Rust MVP is provided under `trae-agent-rs/` to explore a fast, standalone CLI.

```bash
# Build
cargo build --manifest-path trae-agent-rs/Cargo.toml

# Show help
cargo run --manifest-path trae-agent-rs/Cargo.toml -- --help
```

## ⚙️ Configuration

### YAML Configuration (current)

1) Copy the example configuration file:
```bash
cp trae_config.yaml.example trae_config.yaml
cp spark_config.yaml.example spark_config.yaml
```

2) Edit `spark_config.yaml` or `trae_config.yaml` with your API credentials and preferences:

```yaml
agents:
  spark_cli:
    enable_lakeview: true
    model: default_model
    max_steps: 200
    tools:
      - bash
      - str_replace_based_edit_tool
      - sequentialthinking
      - task_done

model_providers:
  openrouter:
    api_key: your_openrouter_api_key
    provider: openrouter
    base_url: https://openrouter.ai/api/v1

models:
  deepseek_model:
    model_provider: openrouter
    model: deepseek/deepseek-chat
    max_tokens: 4096
    temperature: 0.5
```

> Note: File name remains `trae_config.yaml` for now; Spark prefers `spark_config.yaml`.

### Environment Variables (optional)

```bash
export OPENAI_API_KEY="your-openai-api-key"
export ANTHROPIC_API_KEY="your-anthropic-api-key"
export GOOGLE_API_KEY="your-google-api-key"
export OPENROUTER_API_KEY="your-openrouter-api-key"
export OPENROUTER_SITE_URL="https://your.site/"
export OPENROUTER_SITE_NAME="Your App Name"
```

### MCP Services (optional)

```yaml
mcp_servers:
  playwright:
    command: npx
    args:
      - "@playwright/mcp@0.0.27"
```

Configuration priority: CLI args > Config file > Environment variables > Defaults

## 📖 Usage (Python CLI)

> The Python CLI binary is currently `trae-cli` (to be renamed to `spark-cli`).

```bash
# Simple task execution
trae-cli run "Create a hello world Python script"

# Check configuration
trae-cli show-config

# Interactive mode
trae-cli interactive
```

Provider examples:
```bash
# OpenAI
trae-cli run "Fix the bug in main.py" --provider openai --model gpt-4o

# Anthropic
trae-cli run "Add unit tests" --provider anthropic --model claude-sonnet-4-20250514

# Google Gemini
trae-cli run "Optimize this algorithm" --provider google --model gemini-2.5-flash

# OpenRouter (DeepSeek via OpenRouter)
trae-cli run "Refactor module" --provider openrouter --model "deepseek/deepseek-chat"

# OpenRouter (others)
trae-cli run "Review this code" --provider openrouter --model "anthropic/claude-3-5-sonnet"
trae-cli run "Generate documentation" --provider openrouter --model "openai/gpt-4o"

# Doubao
trae-cli run "Refactor the database module" --provider doubao --model doubao-seed-1.6

# Ollama (local)
trae-cli run "Comment this code" --provider ollama --model qwen3
```

Advanced options:
```bash
# Custom working directory
trae-cli run "Add tests for utils module" --working-dir /path/to/project

# Save execution trajectory
trae-cli run "Debug authentication" --trajectory-file debug_session.json

# Force patch generation
trae-cli run "Update API endpoints" --must-patch

# Interactive with custom settings
trae-cli interactive --provider openai --model gpt-4o --max-steps 30
```

### Rust MVP Usage

The Rust MVP provides a minimal set of subcommands and can read the same YAML config:

```bash
# show-config
cargo run --manifest-path trae-agent-rs/Cargo.toml -- show-config

# run
cargo run --manifest-path trae-agent-rs/Cargo.toml -- run "hello from spark"

# bash (with optional working dir)
cargo run --manifest-path trae-agent-rs/Cargo.toml -- --working-dir /workspace bash echo hi

# edit (replace once or all)
cargo run --manifest-path trae-agent-rs/Cargo.toml -- edit README.md Spark SPARK --once

# interactive
cargo run --manifest-path trae-agent-rs/Cargo.toml -- interactive
```

Trajectory recording (Rust MVP):
```bash
cargo run --manifest-path trae-agent-rs/Cargo.toml -- --trajectory-file trae-agent-rs/trajectory.jsonl bash echo recorded
```

## 🔧 Development

- Python: UV for env and deps, Hatch for build backend
- Lint/Format: Ruff, pre-commit
- Tests: pytest, pytest-asyncio, pytest-cov
- Makefile: common tasks (install, test, format, clean)

Useful commands:
```bash
make install-dev
make test
make fix-format
```

## 📄 License

This project is licensed under the MIT License - see the `LICENSE` file for details.

## 🙏 Acknowledgments

Spark CLI is based on the excellent work of the Trae Agent project. We also thank Anthropic for the `anthropic-quickstart` project that served as a valuable reference for the tool ecosystem.
