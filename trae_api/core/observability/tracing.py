"""
Enhanced OpenTelemetry tracing for agent executions.

This module provides detailed tracing for agent execution phases,
LLM interactions, tool usage, and performance monitoring.
"""

import time
from contextlib import contextmanager
from typing import Dict, Any, Optional, Generator
from enum import Enum

try:
    from opentelemetry import trace
    from opentelemetry.trace import Status, StatusCode
    from opentelemetry.trace.span import Span
    from opentelemetry.semconv.trace import SpanAttributes
    OTEL_AVAILABLE = True
except ImportError:
    OTEL_AVAILABLE = False
    trace = None
    Status = None
    StatusCode = None
    Span = None
    SpanAttributes = None

import structlog


logger = structlog.get_logger(__name__)


class TraceAttributes:
    """Custom trace attributes for agent execution."""
    
    # Agent execution attributes
    AGENT_TYPE = "agent.type"
    AGENT_EXECUTION_ID = "agent.execution_id"
    AGENT_CORRELATION_ID = "agent.correlation_id"
    AGENT_PHASE = "agent.phase"
    AGENT_TASK = "agent.task"
    AGENT_TASK_HASH = "agent.task_hash"
    AGENT_PROVIDER = "agent.provider"
    AGENT_MODEL = "agent.model"
    AGENT_MAX_STEPS = "agent.max_steps"
    AGENT_STEPS_TAKEN = "agent.steps_taken"
    AGENT_SUCCESS = "agent.success"
    AGENT_DURATION_MS = "agent.duration_ms"
    
    # LLM interaction attributes
    LLM_REQUEST_ID = "llm.request_id"
    LLM_INPUT_TOKENS = "llm.input_tokens"
    LLM_OUTPUT_TOKENS = "llm.output_tokens"
    LLM_TOTAL_TOKENS = "llm.total_tokens"
    LLM_CACHE_HIT = "llm.cache_hit"
    LLM_FINISH_REASON = "llm.finish_reason"
    LLM_TOKENS_PER_SECOND = "llm.tokens_per_second"
    
    # Tool execution attributes
    TOOL_NAME = "tool.name"
    TOOL_INPUT_SIZE = "tool.input_size_bytes"
    TOOL_OUTPUT_SIZE = "tool.output_size_bytes"
    TOOL_SUCCESS = "tool.success"
    TOOL_ERROR_TYPE = "tool.error_type"
    
    # System resource attributes
    SYSTEM_MEMORY_USAGE = "system.memory_usage_bytes"
    SYSTEM_CPU_USAGE = "system.cpu_usage_percent"
    SYSTEM_DISK_USAGE = "system.disk_usage_bytes"


