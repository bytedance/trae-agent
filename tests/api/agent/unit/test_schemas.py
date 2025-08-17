"""Unit tests for agent API schemas."""

import pytest
from pathlib import Path
from pydantic import ValidationError

from trae_agent.schemas import (
    RunRequest,
    ConfigRequest, 
    ConfigReloadRequest,
    RunResponse,
    ConfigResponse,
    StreamEvent,
    ErrorResponse,
    ExecutionStats,
    TrajectoryData,
    Patch
)


class TestRunRequest:
    """Test RunRequest schema validation."""
    
    def test_valid_run_request(self):
        """Test valid RunRequest creation."""
        request = RunRequest(
            task="Create a Python script",
            provider="anthropic",
            model="claude-3-5-sonnet-20241022", 
            timeout=300,
            max_steps=50
        )
        
        assert request.task == "Create a Python script"
        assert request.provider == "anthropic"
        assert request.model == "claude-3-5-sonnet-20241022"
        assert request.timeout == 300
        assert request.max_steps == 50
        assert request.agent_type == "trae_agent"  # default value
        assert request.must_patch is False  # default value
    
    def test_run_request_with_file_path(self, temp_dir: Path):
        """Test RunRequest with file_path instead of task."""
        task_file = temp_dir / "task.txt"
        task_file.write_text("Create a hello world script")
        
        request = RunRequest(
            file_path=str(task_file),
            provider="openai"
        )
        
        assert request.task is None
        assert request.file_path == str(task_file)
        assert request.provider == "openai"
    
    def test_run_request_validation_errors(self):
        """Test RunRequest validation errors."""
        
        # Test missing task and file_path
        with pytest.raises(ValidationError) as exc_info:
            RunRequest(provider="anthropic")
        
        error_messages = str(exc_info.value)
        assert "Either 'task' or 'file_path' must be provided" in error_messages
        
        # Test invalid timeout range
        with pytest.raises(ValidationError):
            RunRequest(task="test", timeout=3700)  # > 3600 seconds
            
        with pytest.raises(ValidationError):
            RunRequest(task="test", timeout=10)   # < 30 seconds
        
        # Test invalid max_steps
        with pytest.raises(ValidationError):
            RunRequest(task="test", max_steps=0)   # <= 0
            
        with pytest.raises(ValidationError):
            RunRequest(task="test", max_steps=300) # > 200
    
    def test_working_dir_validation(self):
        """Test working directory path validation."""
        
        # Valid absolute path
        request = RunRequest(
            task="test",
            working_dir="/absolute/path"
        )
        assert request.working_dir == "/absolute/path"
        
        # Invalid relative path with ..
        with pytest.raises(ValidationError) as exc_info:
            RunRequest(
                task="test", 
                working_dir="../relative/path"
            )
        assert "Working directory must be absolute path" in str(exc_info.value)
    
    def test_console_type_validation(self):
        """Test console type validation."""
        # Valid console types
        for console_type in ["simple", "rich"]:
            request = RunRequest(task="test", console_type=console_type)
            assert request.console_type == console_type
        
        # Invalid console type
        with pytest.raises(ValidationError):
            RunRequest(task="test", console_type="invalid")
    
    def test_agent_type_validation(self):
        """Test agent type validation."""
        # Valid agent type
        request = RunRequest(task="test", agent_type="trae_agent")
        assert request.agent_type == "trae_agent"
        
        # Invalid agent type
        with pytest.raises(ValidationError):
            RunRequest(task="test", agent_type="invalid_agent")
    
    @pytest.mark.parametrize("seed", [0, 100, 2**32-1])
    def test_valid_seed_values(self, seed):
        """Test valid seed value ranges."""
        request = RunRequest(task="test", seed=seed)
        assert request.seed == seed
    
    @pytest.mark.parametrize("seed", [-1, 2**32])  
    def test_invalid_seed_values(self, seed):
        """Test invalid seed value ranges."""
        with pytest.raises(ValidationError):
            RunRequest(task="test", seed=seed)
    
    @pytest.mark.parametrize("file_path,should_pass,security_concern", [
        # Valid paths
        ("/tmp/safe/file.txt", True, None),
        ("/home/user/project/file.py", True, None),
        ("/opt/workspace/script.sh", True, None),
        
        # Security concerns that should be caught
        ("../../../etc/passwd", False, "path_traversal"),
        ("/etc/passwd", False, "system_file_access"),
        ("/root/.ssh/id_rsa", False, "private_key_access"),
        ("~/../../etc/shadow", False, "home_escape"),
        ("/tmp/../etc/passwd", False, "tmp_traversal"),
        
        # Edge cases
        ("", False, "empty_path"),
        ("relative/path/file.txt", False, "relative_path"),
        ("./config.yaml", True, "current_dir_relative"),  # More permissive for config files
    ])
    def test_file_path_security_validation(self, file_path, should_pass, security_concern):
        """Test comprehensive file path security validation."""
        if should_pass:
            # Should create successfully for non-critical paths
            if security_concern != "current_dir_relative":
                request = RunRequest(task="test", patch_path=file_path)
                assert request.patch_path == file_path
            else:
                # Config files might be more permissive
                request = RunRequest(task="test", config_file=file_path)
                assert request.config_file == file_path
        else:
            # Should raise ValidationError for security concerns
            with pytest.raises(ValidationError) as exc_info:
                if security_concern in ["empty_path", "relative_path"]:
                    RunRequest(task="test", patch_path=file_path)
                else:
                    # For system files, might be caught at different validation levels
                    RunRequest(task="test", file_path=file_path)
            
            # Verify the error is related to the security concern
            error_msg = str(exc_info.value)
            if security_concern == "path_traversal":
                assert ("traversal" in error_msg.lower() or "invalid" in error_msg.lower() or "relative paths with '..' are not allowed" in error_msg.lower())
    
    @pytest.mark.parametrize("api_key,should_pass,reason", [
        # Valid API keys
        ("sk-test-key-12345", True, "standard_openai_format"),
        ("anthropic-key-abc123", True, "anthropic_format"),
        ("x" * 100, True, "very_long_key"),
        ("key-with-special-chars_123!@#", True, "special_characters"),
        
        # Invalid API keys
        ("", False, "empty_key"),
        ("   ", False, "whitespace_only"),
        ("x" * 1001, False, "too_long"),  # Assuming max length limit
        (None, True, "none_allowed"),  # None should be acceptable (no key)
    ])
    def test_api_key_validation(self, api_key, should_pass, reason):
        """Test API key validation with various formats."""
        base_data = {"task": "test"}
        if api_key is not None:
            base_data["api_key"] = api_key
        
        if should_pass:
            request = RunRequest(**base_data)
            if api_key is not None:
                assert request.api_key == api_key
        else:
            with pytest.raises(ValidationError) as exc_info:
                RunRequest(**base_data)
            
            errors = exc_info.value.errors()
            api_key_errors = [e for e in errors if 'api_key' in str(e.get('loc', []))]
            assert len(api_key_errors) > 0, f"Expected api_key validation error for {reason}"


