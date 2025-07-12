# Trajectory Recording Functionality

This document describes the trajectory recording functionality added to the Trae Agent project. The system captures detailed information about LLM interactions and agent execution steps for analysis, debugging, and auditing purposes.

## Overview

The trajectory recording system captures:

- **Raw LLM interactions**: Input messages, responses, token usage, and tool calls for various providers including Anthropic, OpenAI, Google Gemini, Azure, and others.
- **Agent execution steps**: State transitions, tool calls, tool results, reflections, and errors
- **Metadata**: Task description, timestamps, model configuration, and execution metrics

## Key Components

### 1. TrajectoryRecorder (`trae_agent/utils/trajectory_recorder.py`)

The core class that handles recording trajectory data to JSON files.

**Key methods:**

- `start_recording()`: Initialize recording with task metadata
- `record_llm_interaction()`: Capture LLM request/response pairs
- `record_agent_step()`: Capture agent execution steps
- `finalize_recording()`: Complete recording and save final results

### 2. Client Integration

All supported LLM clients automatically record interactions when a trajectory recorder is attached.

**Anthropic Client** (`trae_agent/utils/anthropic_client.py`):

```python
# Record trajectory if recorder is available
if self.trajectory_recorder:
    self.trajectory_recorder.record_llm_interaction(
        messages=messages,
        response=llm_response,
        provider="anthropic",
        model=model_parameters.model,
        tools=tools
    )
```

**OpenAI Client** (`trae_agent/utils/openai_client.py`):

```python
# Record trajectory if recorder is available
if self.trajectory_recorder:
    self.trajectory_recorder.record_llm_interaction(
        messages=messages,
        response=llm_response,
        provider="openai",
        model=model_parameters.model,
        tools=tools
    )
```

**Google Gemini Client** (`trae_agent/utils/google_client.py`):

```python
# Record trajectory if recorder is available
if self.trajectory_recorder:
    self.trajectory_recorder.record_llm_interaction(
        messages=messages,
        response=llm_response,
        provider="google",
        model=model_parameters.model,
        tools=tools,
    )
```

**Azure Client** (`trae_agent/utils/azure_client.py`):

```python
# Record trajectory if recorder is available
if self.trajectory_recorder:
    self.trajectory_recorder.record_llm_interaction(
        messages=messages,
        response=llm_response,
        provider="azure",
        model=model_parameters.model,
        tools=tools,
    )
```

**Doubao Client** (`trae_agent/utils/doubao_client.py`):

```python
# Record trajectory if recorder is available
if self.trajectory_recorder:
    self.trajectory_recorder.record_llm_interaction(
        messages=messages,
        response=llm_response,
        provider="doubao",
        model=model_parameters.model,
        tools=tools,
    )
```

**Ollama Client** (`trae_agent/utils/ollama_client.py`):

```python
# Record trajectory if recorder is available
if self.trajectory_recorder:
    self.trajectory_recorder.record_llm_interaction(
        messages=messages,
        response=llm_response,
        provider="openai", # Ollama client uses OpenAI's provider name for consistency
        model=model_parameters.model,
        tools=tools,
    )
```

**OpenRouter Client** (`trae_agent/utils/openrouter_client.py`):

```python
# Record trajectory if recorder is available
if self.trajectory_recorder:
    self.trajectory_recorder.record_llm_interaction(
        messages=messages,
        response=llm_response,
        provider="openrouter",
        model=model_parameters.model,
        tools=tools,
    )
```

### 3. Agent Integration

The base Agent class automatically records execution steps:

```python
# Record agent step
if self.trajectory_recorder:
    self.trajectory_recorder.record_agent_step(
        step_number=step.step_number,
        state=step.state.value,
        llm_messages=messages,
        llm_response=step.llm_response,
        tool_calls=step.tool_calls,
        tool_results=step.tool_results,
        reflection=step.reflection,
        error=step.error
    )
```

## Usage

### CLI Usage

#### Basic Recording (Auto-generated filename)

```bash
trae run "Create a hello world Python script"
# Trajectory saved to: trajectories/trajectory_20250612_220546.json
```

#### Custom Filename

```bash
trae run "Fix the bug in main.py" --trajectory-file my_debug_session.json
# Trajectory saved to: my_debug_session.json
```

#### Interactive Mode

```bash
trae interactive --trajectory-file session.json
```

### Programmatic Usage

```python
from trae_agent.agent.trae_agent import TraeAgent
from trae_agent.utils.llm_client import LLMProvider
from trae_agent.utils.config import ModelParameters

# Create agent
agent = TraeAgent(LLMProvider.ANTHROPIC, model_parameters, max_steps=10)

# Set up trajectory recording
trajectory_path = agent.setup_trajectory_recording("my_trajectory.json")

# Configure and run task
agent.new_task("My task", task_args)
execution = await agent.execute_task()

# Trajectory is automatically saved
print(f"Trajectory saved to: {trajectory_path}")
```

