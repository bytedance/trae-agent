"""Request schemas for trae_agent HTTP API."""

from pathlib import Path
from typing import Any, Dict, Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator


class RunRequest(BaseModel):
    """
    Request schema for agent execution.
    
    Maps to CLI parameters from trae_agent/cli.py:run() function.
    """
    
    task: Optional[str] = Field(
        None, 
        min_length=1, 
        max_length=50000,
        description="Task description for the agent to execute"
    )
    file_path: Optional[str] = Field(
        None, 
        description="Path to a file containing the task description"
    )
    patch_path: Optional[str] = Field(
        None,
        description="Path to patch file"
    )
    provider: Optional[str] = Field(
        None,
        description="LLM provider to use (e.g., 'anthropic', 'openai', 'google')"
    )
    model: Optional[str] = Field(
        None,
        description="Specific model to use"
    )
    model_base_url: Optional[str] = Field(
        None,
        description="Base URL for the model API"
    )
    api_key: Optional[str] = Field(
        None,
        description="API key for the LLM provider",
        min_length=1,
        max_length=1000  # Reasonable limit for API keys
    )
    max_steps: Optional[int] = Field(
        None, 
        gt=0, 
        le=200,
        description="Maximum number of execution steps"
    )
    working_dir: Optional[str] = Field(
        None,
        description="Working directory for the agent"
    )
    must_patch: bool = Field(
        False,
        description="Whether to patch the code"
    )
    config_file: str = Field(
        "trae_config.yaml",
        description="Path to configuration file"
    )
    trajectory_file: Optional[str] = Field(
        None,
        description="Path to save trajectory file"
    )
    console_type: Optional[Literal["simple", "rich"]] = Field(
        "simple",
        description="Type of console to use"
    )
    agent_type: Literal["trae_agent"] = Field(
        "trae_agent",
        description="Type of agent to use"
    )
    
    # HTTP-specific fields
    timeout: int = Field(
        900, 
        ge=30, 
        le=3600,
        description="Request timeout in seconds (30s-1hr range)"
    )
    seed: Optional[int] = Field(
        None, 
        ge=0, 
        le=2**32-1,
        description="Random seed for reproducible results"
    )
    trajectory: Optional[Dict[str, Any]] = Field(
        None,
        description="Previous trajectory data for continuation"
    )

    @field_validator('working_dir')
    @classmethod
    def validate_working_dir(cls, v: Optional[str]) -> Optional[str]:
        """Validate working directory is absolute path if provided."""
        if v and not Path(v).is_absolute():
            raise ValueError("Working directory must be absolute path")
        return v
    
    @field_validator('api_key')
    @classmethod
    def validate_api_key(cls, v: Optional[str]) -> Optional[str]:
        """Validate API key format."""
        if v is None:
            return v
            
        # Check for whitespace-only keys
        if v.isspace():
            raise ValueError("API key cannot be whitespace only")
            
        # Strip whitespace and check minimum length
        v = v.strip()
        if len(v) == 0:
            raise ValueError("API key cannot be empty")
            
        return v
    
    @model_validator(mode='after')
    def validate_task_or_file_path(self) -> 'RunRequest':
        """Ensure either task or file_path is provided."""
        if not self.task and not self.file_path:
            raise ValueError("Either 'task' or 'file_path' must be provided")
        return self
    
    @field_validator('file_path', 'patch_path', 'config_file', 'trajectory_file')
    @classmethod
    def validate_file_paths(cls, v: Optional[str]) -> Optional[str]:
        """Basic security validation for file paths."""
        if v is None:
            return v
        
        # Empty paths are not allowed
        if not v or v.isspace():
            raise ValueError("Empty file paths are not allowed")
        
        # Prevent path traversal attacks
        if '..' in v:
            raise ValueError("Relative paths with '..' are not allowed")
            
        # Check for system file access (basic protection)
        dangerous_paths = ['/etc/', '/root/', '/sys/', '/proc/', '/dev/']
        if any(v.startswith(path) for path in dangerous_paths):
            raise ValueError("Access to system directories is not allowed")
            
        # Allow certain relative paths for config files
        if not Path(v).is_absolute():
            # More permissive for certain cases
            if v.startswith('./') and v.endswith(('.yaml', '.yml')):
                return v  # Allow relative config files in current directory
            elif v == "trae_config.yaml":
                return v  # Allow default config
            else:
                raise ValueError("Relative paths are not allowed for security")
        
        return v


class ConfigRequest(BaseModel):
    """Request schema for configuration operations."""
    
    config_file: Optional[str] = Field(
        None,
        description="Configuration file to reload"
    )


class ConfigReloadRequest(BaseModel):
    """Request schema for configuration reload."""
    
    config_file: str = Field(
        "trae_config.yaml",
        description="Path to configuration file to reload"
    )