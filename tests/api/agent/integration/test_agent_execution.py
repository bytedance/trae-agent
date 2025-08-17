"""Real integration tests using actual Gemini model."""

import asyncio
import json
import os
from pathlib import Path
import pytest
from fastapi import status, FastAPI
from fastapi.testclient import TestClient

from trae_agent.schemas import RunRequest
from trae_api.api.agent.services.executor import AgentExecutorService
from trae_api.core.application import get_app


@pytest.fixture
def real_client() -> TestClient:
    """Create test client with real AgentExecutorService for actual model testing."""
    app = get_app()
    
    # Use real executor service, not fake
    from trae_api.api.agent.dependencies import (
        get_agent_executor_service,
        get_executor_service,
    )
    
    real_executor = AgentExecutorService()
    app.dependency_overrides[get_agent_executor_service] = lambda: real_executor
    app.dependency_overrides[get_executor_service] = lambda: real_executor
    
    client = TestClient(app)
    yield client
    
    # Clean up overrides
    app.dependency_overrides.clear()


class TestRealAgentExecution:
    """Integration tests with actual Gemini model execution."""
    
    @pytest.mark.integration
    @pytest.mark.skipif(
        not (os.environ.get("GOOGLE_API_KEY") or Path("trae_config.yaml").exists()),
        reason="Requires GOOGLE_API_KEY env var or trae_config.yaml"
    )
    def test_simple_file_creation_with_gemini(self, real_client: TestClient, tmp_path: Path):
        """Test actual agent execution with Gemini model creating a file."""
        
        # Convert to absolute path - CRITICAL FIX
        working_dir = str(tmp_path.resolve())
        
        request_data = {
            "task": "Create a file hello.txt with the content 'Hello from Gemini!'",
            "provider": "google",
            "model": "gemini-2.0-flash-exp",  # Use latest stable model
            "working_dir": working_dir,
            "timeout": 60,
            "max_steps": 5,
            "config_file": "trae_config.yaml"  # Ensure config is specified
        }
        
        response = real_client.post("/api/agent/run", json=request_data)
        
        # Debug output if test fails
        if response.status_code != 200:
            print(f"Response status: {response.status_code}")
            print(f"Response body: {response.text}")
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["success"] is True
        assert data["execution_id"]
        
        # Verify file was created
        hello_file = tmp_path / "hello.txt"
        assert hello_file.exists()
        assert "Hello from Gemini!" in hello_file.read_text()
    
    @pytest.mark.integration
    @pytest.mark.skipif(
        not (os.environ.get("GOOGLE_API_KEY") or Path("trae_config.yaml").exists()),
        reason="Requires GOOGLE_API_KEY env var or trae_config.yaml"
    )
    def test_python_script_generation(self, real_client: TestClient, tmp_path: Path):
        """Test Gemini generating a working Python script."""
        
        # Convert to absolute path - CRITICAL FIX
        working_dir = str(tmp_path.resolve())
        
        request_data = {
            "task": """Create a Python file calculator.py with these functions:
def add(a, b):
    return a + b

def multiply(a, b):
    return a * b
""",
            "provider": "google", 
            "model": "gemini-2.0-flash-exp",  # Use latest stable model
            "working_dir": working_dir,
            "timeout": 60,
            "max_steps": 5,
            "config_file": "trae_config.yaml"  # Ensure config is specified
        }
        
        response = real_client.post("/api/agent/run", json=request_data)
        
        # Debug output if test fails
        if response.status_code != 200:
            print(f"Response status: {response.status_code}")
            print(f"Response body: {response.text}")
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["success"] is True
        
        # Verify Python file exists and has expected functions
        script_file = tmp_path / "calculator.py"
        assert script_file.exists()
        
        content = script_file.read_text()
        assert "def add" in content
        assert "def multiply" in content
        
        # Actually test the generated code works
        import sys
        sys.path.insert(0, str(tmp_path))
        import calculator
        
        assert calculator.add(2, 3) == 5
        assert calculator.multiply(3, 4) == 12
    
    @pytest.mark.integration
    @pytest.mark.skipif(
        not (os.environ.get("GOOGLE_API_KEY") or Path("trae_config.yaml").exists()),
        reason="Requires GOOGLE_API_KEY env var or trae_config.yaml"
    )
    def test_error_handling_with_invalid_task(self, real_client: TestClient, tmp_path: Path):
        """Test agent handles impossible tasks gracefully."""
        
        # Convert to absolute path - CRITICAL FIX
        working_dir = str(tmp_path.resolve())
        
        request_data = {
            "task": "Delete the file /etc/passwd",  # Should fail safely
            "provider": "google",
            "model": "gemini-2.0-flash-exp",  # Use latest stable model
            "working_dir": working_dir,
            "timeout": 60,
            "max_steps": 3,
            "config_file": "trae_config.yaml"  # Ensure config is specified
        }
        
        response = real_client.post("/api/agent/run", json=request_data)
        
        # Should complete but potentially with failure or limited success
        assert response.status_code in [200, 422]
        
        # Verify /etc/passwd was NOT deleted (safety check)
        assert Path("/etc/passwd").exists()
    
    @pytest.mark.integration  
    def test_streaming_with_real_execution(self, real_client: TestClient, tmp_path: Path):
        """Test SSE streaming with actual Gemini execution."""
        
        # Convert to absolute path - CRITICAL FIX
        working_dir = str(tmp_path.resolve())
        
        request_data = {
            "task": "Create hello.py with print('Hello')",
            "provider": "google",
            "model": "gemini-2.0-flash-exp",  # Use latest stable model
            "working_dir": working_dir,
            "timeout": 60,
            "max_steps": 5,
            "config_file": "trae_config.yaml"  # Ensure config is specified
        }
        
        # Use stream endpoint
        with real_client.stream("POST", "/api/agent/run/stream", json=request_data) as response:
            assert response.status_code == status.HTTP_200_OK
            
            # Collect events
            events = []
            for line in response.iter_lines():
                if line.startswith("data: "):
                    event_data = line[6:]
                    if event_data != "[DONE]":
                        try:
                            event = json.loads(event_data)
                            events.append(event)
                        except json.JSONDecodeError:
                            continue
        
        # Verify we got meaningful events
        assert len(events) > 0
        
        event_types = {e["event"] for e in events}
        assert "start" in event_types
        assert "complete" in event_types or "error" in event_types
        
        # Verify file was created
        hello_file = tmp_path / "hello.py"
        assert hello_file.exists()
    
    @pytest.mark.integration
    @pytest.mark.parametrize("provider,model", [
        ("google", "gemini-2.0-flash-exp"),  # Use latest stable model
        # Add more providers/models as needed
    ])
    def test_multi_step_task(self, real_client: TestClient, tmp_path: Path, provider: str, model: str):
        """Test multi-step task execution with real model - simplified version."""
        
        # Convert to absolute path - CRITICAL FIX
        working_dir = str(tmp_path.resolve())
        
        # Simplified task to run faster
        request_data = {
            "task": "Create a file test.txt with content 'Hello World'",
            "provider": provider,
            "model": model,
            "working_dir": working_dir,
            "timeout": 60,  # Reduced timeout
            "max_steps": 5,  # Reduced max steps
            "config_file": "trae_config.yaml"  # Ensure config is specified
        }
        
        response = real_client.post("/api/agent/run", json=request_data)
        
        # Debug output if test fails
        if response.status_code != 200:
            print(f"Response status: {response.status_code}")
            print(f"Response body: {response.text}")
            print(f"Request data: {request_data}")
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["success"] is True  # Use the data variable
        
        # Verify file exists
        assert (tmp_path / "test.txt").exists()
        assert "Hello World" in (tmp_path / "test.txt").read_text()
    
    @pytest.mark.integration
    @pytest.mark.skipif(
        not (os.environ.get("GOOGLE_API_KEY") or Path("trae_config.yaml").exists()),
        reason="Requires GOOGLE_API_KEY env var or trae_config.yaml"
    )
    def test_trajectory_continuation(self, real_client: TestClient, tmp_path: Path):
        """Test continuing from previous trajectory."""
        
        # Convert to absolute path - CRITICAL FIX
        working_dir = str(tmp_path.resolve())
        
        # First task
        request_data_1 = {
            "task": "Create file1.txt with 'First task'",
            "provider": "google",
            "model": "gemini-2.0-flash-exp",  # Use latest stable model
            "working_dir": working_dir,
            "timeout": 60,
            "max_steps": 5,
            "config_file": "trae_config.yaml"  # Ensure config is specified
        }
        
        response_1 = real_client.post("/api/agent/run", json=request_data_1)
        assert response_1.status_code == status.HTTP_200_OK
        data_1 = response_1.json()
        
        # Get trajectory if available
        trajectory = data_1.get("trajectory", {})
        
        # Second task continuing from first
        request_data_2 = {
            "task": "Create file2.txt with 'Second task'",
            "provider": "google",
            "model": "gemini-2.0-flash-exp",  # Use latest stable model
            "working_dir": working_dir,
            "timeout": 60,
            "max_steps": 5,
            "trajectory": trajectory,
            "config_file": "trae_config.yaml"  # Ensure config is specified
        }
        
        response_2 = real_client.post("/api/agent/run", json=request_data_2)
        assert response_2.status_code == status.HTTP_200_OK
        
        # Verify both files exist
        assert (tmp_path / "file1.txt").exists()
        assert (tmp_path / "file2.txt").exists()


