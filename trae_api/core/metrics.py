"""Custom metrics for agent execution monitoring."""

import time
from enum import Enum
from typing import Dict, Optional

try:
    from prometheus_client import Counter, Histogram, Gauge, Info, start_http_server
    PROMETHEUS_AVAILABLE = True
except ImportError:
    PROMETHEUS_AVAILABLE = False

import structlog


logger = structlog.get_logger(__name__)


class MetricType(Enum):
    """Types of metrics we track."""
    
    EXECUTION_COUNT = "execution_count"
    EXECUTION_DURATION = "execution_duration"
    EXECUTION_SUCCESS_RATE = "execution_success_rate"
    CONCURRENT_EXECUTIONS = "concurrent_executions"
    TOKEN_USAGE = "token_usage"
    TOOL_USAGE = "tool_usage"
    ERROR_COUNT = "error_count"
    STREAM_CONNECTIONS = "stream_connections"
    REQUEST_SIZE = "request_size"
    RESPONSE_SIZE = "response_size"


class AgentMetrics:
    """Metrics collector for agent execution monitoring."""
    
    def __init__(self, enable_prometheus: bool = True):
        """
        Initialize metrics collector.
        
        Args:
            enable_prometheus: Whether to enable Prometheus metrics.
        """
        self.enable_prometheus = enable_prometheus and PROMETHEUS_AVAILABLE
        self._metrics = {}
        self._timers = {}
        
        if self.enable_prometheus:
            self._init_prometheus_metrics()
        
        logger.info(
            "Agent metrics initialized",
            prometheus_enabled=self.enable_prometheus
        )
    
    def _init_prometheus_metrics(self):
        """Initialize Prometheus metrics."""
        
        # Execution metrics
        self._metrics["executions_total"] = Counter(
            'trae_agent_executions_total',
            'Total number of agent executions',
            ['provider', 'model', 'status', 'agent_type']
        )
        
        self._metrics["execution_duration_seconds"] = Histogram(
            'trae_agent_execution_duration_seconds',
            'Agent execution duration in seconds',
            ['provider', 'model', 'agent_type'],
            buckets=(0.1, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0, 120.0, 300.0, 600.0, float('inf'))
        )
        
        self._metrics["concurrent_executions"] = Gauge(
            'trae_agent_concurrent_executions',
            'Current number of concurrent executions'
        )
        
        self._metrics["available_slots"] = Gauge(
            'trae_agent_available_slots',
            'Number of available execution slots'
        )
        
        # Token usage metrics
        self._metrics["tokens_used_total"] = Counter(
            'trae_agent_tokens_used_total',
            'Total tokens used by agent executions',
            ['provider', 'model', 'token_type']  # token_type: input, output, cache_read, etc.
        )
        
        # Tool usage metrics
        self._metrics["tool_calls_total"] = Counter(
            'trae_agent_tool_calls_total',
            'Total number of tool calls',
            ['tool_name', 'status']
        )
        
        # Error metrics
        self._metrics["errors_total"] = Counter(
            'trae_agent_errors_total',
            'Total number of errors',
            ['error_type', 'error_code']
        )
        
        # Streaming metrics
        self._metrics["stream_connections_total"] = Counter(
            'trae_agent_stream_connections_total',
            'Total number of streaming connections',
            ['format_type', 'status']
        )
        
        self._metrics["stream_events_total"] = Counter(
            'trae_agent_stream_events_total',
            'Total number of streaming events sent',
            ['event_type']
        )
        
        # Request/Response size metrics
        self._metrics["request_size_bytes"] = Histogram(
            'trae_agent_request_size_bytes',
            'Request size in bytes',
            buckets=(1024, 4096, 16384, 65536, 262144, 1048576, float('inf'))
        )
        
        self._metrics["response_size_bytes"] = Histogram(
            'trae_agent_response_size_bytes',
            'Response size in bytes',
            buckets=(1024, 4096, 16384, 65536, 262144, 1048576, float('inf'))
        )
        
        # Agent step metrics
        self._metrics["agent_steps_total"] = Counter(
            'trae_agent_steps_total',
            'Total number of agent steps taken',
            ['provider', 'model', 'agent_type', 'completion_reason']
        )
        
        self._metrics["agent_step_efficiency"] = Histogram(
            'trae_agent_step_efficiency_ratio',
            'Ratio of steps taken to max steps allowed',
            ['provider', 'model', 'agent_type'],
            buckets=(0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0, float('inf'))
        )
        
        # Task complexity metrics
        self._metrics["task_complexity_total"] = Counter(
            'trae_agent_task_complexity_total',
            'Total tasks by complexity level',
            ['complexity', 'success', 'provider', 'model']
        )
        
        # Success rate metrics
        self._metrics["success_rate"] = Gauge(
            'trae_agent_success_rate',
            'Current success rate (rolling average)'
        )
        
        # Phase timing metrics
        self._metrics["phase_duration_seconds"] = Histogram(
            'trae_agent_phase_duration_seconds',
            'Duration of agent execution phases',
            ['phase', 'provider', 'model'],
            buckets=(0.01, 0.05, 0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0, float('inf'))
        )
        
        # System info
        self._metrics["info"] = Info(
            'trae_agent_info',
            'Information about the agent system'
        )
        
        # Set initial info
        self._metrics["info"].info({
            'version': '0.1.0',
            'prometheus_enabled': str(self.enable_prometheus)
        })
    
    def record_execution_start(
        self,
        execution_id: str,
        provider: str,
        model: str,
        agent_type: str = "trae_agent"
    ):
        """Record the start of an agent execution."""
        
        # Record start time for duration calculation
        self._timers[execution_id] = time.time()
        
        if self.enable_prometheus:
            # Increment concurrent executions
            self._metrics["concurrent_executions"].inc()
        
        logger.debug(
            "Execution started",
            execution_id=execution_id,
            provider=provider,
            model=model,
            agent_type=agent_type
        )
    
    def record_execution_complete(
        self,
        execution_id: str,
        provider: str,
        model: str,
        success: bool,
        agent_type: str = "trae_agent",
        token_usage: Optional[Dict[str, int]] = None,
        tool_usage: Optional[Dict[str, int]] = None,
        steps_taken: Optional[int] = None,
        max_steps: Optional[int] = None,
        task_complexity: Optional[str] = None
    ):
        """Record the completion of an agent execution."""
        
        # Calculate duration
        start_time = self._timers.pop(execution_id, None)
        duration = time.time() - start_time if start_time else 0
        
        status = "success" if success else "failure"
        
        if self.enable_prometheus:
            # Record completion
            self._metrics["executions_total"].labels(
                provider=provider,
                model=model,
                status=status,
                agent_type=agent_type
            ).inc()
            
            # Record duration
            self._metrics["execution_duration_seconds"].labels(
                provider=provider,
                model=model,
                agent_type=agent_type
            ).observe(duration)
            
            # Decrement concurrent executions
            self._metrics["concurrent_executions"].dec()
            
            # Record token usage
            if token_usage:
                for token_type, count in token_usage.items():
                    self._metrics["tokens_used_total"].labels(
                        provider=provider,
                        model=model,
                        token_type=token_type
                    ).inc(count)
            
            # Record tool usage
            if tool_usage:
                for tool_name, count in tool_usage.items():
                    self._metrics["tool_calls_total"].labels(
                        tool_name=tool_name,
                        status="success"  # Assume success if we get usage stats
                    ).inc(count)
            
            # Record agent steps and efficiency
            if steps_taken is not None and max_steps is not None:
                completion_reason = "max_steps" if steps_taken >= max_steps else "completed"
                
                self._metrics["agent_steps_total"].labels(
                    provider=provider,
                    model=model,
                    agent_type=agent_type,
                    completion_reason=completion_reason
                ).inc(steps_taken)
                
                # Calculate step efficiency ratio
                efficiency_ratio = steps_taken / max_steps if max_steps > 0 else 0
                self._metrics["agent_step_efficiency"].labels(
                    provider=provider,
                    model=model,
                    agent_type=agent_type
                ).observe(efficiency_ratio)
            
            # Record task complexity if provided
            if task_complexity:
                self._metrics["task_complexity_total"].labels(
                    complexity=task_complexity,
                    success=str(success),
                    provider=provider,
                    model=model
                ).inc()
        
        logger.info(
            "Execution completed",
            execution_id=execution_id,
            provider=provider,
            model=model,
            success=success,
            duration_seconds=duration,
            token_usage=token_usage,
            tool_usage=tool_usage
        )
    
    def record_execution_error(
        self,
        execution_id: str,
        error_type: str,
        error_code: int,
        provider: Optional[str] = None,
        model: Optional[str] = None
    ):
        """Record an execution error."""
        
        # Clean up timer if exists
        start_time = self._timers.pop(execution_id, None)
        duration = time.time() - start_time if start_time else 0
        
        if self.enable_prometheus:
            # Record error
            self._metrics["errors_total"].labels(
                error_type=error_type,
                error_code=str(error_code)
            ).inc()
            
            # Decrement concurrent executions
            self._metrics["concurrent_executions"].dec()
            
            # Record failed execution if we have provider info
            if provider and model:
                self._metrics["executions_total"].labels(
                    provider=provider,
                    model=model,
                    status="error",
                    agent_type="trae_agent"
                ).inc()
        
        logger.error(
            "Execution error recorded",
            execution_id=execution_id,
            error_type=error_type,
            error_code=error_code,
            duration_seconds=duration,
            provider=provider,
            model=model
        )
    
    def record_stream_connection(
        self,
        format_type: str,
        status: str = "started"
    ):
        """Record a streaming connection."""
        
        if self.enable_prometheus:
            self._metrics["stream_connections_total"].labels(
                format_type=format_type,
                status=status
            ).inc()
        
        logger.debug(
            "Stream connection recorded",
            format_type=format_type,
            status=status
        )
    
    def record_stream_event(self, event_type: str):
        """Record a streaming event."""
        
        if self.enable_prometheus:
            self._metrics["stream_events_total"].labels(
                event_type=event_type
            ).inc()
    
    def record_request_size(self, size_bytes: int):
        """Record request size."""
        
        if self.enable_prometheus:
            self._metrics["request_size_bytes"].observe(size_bytes)
    
    def record_response_size(self, size_bytes: int):
        """Record response size."""
        
        if self.enable_prometheus:
            self._metrics["response_size_bytes"].observe(size_bytes)
    
    def update_concurrent_executions(self, count: int):
        """Update the concurrent executions gauge."""
        
        if self.enable_prometheus:
            self._metrics["concurrent_executions"].set(count)
    
    def update_available_slots(self, count: int):
        """Update the available slots gauge."""
        
        if self.enable_prometheus:
            self._metrics["available_slots"].set(count)
    
    def record_tool_call(
        self,
        tool_name: str,
        status: str = "success",
        duration_ms: Optional[float] = None
    ):
        """Record a tool call."""
        
        if self.enable_prometheus:
            self._metrics["tool_calls_total"].labels(
                tool_name=tool_name,
                status=status
            ).inc()
        
        logger.debug(
            "Tool call recorded",
            tool_name=tool_name,
            status=status,
            duration_ms=duration_ms
        )
    
    def record_phase_duration(
        self,
        phase: str,
        duration_seconds: float,
        provider: str,
        model: str
    ):
        """Record duration of an agent execution phase."""
        
        if self.enable_prometheus:
            self._metrics["phase_duration_seconds"].labels(
                phase=phase,
                provider=provider,
                model=model
            ).observe(duration_seconds)
        
        logger.debug(
            "Phase duration recorded",
            phase=phase,
            duration_seconds=duration_seconds,
            provider=provider,
            model=model
        )
    
    def record_active_executions(self, count: int):
        """Record number of active executions."""
        if self.enable_prometheus and "_active_executions" in self._metrics:
            self._metrics["_active_executions"].set(count)
        logger.debug("Active executions recorded", count=count)
    
    def record_execution_phase(
        self,
        execution_id: str,
        phase: str,
        provider: Optional[str] = None,
        model: Optional[str] = None
    ):
        """Record execution phase transition."""
        labels = {
            "phase": phase,
            "provider": provider or "unknown",
            "model": model or "unknown"
        }
        
        logger.debug(
            "Execution phase recorded",
            execution_id=execution_id,
            phase=phase,
            provider=provider,
            model=model
        )
    
    def record_llm_performance(
        self,
        provider: str,
        model: str,
        response_time_ms: float,
        input_tokens: int,
        output_tokens: int,
        cache_hit: bool = False
    ):
        """Record LLM performance metrics."""
        
        if self.enable_prometheus:
            # Record tokens
            self._metrics["tokens_used_total"].labels(
                provider=provider,
                model=model,
                token_type="input"
            ).inc(input_tokens)
            
            self._metrics["tokens_used_total"].labels(
                provider=provider,
                model=model,
                token_type="output"
            ).inc(output_tokens)
            
            if cache_hit:
                self._metrics["tokens_used_total"].labels(
                    provider=provider,
                    model=model,
                    token_type="cache_hit"
                ).inc(1)
        
        logger.debug(
            "LLM performance recorded",
            provider=provider,
            model=model,
            response_time_ms=response_time_ms,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            tokens_per_second=(input_tokens + output_tokens) / (response_time_ms / 1000) if response_time_ms > 0 else 0,
            cache_hit=cache_hit
        )
    
    def calculate_task_complexity(self, task: str, max_steps: int) -> str:
        """Calculate task complexity based on task content and max steps."""
        
        task_length = len(task)
        
        # Simple heuristics for task complexity
        if max_steps <= 5 and task_length <= 100:
            return "simple"
        elif max_steps <= 15 and task_length <= 500:
            return "medium"
        elif max_steps <= 50 and task_length <= 2000:
            return "complex"
        else:
            return "very_complex"
    
    def get_current_metrics(self) -> Dict[str, any]:
        """Get current metrics snapshot for non-Prometheus monitoring."""
        
        # This could be enhanced to return current metric values
        # For now, return basic info
        return {
            "prometheus_enabled": self.enable_prometheus,
            "active_timers": len(self._timers),
            "metric_types": len(self._metrics) if self.enable_prometheus else 0
        }
    
    def start_metrics_server(self, port: int = 8000):
        """Start Prometheus metrics server."""
        
        if not self.enable_prometheus:
            logger.warning("Prometheus not available, cannot start metrics server")
            return False
        
        try:
            start_http_server(port)
            logger.info(f"Metrics server started on port {port}")
            return True
        except Exception as e:
            logger.error(f"Failed to start metrics server: {e}")
            return False


# Global metrics instance
_metrics_instance: Optional[AgentMetrics] = None


def get_metrics() -> AgentMetrics:
    """Get global metrics instance."""
    global _metrics_instance
    
    if _metrics_instance is None:
        _metrics_instance = AgentMetrics()
    
    return _metrics_instance


def init_metrics(enable_prometheus: bool = True) -> AgentMetrics:
    """Initialize global metrics instance."""
    global _metrics_instance
    
    _metrics_instance = AgentMetrics(enable_prometheus=enable_prometheus)
    return _metrics_instance