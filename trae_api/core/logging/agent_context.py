"""
Agent execution context logging for detailed observability.

This module provides specialized logging context for agent executions,
tracking phases, performance, and resource usage.
"""

import time
from contextlib import contextmanager
from typing import Dict, Any, Optional, Generator
from enum import Enum
from dataclasses import dataclass, field

import structlog
from trae_api.core.metrics import get_metrics
from trae_api.core.observability.tracing import get_agent_tracer


class AgentPhase(Enum):
    """Agent execution phases for detailed tracking."""
    
    INITIALIZATION = "initialization"
    CONFIGURATION = "configuration"
    MCP_SETUP = "mcp_setup"
    TASK_PREPARATION = "task_preparation"
    AGENT_EXECUTION = "agent_execution"
    LLM_INTERACTION = "llm_interaction"
    TOOL_EXECUTION = "tool_execution"
    RESULT_PROCESSING = "result_processing"
    CLEANUP = "cleanup"
    COMPLETE = "complete"


@dataclass
class PhaseMetrics:
    """Metrics for a single execution phase."""
    
    phase: AgentPhase
    start_time: float
    end_time: Optional[float] = None
    duration_ms: Optional[float] = None
    memory_usage_bytes: Optional[int] = None
    cpu_usage_percent: Optional[float] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def complete(self):
        """Mark phase as complete and calculate duration."""
        self.end_time = time.time()
        self.duration_ms = (self.end_time - self.start_time) * 1000


@dataclass
class AgentExecutionContext:
    """Context for tracking agent execution phases and metrics."""
    
    execution_id: str
    correlation_id: str
    task_hash: str
    provider: str
    model: str
    agent_type: str = "trae_agent"
    start_time: float = field(default_factory=time.time)
    end_time: Optional[float] = None
    current_phase: Optional[AgentPhase] = None
    phase_metrics: Dict[AgentPhase, PhaseMetrics] = field(default_factory=dict)
    total_token_usage: Dict[str, int] = field(default_factory=dict)
    tool_usage: Dict[str, int] = field(default_factory=dict)
    error_count: int = 0
    success: Optional[bool] = None
    
    def get_total_duration_ms(self) -> float:
        """Get total execution duration."""
        if self.end_time:
            return (self.end_time - self.start_time) * 1000
        return (time.time() - self.start_time) * 1000
    
    def get_phase_summary(self) -> Dict[str, Any]:
        """Get summary of all phases."""
        return {
            phase.value: {
                "duration_ms": metrics.duration_ms,
                "memory_usage_bytes": metrics.memory_usage_bytes,
                "metadata": metrics.metadata
            }
            for phase, metrics in self.phase_metrics.items()
            if metrics.duration_ms is not None
        }


