"""Centralized fixtures for agent API tests."""

import asyncio
import json
import tempfile
from pathlib import Path
from typing import AsyncGenerator, Dict, Generator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from fastapi import FastAPI
from fastapi.testclient import TestClient
from httpx import AsyncClient

from trae_agent.schemas import RunRequest, RunResponse
from trae_agent.utils.temp_dir import TempDirManager
from trae_api.api.agent.services.executor import AgentExecutorService
from trae_api.api.agent.services.streaming import StreamingService
from trae_api.core.application import get_app
from tests.doubles import FakeAgentExecutorService, FailingAgentExecutorService, SlowAgentExecutorService
from tests.config import test_service_provider


@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def temp_dir() -> Generator[Path, None, None]:
    """Create a temporary directory for testing."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        yield Path(tmp_dir)


@pytest.fixture
def mock_config_file(temp_dir: Path) -> Path:
    """Create a mock configuration file for testing."""
    config_content = {
        "agent": {
            "model": {
                "provider": "anthropic",
                "model": "claude-3-5-sonnet-20241022",
                "api_key": "test-api-key",
                "model_base_url": None
            },
            "max_steps": 100,
            "working_dir": str(temp_dir),
            "tools": ["str_replace_based_edit_tool", "bash"]
        },
        "mcp_servers_config": {}
    }
    
    config_file = temp_dir / "test_config.yaml"
    
    # Write as YAML format (new structure)
    yaml_content = f"""
agents:
  trae_agent:
    model: test_model
    max_steps: {config_content['agent']['max_steps']}
    enable_lakeview: false
    tools:
      - str_replace_based_edit_tool
      - bash

model_providers:
  {config_content['agent']['model']['provider']}:
    api_key: {config_content['agent']['model']['api_key']}
    provider: {config_content['agent']['model']['provider']}

models:
  test_model:
    model_provider: {config_content['agent']['model']['provider']}
    model: {config_content['agent']['model']['model']}
    max_tokens: 8192
    temperature: 0.3
    top_p: 0.95
    top_k: 40
    max_retries: 10
    parallel_tool_calls: true

