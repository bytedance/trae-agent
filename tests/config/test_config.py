"""Test-specific configuration management following Django/Flask patterns."""

import tempfile
from pathlib import Path
from typing import Any, Dict, Optional

from trae_api.api.agent.services.executor import AgentExecutorService
from tests.doubles import FakeAgentExecutorService


class ConfigManager:
    """Manages test configurations with proper isolation and cleanup.
    
    This follows the configuration management patterns from Django's test framework
    and Flask-Testing, providing isolated configuration for each test case.
    """
    
    def __init__(self):
        self._temp_dirs = []
        self._config_files = []
        
    def create_test_config(self, 
                          provider: str = "anthropic",
                          model: str = "claude-3-5-sonnet-20241022",
                          **overrides) -> Path:
        """Create a temporary configuration file for testing."""
        temp_dir = Path(tempfile.mkdtemp())
        self._temp_dirs.append(temp_dir)
        
        config_data = {
            "agents": {
                "trae_agent": {
                    "model": "test_model",
                    "max_steps": 100,
                    "tools": ["str_replace_based_edit_tool", "bash"]
                }
            },
            "model_providers": {
                provider: {
                    "api_key": "test-api-key-12345",
                    "provider": provider
                }
            },
            "models": {
                "test_model": {
                    "model_provider": provider,
                    "model": model,
                    "max_tokens": 8192,
                    "temperature": 0.3,
                    "top_p": 0.95,
                    "top_k": 40,
                    "max_retries": 10,
                    "parallel_tool_calls": True
                }
            },
            "allow_mcp_servers": [],
            "mcp_servers": {}
        }
        
        # Apply any overrides
        self._deep_update(config_data, overrides)
        
        config_file = temp_dir / "test_config.yaml"
        with open(config_file, 'w') as f:
            import yaml
            yaml.dump(config_data, f)
            
        self._config_files.append(config_file)
        return config_file
        
    def _deep_update(self, base_dict: Dict, update_dict: Dict) -> None:
        """Recursively update nested dictionaries."""
        for key, value in update_dict.items():
            if key in base_dict and isinstance(base_dict[key], dict) and isinstance(value, dict):
                self._deep_update(base_dict[key], value)
            else:
                base_dict[key] = value
                
    def cleanup(self):
        """Clean up temporary files and directories."""
        import shutil
        for temp_dir in self._temp_dirs:
            if temp_dir.exists():
                shutil.rmtree(temp_dir, ignore_errors=True)
        self._temp_dirs.clear()
        self._config_files.clear()


class ServiceProvider:
    """Provides test-specific service instances with proper dependency injection.
    
    This implements the Service Locator pattern used by major frameworks like Spring
    and .NET Core for testable dependency management.
    """
    
    def __init__(self):
        self._services = {}
        self._config_manager = ConfigManager()
        
    def get_agent_executor_service(self, 
                                  service_type: str = "fake",
                                  **kwargs) -> AgentExecutorService:
        """Get an agent executor service suitable for testing."""
        if service_type == "fake":
            return FakeAgentExecutorService(**kwargs)
        elif service_type == "real":
            # For integration tests that need real service behavior
            config_file = self._config_manager.create_test_config()
            return AgentExecutorService(
                max_concurrency=kwargs.get("max_concurrency", 2),
                default_timeout=kwargs.get("default_timeout", 30)
            )
        else:
            raise ValueError(f"Unknown service type: {service_type}")
            
    def cleanup(self):
        """Clean up all test resources."""
        self._config_manager.cleanup()
        self._services.clear()


# Global test service provider instance
test_service_provider = ServiceProvider()