class TestConfigRequest:
    """Test ConfigRequest schema validation."""
    
    def test_valid_config_request(self):
        """Test valid ConfigRequest creation."""
        request = ConfigRequest(config_file="custom_config.yaml")
        assert request.config_file == "custom_config.yaml"
    
    def test_config_request_defaults(self):
        """Test ConfigRequest with default values."""
        request = ConfigRequest()
        assert request.config_file is None


class TestConfigReloadRequest:
    """Test ConfigReloadRequest schema validation."""
    
    def test_valid_config_reload_request(self):
        """Test valid ConfigReloadRequest creation."""
        request = ConfigReloadRequest(config_file="reload_config.yaml")
        assert request.config_file == "reload_config.yaml"
    
    def test_config_reload_request_defaults(self):
        """Test ConfigReloadRequest with default values."""
        request = ConfigReloadRequest()
        assert request.config_file == "trae_config.yaml"


class TestRunResponse:
    """Test RunResponse schema validation."""
    
    def test_valid_run_response(self, sample_run_response: RunResponse):
        """Test valid RunResponse structure."""
        response = sample_run_response
        
        assert response.success is True
        assert response.result == "Successfully created hello_world.py script"
        assert response.execution_id == "test-execution-123"
        assert response.patches == []
        assert response.patch_path is None
        assert isinstance(response.trajectory, TrajectoryData)
        assert isinstance(response.stats, ExecutionStats)
        assert response.error_message is None
    
    def test_run_response_with_error(self):
        """Test RunResponse with error information."""
        from trae_agent.schemas.responses import ExecutionStats, TrajectoryData
        
        response = RunResponse(
            success=False,
            result="Task failed",
            patches=[],
            patch_path=None,
            trajectory=TrajectoryData(
                task="Failed task",
                start_time="2025-01-01T00:00:00.000000",
                provider="anthropic",
                model="claude-3-5-sonnet-20241022",
                max_steps=10,
                success=False
            ),
            stats=ExecutionStats(),
            execution_id="error-execution-456",
            error_message="Agent execution failed due to invalid input"
        )
        
        assert response.success is False
        assert response.result == "Task failed"
        assert response.error_message == "Agent execution failed due to invalid input"
    
    def test_run_response_with_patches(self):
        """Test RunResponse with patches."""
        from trae_agent.schemas.responses import ExecutionStats, TrajectoryData, Patch
        
        patch = Patch(
            file_path="/test/file.py",
            patched_content="print('hello world')",
            line_changes={"added": 1, "removed": 0, "modified": 0}
        )
        
        response = RunResponse(
            success=True,
            result="Applied patches",
            patches=[patch],
            patch_path="/test/patches.diff",
            trajectory=TrajectoryData(
                task="Patch task",
                start_time="2025-01-01T00:00:00.000000",
                provider="anthropic",
                model="claude-3-5-sonnet-20241022", 
                max_steps=10,
                success=True
            ),
            stats=ExecutionStats(),
            execution_id="patch-execution-789"
        )
        
        assert len(response.patches) == 1
        assert response.patches[0].file_path == "/test/file.py"
        assert response.patch_path == "/test/patches.diff"


