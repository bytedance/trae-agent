"""Response schemas for trae_agent HTTP API."""

from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


class LLMUsage(BaseModel):
    """LLM usage statistics."""
    
    input_tokens: int = Field(0, description="Number of input tokens")
    output_tokens: int = Field(0, description="Number of output tokens") 
    cache_creation_input_tokens: int = Field(0, description="Cache creation input tokens")
    cache_read_input_tokens: int = Field(0, description="Cache read input tokens")
    reasoning_tokens: int = Field(0, description="Reasoning tokens")


class ToolCall(BaseModel):
    """Tool call information."""
    
    call_id: str = Field(description="Unique call identifier")
    name: str = Field(description="Tool name")
    arguments: Dict[str, Any] = Field(default_factory=dict, description="Tool arguments")


class LLMMessage(BaseModel):
    """LLM message structure."""
    
    role: Literal["system", "user", "assistant"] = Field(description="Message role")
    content: str = Field(description="Message content")


class LLMResponse(BaseModel):
    """LLM response structure."""
    
    content: str = Field(description="Response content")
    model: str = Field(description="Model used")
    finish_reason: str = Field(description="Finish reason")
    usage: LLMUsage = Field(description="Usage statistics")
    tool_calls: List[ToolCall] = Field(default_factory=list, description="Tool calls made")


class LLMInteraction(BaseModel):
    """Complete LLM interaction record."""
    
    timestamp: str = Field(description="ISO timestamp of interaction")
    provider: str = Field(description="LLM provider used")
    model: str = Field(description="Model used")
    input_messages: List[LLMMessage] = Field(description="Input messages")
    response: LLMResponse = Field(description="LLM response")
    tools_available: List[str] = Field(default_factory=list, description="Available tools")


class ExecutionStep(BaseModel):
    """Single execution step information."""
    
    step_number: int = Field(description="Step sequence number")
    timestamp: str = Field(description="ISO timestamp of step")
    tool_used: Optional[str] = Field(None, description="Tool used in this step")
    tool_input: Optional[Dict[str, Any]] = Field(None, description="Tool input parameters")
    tool_output: Optional[str] = Field(None, description="Tool output result")
    duration_ms: Optional[int] = Field(None, description="Step duration in milliseconds")
    success: bool = Field(True, description="Whether step completed successfully")
    error_message: Optional[str] = Field(None, description="Error message if step failed")


class TrajectoryData(BaseModel):
    """Complete trajectory information."""
    
    task: str = Field(description="Original task description")
    start_time: str = Field(description="ISO timestamp of execution start")
    end_time: Optional[str] = Field(None, description="ISO timestamp of execution end")
    provider: str = Field(description="LLM provider used")
    model: str = Field(description="Model used")
    max_steps: int = Field(description="Maximum allowed steps")
    llm_interactions: List[LLMInteraction] = Field(default_factory=list, description="All LLM interactions")
    execution_steps: List[ExecutionStep] = Field(default_factory=list, description="Detailed execution steps")
    total_duration_ms: Optional[int] = Field(None, description="Total execution duration")
    success: bool = Field(False, description="Whether execution completed successfully")
    result_summary: Optional[str] = Field(None, description="Summary of execution result")


class ExecutionStats(BaseModel):
    """Execution statistics and metrics."""
    
    total_steps: int = Field(0, description="Total number of steps executed")
    total_llm_interactions: int = Field(0, description="Total LLM interactions")
    total_input_tokens: int = Field(0, description="Total input tokens across all interactions")
    total_output_tokens: int = Field(0, description="Total output tokens across all interactions")
    execution_duration_ms: int = Field(0, description="Total execution duration in milliseconds")
    tools_used: Dict[str, int] = Field(default_factory=dict, description="Count of each tool used")
    success_rate: float = Field(1.0, description="Percentage of successful steps")
    average_step_duration_ms: Optional[float] = Field(None, description="Average step duration")


class Patch(BaseModel):
    """Code patch information."""
    
    file_path: str = Field(description="Path to the patched file")
    original_content: Optional[str] = Field(None, description="Original file content")
    patched_content: str = Field(description="Patched file content")
    diff: Optional[str] = Field(None, description="Unified diff format")
    line_changes: Dict[str, int] = Field(
        default_factory=dict,
        description="Line changes summary (added, removed, modified)"
    )


class RunResponse(BaseModel):
    """Response schema for agent execution."""
    
    success: bool = Field(description="Whether execution completed successfully")
    result: str = Field(description="Main result or output message")
    patches: List[Patch] = Field(default_factory=list, description="Code patches applied")
    patch_path: Optional[str] = Field(None, description="Path to patch file if created")
    trajectory: TrajectoryData = Field(description="Complete execution trajectory")
    stats: ExecutionStats = Field(description="Execution statistics")
    execution_id: str = Field(description="Unique execution identifier")
    start_time: str = Field(default_factory=lambda: datetime.utcnow().isoformat(), description="Execution start time")
    end_time: Optional[str] = Field(None, description="Execution end time")
    error_message: Optional[str] = Field(None, description="Error message if execution failed")


class ConfigData(BaseModel):
    """Configuration data structure."""
    
    provider: Optional[str] = Field(None, description="Default LLM provider")
    model: Optional[str] = Field(None, description="Default model")
    api_key_configured: bool = Field(False, description="Whether API key is configured")
    working_dir: Optional[str] = Field(None, description="Default working directory") 
    max_steps: Optional[int] = Field(None, description="Default max steps")
    timeout: int = Field(900, description="Default timeout")
    console_type: str = Field("simple", description="Default console type")
    mcp_servers: Dict[str, Any] = Field(default_factory=dict, description="MCP server configurations")


class ConfigResponse(BaseModel):
    """Response schema for configuration display."""
    
    config: ConfigData = Field(description="Current configuration")
    config_file_path: str = Field(description="Path to configuration file")
    config_file_exists: bool = Field(description="Whether configuration file exists")
    last_modified: Optional[str] = Field(None, description="Last modification timestamp")


class StreamEvent(BaseModel):
    """Streaming event for real-time execution updates."""
    
    event: Literal[
        "start", 
        "step", 
        "tool_call", 
        "llm_interaction", 
        "progress",
        "complete", 
        "error",
        "test"  # For testing purposes
    ] = Field(description="Event type")
    data: Dict[str, Any] = Field(description="Event data payload")
    timestamp: str = Field(
        default_factory=lambda: datetime.utcnow().isoformat(),
        description="Event timestamp"
    )
    execution_id: str = Field(description="Execution identifier for correlation")
    sequence_number: int = Field(description="Event sequence number")


class ErrorResponse(BaseModel):
    """Error response schema."""
    
    error: str = Field(description="Error type")
    message: str = Field(description="Human-readable error message")
    details: Optional[Dict[str, Any]] = Field(None, description="Additional error details")
    timestamp: str = Field(
        default_factory=lambda: datetime.utcnow().isoformat(),
        description="Error timestamp"
    )
    execution_id: Optional[str] = Field(None, description="Execution ID if applicable")