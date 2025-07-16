# Tools

Trae Agent provides five built-in tools for software engineering tasks:

## str_replace_based_edit_tool

File and directory manipulation tool with persistent state.

**Operations:**
- `view` - Display file contents with line numbers, or list directory contents up to 2 levels deep
- `create` - Create new files (fails if file already exists)
- `str_replace` - Replace exact string matches in files (must be unique)
- `insert` - Insert text after a specified line number

**Key features:**
- Requires absolute paths (e.g., `/repo/file.py`)
- String replacements must match exactly, including whitespace
- Supports line range viewing for large files

## bash

Execute shell commands in a persistent session.

**Features:**
- Commands run in a shared bash session that maintains state
- 120-second timeout per command
- Session restart capability
- Background process support

**Usage notes:**
- Use `restart: true` to reset the session
- Avoid commands with excessive output
- Long-running commands should use `&` for background execution

## sequential_thinking

Structured problem-solving tool for complex analysis.

**Capabilities:**
- Break down problems into sequential thoughts
- Revise and branch from previous thoughts
- Dynamically adjust the number of thoughts needed
- Track thinking history and alternative approaches
- Generate and verify solution hypotheses

**Parameters:**
- `thought` - Current thinking step
- `thought_number` / `total_thoughts` - Progress tracking
- `next_thought_needed` - Continue thinking flag
- `is_revision` / `revises_thought` - Revision tracking
- `branch_from_thought` / `branch_id` - Alternative exploration

## task_done

Signal task completion with verification requirement.

**Purpose:**
- Mark tasks as successfully completed
- Must be called only after proper verification
- Encourages writing test/reproduction scripts

**Output:**
- Simple "Task done." message
- No parameters required

## json_edit_tool

Precise JSON file editing using JSONPath expressions.

**Operations:**
- `view` - Display entire file or content at specific JSONPaths
- `set` - Update existing values at specified paths
- `add` - Add new properties to objects or append to arrays
- `remove` - Delete elements at specified paths

**JSONPath examples:**
- `$.users[0].name` - First user's name
- `$.config.database.host` - Nested object property
- `$.items[*].price` - All item prices
- `$..key` - Recursive search for key

**Features:**
- Validates JSON syntax and structure
- Preserves formatting with pretty printing option
- Detailed error messages for invalid operations
