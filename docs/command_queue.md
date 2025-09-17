# Command Queue Usage Guide

This document describes how to use the Trae Agent command queue functionality to implement command caching and sequential execution.

## Feature Overview

The command queue functionality allows you to:
- Add multiple commands to the queue for sequential execution
- Continue adding new commands during command execution (real-time queuing)
- Persistently store commands to avoid command loss (stored in user home directory by default)
- View queue status and recent command list
- Cancel pending commands
- Clean up completed/cancelled/failed commands
- Manually start the queue processor

## Basic Usage

### 1) Adding Commands to Queue

Use the `add-queue` command to add tasks to the queue:

```bash
# Add first command to queue
trae-cli add-queue "Add tests for utils module" 
trae-cli add-queue "Add tests for utils module" --working-dir /path/to/project

# Continue adding more commands
trae-cli add-queue "Fix linting issues" --working-dir /path/to/project
trae-cli add-queue "Update documentation" --working-dir /path/to/project
```

Key points:
- Must provide task text or specify task file via `--file` (choose one).
- Recommend always explicitly setting `--working-dir` to absolute path.
- Supports all the same parameters as normal execution (e.g., `--provider`, `--model`, `--config-file`, `--must-patch`, `--trajectory-file`, `--patch-path`, `--console-type`, `--agent-type`, etc.). These options will be persisted together and take effect as-is during execution.

### 2) Viewing Queue Status

```bash
# View current queue status (commands: queue-status or queue_status both work)
trae-cli queue-status
```

Output includes:
- Count of total/pending/running/completed/failed commands
- Whether processor is running
- Current executing command ID (if any)
- Brief information of recent 10 commands (ID, status, task summary, working directory, creation time)

### 3) Starting Queue Processor

Normally, when you first use `add-queue` to enqueue and no processor is currently running, it will automatically start the processor and begin execution.
To manually start or restart when stopped, execute:

```bash
trae-cli run --queue
```

### 4) Cleaning Queue

Cancel all pending commands and clear all queue commands:

```bash
trae-cli clear-all
```

This command will:
- First cancel all commands with "pending" status, marking them as "cancelled"
- Then clear all completed, cancelled, and failed commands
- Finally the queue will become empty

## Available Commands and Parameters Overview

- Queue execution (core):
  - `trae-cli add-queue <TASK> [common parameters]`
  - `trae-cli add-queue --file <TASK_FILE> [common parameters]`

- Queue management:
  - View status: `trae-cli queue-status` (or `queue_status`)
  - Clean queue: `trae-cli clear-all` (or `clear_all`)
  - Manual processing: `trae-cli run --queue`

- Common parameters (consistent with normal execution, all can be persisted with commands):
  - `--working-dir, -w` Absolute path working directory
  - `--provider, -p` Model provider
  - `--model, -m` Model name
  - `--model-base-url` Model API base URL
  - `--api-key, -k` API Key (can also be set via environment variable)
  - `--max-steps` Maximum execution steps
  - `--must-patch, -mp` Whether patch generation is required
  - `--patch-path, -pp` Patch output path
  - `--config-file` Configuration file path (supports .yaml/.yml; will fallback to same-name .json if not exists)
  - `--trajectory-file, -t` Trajectory file path
  - `--console-type, -ct` Console type: `simple`/`rich`
  - `--agent-type, -at` Agent type: `trae_agent`

Tip: Command names and options using dash format (like `queue-status`, `clear-completed`, `process-queue`) are more CLI-conventional, also compatible with underscore format.

## Execution Principles (Brief)

- Each queued command is saved as a record containing: task, working directory, original CLI options, etc.
- The queue processor sequentially retrieves "pending" commands, switches to the command's working directory, and creates and runs Agent according to recorded options.
- Upon completion, it's marked as "completed"; if exception occurs, it's marked as "failed" with error information recorded; if cancelled, it's marked as "cancelled".
- The processor handles one command at a time, executing in queue order, while new commands can be continuously queued during processing.

## Persistence and File Location

- Queue file is located by default at: `.trae_queue.json` in user home directory.
- The file is automatically loaded on application startup; if "running" commands exist from last exit, they will be reset to "pending" to avoid deadlock after interruption.
- Note: Queued options are written to the file as-is (including potentially sensitive information like `--api-key`). Please properly protect local file permissions to avoid leakage.

## Best Practices

- Always use absolute paths for `--working-dir`.
- Queuing during processor execution won't interrupt current execution; new commands will be processed in order afterwards.
- After long-term queue usage, recommend periodically executing `clear-all` for cleanup to keep file size manageable.
- If queue has "pending" commands but `queue-status` shows processor not running, manually execute `run --queue`.

## Frequently Asked Questions (FAQ)

- What if queue doesn't auto-start?
  - Execute `trae-cli run --queue` to manually start. Check the "Processor Running" indicator in `queue-status` to confirm if it's running.

- Can multiple commands execute simultaneously?
  - Current processor works in single-instance serial mode to ensure order and safety. Parallel execution is not in default support scope.

- Command cancellation not working?
  - Only "pending" status can be cancelled; "running" commands cannot be forcibly terminated.

- Windows usage notes?
  - Please ensure `--working-dir` uses absolute paths. If path contains spaces, please add quotes.

For more CLI functionality, please refer to `trae-cli --help` and normal execution mode documentation.