## Trajectory File Format

The trajectory file is a JSON document with the following structure:

```json
{
  "task": "Description of the task",
  "start_time": "2025-06-12T22:05:46.433797",
  "end_time": "2025-06-12T22:06:15.123456",
  "provider": "anthropic",
  "model": "claude-sonnet-4-20250514",
  "max_steps": 20,
  "llm_interactions": [
    {
      "timestamp": "2025-06-12T22:05:47.000000",
      "provider": "anthropic",
      "model": "claude-sonnet-4-20250514",
      "input_messages": [
        {
          "role": "system",
          "content": "You are a software engineering assistant..."
        },
        {
          "role": "user",
          "content": "Create a hello world Python script"
        }
      ],
      "response": {
        "content": "I'll help you create a hello world Python script...",
        "model": "claude-sonnet-4-20250514",
        "finish_reason": "end_turn",
        "usage": {
          "input_tokens": 150,
          "output_tokens": 75,
          "cache_creation_input_tokens": 0,
          "cache_read_input_tokens": 0,
          "reasoning_tokens": null
        },
        "tool_calls": [
          {
            "call_id": "call_123",
            "name": "str_replace_based_edit_tool",
            "arguments": {
              "command": "create",
              "path": "hello.py",
              "file_text": "print('Hello, World!')"
            }
          }
        ]
      },
      "tools_available": ["str_replace_based_edit_tool", "bash", "task_done"]
    }
  ],
  "agent_steps": [
    {
      "step_number": 1,
      "timestamp": "2025-06-12T22:05:47.500000",
      "state": "thinking",
      "llm_messages": [...],
      "llm_response": {...},
      "tool_calls": [
        {
          "call_id": "call_123",
          "name": "str_replace_based_edit_tool",
          "arguments": {...}
        }
      ],
      "tool_results": [
        {
          "call_id": "call_123",
          "success": true,
          "result": "File created successfully",
          "error": null
        }
      ],
      "reflection": null,
      "error": null
    }
  ],
  "success": true,
  "final_result": "Hello world Python script created successfully!",
  "execution_time": 28.689999
}
```

### Field Descriptions

**Root Level:**

- `task`: The original task description
- `start_time`/`end_time`: ISO format timestamps
- `provider`: LLM provider used (e.g., "anthropic", "openai", "google", "azure", "doubao", "ollama", "openrouter")
- `model`: Model name
- `max_steps`: Maximum allowed execution steps
- `success`: Whether the task completed successfully
- `final_result`: Final output or result message
- `execution_time`: Total execution time in seconds

**LLM Interactions:**

- `timestamp`: When the interaction occurred
- `provider`: LLM provider used for this interaction
- `model`: Model used for this interaction
- `input_messages`: Messages sent to the LLM
- `response`: Complete LLM response including content, usage, and tool calls
- `tools_available`: List of tools available during this interaction

**Agent Steps:**

- `step_number`: Sequential step number
- `state`: Agent state ("thinking", "calling_tool", "reflecting", "completed", "error")
- `llm_messages`: Messages used in this step
- `llm_response`: LLM response for this step
- `tool_calls`: Tools called in this step
- `tool_results`: Results from tool execution
- `reflection`: Agent's reflection on the step
- `error`: Error message if the step failed

## Benefits

1. **Debugging**: Trace exactly what happened during agent execution
2. **Analysis**: Understand LLM reasoning and tool usage patterns
3. **Auditing**: Maintain records of what changes were made and why
4. **Research**: Analyze agent behavior for improvements
5. **Compliance**: Keep detailed logs of automated actions

## File Management

- Trajectory files are saved in the current working directory by default
- Files use timestamp-based naming if no custom path is provided
- Files are automatically created/overwritten
- The system handles directory creation if needed
- Files are saved continuously during execution (not just at the end)

## Security Considerations

- Trajectory files may contain sensitive information (API keys are not logged)
- Store trajectory files securely if they contain proprietary code or data
- Trajectory files are automatically saved to the `trajectories/` directory, which is excluded from version control

## Example Use Cases

1. **Debugging Failed Tasks**: Review what went wrong in agent execution
2. **Performance Analysis**: Analyze token usage and execution patterns
3. **Compliance Auditing**: Track all changes made by the agent
4. **Model Comparison**: Compare behavior across different LLM providers/models
5. **Tool Usage Analysis**: Understand which tools are used and how often
