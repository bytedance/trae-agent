# Trae Agent CLI Usage Guide

This document describes how to use the Trae Agent CLI with its new Ratatui-based interface.

## Installation

Build the project:
```bash
cargo build --release
```

The binary will be available at `target/release/trae-agent`.

## Usage Modes

The Trae Agent CLI supports three primary usage modes:

### 1. Interactive Mode (Default)

Start interactive mode with:
```bash
trae-agent
# or explicitly
trae-agent --interactive
```

**Interactive Mode Features:**
- **Top 70%**: Agent output display with welcome message initially, then real-time agent output during task execution
- **Next 10%**: Real-time agent status and token usage statistics
- **Next 10%**: Input box where you type tasks to execute
- **Bottom 10%**: Keyboard shortcuts and help information

**Keyboard Controls:**
- `Enter`: Execute the task typed in the input box
- `Ctrl+C`, `Ctrl+Q`, `Esc`: Quit the application (with confirmation if task is running)
- `↑/↓`: Scroll through output history (or navigate autocomplete suggestions)
- `←/→`: Move cursor in the input field
- `Backspace`: Delete characters in input
- `Tab`: Accept autocomplete suggestion

**Special Commands:**
- `/help`: Show help information
- `/quit` or `/exit`: Exit the application

**Auto-completion:**
- Type `/` to see available commands
- Use `↑/↓` or `Tab` to navigate and select suggestions
- Press `Enter` or `Tab` to apply the selected suggestion
- Press `Esc` to hide autocomplete

**Quit Confirmation:**
- When a task is running, quit attempts show a confirmation popup
- Press `Y` to confirm quit, `N` or `Esc` to cancel

### 2. Single Run Mode

Execute a task directly without interactive mode:
```bash
trae-agent --run "your task description"
```

Example:
```bash
trae-agent --run "Fix the bug in the authentication module"
```

### 3. Help Mode

Display help information:
```bash
trae-agent --help
```

## Configuration Options

### Global Options

All modes support these configuration options:

- `--workspace <PATH>`: Set the working directory (default: current directory)
- `--provider <PROVIDER>`: Choose AI provider (openai, anthropic, azure) (default: openai)
- `--model <MODEL>`: Specify the model to use (default: gpt-4)
- `--verbose`: Enable verbose logging
- `--config <CONFIG>`: Specify configuration file path

### Examples

```bash
# Interactive mode with custom workspace and model
trae-agent --workspace /path/to/project --provider anthropic --model claude-3-sonnet

# Single run with custom settings
trae-agent --run "Refactor the main function" --workspace /my/project --model gpt-4-turbo

# Verbose logging enabled
trae-agent --run "Debug the connection issue" --verbose
```

## Environment Variables

Set up your API keys using environment variables:

### OpenAI
```bash
export OPENAI_API_KEY="your-openai-api-key"
# or
export API_KEY="your-openai-api-key"
```

### Anthropic
```bash
export ANTHROPIC_API_KEY="your-anthropic-api-key"
```

### Azure OpenAI
```bash
export AZURE_API_KEY="your-azure-api-key"
export AZURE_BASE_URL="https://your-resource.openai.azure.com"
```

## Interactive Mode Layout

```
┌─────────────────────────────────────────────────────────────────────┐
│                        Agent Output (70%)                          │
│  ████████┐██████┐  █████┐ ███████┐    █████┐  ██████┐ ███████┐     │
│  └──██┌──┘██┌──██┐██┌──██┐██┌────┘   ██┌──██┐██┌────┘ ██┌────┘     │
│     ██│   ██████┌┘███████│█████┐     ███████│██│  ██┐ █████┐       │
│     ██│   ██┌──██┐██┌──██│██┌──┘     ██┌──██│██│  └██┐██┌──┘       │
│     ██│   ██│  ██│██│  ██│███████┐   ██│  ██│└██████┌┘███████┐     │
│     └─┘   └─┘  └─┘└─┘  └─┘└──────┘   └─┘  └─┘ └─────┘ └──────┘     │
│                                                                     │
│  🤖 Trae Agent - Intelligent coding assistant                      │
│  💡 Version: 0.1.0                                                 │
│                                                                     │
│  Welcome to Trae Agent interactive mode!                           │
│  Type your task below and press Enter to start.                    │
├─────────────────────────────────────────────────────────────────────┤
│ Agent Status (10%)          │ Token Usage (10%)                    │
│ Status: Idle                │ Input: 0 | Output: 0 | Total: 0     │
├─────────────────────────────────────────────────────────────────────┤
│ Enter Task (10%)                                                   │
│ > [Type your task here...]                                         │
├─────────────────────────────────────────────────────────────────────┤
│ Shortcuts (10%)                                                    │
│ • Enter: Run task                                                  │
│ • Ctrl+C/Ctrl+Q/Esc: Quit                                         │
│ • ↑/↓: Scroll output                                               │
│ • /help: Show help                                                 │
└─────────────────────────────────────────────────────────────────────┘
```

## Agent Status Indicators

The agent status section shows real-time information about what the agent is doing:

- **Idle**: Agent is waiting for input
- **Running**: Agent is processing a task
- **Thinking**: Agent is analyzing the task
- **Calling Tool**: Agent is executing tools (bash, file editing, etc.)
- **Reflecting**: Agent is reviewing its actions
- **Completed**: Task has finished successfully
- **Error**: An error occurred during execution

## Token Usage Tracking

The token usage section provides real-time statistics:
- **Input**: Tokens sent to the AI model
- **Output**: Tokens received from the AI model
- **Total**: Combined input and output tokens

This helps you monitor API usage costs in real-time.

## Troubleshooting

### Common Issues

1. **API Key Not Found**
   ```
   ❌ API key not found. Please set the appropriate environment variable
   ```
   Solution: Set the correct environment variable for your chosen provider.

2. **Unknown Provider**
   ```
   ❌ Unknown provider: xyz. Supported providers: openai, anthropic, azure
   ```
   Solution: Use one of the supported providers: `openai`, `anthropic`, or `azure`.

3. **Connection Issues**
   - Check your internet connection
   - Verify your API key is valid
   - For Azure, ensure `AZURE_BASE_URL` is correctly set

### Debug Mode

Use `--verbose` flag to enable detailed logging:
```bash
trae-agent --run "your task" --verbose
```

This will show detailed information about the agent's execution process, API calls, and any errors encountered.