class AgentLogger:
    """Specialized logger for agent execution with phase tracking."""
    
    def __init__(self):
        self.logger = structlog.get_logger(__name__)
        self._contexts: Dict[str, AgentExecutionContext] = {}
        self.tracer = get_agent_tracer()
    
    def create_execution_context(
        self,
        execution_id: str,
        correlation_id: str,
        task: str,
        provider: str,
        model: str,
        agent_type: str = "trae_agent"
    ) -> AgentExecutionContext:
        """Create new agent execution context."""
        
        # Create task hash for grouping similar tasks
        import hashlib
        # Use full SHA-256 hash for better entropy (256 bits)
        task_hash = hashlib.sha256(task.encode()).hexdigest()
        
        context = AgentExecutionContext(
            execution_id=execution_id,
            correlation_id=correlation_id,
            task_hash=task_hash,
            provider=provider,
            model=model,
            agent_type=agent_type
        )
        
        self._contexts[execution_id] = context
        
        # Set up structured logging context
        structlog.contextvars.bind_contextvars(
            execution_id=execution_id,
            correlation_id=correlation_id,
            task_hash=task_hash,
            provider=provider,
            model=model,
            agent_type=agent_type
        )
        
        self.logger.info(
            "Agent execution context created",
            event_type="execution_context_created",
            task_length=len(task),
            total_contexts_active=len(self._contexts)
        )
        
        return context
    
    def get_context(self, execution_id: str) -> Optional[AgentExecutionContext]:
        """Get execution context by ID."""
        return self._contexts.get(execution_id)
    
    @contextmanager
    def phase_context(
        self,
        execution_id: str,
        phase: AgentPhase,
        **metadata
    ) -> Generator[PhaseMetrics, None, None]:
        """Context manager for tracking execution phases."""
        
        context = self._contexts.get(execution_id)
        if not context:
            self.logger.warning(
                "Phase tracking without execution context",
                execution_id=execution_id,
                phase=phase.value
            )
            # Create a temporary metrics object
            metrics = PhaseMetrics(phase=phase, start_time=time.time(), metadata=metadata)
            yield metrics
            metrics.complete()
            return
        
        # Update current phase
        context.current_phase = phase
        
        # Create phase metrics
        metrics = PhaseMetrics(
            phase=phase,
            start_time=time.time(),
            metadata=metadata
        )
        context.phase_metrics[phase] = metrics
        
        # Log phase start
        self.logger.info(
            f"Agent phase started: {phase.value}",
            event_type="phase_started",
            phase=phase.value,
            phase_metadata=metadata,
            execution_phase=phase.value
        )
        
        try:
            # Create tracing span for phase
            with self.tracer.agent_phase_span(
                phase=phase.value,
                execution_id=execution_id,
                **metadata
            ):
                yield metrics
                
                # Log phase completion
                metrics.complete()
                
                # Record phase metrics
                if context and metrics.duration_ms:
                    agent_metrics = get_metrics()
                    agent_metrics.record_phase_duration(
                        phase=phase.value,
                        duration_seconds=metrics.duration_ms / 1000,
                        provider=context.provider,
                        model=context.model
                    )
                
                self.logger.info(
                    f"Agent phase completed: {phase.value}",
                    event_type="phase_completed",
                    phase=phase.value,
                    duration_ms=metrics.duration_ms,
                    phase_metadata=metadata
                )
            
        except Exception as exc:
            metrics.complete()
            if context:
                context.error_count += 1
            
            self.logger.error(
                f"Agent phase failed: {phase.value}",
                event_type="phase_failed",
                phase=phase.value,
                duration_ms=metrics.duration_ms,
                error_type=type(exc).__name__,
                error_message=str(exc),
                exc_info=True
            )
            raise
        finally:
            # Clear current phase
            if context:
                context.current_phase = None
    
    def log_llm_interaction(
        self,
        execution_id: str,
        provider: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
        duration_ms: float,
        status: str = "success",
        **metadata
    ):
        """Log LLM interaction with detailed metrics."""
        
        context = self._contexts.get(execution_id)
        if context:
            # Update token usage
            context.total_token_usage["input"] = context.total_token_usage.get("input", 0) + input_tokens
            context.total_token_usage["output"] = context.total_token_usage.get("output", 0) + output_tokens
        
        # Record LLM performance metrics
        agent_metrics = get_metrics()
        agent_metrics.record_llm_performance(
            provider=provider,
            model=model,
            response_time_ms=duration_ms,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cache_hit=metadata.get("cache_hit", False)
        )
        
        # Create tracing for LLM interaction
        with self.tracer.llm_interaction_span(
            provider=provider,
            model=model,
            input_tokens=input_tokens
        ) as span:
            if span:
                self.tracer.record_llm_completion(
                    span=span,
                    output_tokens=output_tokens,
                    total_tokens=input_tokens + output_tokens,
                    duration_ms=duration_ms,
                    finish_reason=metadata.get("finish_reason"),
                    cache_hit=metadata.get("cache_hit", False)
                )
        
        self.logger.info(
            "LLM interaction completed",
            event_type="llm_interaction",
            provider=provider,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=input_tokens + output_tokens,
            duration_ms=duration_ms,
            status=status,
            tokens_per_second=(input_tokens + output_tokens) / (duration_ms / 1000) if duration_ms > 0 else 0,
            **metadata
        )
    
    def log_tool_execution(
        self,
        execution_id: str,
        tool_name: str,
        duration_ms: float,
        status: str = "success",
        result_size_bytes: Optional[int] = None,
        **metadata
    ):
        """Log tool execution with performance metrics."""
        
        context = self._contexts.get(execution_id)
        if context:
            # Update tool usage
            context.tool_usage[tool_name] = context.tool_usage.get(tool_name, 0) + 1
        
        # Record tool metrics
        agent_metrics = get_metrics()
        agent_metrics.record_tool_call(
            tool_name=tool_name,
            status=status,
            duration_ms=duration_ms
        )
        
        self.logger.info(
            "Tool execution completed",
            event_type="tool_execution",
            tool_name=tool_name,
            duration_ms=duration_ms,
            status=status,
            result_size_bytes=result_size_bytes,
            **metadata
        )
    
    def log_resource_usage(
        self,
        execution_id: str,
        memory_usage_bytes: Optional[int] = None,
        cpu_usage_percent: Optional[float] = None,
        disk_usage_bytes: Optional[int] = None,
        **metadata
    ):
        """Log resource usage metrics."""
        
        self.logger.info(
            "Resource usage snapshot",
            event_type="resource_usage",
            memory_usage_bytes=memory_usage_bytes,
            memory_usage_mb=memory_usage_bytes / (1024 * 1024) if memory_usage_bytes else None,
            cpu_usage_percent=cpu_usage_percent,
            disk_usage_bytes=disk_usage_bytes,
            **metadata
        )
    
    def complete_execution(
        self,
        execution_id: str,
        success: bool,
        result_summary: Optional[str] = None,
        **metadata
    ):
        """Mark execution as complete and log summary."""
        
        context = self._contexts.get(execution_id)
        if not context:
            self.logger.warning(
                "Completing execution without context",
                execution_id=execution_id
            )
            return
        
        context.end_time = time.time()
        context.success = success
        
        total_duration = context.get_total_duration_ms()
        phase_summary = context.get_phase_summary()
        
        self.logger.info(
            "Agent execution completed",
            event_type="execution_completed",
            success=success,
            total_duration_ms=total_duration,
            total_token_usage=context.total_token_usage,
            tool_usage=context.tool_usage,
            error_count=context.error_count,
            phase_count=len(context.phase_metrics),
            phase_summary=phase_summary,
            result_summary=result_summary[:500] if result_summary else None,
            **metadata
        )
        
        # Clean up context
        del self._contexts[execution_id]
        structlog.contextvars.clear_contextvars()
    
    def cleanup_stale_contexts(self, max_age_seconds: int = 3600):
        """Clean up stale execution contexts."""
        
        current_time = time.time()
        stale_contexts = []
        
        for execution_id, context in self._contexts.items():
            age_seconds = current_time - context.start_time
            if age_seconds > max_age_seconds:
                stale_contexts.append(execution_id)
        
        for execution_id in stale_contexts:
            self.logger.warning(
                "Cleaning up stale execution context",
                execution_id=execution_id,
                age_seconds=current_time - self._contexts[execution_id].start_time
            )
            del self._contexts[execution_id]
        
        if stale_contexts:
            self.logger.info(
                "Stale context cleanup completed",
                cleaned_contexts=len(stale_contexts),
                active_contexts=len(self._contexts)
            )


# Global agent logger instance
_agent_logger: Optional[AgentLogger] = None


def get_agent_logger() -> AgentLogger:
    """Get global agent logger instance."""
    global _agent_logger
    
    if _agent_logger is None:
        _agent_logger = AgentLogger()
    
    return _agent_logger