class AgentTracer:
    """Enhanced tracer for agent executions with OpenTelemetry."""
    
    def __init__(self, service_name: str = "trae-agent-api"):
        self.service_name = service_name
        self.tracer = None
        
        if OTEL_AVAILABLE:
            self.tracer = trace.get_tracer(__name__)
            logger.info("OpenTelemetry tracer initialized", service_name=service_name)
        else:
            logger.warning("OpenTelemetry not available, tracing disabled")
    
    @contextmanager
    def agent_execution_span(
        self,
        execution_id: str,
        correlation_id: str,
        task: str,
        provider: str,
        model: str,
        max_steps: int,
        agent_type: str = "trae_agent"
    ) -> Generator[Optional[Span], None, None]:
        """Create a span for complete agent execution."""
        
        if not self.tracer:
            yield None
            return
        
        # Create task hash for grouping
        import hashlib
        task_hash = hashlib.sha256(task.encode()).hexdigest()[:12]
        
        with self.tracer.start_as_current_span(
            f"agent_execution:{agent_type}",
            kind=trace.SpanKind.SERVER
        ) as span:
            # Set common attributes
            span.set_attributes({
                TraceAttributes.AGENT_TYPE: agent_type,
                TraceAttributes.AGENT_EXECUTION_ID: execution_id,
                TraceAttributes.AGENT_CORRELATION_ID: correlation_id,
                TraceAttributes.AGENT_TASK_HASH: task_hash,
                TraceAttributes.AGENT_PROVIDER: provider,
                TraceAttributes.AGENT_MODEL: model,
                TraceAttributes.AGENT_MAX_STEPS: max_steps,
                SpanAttributes.ENDUSER_ID: correlation_id,  # Use correlation ID as user ID
            })
            
            # Add task content as event (truncated for safety)
            span.add_event(
                "agent_task_received",
                attributes={
                    "task_length": len(task),
                    "task_preview": task[:200] if len(task) > 200 else task
                }
            )
            
            try:
                yield span
                
                # Mark as successful if no exception
                span.set_status(Status(StatusCode.OK))
                
            except Exception as exc:
                # Record error details
                span.record_exception(exc)
                span.set_status(Status(StatusCode.ERROR, str(exc)))
                
                # Add error attributes
                span.set_attributes({
                    TraceAttributes.AGENT_SUCCESS: False,
                    "error.type": type(exc).__name__,
                    "error.message": str(exc)[:500]
                })
                raise
    
    @contextmanager
    def agent_phase_span(
        self,
        phase: str,
        execution_id: str,
        **metadata
    ) -> Generator[Optional[Span], None, None]:
        """Create a span for an agent execution phase."""
        
        if not self.tracer:
            yield None
            return
        
        with self.tracer.start_as_current_span(
            f"agent_phase:{phase}",
            kind=trace.SpanKind.INTERNAL
        ) as span:
            # Set phase attributes
            span.set_attributes({
                TraceAttributes.AGENT_PHASE: phase,
                TraceAttributes.AGENT_EXECUTION_ID: execution_id,
                **{f"phase.{k}": str(v) for k, v in metadata.items()}
            })
            
            span.add_event(f"phase_started:{phase}")
            
            try:
                yield span
                span.add_event(f"phase_completed:{phase}")
                span.set_status(Status(StatusCode.OK))
                
            except Exception as exc:
                span.record_exception(exc)
                span.set_status(Status(StatusCode.ERROR, str(exc)))
                span.add_event(f"phase_failed:{phase}")
                raise
    
    @contextmanager
    def llm_interaction_span(
        self,
        provider: str,
        model: str,
        request_id: Optional[str] = None,
        input_tokens: Optional[int] = None,
        max_tokens: Optional[int] = None
    ) -> Generator[Optional[Span], None, None]:
        """Create a span for LLM interaction."""
        
        if not self.tracer:
            yield None
            return
        
        with self.tracer.start_as_current_span(
            f"llm_interaction:{provider}:{model}",
            kind=trace.SpanKind.CLIENT
        ) as span:
            # Set LLM attributes
            attributes = {
                TraceAttributes.AGENT_PROVIDER: provider,
                TraceAttributes.AGENT_MODEL: model,
            }
            
            if request_id:
                attributes[TraceAttributes.LLM_REQUEST_ID] = request_id
            if input_tokens is not None:
                attributes[TraceAttributes.LLM_INPUT_TOKENS] = input_tokens
            if max_tokens is not None:
                attributes["llm.max_tokens"] = max_tokens
            
            span.set_attributes(attributes)
            
            span.add_event("llm_request_sent")
            
            try:
                yield span
                span.add_event("llm_response_received")
                span.set_status(Status(StatusCode.OK))
                
            except Exception as exc:
                span.record_exception(exc)
                span.set_status(Status(StatusCode.ERROR, str(exc)))
                span.add_event("llm_request_failed")
                raise
    
    @contextmanager
    def tool_execution_span(
        self,
        tool_name: str,
        input_size_bytes: Optional[int] = None,
        **metadata
    ) -> Generator[Optional[Span], None, None]:
        """Create a span for tool execution."""
        
        if not self.tracer:
            yield None
            return
        
        with self.tracer.start_as_current_span(
            f"tool_execution:{tool_name}",
            kind=trace.SpanKind.INTERNAL
        ) as span:
            # Set tool attributes
            attributes = {
                TraceAttributes.TOOL_NAME: tool_name,
            }
            
            if input_size_bytes:
                attributes[TraceAttributes.TOOL_INPUT_SIZE] = input_size_bytes
            
            # Add metadata as attributes
            for k, v in metadata.items():
                attributes[f"tool.{k}"] = str(v)
            
            span.set_attributes(attributes)
            
            span.add_event(f"tool_started:{tool_name}")
            
            try:
                yield span
                span.add_event(f"tool_completed:{tool_name}")
                span.set_attributes({TraceAttributes.TOOL_SUCCESS: True})
                span.set_status(Status(StatusCode.OK))
                
            except Exception as exc:
                span.record_exception(exc)
                span.set_status(Status(StatusCode.ERROR, str(exc)))
                span.set_attributes({
                    TraceAttributes.TOOL_SUCCESS: False,
                    TraceAttributes.TOOL_ERROR_TYPE: type(exc).__name__
                })
                span.add_event(f"tool_failed:{tool_name}")
                raise
    
    def record_llm_completion(
        self,
        span: Optional[Span],
        output_tokens: int,
        total_tokens: int,
        duration_ms: float,
        finish_reason: Optional[str] = None,
        cache_hit: bool = False
    ):
        """Record LLM completion details to span."""
        
        if not span:
            return
        
        # Calculate tokens per second
        tokens_per_second = total_tokens / (duration_ms / 1000) if duration_ms > 0 else 0
        
        span.set_attributes({
            TraceAttributes.LLM_OUTPUT_TOKENS: output_tokens,
            TraceAttributes.LLM_TOTAL_TOKENS: total_tokens,
            TraceAttributes.LLM_TOKENS_PER_SECOND: round(tokens_per_second, 2),
            TraceAttributes.AGENT_DURATION_MS: round(duration_ms, 2),
            TraceAttributes.LLM_CACHE_HIT: cache_hit
        })
        
        if finish_reason:
            span.set_attributes({TraceAttributes.LLM_FINISH_REASON: finish_reason})
        
        span.add_event(
            "llm_completion_recorded",
            attributes={
                "output_tokens": output_tokens,
                "tokens_per_second": round(tokens_per_second, 2),
                "cache_hit": cache_hit
            }
        )
    
    def record_tool_completion(
        self,
        span: Optional[Span],
        output_size_bytes: Optional[int] = None,
        duration_ms: Optional[float] = None,
        success: bool = True
    ):
        """Record tool completion details to span."""
        
        if not span:
            return
        
        attributes = {TraceAttributes.TOOL_SUCCESS: success}
        
        if output_size_bytes:
            attributes[TraceAttributes.TOOL_OUTPUT_SIZE] = output_size_bytes
        if duration_ms:
            attributes[TraceAttributes.AGENT_DURATION_MS] = round(duration_ms, 2)
        
        span.set_attributes(attributes)
        
        span.add_event(
            "tool_completion_recorded",
            attributes={
                "success": success,
                "output_size_bytes": output_size_bytes,
                "duration_ms": duration_ms
            }
        )
    
    def record_agent_completion(
        self,
        span: Optional[Span],
        steps_taken: int,
        success: bool,
        duration_ms: float,
        memory_usage_bytes: Optional[int] = None
    ):
        """Record agent execution completion details."""
        
        if not span:
            return
        
        attributes = {
            TraceAttributes.AGENT_STEPS_TAKEN: steps_taken,
            TraceAttributes.AGENT_SUCCESS: success,
            TraceAttributes.AGENT_DURATION_MS: round(duration_ms, 2)
        }
        
        if memory_usage_bytes:
            attributes[TraceAttributes.SYSTEM_MEMORY_USAGE] = memory_usage_bytes
        
        span.set_attributes(attributes)
        
        span.add_event(
            "agent_execution_completed",
            attributes={
                "steps_taken": steps_taken,
                "success": success,
                "duration_seconds": round(duration_ms / 1000, 2)
            }
        )
    
    def record_system_metrics(
        self,
        span: Optional[Span],
        memory_usage_bytes: Optional[int] = None,
        cpu_usage_percent: Optional[float] = None,
        disk_usage_bytes: Optional[int] = None
    ):
        """Record system resource metrics to span."""
        
        if not span:
            return
        
        attributes = {}
        event_attrs = {}
        
        if memory_usage_bytes is not None:
            attributes[TraceAttributes.SYSTEM_MEMORY_USAGE] = memory_usage_bytes
            event_attrs["memory_usage_mb"] = memory_usage_bytes / (1024 * 1024)
        
        if cpu_usage_percent is not None:
            attributes[TraceAttributes.SYSTEM_CPU_USAGE] = cpu_usage_percent
            event_attrs["cpu_usage_percent"] = cpu_usage_percent
        
        if disk_usage_bytes is not None:
            attributes[TraceAttributes.SYSTEM_DISK_USAGE] = disk_usage_bytes
            event_attrs["disk_usage_mb"] = disk_usage_bytes / (1024 * 1024)
        
        if attributes:
            span.set_attributes(attributes)
            span.add_event("system_metrics_recorded", attributes=event_attrs)


# Global tracer instance
_agent_tracer: Optional[AgentTracer] = None


def get_agent_tracer() -> AgentTracer:
    """Get global agent tracer instance."""
    global _agent_tracer
    
    if _agent_tracer is None:
        _agent_tracer = AgentTracer()
    
    return _agent_tracer


def init_agent_tracer(service_name: str = "trae-agent-api") -> AgentTracer:
    """Initialize global agent tracer instance."""
    global _agent_tracer
    
    _agent_tracer = AgentTracer(service_name=service_name)
    return _agent_tracer