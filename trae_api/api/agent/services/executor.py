"""Production-grade agent execution service - refactored version.

Following Meta/PyTorch patterns: clear separation of concerns, single responsibility,
and production-grade error handling while preserving all telemetry and monitoring.
"""

import asyncio
import hashlib
import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

import structlog
from fastapi import HTTPException

from trae_agent.schemas.requests import RunRequest
from trae_agent.schemas.responses import RunResponse, ExecutionStats, TrajectoryData
from trae_agent.utils.config import Config
from trae_api.api.agent.services.execution_components import (
    ExecutionContext,
    ResourceCoordinator,
    TelemetryRecorder,
    preserve_error_context
)
from trae_api.core.resources import get_cleanup_scheduler
from trae_api.core.metrics import get_metrics
from trae_api.core.logging import (
    get_execution_logger,
    set_correlation_context,
    generate_correlation_id
)
from trae_api.core.logging.agent_context import get_agent_logger, AgentPhase
from trae_api.core.observability.tracing import get_agent_tracer

# Import Agent components with fallback for testing
try:
    from trae_agent.agent import Agent
    from trae_agent.utils.trajectory_recorder import TrajectoryRecorder
    from trae_agent.utils.cli import ConsoleFactory, ConsoleMode, ConsoleType
except ImportError:
    Agent = None
    TrajectoryRecorder = None
    ConsoleFactory = None
    ConsoleMode = None
    ConsoleType = None

logger = structlog.get_logger(__name__)


