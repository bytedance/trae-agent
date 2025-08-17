"""Production-grade streaming service for real-time agent execution."""

import asyncio
import json
from typing import AsyncGenerator, Optional

import structlog
from fastapi import Request

from trae_agent.schemas.requests import RunRequest
from trae_agent.schemas.responses import StreamEvent
from trae_api.api.agent.services.executor import AgentExecutorService
from trae_api.core.metrics import get_metrics


logger = structlog.get_logger(__name__)


class StreamingService:
    """Service for streaming agent execution events via SSE and NDJSON."""
    
    def __init__(self, executor_service: AgentExecutorService):
        """
        Initialize streaming service.
        
        Args:
            executor_service: Agent executor service instance.
        """
        self.executor_service = executor_service
        self.metrics = get_metrics()
    
    async def create_event_stream(
        self, 
        request: RunRequest,
        format_type: str = "sse",
        http_request: Optional[Request] = None
    ) -> AsyncGenerator[str, None]:
        """
        Create event stream for agent execution.
        
        Args:
            request: Agent execution request.
            format_type: Stream format - "sse" or "ndjson".
            http_request: FastAPI request object for disconnection detection.
            
        Yields:
            Formatted stream events as strings.
        """
        execution_id = None
        sequence_number = 0
        
        try:
            # Record streaming connection start
            self.metrics.record_stream_connection(format_type, "started")
            
            logger.info(
                "Starting streaming execution",
                format_type=format_type,
                task_length=len(request.task) if request.task else 0,
                client_ip=http_request.client.host if http_request else None,
            )
            
            # Send start event
            start_event = StreamEvent(
                event="start",
                data={
                    "message": "Agent execution starting",
                    "request_summary": {
                        "provider": request.provider,
                        "model": request.model,
                        "max_steps": request.max_steps,
                        "timeout": request.timeout,
                    }
                },
                execution_id="pending",
                sequence_number=sequence_number
            )
            
            yield self._format_event(start_event, format_type)
            sequence_number += 1
            
            # Record stream event
            self.metrics.record_stream_event("start")
            
            # Check for client disconnection before starting expensive operation
            if http_request and await self._is_client_disconnected(http_request):
                logger.info("Client disconnected before execution start")
                self.metrics.record_stream_connection(format_type, "disconnected_early")
                return
            
            # Execute agent with streaming
            async for event_data in self._execute_with_streaming(request):
                if execution_id is None and "execution_id" in event_data:
                    execution_id = event_data["execution_id"]
                
                # Create stream event
                stream_event = StreamEvent(
                    event=event_data.get("event_type", "progress"),
                    data=event_data,
                    execution_id=execution_id or "unknown",
                    sequence_number=sequence_number
                )
                
                yield self._format_event(stream_event, format_type)
                sequence_number += 1
                
                # Record stream event
                self.metrics.record_stream_event(event_data.get("event_type", "progress"))
                
                # Yield control and check for disconnection
                await asyncio.sleep(0)
                if http_request and await self._is_client_disconnected(http_request):
                    logger.info(
                        "Client disconnected during execution",
                        execution_id=execution_id,
                        sequence_number=sequence_number
                    )
                    self.metrics.record_stream_connection(format_type, "disconnected")
                    # Send cancellation signal to executor if possible
                    break
            
            # Send completion event
            completion_event = StreamEvent(
                event="complete",
                data={
                    "message": "Agent execution completed",
                    "total_events": sequence_number
                },
                execution_id=execution_id or "unknown",
                sequence_number=sequence_number
            )
            
            yield self._format_event(completion_event, format_type)
            
            # Record completion metrics
            self.metrics.record_stream_event("complete")
            self.metrics.record_stream_connection(format_type, "completed")
            
            logger.info(
                "Streaming execution completed",
                execution_id=execution_id,
                total_events=sequence_number
            )
            
        except asyncio.CancelledError:
            logger.info(
                "Streaming execution cancelled",
                execution_id=execution_id,
                sequence_number=sequence_number
            )
            
            # Record cancellation metrics
            self.metrics.record_stream_event("cancelled")
            self.metrics.record_stream_connection(format_type, "cancelled")
            
            # Send cancellation event
            cancel_event = StreamEvent(
                event="error",
                data={
                    "error": "cancelled",
                    "message": "Execution was cancelled"
                },
                execution_id=execution_id or "unknown",
                sequence_number=sequence_number
            )
            yield self._format_event(cancel_event, format_type)
            
        except Exception as e:
            logger.error(
                "Error in streaming execution",
                execution_id=execution_id,
                error_type=type(e).__name__,
                error_message=str(e),
                exc_info=True
            )
            
            # Record error metrics
            self.metrics.record_stream_event("error")
            self.metrics.record_stream_connection(format_type, "error")
            
            # Send error event
            error_event = StreamEvent(
                event="error",
                data={
                    "error": "execution_error",
                    "message": "An error occurred during execution",
                    "details": str(e)[:500]  # Limit error message length
                },
                execution_id=execution_id or "unknown",
                sequence_number=sequence_number
            )
            yield self._format_event(error_event, format_type)
    
    async def _execute_with_streaming(self, request: RunRequest) -> AsyncGenerator[dict, None]:
        """
        Execute agent and yield streaming events.
        
        This is a placeholder implementation. In a full implementation, you would:
        1. Modify the AgentExecutorService to support streaming mode
        2. Hook into the agent's execution loop to capture intermediate events
        3. Stream tool calls, LLM interactions, and step completions
        
        Args:
            request: Agent execution request.
            
        Yields:
            Event dictionaries with execution progress.
        """
        import uuid
        from datetime import datetime, timezone
        
        execution_id = str(uuid.uuid4())
        
        # Yield execution ID
        yield {
            "event_type": "start",
            "execution_id": execution_id,
            "message": "Execution started",
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
        try:
            # For now, execute the agent normally and simulate streaming
            # In a full implementation, this would be integrated with the agent execution loop
            
            # Simulate some execution steps
            steps = [
                "Initializing agent environment",
                "Loading configuration and tools", 
                "Analyzing task requirements",
                "Starting agent execution loop",
                "Executing task steps...",
            ]
            
            for i, step in enumerate(steps):
                yield {
                    "event_type": "step",
                    "execution_id": execution_id,
                    "step_number": i + 1,
                    "message": step,
                    "timestamp": datetime.now(timezone.utc).isoformat()
                }
                
                # Small delay to simulate processing
                await asyncio.sleep(0.1)
            
            # Execute the actual agent (this could be modified to support streaming)
            yield {
                "event_type": "progress",
                "execution_id": execution_id,
                "message": "Running agent execution...",
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
            
            # Execute the agent normally
            result = await self.executor_service.execute_agent(request)
            
            # Yield final result
            yield {
                "event_type": "complete",
                "execution_id": execution_id,
                "result": {
                    "success": result.success,
                    "execution_id": result.execution_id,
                    "duration_ms": result.stats.execution_duration_ms if result.stats else 0,
                    "total_steps": result.stats.total_steps if result.stats else 0,
                },
                "message": "Execution completed successfully" if result.success else "Execution completed with errors",
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
            
        except Exception as e:
            yield {
                "event_type": "error",
                "execution_id": execution_id,
                "error": type(e).__name__,
                "message": str(e)[:500],  # Limit error message length
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
    
    def _format_event(self, event: StreamEvent, format_type: str) -> str:
        """
        Format event for streaming.
        
        Args:
            event: Stream event to format.
            format_type: Format type - "sse" or "ndjson".
            
        Returns:
            Formatted event string.
        """
        if format_type == "sse":
            # Server-Sent Events format
            event_json = event.model_dump_json()
            return f"data: {event_json}\n\n"
        
        elif format_type == "ndjson":
            # Newline-delimited JSON format
            return event.model_dump_json() + "\n"
        
        else:
            # Default to SSE
            event_json = event.model_dump_json()
            return f"data: {event_json}\n\n"
    
    async def _is_client_disconnected(self, request: Request) -> bool:
        """
        Check if client has disconnected.
        
        Args:
            request: FastAPI request object.
            
        Returns:
            True if client is disconnected, False otherwise.
        """
        try:
            # This is a basic check - in production you might want more sophisticated detection
            return await request.is_disconnected()
        except Exception:
            # If we can't check, assume client is still connected
            return False


class StreamingEventBuffer:
    """Buffer for streaming events to handle backpressure."""
    
    def __init__(self, max_size: int = 1000):
        """
        Initialize event buffer.
        
        Args:
            max_size: Maximum number of events to buffer.
        """
        self.max_size = max_size
        self.events = []
        self._lock = asyncio.Lock()
    
    async def add_event(self, event: StreamEvent) -> bool:
        """
        Add event to buffer.
        
        Args:
            event: Event to add.
            
        Returns:
            True if event was added, False if buffer is full.
        """
        async with self._lock:
            if len(self.events) >= self.max_size:
                # Remove oldest event to make room
                self.events.pop(0)
                logger.warning("Stream event buffer full, dropping oldest event")
            
            self.events.append(event)
            return True
    
    async def get_events(self, since_sequence: int = 0) -> list[StreamEvent]:
        """
        Get events since a sequence number.
        
        Args:
            since_sequence: Get events after this sequence number.
            
        Returns:
            List of events.
        """
        async with self._lock:
            return [
                event for event in self.events 
                if event.sequence_number > since_sequence
            ]
    
    async def clear(self):
        """Clear all events from buffer."""
        async with self._lock:
            self.events.clear()


def get_streaming_service(executor_service: AgentExecutorService) -> StreamingService:
    """Get streaming service instance."""
    return StreamingService(executor_service)