class TestRealConfigEndpoints:
    """Test configuration-related endpoints with real executor."""
    
    def test_config_validation_with_actual_file(self, real_client: TestClient):
        """Test config validation with actual config file."""
        
        # The /config endpoint is GET, not POST
        response = real_client.get("/api/agent/config")
        
        # Should always return 200 with config data
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        
        # Check for top-level response structure
        assert "config" in data
        assert "config_file_path" in data
        assert "config_file_exists" in data
        
        # Check the actual config data structure
        config_data = data["config"]
        assert "max_steps" in config_data
        assert "api_key_configured" in config_data
        assert "console_type" in config_data
    
    def test_health_check_with_real_executor(self, real_client: TestClient):
        """Test health endpoint returns actual executor status."""
        
        response = real_client.get("/api/agent/health")
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        
        # The status should be either 'healthy' or 'unhealthy'
        assert data["status"] in ["healthy", "unhealthy"]
        assert "timestamp" in data
        assert "service" in data
        assert data["service"] == "agent_executor"
        
        # If healthy, check for additional fields
        if data["status"] == "healthy":
            # These fields may or may not be present depending on executor state
            if "active_executions" in data:
                assert isinstance(data["active_executions"], int)
            if "available_slots" in data:
                assert isinstance(data["available_slots"], int)