# Trae Agent

[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/) [![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
 ![Alpha]( https://img.shields.io/badge/Status-Alpha-red)

**Trae Agent** is an LLM-based agent for general purpose software engineering tasks. It provides a powerful CLI interface that can understand natural language instructions and execute complex software engineering workflows using various tools and LLM providers.

*Please note that this project is still in the alpha stage and being actively developed. We welcome various contributions from the community.*

- [ ] Unit tests
- [ ] Richer CLI support
- [ ] Migrate to Rust

## ✨ Features

- 🌊 **Lakeview**: Provides short and concise summarisation for agent steps
- 🤖 **Multi-LLM Support**: Works with OpenAI, Anthropic, and OpenAI-compatible services
- 🔗 **OpenAI-Compatible Services**: Support for OpenRouter, Together AI, Groq, DeepSeek, Alibaba Cloud, Novita AI, and Ollama
- 🛠️ **Rich Tool Ecosystem**: File editing, bash execution, sequential thinking, and more
- 🎯 **Interactive Mode**: Conversational interface for iterative development
- 📊 **Trajectory Recording**: Detailed logging of all agent actions for debugging and analysis
- ⚙️ **Flexible Configuration**: JSON-based configuration with environment variable support
- 🚀 **Easy Installation**: Simple pip-based installation

## 🚀 Quick Start

### Installation

We strongly recommend using [UV](https://docs.astral.sh/uv/) to setup the project.

```bash
git clone <repository-url>
cd trae-agent
uv sync
```

### Setup API Keys

Configure Trae Agent using the config file or environment variables.

**For OpenAI-compatible services**, you can set API keys as environment variables:

```bash
# For OpenAI
export OPENAI_API_KEY="your-openai-api-key"

# For Anthropic
export ANTHROPIC_API_KEY="your-anthropic-api-key"

# For OpenAI-compatible services
export OPENROUTER_API_KEY="sk-or-v1-your-openrouter-key"
export TOGETHER_API_KEY="your-together-api-key"
export GROQ_API_KEY="gsk_your-groq-key"
export DEEPSEEK_API_KEY="sk-your-deepseek-key"
export ALIBABA_API_KEY="your-alibaba-api-key"
export NOVITA_API_KEY="your-novita-api-key"
```

### Basic Usage

```bash
# Run a simple task
trae-cli run "Create a hello world Python script"
```

## 📖 Usage

### Command Line Interface

The main entry point is the `trae` command with several subcommands:

#### `trae run` - Execute a Task

```bash
# Basic task execution
trae-cli run "Create a Python script that calculates fibonacci numbers"

# With specific provider and model
trae-cli run "Fix the bug in main.py" --provider anthropic --model claude-sonnet-4-20250514

# Using OpenRouter with Claude
trae-cli run "Create unit tests" --provider openrouter --model "anthropic/claude-3.5-sonnet"

# Using Groq for fast inference
trae-cli run "Debug this function" --provider groq --model "llama-3.1-70b-versatile"

# Using Alibaba Cloud with free 1M tokens
trae-cli run "Create unit tests" --provider alibaba --model "qwen-turbo"

# Using local Ollama
trae-cli run "Explain this code" --provider ollama --model "llama3.2:latest"

# With custom working directory
trae-cli run "Add unit tests for the utils module" --working-dir /path/to/project

# Save trajectory for debugging
trae-cli run "Refactor the database module" --trajectory-file debug_session.json

# Force to generate patches
trae-cli run "Update the API endpoints" --must-patch
```

#### `trae interactive` - Interactive Mode

```bash
# Start interactive session
trae-cli interactive

# With custom configuration
trae-cli interactive --provider openai --model gpt-4o --max-steps 30
```

In interactive mode, you can:
- Type any task description to execute it
- Use `status` to see agent information
- Use `help` for available commands
- Use `clear` to clear the screen
- Use `exit` or `quit` to end the session

#### `trae show-config` - Configuration Status

```bash
trae-cli show-config

# With custom config file
trae-cli show-config --config-file my_config.json
```

### Configuration

Trae Agent uses a JSON configuration file (`trae_config.json`) for settings. You can copy the example configuration:

```bash
cp trae_config.example.json trae_config.json
# Edit trae_config.json with your API keys
```

Example configuration:

```json
{
  "default_provider": "openrouter",
  "max_steps": 20,
  "model_providers": {
    "openai": {
      "api_key": "your_openai_api_key",
      "model": "gpt-4o",
      "max_tokens": 128000,
      "temperature": 0.5,
      "top_p": 1
    },
    "anthropic": {
      "api_key": "your_anthropic_api_key", 
      "model": "claude-sonnet-4-20250514",
      "max_tokens": 4096,
      "temperature": 0.5,
      "top_p": 1,
      "top_k": 0
    },
    "openrouter": {
      "api_key": "sk-or-v1-your-openrouter-key",
      "base_url": "https://openrouter.ai/api/v1",
      "model": "anthropic/claude-3.5-sonnet",
      "max_tokens": 4096,
      "temperature": 0.5,
      "top_p": 1,
      "parallel_tool_calls": true
    },
    "groq": {
      "api_key": "gsk_your-groq-key",
      "base_url": "https://api.groq.com/openai/v1",
      "model": "llama-3.1-70b-versatile",
      "max_tokens": 4096,
      "temperature": 0.5,
      "top_p": 1,
      "parallel_tool_calls": true
    }
  }
}
```

**Configuration Priority:**
1. Command-line arguments (highest)
2. Configuration file values
3. Environment variables
4. Default values (lowest)

For detailed configuration of OpenAI-compatible services, see [OPENAI_COMPATIBLE_SERVICES.md](OPENAI_COMPATIBLE_SERVICES.md).

### Environment Variables

- `OPENAI_API_KEY` - OpenAI API key
- `ANTHROPIC_API_KEY` - Anthropic API key

## 🛠️ Available Tools

Trae Agent comes with several built-in tools:

- **str_replace_based_edit_tool**: Create, edit, view, and manipulate files
  - `view` - Display file contents or directory listings
  - `create` - Create new files
  - `str_replace` - Replace text in files
  - `insert` - Insert text at specific lines

- **bash**: Execute shell commands and scripts
  - Run commands with persistent state
  - Handle long-running processes
  - Capture output and errors

- **sequential_thinking**: Structured problem-solving and analysis
  - Break down complex problems
  - Iterative thinking with revision capabilities
  - Hypothesis generation and verification

- **task_done**: Signal task completion
  - Mark tasks as successfully completed
  - Provide final results and summaries

## 📊 Trajectory Recording

Trae Agent automatically records detailed execution trajectories for debugging and analysis:

```bash
# Auto-generated trajectory file
trae-cli run "Debug the authentication module"
# Saves to: trajectory_20250612_220546.json

# Custom trajectory file
trae-cli-cliae run "Optimize the database queries" --trajectory-file optimization_debug.json
```

Trajectory files contain:
- **LLM Interactions**: All messages, responses, and tool calls
- **Agent Steps**: State transitions and decision points
- **Tool Usage**: Which tools were called and their results
- **Metadata**: Timestamps, token usage, and execution metrics

For more details, see [TRAJECTORY_RECORDING.md](TRAJECTORY_RECORDING.md).

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Make your changes
4. Add tests for new functionality
6. Commit your changes (`git commit -m 'Add amazing feature'`)
7. Push to the branch (`git push origin feature/amazing-feature`)
8. Open a Pull Request

### Development Guidelines

- Follow PEP 8 style guidelines
- Add tests for new features
- Update documentation as needed
- Use type hints where appropriate
- Ensure all tests pass before submitting

## 📋 Requirements

- Python 3.12+
- OpenAI API key (for OpenAI models)
- Anthropic API key (for Anthropic models)

## 🔧 Troubleshooting

### Common Issues

**Import Errors:**
```bash
# Try setting PYTHONPATH
PYTHONPATH=. trae-cli run "your task"
```

**API Key Issues:**
```bash
# Verify your API keys are set
echo $OPENAI_API_KEY
echo $ANTHROPIC_API_KEY

# Check configuration
trae show-config
```

**Permission Errors:**
```bash
# Ensure proper permissions for file operations
chmod +x /path/to/your/project
```

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

We thank Anthropic for building the [anthropic-quickstart](https://github.com/anthropics/anthropic-quickstarts) project that served as a valuable reference for the tool ecosystem.