allow_mcp_servers: []
mcp_servers: {{}}
"""
    
    config_file.write_text(yaml_content.strip())
    return config_file


@pytest.fixture
def temp_dir_manager(temp_dir: Path) -> TempDirManager:
    """Create a test-specific temp directory manager."""
    return TempDirManager(base_temp_dir=temp_dir / "temp")


@pytest_asyncio.fixture
async def agent_executor_service(temp_dir_manager: TempDirManager) -> AsyncGenerator[AgentExecutorService, None]:
    """Create a test AgentExecutorService with proper cleanup."""
    # Initialize metrics with disabled Prometheus for testing
    from trae_api.core.metrics import init_metrics
    init_metrics(enable_prometheus=False)
    
    service = AgentExecutorService(
        max_concurrency=2,
        default_timeout=30,
        temp_dir_manager=temp_dir_manager,
        enable_background_cleanup=False,
        cleanup_delay_seconds=0.0
    )
    
    yield service
    
    # Cleanup any remaining active executions
    for execution_id in list(service.active_executions.keys()):
        if execution_id in service.active_executions:
            del service.active_executions[execution_id]


@pytest.fixture
def streaming_service() -> StreamingService:
    """Create a streaming service for testing using a fake executor.

    Using the fake executor ensures no real provider SDKs or HTTP calls are made
    during streaming unit/performance tests.
    """
    fake_executor = FakeAgentExecutorService()
    return StreamingService(fake_executor)


@pytest.fixture
def sample_run_request(mock_config_file: Path) -> RunRequest:
    """Create a sample RunRequest for testing."""
    return RunRequest(
        task="Create a simple hello world Python script",
        provider="anthropic",
        model="claude-3-5-sonnet-20241022",
        config_file=str(mock_config_file),
        timeout=60,
        max_steps=10
    )


@pytest.fixture
def sample_run_response() -> RunResponse:
    """Create a sample RunResponse for testing."""
    from trae_agent.schemas.responses import ExecutionStats, TrajectoryData
    
    return RunResponse(
        success=True,
        result="Successfully created hello_world.py script",
        patches=[],
        patch_path=None,
        trajectory=TrajectoryData(
            task="Create a simple hello world Python script",
            start_time="2025-01-01T00:00:00.000000",
            end_time="2025-01-01T00:01:00.000000",
            provider="anthropic",
            model="claude-3-5-sonnet-20241022",
            max_steps=10,
            llm_interactions=[],
            execution_steps=[],
            total_duration_ms=60000,
            success=True,
            result_summary="Created hello_world.py successfully"
        ),
        stats=ExecutionStats(
            total_steps=3,
            total_llm_interactions=1,
            total_input_tokens=100,
            total_output_tokens=50,
            execution_duration_ms=60000,
            tools_used={"str_replace_based_edit_tool": 1},
            success_rate=1.0,
            average_step_duration_ms=20000.0
        ),
        execution_id="test-execution-123",
        start_time="2025-01-01T00:00:00.000000",
        end_time="2025-01-01T00:01:00.000000"
    )


@pytest.fixture(params=["anthropic", "openai", "google"])
def mock_llm_provider(request) -> str:
    """Parametrized fixture for different LLM providers."""
    return request.param


@pytest.fixture
def mock_agent():
    """Create a mock agent for testing."""
    mock = MagicMock()
    mock.arun = AsyncMock()
    mock.setup_trajectory_recording = MagicMock()
    mock.discover_mcp_tools = AsyncMock()
    mock._trajectory_recorder = None
    mock.mcp_clients = []
    mock.project_path = "/test/project"
    mock.must_patch = "false"
    mock.patch_path = None
    return mock


@pytest.fixture
def mock_run_response():
    """Create a properly structured mock RunResponse for testing."""
    from trae_agent.schemas.responses import ExecutionStats
    
    mock_response = MagicMock()
    mock_response.success = True
    mock_response.result = "Task completed successfully"
    
    # Create proper stats with real values instead of MagicMock
    mock_stats = MagicMock()
    mock_stats.total_input_tokens = 100
    mock_stats.total_output_tokens = 50
    mock_stats.total_steps = 3
    mock_stats.tools_used = {"str_replace_based_edit_tool": 1}
    mock_response.stats = mock_stats
    
    return mock_response


@pytest.fixture
def mock_config():
    """Create a mock configuration for testing."""
    mock = MagicMock()
    mock.trae_agent = MagicMock()
    mock.trae_agent.model.model_provider.provider = "anthropic"
    mock.trae_agent.model.model = "claude-3-5-sonnet-20241022"
    mock.trae_agent.model.model_provider.api_key = "test-key"
    mock.trae_agent.model.model_provider.base_url = None
    mock.trae_agent.max_steps = 100
    mock.trae_agent.mcp_servers_config = {}
    mock.trae_agent.enable_lakeview = False  # Disable lakeview for testing
    mock.lakeview = None
    return mock


@pytest.fixture
def app() -> FastAPI:
    """Create FastAPI app for testing with dependency injection."""
    app = get_app()
    return app


@pytest.fixture  
def client(app: FastAPI) -> TestClient:
    """Create test client with proper service injection."""
    # Override dependencies for testing
    from trae_api.api.agent.dependencies import (
        get_agent_executor_service,
        get_streaming_service,
        get_executor_service,
    )
    
    fake_executor = FakeAgentExecutorService()
    fake_streaming = StreamingService(fake_executor)
    
    app.dependency_overrides[get_agent_executor_service] = lambda: fake_executor
    # Also override the endpoint's dependency factory to ensure fake executor is used by default
    app.dependency_overrides[get_executor_service] = lambda: fake_executor
    app.dependency_overrides[get_streaming_service] = lambda: fake_streaming
    
    client = TestClient(app)
    yield client
    
    # Clean up overrides
    app.dependency_overrides.clear()


@pytest.fixture
def failing_client(app: FastAPI) -> TestClient:
    """Create test client that simulates service failures."""
    from trae_api.api.agent.dependencies import (
        get_agent_executor_service,
        get_executor_service,
    )
    
    failing_executor = FailingAgentExecutorService("agent_error")
    app.dependency_overrides[get_agent_executor_service] = lambda: failing_executor
    app.dependency_overrides[get_executor_service] = lambda: failing_executor
    
    client = TestClient(app) 
    yield client
    
    app.dependency_overrides.clear()


@pytest.fixture
def timeout_client(app: FastAPI) -> TestClient:
    """Create test client that simulates timeouts."""
    from trae_api.api.agent.dependencies import (
        get_agent_executor_service,
        get_executor_service,
    )
    
    slow_executor = SlowAgentExecutorService(delay_seconds=2.0)
    app.dependency_overrides[get_agent_executor_service] = lambda: slow_executor
    app.dependency_overrides[get_executor_service] = lambda: slow_executor
    
    client = TestClient(app)
    yield client
    
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def async_client(app: FastAPI) -> AsyncGenerator[AsyncClient, None]:
    """Create async test client with dependency injection."""
    from httpx._transports.asgi import ASGITransport
    from trae_api.api.agent.dependencies import (
        get_agent_executor_service,
        get_streaming_service,
        get_executor_service,
    )
    
    # Set up dependency overrides
    fake_executor = FakeAgentExecutorService()
    fake_streaming = StreamingService(fake_executor)
    
    app.dependency_overrides[get_agent_executor_service] = lambda: fake_executor
    app.dependency_overrides[get_executor_service] = lambda: fake_executor
    app.dependency_overrides[get_streaming_service] = lambda: fake_streaming
    
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
        
    # Clean up overrides
    app.dependency_overrides.clear()


@pytest.fixture
def error_scenarios():
    """Common error scenarios for testing."""
    return [
        {
            "name": "agent_execution_error",
            "exception": "AgentExecutionError",
            "message": "Agent failed to execute task",
            "expected_status": 422
        },
        {
            "name": "timeout_error", 
            "exception": "asyncio.TimeoutError",
            "message": "Task timed out",
            "expected_status": 408
        },
        {
            "name": "validation_error",
            "exception": "ValidationError",
            "message": "Invalid request data", 
            "expected_status": 400
        },
        {
            "name": "resource_exhausted",
            "exception": "ResourceExhaustedError",
            "message": "Server overloaded",
            "expected_status": 429
        },
        {
            "name": "internal_error",
            "exception": "Exception",
            "message": "Unexpected internal error",
            "expected_status": 500
        }
    ]


@pytest.fixture
def concurrency_test_requests():
    """Generate multiple requests for concurrency testing."""
    return [
        RunRequest(
            task=f"Test task {i}",
            provider="anthropic", 
            model="claude-3-5-sonnet-20241022",
            timeout=30,
            max_steps=5
        )
        for i in range(10)
    ]


@pytest.fixture
def streaming_events():
    """Sample streaming events for testing."""
    return [
        {
            "event": "start",
            "data": {"message": "Starting execution"},
            "execution_id": "test-123",
            "sequence_number": 0
        },
        {
            "event": "step", 
            "data": {"step_number": 1, "message": "Analyzing task"},
            "execution_id": "test-123",
            "sequence_number": 1
        },
        {
            "event": "tool_call",
            "data": {"tool": "str_replace_based_edit_tool", "status": "success"},
            "execution_id": "test-123", 
            "sequence_number": 2
        },
        {
            "event": "complete",
            "data": {"message": "Task completed successfully"},
            "execution_id": "test-123",
            "sequence_number": 3
        }
    ]


# Performance test fixtures
@pytest.fixture
def performance_config():
    """Configuration for performance tests."""
    return {
        "max_concurrent_requests": 20,
        "request_timeout": 60,
        "expected_latency_p95": 30.0,  # seconds
        "expected_throughput": 5.0,    # requests per second
        "memory_limit_mb": 1000,
        "cpu_threshold": 80.0          # percentage
    }


@pytest.fixture(autouse=True)
def cleanup_temp_dirs():
    """Automatically cleanup any stray temp directories after each test."""
    yield
    
    # Clean up any test temp directories
    import shutil
    temp_base = Path("/tmp")
    for item in temp_base.glob("pytest-*"):
        if item.is_dir():
            try:
                shutil.rmtree(item, ignore_errors=True)
            except Exception:
                pass


@pytest.fixture(autouse=True)  
def reset_metrics():
    """Reset metrics instance between tests to avoid interference."""
    from trae_api.core.metrics import init_metrics
    # Initialize clean metrics for each test
    init_metrics(enable_prometheus=False)
    yield
    # Reset global state
    import trae_api.core.metrics
    trae_api.core.metrics._metrics_instance = None


# Integration test fixtures
@pytest.fixture
def integration_test_config():
    """Configuration for integration tests."""
    return {
        "test_timeout": 120,
        "max_test_steps": 20,
        "expected_success_rate": 0.95,
        "retry_count": 3,
        "cleanup_delay": 1.0
    }


# Enhanced fixture architecture for better reusability
@pytest.fixture
def mock_llm_responses():
    """Predefined LLM response patterns for consistent testing."""
    return {
        "simple_success": {
            "success": True,
            "result": "Task completed successfully",
            "reasoning": "Analyzed the task and executed it step by step",
            "confidence": 0.95
        },
        "complex_success": {
            "success": True, 
            "result": "Multi-step task completed with 3 tool calls",
            "reasoning": "Used multiple tools to complete complex requirements",
            "confidence": 0.87,
            "tools_used": ["str_replace_based_edit_tool", "bash", "read_file"]
        },
        "partial_success": {
            "success": True,
            "result": "Task partially completed - some requirements unclear", 
            "reasoning": "Completed what was possible given the constraints",
            "confidence": 0.65,
            "warnings": ["Unclear requirement for file format"]
        },
        "failure": {
            "success": False,
            "result": "Task failed due to missing dependencies",
            "reasoning": "Could not proceed without required libraries",
            "confidence": 0.20,
            "error": "ModuleNotFoundError: No module named 'required_lib'"
        }
    }


@pytest.fixture
def error_scenario_factory():
    """Factory for creating various error scenarios."""
    def create_error_scenario(error_type: str, **kwargs):
        from trae_api.api.agent.services.executor import AgentExecutionError, ResourceExhaustedError
        from pydantic import ValidationError
        import asyncio
        
        scenarios = {
            "timeout": {
                "exception": asyncio.TimeoutError(),
                "expected_status": 408,
                "expected_error": "timeout",
                "message": "Request timed out"
            },
            "validation": {
                "exception": ValidationError([{"type": "missing", "loc": ("field",)}]),
                "expected_status": 400,
                "expected_error": "validation_error",
                "message": "Invalid request data"
            },
            "agent_execution": {
                "exception": AgentExecutionError("Tool failed"),
                "expected_status": 422,
                "expected_error": "agent_error",
                "message": "Agent execution failed"
            },
            "resource_exhausted": {
                "exception": ResourceExhaustedError("Server overloaded"),
                "expected_status": 429,
                "expected_error": "resource_exhausted", 
                "message": "Server overloaded"
            },
            "internal": {
                "exception": RuntimeError("Unexpected error"),
                "expected_status": 500,
                "expected_error": "internal_error",
                "message": "Internal server error"
            }
        }
        
        scenario = scenarios.get(error_type, scenarios["internal"]).copy()
        scenario.update(kwargs)
        return scenario
    
    return create_error_scenario


@pytest.fixture
def request_factory():
    """Factory for creating test requests with various configurations."""
    def create_request(template: str = "basic", **overrides):
        templates = {
            "basic": {
                "task": "Create a hello world script",
                "provider": "anthropic",
                "model": "claude-3-5-sonnet-20241022",
                "timeout": 60,
                "max_steps": 10
            },
            "advanced": {
                "task": "Build a web scraper with error handling",
                "provider": "anthropic",
                "model": "claude-3-5-sonnet-20241022", 
                "timeout": 300,
                "max_steps": 50,
                "must_patch": True,
                "working_dir": "/tmp/advanced_project"
            },
            "minimal": {
                "task": "List files"
            },
            "file_based": {
                "file_path": "/tmp/task_description.txt",
                "provider": "openai",
                "model": "gpt-4"
            }
        }
        
        base_request = templates.get(template, templates["basic"]).copy()
        base_request.update(overrides)
        return RunRequest(**base_request)
    
    return create_request


@pytest.fixture
def mock_trajectory_data():
    """Mock trajectory data for testing."""
    return {
        "task": "Test task",
        "start_time": "2025-01-01T00:00:00.000000",
        "end_time": "2025-01-01T00:01:00.000000", 
        "provider": "anthropic",
        "model": "claude-3-5-sonnet-20241022",
        "max_steps": 10,
        "llm_interactions": [
            {
                "timestamp": "2025-01-01T00:00:30.000000",
                "provider": "anthropic",
                "model": "claude-3-5-sonnet-20241022",
                "input_messages": [{"role": "user", "content": "Test task"}],
                "response": {
                    "content": "I'll help you with that task.",
                    "model": "claude-3-5-sonnet-20241022",
                    "finish_reason": "stop",
                    "usage": {
                        "input_tokens": 10,
                        "output_tokens": 8,
                        "cache_creation_input_tokens": 0,
                        "cache_read_input_tokens": 0,
                        "reasoning_tokens": 0
                    },
                    "tool_calls": []
                },
                "tools_available": ["str_replace_based_edit_tool", "bash"]
            }
        ],
        "execution_steps": [
            {
                "step_number": 1,
                "timestamp": "2025-01-01T00:00:30.500000",
                "tool_used": "str_replace_based_edit_tool",
                "tool_input": {"command": "create", "path": "/tmp/test.py"},
                "tool_output": "File created successfully",
                "duration_ms": 500,
                "success": True
            }
        ],
        "total_duration_ms": 60000,
        "success": True,
        "result_summary": "Task completed successfully"
    }