class TestStreamEvent:
    """Test StreamEvent schema validation."""
    
    def test_valid_stream_event(self):
        """Test valid StreamEvent creation."""
        event = StreamEvent(
            event="start",
            data={"message": "Starting execution"},
            execution_id="stream-test-123",
            sequence_number=0
        )
        
        assert event.event == "start"
        assert event.data == {"message": "Starting execution"}
        assert event.execution_id == "stream-test-123"
        assert event.sequence_number == 0
        assert event.timestamp  # Should have auto-generated timestamp
    
    @pytest.mark.parametrize("event_type", [
        "start", "step", "tool_call", "llm_interaction", 
        "progress", "complete", "error"
    ])
    def test_valid_event_types(self, event_type):
        """Test all valid event types."""
        event = StreamEvent(
            event=event_type,
            data={},
            execution_id="test", 
            sequence_number=0
        )
        assert event.event == event_type
    
    def test_invalid_event_type(self):
        """Test invalid event type."""
        with pytest.raises(ValidationError):
            StreamEvent(
                event="invalid_event",
                data={},
                execution_id="test",
                sequence_number=0
            )
    
    def test_stream_event_with_complex_data(self):
        """Test StreamEvent with complex data payload."""
        complex_data = {
            "step_number": 5,
            "tool_used": "str_replace_based_edit_tool",
            "tool_input": {"command": "create", "path": "/test.py"},
            "tool_output": "File created successfully",
            "duration_ms": 1500,
            "metadata": {
                "retries": 0,
                "cache_hit": True
            }
        }
        
        event = StreamEvent(
            event="tool_call",
            data=complex_data,
            execution_id="complex-test-456",
            sequence_number=5
        )
        
        assert event.data["step_number"] == 5
        assert event.data["tool_used"] == "str_replace_based_edit_tool"
        assert event.data["metadata"]["cache_hit"] is True


class TestExecutionStats:
    """Test ExecutionStats schema validation."""
    
    def test_valid_execution_stats(self):
        """Test valid ExecutionStats creation."""
        stats = ExecutionStats(
            total_steps=10,
            total_llm_interactions=3,
            total_input_tokens=500,
            total_output_tokens=200,
            execution_duration_ms=30000,
            tools_used={"str_replace_based_edit_tool": 2, "bash": 1},
            success_rate=1.0,
            average_step_duration_ms=3000.0
        )
        
        assert stats.total_steps == 10
        assert stats.total_llm_interactions == 3
        assert stats.execution_duration_ms == 30000
        assert stats.tools_used["str_replace_based_edit_tool"] == 2
        assert stats.success_rate == 1.0
    
    def test_execution_stats_defaults(self):
        """Test ExecutionStats with default values."""
        stats = ExecutionStats()
        
        assert stats.total_steps == 0
        assert stats.total_llm_interactions == 0
        assert stats.total_input_tokens == 0
        assert stats.total_output_tokens == 0
        assert stats.execution_duration_ms == 0
        assert stats.tools_used == {}
        assert stats.success_rate == 1.0
        assert stats.average_step_duration_ms is None


