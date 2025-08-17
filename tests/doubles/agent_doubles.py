"""Test doubles for agent components following Netflix/Google patterns."""

import asyncio
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock
from datetime import datetime, timezone

from trae_agent.schemas import RunRequest
from trae_agent.schemas.responses import ExecutionStats, RunResponse, TrajectoryData
from trae_api.api.agent.services.executor import AgentExecutorService


class FakeAgentExecutorService:
    """Fake implementation that preserves AgentExecutorService behavior for testing.
    
    This follows the Test Double pattern from Martin Fowler, providing predictable
    behavior without external dependencies.
    """
    
    def __init__(self, 
                 max_concurrency: int = 10, 
                 default_timeout: int = 30,
                 should_fail: bool = False,
                 response_delay: float = 0.0):
        self.max_concurrency = max_concurrency
        self.default_timeout = default_timeout
        self.should_fail = should_fail
        self.response_delay = response_delay
        self.active_executions: Dict[str, Dict[str, Any]] = {}
        self._execution_counter = 0
        
    async def execute_agent(self, request: RunRequest) -> RunResponse:
        """Fake execution that simulates real behavior patterns with timeouts and errors."""
        from fastapi import HTTPException
        import inspect
        from importlib import import_module

        # Optional artificial delay before starting
        if self.response_delay > 0:
            await asyncio.sleep(self.response_delay)

        self._execution_counter += 1
        execution_id = f"fake-exec-{self._execution_counter:06d}"

        # Enforce simple concurrency limits
        if len(self.active_executions) >= self.max_concurrency:
            raise HTTPException(status_code=429, detail="Service overloaded")

        # Determine timeout (fallback to default)
        timeout_seconds = request.timeout or self.default_timeout

        # Record execution metadata for status/list endpoints
        self.active_executions[execution_id] = {
            "status": "running",
            "start_time": datetime.now(timezone.utc).isoformat(),
            "task": request.task,
            "provider": request.provider,
            "model": request.model,
            "timeout": timeout_seconds,
            "request": request.model_dump(),
        }

        # Resolve AgentError type for specific handling
        try:
            from trae_agent.agent.agent_basics import AgentError as _AgentError
        except Exception:  # pragma: no cover - during tests import may vary
            class _AgentError(Exception):  # type: ignore
                pass

        async def _do_execute() -> RunResponse:
            # Invoke patched Agent MagicMock if present to allow side effects
            try:
                agent_mod = import_module("trae_agent.agent")
                from unittest.mock import MagicMock
                AgentObj = getattr(agent_mod, "Agent", None)
                if AgentObj is not None and isinstance(AgentObj, MagicMock):
                    agent_instance = AgentObj()
                    method = None
                    # Prefer arun when available (AsyncMock), else run
                    if hasattr(agent_instance, "arun"):
                        method = getattr(agent_instance, "arun")
                    elif hasattr(agent_instance, "run"):
                        method = getattr(agent_instance, "run")
                    if callable(method):
                        result = method(request.task, {})
                        if inspect.isawaitable(result):
                            await result
            except _AgentError:
                # Re-raise for outer handler to convert into HTTP 422
                raise
            except Exception:
                # Let other exceptions propagate for consistent handling
                raise

            if self.should_fail:
                raise HTTPException(
                    status_code=422,
                    detail={
                        "error": "agent_error",
                        "message": "Simulated agent failure",
                    },
                )

            # Simulate realistic execution time based on task complexity
            task_length = len(request.task or "")
            simulated_duration = min(max(task_length / 100, 0.01), 2.0)  # 10ms-2s
            await asyncio.sleep(simulated_duration)

            # Determine result text tailored for common test scenarios
            task_text = (request.task or "").strip()
            if "hello world" in task_text.lower():
                result_text = "Hello world script created successfully"
            elif task_text:
                result_text = f"Successfully completed: {task_text}"
            else:
                result_text = "Task completed successfully"

            # Create realistic response
            stats = ExecutionStats(
                total_steps=3,
                total_llm_interactions=1,
                total_input_tokens=max(task_length // 4, 50),
                total_output_tokens=max(task_length // 8, 25),
                execution_duration_ms=int(simulated_duration * 1000),
                tools_used={"str_replace_based_edit_tool": 1},
                success_rate=1.0,
                average_step_duration_ms=simulated_duration * 1000 / 3,
            )

            trajectory = TrajectoryData(
                task=request.task or "test task",
                start_time="2025-01-01T00:00:00.000000",
                end_time="2025-01-01T00:01:00.000000",
                provider=request.provider or "anthropic",
                model=request.model or "claude-3-5-sonnet-20241022",
                max_steps=request.max_steps or 100,
                llm_interactions=[],
                execution_steps=[],
                total_duration_ms=int(simulated_duration * 1000),
                success=True,
                result_summary="Task completed successfully",
            )

            return RunResponse(
                success=True,
                result=result_text,
                patches=[],
                patch_path=None,
                trajectory=trajectory,
                stats=stats,
                execution_id=execution_id,
                start_time="2025-01-01T00:00:00.000000",
                end_time="2025-01-01T00:01:00.000000",
            )

        try:
            # Enforce timeout over the full fake execution, including mocked Agent
            return await asyncio.wait_for(_do_execute(), timeout=timeout_seconds)
        except asyncio.TimeoutError:
            raise HTTPException(
                status_code=408,
                detail={
                    "error": "timeout",
                    "message": "Execution timed out",
                    "execution_id": execution_id,
                },
            )
        except HTTPException:
            raise
        except _AgentError as e:  # Map Agent errors to 422 for API consistency
            raise HTTPException(
                status_code=422,
                detail={
                    "error": "agent_error",
                    "message": str(e),
                },
            )
        except Exception as e:
            # Ensure unexpected errors surface as HTTP 500 in endpoint
            raise HTTPException(
                status_code=500,
                detail={
                    "error": "internal_error",
                    "message": str(e),
                },
            )
        finally:
            # Clean up execution tracking
            self.active_executions.pop(execution_id, None)

    async def get_execution_status(self, execution_id: str) -> Optional[Dict[str, Any]]:
        """Get status of a running execution (fake implementation)."""
        return self.active_executions.get(execution_id)

    async def list_active_executions(self) -> Dict[str, Dict[str, Any]]:
        """List all active executions (fake implementation)."""
        return dict(self.active_executions)

    async def health_check(self) -> Dict[str, Any]:
        """Health check for the fake executor service."""
        active_count = len(self.active_executions)
        available_slots = max(0, self.max_concurrency - active_count)
        return {
            "status": "healthy",
            "active_executions": active_count,
            "max_concurrency": self.max_concurrency,
            "available_slots": available_slots,
        }


class SlowAgentExecutorService(FakeAgentExecutorService):
    """Fake service that simulates slow responses for timeout testing."""
    
    def __init__(self, delay_seconds: float = 5.0):
        super().__init__(response_delay=delay_seconds)


class FailingAgentExecutorService(FakeAgentExecutorService):
    """Fake service that always fails for error handling testing."""
    
    def __init__(self, error_type: str = "agent_error"):
        super().__init__(should_fail=True)
        self.error_type = error_type
        
    async def execute_agent(self, request: RunRequest) -> RunResponse:
        from fastapi import HTTPException
        error_map = {
            "agent_error": (422, "Agent execution failed"),
            "timeout": (408, "Request timed out"),
            "validation": (400, "Invalid request data"),
            "internal_error": (500, "Internal server error")
        }
        status_code, message = error_map.get(self.error_type, (500, "Unknown error"))
        raise HTTPException(status_code=status_code, detail={
            "error": self.error_type,
            "message": message
        })


class ResourceConstrainedAgentService(FakeAgentExecutorService):
    """Fake service with realistic resource constraints for performance testing."""
    
    def __init__(self, max_concurrency: int = 2, cpu_simulation: bool = True):
        super().__init__(max_concurrency=max_concurrency)
        self.cpu_simulation = cpu_simulation
        
    async def execute_agent(self, request: RunRequest) -> RunResponse:
        if self.cpu_simulation:
            # Simulate CPU-intensive work
            import time
            start = time.time()
            # Busy work to simulate real CPU load
            while time.time() - start < 0.1:  # 100ms of CPU work
                _ = sum(i ** 2 for i in range(1000))
                
        return await super().execute_agent(request)