class AgentExecutionError(Exception):
    """Custom exception for agent execution errors."""
    
    def __init__(self, message: str, error_type: str = "execution_error", 
                 details: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.message = message
        self.error_type = error_type
        self.details = details or {}


class AgentExecutorService:
    """Production-grade agent execution service with resource management.
    
    Refactored to follow Meta/PyTorch patterns with clear separation of concerns,
    reduced complexity, and maintained production telemetry.
    """
    
    def __init__(
        self,
        max_concurrency: Optional[int] = None,
        default_timeout: int = 900,
        temp_dir_manager: Optional[Any] = None,
        enable_background_cleanup: bool = True,
        cleanup_delay_seconds: float = 300.0
    ):
        """Initialize the agent executor service."""
        # Core configuration
        self.max_concurrency = max_concurrency or (os.cpu_count() or 4) * 4
        self.default_timeout = default_timeout
        self.cleanup_delay_seconds = cleanup_delay_seconds
        
        # Resource management
        self.semaphore = asyncio.Semaphore(self.max_concurrency)
        
        # Lazy load temp_dir_manager to avoid circular import
        if temp_dir_manager is None:
            from trae_agent.utils.temp_dir import get_temp_dir_manager
            temp_dir_manager = get_temp_dir_manager()
        
        self.resource_coordinator = ResourceCoordinator(
            temp_dir_manager,
            get_cleanup_scheduler()
        )
        
        # Telemetry and monitoring
        self.telemetry = TelemetryRecorder(get_agent_tracer())
        self.metrics = get_metrics()
        
        # Execution tracking
        self.active_executions: Dict[str, Dict[str, Any]] = {}
        
        logger.info(
            "AgentExecutorService initialized",
            max_concurrency=self.max_concurrency,
            default_timeout=self.default_timeout
        )
    
    async def execute_agent(self, request: RunRequest) -> RunResponse:
        """Execute agent task with full production monitoring.
        
        Significantly refactored for clarity while maintaining all telemetry,
        error handling, and production safety features.
        """
        execution_id = str(uuid.uuid4())
        context = ExecutionContext(execution_id=execution_id, request=request)
        
        # Set up correlation and logging
        context.correlation_id = generate_correlation_id()
        set_correlation_context(
            execution_id=execution_id,
            correlation_id=context.correlation_id
        )
        
        # Calculate task hash for deduplication
        context.task_hash = self._calculate_task_hash(request)
        
        try:
            # Phase 1: Validation and resource checking
            await self._validate_and_prepare_request(request, context)
            
            # Phase 2: Resource acquisition
            async with self.semaphore:
                self._track_execution_start(context)
                
                try:
                    # Phase 3: Execute with isolation
                    result = await asyncio.wait_for(
                        self._execute_with_isolation(context),
                        timeout=request.timeout or self.default_timeout
                    )
                    
                    # Phase 4: Record success
                    context.update_status("completed")
                    self.telemetry.record_completion(result, context)
                    
                    return result
                    
                except asyncio.TimeoutError:
                    context.update_status("timeout")
                    self._handle_timeout(context)
                    
                except AgentExecutionError as e:
                    context.update_status("failed")
                    context.error = e
                    self._handle_agent_error(e, context)
                    
                except Exception as e:
                    context.update_status("failed")
                    context.error = e
                    self._handle_unexpected_error(e, context)
                    
                finally:
                    self._track_execution_end(context)
                    
        except HTTPException:
            raise
        except Exception as e:
            logger.error(
                "Fatal error in execute_agent",
                execution_id=execution_id,
                error=str(e),
                exc_info=True
            )
            raise HTTPException(
                status_code=500,
                detail={
                    "error": "internal_error",
                    "message": "An unexpected error occurred",
                    "execution_id": execution_id
                }
            )
    
    async def _validate_and_prepare_request(self, request: RunRequest, 
                                           context: ExecutionContext) -> None:
        """Validate request and check resource availability."""
        # Validate task
        task = await self._resolve_task(request)
        if not task or not task.strip():
            raise AgentExecutionError(
                "No task provided",
                error_type="validation_error"
            )
        request.task = task
        
        # Check resource availability
        if len(self.active_executions) >= self.max_concurrency:
            raise HTTPException(
                status_code=429,
                detail={
                    "error": "resource_exhausted",
                    "message": f"Maximum concurrent executions ({self.max_concurrency}) reached",
                    "execution_id": context.execution_id
                }
            )
        
        # Validate timeout
        if request.timeout:
            request.timeout = max(30, min(request.timeout, 3600))
        else:
            request.timeout = self.default_timeout
    
    async def _execute_with_isolation(self, context: ExecutionContext) -> RunResponse:
        """Execute agent task in isolated environment.
        
        Significantly simplified while maintaining all functionality.
        """
        exec_logger = get_execution_logger(context.execution_id)
        
        async with self.resource_coordinator.acquire_resources(
            context.execution_id, 
            context.request.working_dir
        ) as (temp_dir, working_dir):
            
            with preserve_error_context("agent_execution", context.execution_id):
                # Load configuration
                config = await self._load_and_prepare_config(context.request)
                
                # Create agent
                agent = await self._create_configured_agent(
                    config, temp_dir, working_dir, context
                )
                
                try:
                    # Execute task
                    self.telemetry.record_phase("executing", context)
                    
                    extra_args = {
                        "project_path": str(working_dir),
                        "issue": context.request.task,
                        "should_write_output": True,
                        "should_stream_output": False,
                        "use_simple_diffs": True,
                    }
                    
                    if context.request.must_patch:
                        extra_args["must_patch"] = True
                    
                    execution_result = await agent.run(
                        context.request.task, extra_args
                    )
                    
                    # Build response
                    return await self._build_execution_response(
                        execution_result, agent, context, temp_dir
                    )
                    
                finally:
                    # Cleanup agent resources
                    await self._cleanup_agent_resources(agent, context.execution_id)
    
    async def _load_and_prepare_config(self, request: RunRequest) -> Config:
        """Load and prepare configuration with overrides."""
        try:
            config = Config.create(config_file=request.config_file)
            
            if config.trae_agent is None:
                raise AgentExecutionError(
                    "trae_agent configuration is required",
                    error_type="config_error"
                )
            
            # Apply overrides
            config.resolve_config_values(
                provider=request.provider,
                model=request.model,
                api_key=request.api_key,
                model_base_url=request.model_base_url,
                max_steps=request.max_steps
            )
            
            return config
            
        except Exception as e:
            raise AgentExecutionError(
                f"Failed to load configuration: {str(e)}",
                error_type="config_error"
            ) from e
    
    async def _create_configured_agent(self, config: Config, temp_dir: Path,
                                      working_dir: Path, 
                                      context: ExecutionContext) -> Agent:
        """Create and configure agent instance."""
        if not Agent:
            raise ImportError("Agent module not available")
        
        # Set up trajectory recording
        trajectory_path = temp_dir / f"trajectory_{context.execution_id}.json"
        recorder = TrajectoryRecorder(str(trajectory_path))
        
        # Create console
        console = ConsoleFactory.create_console(
            mode=ConsoleMode.RUN,
            console_type=ConsoleType.SIMPLE
        )
        
        # Create agent
        agent = Agent(
            agent_type="trae_agent",
            config=config,
            trajectory_recorder=recorder,
            cli_console=console
        )
        
        return agent
    
    async def _build_execution_response(self, execution_result: Any, agent: Agent,
                                       context: ExecutionContext, 
                                       temp_dir: Path) -> RunResponse:
        """Build response from execution results."""
        # Extract trajectory data
        trajectory_path = temp_dir / f"trajectory_{context.execution_id}.json"
        trajectory_data = await self._extract_trajectory_data(
            trajectory_path, context.execution_id
        )
        
        # Extract patches
        patches = []
        if hasattr(agent, 'patches') and agent.patches:
            patches = [str(p) for p in agent.patches]
        
        # Calculate stats
        stats = self._calculate_execution_stats(trajectory_data)
        
        # Create TrajectoryData from cleaned data
        if trajectory_data:
            try:
                trajectory = TrajectoryData(**trajectory_data)
            except Exception as e:
                logger.warning(
                    "Failed to parse trajectory data, using empty trajectory",
                    execution_id=context.execution_id,
                    error=str(e)
                )
                trajectory = TrajectoryData(steps=[], llm_interactions=[])
        else:
            trajectory = TrajectoryData(steps=[], llm_interactions=[])
        
        return RunResponse(
            success=True,
            execution_id=context.execution_id,
            result=execution_result.final_result if execution_result else "Task completed",
            patches=patches,
            trajectory=trajectory,
            stats=stats,
            error_message=None
        )
    
    async def _extract_trajectory_data(self, trajectory_path: Path, 
                                      execution_id: str) -> Optional[Dict]:
        """Extract trajectory data from file."""
        try:
            if trajectory_path.exists():
                with open(trajectory_path, 'r') as f:
                    data = json.load(f)
                    # Clean up None values in trajectory data to avoid validation errors
                    if data and 'llm_interactions' in data:
                        for interaction in data['llm_interactions']:
                            # Fix None content in input_messages
                            if 'input_messages' in interaction:
                                for msg in interaction['input_messages']:
                                    if msg.get('content') is None:
                                        msg['content'] = ""
                            # Fix None tool_calls in response
                            if 'response' in interaction:
                                if interaction['response'].get('tool_calls') is None:
                                    interaction['response']['tool_calls'] = []
                    return data
        except Exception as e:
            logger.warning(
                "Failed to extract trajectory data",
                execution_id=execution_id,
                error=str(e)
            )
        return None
    
    def _calculate_execution_stats(self, trajectory_data: Optional[Dict]) -> ExecutionStats:
        """Calculate execution statistics from trajectory."""
        if not trajectory_data:
            return ExecutionStats(
                total_steps=0,
                total_tokens=0,
                total_cost=0.0,
                duration_seconds=0.0
            )
        
        steps = trajectory_data.get('steps', [])
        total_tokens = sum(
            step.get('usage', {}).get('total_tokens', 0)
            for step in steps
        )
        
        return ExecutionStats(
            total_steps=len(steps),
            total_tokens=total_tokens,
            total_cost=0.0,  # Cost calculation would go here
            duration_seconds=trajectory_data.get('duration_seconds', 0.0)
        )
    
    async def _cleanup_agent_resources(self, agent: Any, execution_id: str) -> None:
        """Clean up agent resources like MCP clients."""
        try:
            if hasattr(agent, 'mcp_clients') and agent.mcp_clients:
                for mcp_client in agent.mcp_clients:
                    if hasattr(mcp_client, 'cleanup'):
                        await mcp_client.cleanup()
        except Exception as e:
            logger.warning(
                "Failed to cleanup agent resources",
                execution_id=execution_id,
                error=str(e)
            )
    
    async def _resolve_task(self, request: RunRequest) -> str:
        """Resolve task from request or file."""
        if request.task:
            return request.task
        
        if request.file_path:
            file_path = Path(request.file_path)
            if file_path.exists():
                return file_path.read_text().strip()
        
        return ""
    
    def _calculate_task_hash(self, request: RunRequest) -> str:
        """Calculate hash for task deduplication."""
        task_str = f"{request.task or ''}{request.provider}{request.model}"
        return hashlib.md5(task_str.encode()).hexdigest()[:12]
    
    def _track_execution_start(self, context: ExecutionContext) -> None:
        """Track execution start in active executions."""
        self.active_executions[context.execution_id] = {
            "status": "running",
            "start_time": context.start_time,
            "request": context.request.model_dump()
        }
        
        self.metrics.record_active_executions(len(self.active_executions))
    
    def _track_execution_end(self, context: ExecutionContext) -> None:
        """Track execution end and cleanup."""
        self.active_executions.pop(context.execution_id, None)
        self.metrics.record_active_executions(len(self.active_executions))
    
    def _handle_timeout(self, context: ExecutionContext) -> None:
        """Handle execution timeout."""
        self.telemetry.record_error(
            asyncio.TimeoutError(f"Execution timeout after {context.request.timeout}s"),
            context,
            error_type="timeout"
        )
        
        raise HTTPException(
            status_code=408,
            detail={
                "error": "timeout",
                "message": f"Agent execution timeout after {context.request.timeout} seconds",
                "execution_id": context.execution_id
            }
        )
    
    def _handle_agent_error(self, error: AgentExecutionError, 
                          context: ExecutionContext) -> None:
        """Handle agent execution errors."""
        self.telemetry.record_error(error, context, error_type=error.error_type)
        
        raise HTTPException(
            status_code=422,
            detail={
                "error": error.error_type,
                "message": error.message,
                "execution_id": context.execution_id
            }
        )
    
    def _handle_unexpected_error(self, error: Exception, 
                                context: ExecutionContext) -> None:
        """Handle unexpected errors."""
        self.telemetry.record_error(error, context, error_type="internal_error")
        
        raise HTTPException(
            status_code=500,
            detail={
                "error": "internal_error",
                "message": "An unexpected error occurred during execution",
                "execution_id": context.execution_id
            }
        )
    
    async def get_execution_status(self, execution_id: str) -> Optional[Dict[str, Any]]:
        """Get status of a specific execution."""
        return self.active_executions.get(execution_id)
    
    async def list_active_executions(self) -> Dict[str, Dict[str, Any]]:
        """List all active executions."""
        return dict(self.active_executions)
    
    async def health_check(self) -> Dict[str, Any]:
        """Health check endpoint data."""
        return {
            "active_executions": len(self.active_executions),
            "max_concurrency": self.max_concurrency,
            "available_slots": self.max_concurrency - len(self.active_executions),
            "semaphore_available": self.semaphore._value if hasattr(self.semaphore, '_value') else 0
        }