class TestTrajectoryData:
    """Test TrajectoryData schema validation."""
    
    def test_valid_trajectory_data(self, mock_trajectory_data):
        """Test valid TrajectoryData creation."""
        trajectory = TrajectoryData(**mock_trajectory_data)
        
        assert trajectory.task == "Test task"
        assert trajectory.provider == "anthropic"
        assert trajectory.model == "claude-3-5-sonnet-20241022"
        assert trajectory.max_steps == 10
        assert trajectory.success is True
        assert len(trajectory.llm_interactions) == 1
        assert len(trajectory.execution_steps) == 1
        assert trajectory.total_duration_ms == 60000
    
    def test_trajectory_data_minimal(self):
        """Test TrajectoryData with minimal required fields."""
        trajectory = TrajectoryData(
            task="Minimal test",
            start_time="2025-01-01T00:00:00.000000",
            provider="anthropic",
            model="claude-3-5-sonnet-20241022",
            max_steps=5
        )
        
        assert trajectory.task == "Minimal test"
        assert trajectory.end_time is None
        assert trajectory.success is False  # default
        assert trajectory.llm_interactions == []
        assert trajectory.execution_steps == []


class TestErrorResponse:
    """Test ErrorResponse schema validation."""
    
    def test_valid_error_response(self):
        """Test valid ErrorResponse creation."""
        error = ErrorResponse(
            error="validation_error",
            message="Invalid request parameters",
            details={"field": "task", "issue": "required"},
            execution_id="error-test-123"
        )
        
        assert error.error == "validation_error"
        assert error.message == "Invalid request parameters"
        assert error.details["field"] == "task"
        assert error.execution_id == "error-test-123"
        assert error.timestamp  # Auto-generated
    
    def test_error_response_minimal(self):
        """Test ErrorResponse with minimal fields."""
        error = ErrorResponse(
            error="internal_error",
            message="Something went wrong"
        )
        
        assert error.error == "internal_error"
        assert error.message == "Something went wrong"
        assert error.details is None
        assert error.execution_id is None


class TestPatch:
    """Test Patch schema validation."""
    
    def test_valid_patch(self):
        """Test valid Patch creation."""
        patch = Patch(
            file_path="/test/script.py",
            original_content="# Original code",
            patched_content="print('Hello, World!')",
            diff="@@ -1 +1 @@\n-# Original code\n+print('Hello, World!')",
            line_changes={"added": 1, "removed": 1, "modified": 0}
        )
        
        assert patch.file_path == "/test/script.py"
        assert patch.original_content == "# Original code"
        assert patch.patched_content == "print('Hello, World!')"
        assert patch.diff is not None
        assert patch.line_changes["added"] == 1
    
    def test_patch_minimal(self):
        """Test Patch with minimal required fields."""
        patch = Patch(
            file_path="/test/minimal.py",
            patched_content="# Minimal patch"
        )
        
        assert patch.file_path == "/test/minimal.py"
        assert patch.patched_content == "# Minimal patch"
        assert patch.original_content is None
        assert patch.diff is None
        assert patch.line_changes == {}  # Default empty dict


class TestSchemaIntegration:
    """Test schema integration and edge cases."""
    
    def test_request_response_cycle(self, sample_run_request: RunRequest):
        """Test that request can produce valid response."""
        # This would normally be handled by the service layer
        # but we can test the schema compatibility
        
        request = sample_run_request
        
        # Simulate creating a response from the request
        response_data = {
            "success": True,
            "result": f"Completed task: {request.task}",
            "patches": [],
            "patch_path": None,
            "trajectory": TrajectoryData(
                task=request.task,
                start_time="2025-01-01T00:00:00.000000",
                provider=request.provider,
                model=request.model, 
                max_steps=request.max_steps or 100
            ),
            "stats": ExecutionStats(),
            "execution_id": "integration-test-999"
        }
        
        response = RunResponse(**response_data)
        
        assert response.success is True
        assert request.task in response.result
        assert response.trajectory.provider == request.provider
        assert response.trajectory.model == request.model
    
    def test_json_serialization(self, sample_run_request: RunRequest, sample_run_response: RunResponse):
        """Test JSON serialization/deserialization."""
        
        # Test request serialization
        request_json = sample_run_request.model_dump_json()
        request_dict = sample_run_request.model_dump()
        
        # Should be able to recreate from JSON
        recreated_request = RunRequest.model_validate_json(request_json)
        assert recreated_request.task == sample_run_request.task
        
        # Test response serialization
        response_json = sample_run_response.model_dump_json()
        response_dict = sample_run_response.model_dump()
        
        # Should be able to recreate from JSON
        recreated_response = RunResponse.model_validate_json(response_json)
        assert recreated_response.success == sample_run_response.success
        assert recreated_response.execution_id == sample_run_response.execution_id