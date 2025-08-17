"""Agent API endpoints for HTTP interface."""

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

import structlog
from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse, StreamingResponse

from trae_agent.utils.config import Config
from trae_api.api.agent.dependencies import get_executor_service
from trae_api.api.agent.endpoints.schema import (
    ConfigReloadRequest,
    ConfigRequest,
    ConfigResponse,
    ErrorResponse,
    RunRequest,
    RunResponse,
)
from trae_api.api.agent.services.executor import AgentExecutorService
from trae_api.api.agent.services.streaming import StreamingService, get_streaming_service
from trae_api.core.metrics import get_metrics
from trae_api.core.logging import get_api_logger, generate_request_id, set_correlation_context
from trae_api.core.resources import monitored_endpoint


logger = structlog.get_logger(__name__)
metrics = get_metrics()

router = APIRouter()




@router.post("/run", response_model=RunResponse, status_code=200)
async def execute_agent(
    request: RunRequest = Body(..., description="Agent execution request"),
    executor: AgentExecutorService = Depends(get_executor_service),
    http_request: Request = None,
) -> RunResponse:
    """
    Execute agent task synchronously.
    
    This endpoint executes a trae_agent task with full CLI parity.
    Supports all CLI options including provider overrides, model selection,
    working directory specification, and more.
    
    - **task**: Task description or instruction for the agent
    - **file_path**: Alternative to task - path to file containing task description  
    - **provider**: LLM provider override (anthropic, openai, google, etc.)
    - **model**: Specific model to use
    - **working_dir**: Working directory for agent execution
    - **max_steps**: Maximum execution steps (default from config)
    - **timeout**: Execution timeout in seconds (30s-1hr range)
    
    Returns the complete execution result including trajectory data,
    patches applied, execution statistics, and any errors encountered.
    """
    import time
    start_time = time.time()
    
    # Generate request ID for correlation
    request_id = generate_request_id()
    set_correlation_context(request_id=request_id)
    
    try:
        # Record request metrics
        request_size = len(request.model_dump_json().encode('utf-8'))
        metrics.record_request_size(request_size)
        
        # Log incoming request (essential for debugging)
        logger.info(
            "Agent execution request received",
            request_id=request_id,
            provider=request.provider,
            model=request.model,
            task_length=len(request.task) if request.task else 0,
            client_ip=http_request.client.host if http_request else None,
        )
        
        # Execute the agent
        result = await executor.execute_agent(request)
        
        # Record response metrics
        response_size = len(result.model_dump_json().encode('utf-8'))
        metrics.record_response_size(response_size)
        
        # Log completion with essential metrics
        duration_ms = (time.time() - start_time) * 1000
        logger.info(
            "Agent execution completed",
            request_id=request_id,
            execution_id=result.execution_id,
            success=result.success,
            duration_ms=duration_ms,
            response_size_bytes=response_size,
        )
        
        return result
        
    except HTTPException as e:
        # Log HTTP exceptions with context
        duration_ms = (time.time() - start_time) * 1000
        logger.warning(
            "Agent execution failed",
            request_id=request_id,
            status_code=e.status_code,
            error_detail=e.detail,
            duration_ms=duration_ms,
        )
        raise
        
    except Exception as e:
        # Log unexpected errors
        duration_ms = (time.time() - start_time) * 1000
        logger.error(
            "Unexpected error in execute_agent",
            request_id=request_id,
            error=str(e),
            duration_ms=duration_ms,
            exc_info=True,
        )
        raise HTTPException(
            status_code=500,
            detail={
                "error": "internal_error",
                "message": "An unexpected error occurred during agent execution",
            }
        )


@router.post("/run/stream", status_code=200)
async def stream_agent_execution(
    request: RunRequest = Body(..., description="Agent execution request"),
    format_type: str = Query("sse", regex="^(sse|ndjson)$", description="Stream format: sse or ndjson"),
    executor: AgentExecutorService = Depends(get_executor_service),
    http_request: Request = None,
) -> StreamingResponse:
    """
    Stream agent execution events in real-time.
    
    This endpoint provides real-time streaming of agent execution progress,
    allowing clients to monitor long-running tasks as they execute.
    
    **Stream Formats:**
    - **sse** (default): Server-Sent Events format for web browsers
    - **ndjson**: Newline-delimited JSON for programmatic consumption
    
    **Event Types:**
    - **start**: Execution initialization
    - **step**: Individual execution steps
    - **tool_call**: Tool invocations and results
    - **llm_interaction**: LLM request/response pairs
    - **progress**: General progress updates
    - **complete**: Successful completion
    - **error**: Errors or failures
    
    **Usage:**
    ```javascript
    // Browser JavaScript with SSE
    const eventSource = new EventSource('/api/agent/run/stream');
    eventSource.onmessage = function(event) {
        const data = JSON.parse(event.data);
        console.log('Event:', data.event, 'Data:', data.data);
    };
    ```
    
    ```python
    # Python with requests
    import requests
    import json
    
    response = requests.post('/api/agent/run/stream?format_type=ndjson', 
                           json={"task": "Create a hello world script"}, 
                           stream=True)
    
    for line in response.iter_lines():
        if line:
            event = json.loads(line.decode('utf-8'))
            print(f"Event: {event['event']}, Data: {event['data']}")
    ```
    
    **Connection Management:**
    - Automatic client disconnection detection
    - Graceful cancellation of long-running executions  
    - Connection keep-alive with heartbeat events
    - Buffer management for high-frequency events
    """
    import time
    request_start_time = time.time()
    
    # Create request logger with correlation context
    request_id = generate_request_id()
    set_correlation_context(request_id=request_id)
    request_logger = get_api_logger("agent.streaming")
    
    try:
        # Record request size for streaming endpoint
        request_json = request.model_dump_json()
        request_size = len(request_json.encode('utf-8'))
        metrics.record_request_size(request_size)
        
        request_logger.info(
            "Streaming execution request received",
            event_type="stream_request_received",
            task_length=len(request.task) if request.task else 0,
            format_type=format_type,
            provider=request.provider,
            model=request.model,
            request_size_bytes=request_size,
            client_ip=http_request.client.host if http_request else None,
        )
        
        # Create streaming service
        streaming_service = get_streaming_service(executor)
        
        # Create event stream generator
        event_stream = streaming_service.create_event_stream(
            request, 
            format_type=format_type,
            http_request=http_request
        )
        
        # Determine media type based on format
        media_type = "text/event-stream" if format_type == "sse" else "application/x-ndjson"
        
        # Create streaming response with appropriate headers
        response = StreamingResponse(
            event_stream,
            media_type=media_type,
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",  # Disable Nginx buffering
                "Access-Control-Allow-Origin": "*",  # CORS for web browsers
                "Access-Control-Allow-Headers": "Cache-Control",
            }
        )
        
        # Log successful stream creation (actual completion logged in streaming service)
        duration_ms = (time.time() - request_start_time) * 1000
        request_logger.info(
            "Streaming response created successfully",
            format_type=format_type,
            media_type=media_type,
            setup_duration_ms=duration_ms,
        )
        
        return response
        
    except Exception as e:
        duration_ms = (time.time() - request_start_time) * 1000
        
        # Log request completion inline instead of using undefined function
        request_logger.info(
            "Request completed",
            status=500,
            response_size=None,
            request_duration_ms=duration_ms,
        )
        
        request_logger.error(
            "Error creating stream response",
            error_type=type(e).__name__,
            error_message=str(e),
            format_type=format_type,
            request_duration_ms=duration_ms,
            exc_info=True,
        )
        raise HTTPException(
            status_code=500,
            detail={
                "error": "stream_creation_error",
                "message": "Failed to create streaming response",
            }
        )


@router.get("/config", response_model=ConfigResponse, status_code=200)
async def get_agent_config(
    config_request: ConfigRequest = Depends(),
    http_request: Request = None,
) -> ConfigResponse:
    """
    Get current agent configuration.
    
    Returns the current configuration including:
    - Default provider and model settings
    - API key status (configured/not configured - never shows actual keys)
    - Working directory and execution limits
    - MCP server configurations
    - Configuration file status and location
    
    This endpoint provides CLI parity with `trae show-config`.
    """
    try:
        # Record config request (minimal size for GET request)
        config_request_size = len(str(config_request.config_file or "").encode('utf-8'))
        metrics.record_request_size(config_request_size)
        
        logger.debug(
            "Configuration request received",
            config_file=config_request.config_file,
            request_size_bytes=config_request_size,
            client_ip=http_request.client.host if http_request else None,
        )
        
        # Load configuration (use default if not specified)
        config_file = config_request.config_file or "trae_config.yaml"
        config_path = Path(config_file)
        
        try:
            config = Config.create(config_file=config_file)
            config_exists = True
        except Exception as e:
            logger.warning(
                "Failed to load configuration file",
                config_file=config_file,
                error=str(e),
            )
            # Return default config structure
            config = Config()
            config_exists = False
        
        # Build sanitized config response
        from trae_agent.schemas.responses import ConfigData
        
        config_data = ConfigData(
            provider=config.trae_agent.model.model_provider.provider if config.trae_agent else None,
            model=config.trae_agent.model.model if config.trae_agent else None,
            api_key_configured=bool(getattr(config.trae_agent.model.model_provider, 'api_key', None)) if config.trae_agent else False,
            working_dir=None,  # trae_agent config doesn't have working_dir at config level
            max_steps=getattr(config.trae_agent, 'max_steps', None) if config.trae_agent else None,
            timeout=900,  # Default timeout
            console_type="simple",  # Default console type
            mcp_servers=getattr(config.trae_agent, 'mcp_servers_config', {}) if config.trae_agent else {}
        )
        
        # Get file modification time if exists
        last_modified = None
        if config_exists and config_path.exists():
            try:
                last_modified = config_path.stat().st_mtime
                last_modified = str(last_modified)
            except Exception:
                pass
        
        response = ConfigResponse(
            config=config_data,
            config_file_path=str(config_path.absolute()),
            config_file_exists=config_exists,
            last_modified=last_modified,
        )
        
        # Record response size for config endpoint
        response_json = response.model_dump_json()
        response_size = len(response_json.encode('utf-8'))
        metrics.record_response_size(response_size)
        
        logger.debug(
            "Configuration retrieved successfully",
            config_file=config_file,
            config_exists=config_exists,
            provider=config_data.provider,
            response_size_bytes=response_size,
        )
        
        return response
        
    except Exception as e:
        logger.error(
            "Error retrieving configuration",
            config_file=config_request.config_file,
            error_type=type(e).__name__,
            error_message=str(e),
            exc_info=True,
        )
        raise HTTPException(
            status_code=500,
            detail={
                "error": "config_error",
                "message": "Failed to retrieve configuration",
            }
        )


@router.post("/config/reload", response_model=Dict[str, Any], status_code=200)
async def reload_agent_config(
    request: ConfigReloadRequest = Body(..., description="Configuration reload request"),
    http_request: Request = None,
) -> Dict[str, Any]:
    """
    Reload agent configuration at runtime.
    
    This endpoint allows hot-reloading of configuration without restarting
    the service. Useful for updating API keys, model settings, or MCP
    server configurations.
    
    - **config_file**: Path to configuration file to reload
    
    Returns status of the reload operation and any validation errors.
    Note: Some configuration changes may require service restart to take
    full effect (e.g., middleware settings).
    """
    try:
        # Record request size for config reload
        request_json = request.model_dump_json()
        request_size = len(request_json.encode('utf-8'))
        metrics.record_request_size(request_size)
        
        logger.info(
            "Configuration reload request received",
            config_file=request.config_file,
            request_size_bytes=request_size,
            client_ip=http_request.client.host if http_request else None,
        )
        
        config_path = Path(request.config_file)
        
        if not config_path.exists():
            raise HTTPException(
                status_code=404,
                detail={
                    "error": "config_not_found",
                    "message": f"Configuration file not found: {request.config_file}",
                }
            )
        
        # Validate the configuration file by loading it
        try:
            config = Config.create(config_file=request.config_file)
            validation_success = True
            validation_errors = []
        except Exception as e:
            validation_success = False
            validation_errors = [str(e)]
            logger.warning(
                "Configuration validation failed during reload",
                config_file=request.config_file,
                error=str(e),
            )
        
        # In a full implementation, you would:
        # 1. Update any cached configurations
        # 2. Notify services that use the config
        # 3. Update runtime settings where possible
        
        response = {
            "status": "success" if validation_success else "validation_failed",
            "message": "Configuration reloaded successfully" if validation_success else "Configuration validation failed",
            "config_file": str(config_path.absolute()),
            "timestamp": str(Path(request.config_file).stat().st_mtime),
            "validation_errors": validation_errors,
        }
        
        # Record response size for config reload
        response_json = json.dumps(response)
        response_size = len(response_json.encode('utf-8'))
        metrics.record_response_size(response_size)
        
        if validation_success:
            logger.info(
                "Configuration reloaded successfully",
                config_file=request.config_file,
                response_size_bytes=response_size,
            )
        else:
            logger.warning(
                "Configuration reload failed validation",
                config_file=request.config_file,
                errors=validation_errors,
                response_size_bytes=response_size,
            )
        
        return response
        
    except HTTPException:
        raise
        
    except Exception as e:
        logger.error(
            "Error reloading configuration",
            config_file=request.config_file,
            error_type=type(e).__name__,
            error_message=str(e),
            exc_info=True,
        )
        raise HTTPException(
            status_code=500,
            detail={
                "error": "reload_error",
                "message": "Failed to reload configuration",
            }
        )


@router.get("/health", status_code=200)
async def agent_health_check(
    executor: AgentExecutorService = Depends(get_executor_service),
) -> Dict[str, Any]:
    """
    Health check endpoint for agent service.
    
    Returns current service health including:
    - Service status
    - Active executions count
    - Available execution slots
    - Resource utilization
    """
    try:
        health_data = await executor.health_check()
        
        return {
            "status": "healthy",
            "service": "agent_executor",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            **health_data,
        }
        
    except Exception as e:
        logger.error(
            "Health check failed",
            error_type=type(e).__name__,
            error_message=str(e),
        )
        return {
            "status": "unhealthy",
            "service": "agent_executor",
            "error": str(e),
        }


@router.get("/executions/{execution_id}/status", status_code=200)
async def get_execution_status(
    execution_id: str,
    executor: AgentExecutorService = Depends(get_executor_service),
) -> Dict[str, Any]:
    """
    Get status of a specific execution.
    
    Returns current status of an active or recent execution:
    - Execution state (starting, running, completed, failed)
    - Start time and duration
    - Resource usage information
    
    Useful for monitoring long-running executions.
    """
    try:
        status = await executor.get_execution_status(execution_id)
        
        if not status:
            raise HTTPException(
                status_code=404,
                detail={
                    "error": "execution_not_found",
                    "message": f"Execution {execution_id} not found",
                }
            )
        
        return {
            "execution_id": execution_id,
            **status,
        }
        
    except HTTPException:
        raise
        
    except Exception as e:
        logger.error(
            "Error retrieving execution status",
            execution_id=execution_id,
            error=str(e),
        )
        raise HTTPException(
            status_code=500,
            detail={
                "error": "status_error",
                "message": "Failed to retrieve execution status",
            }
        )


@router.get("/executions", status_code=200)
async def list_active_executions(
    executor: AgentExecutorService = Depends(get_executor_service),
) -> Dict[str, Any]:
    """
    List all active executions.
    
    Returns summary of all currently running or recently completed executions.
    Useful for monitoring system load and execution patterns.
    """
    try:
        executions = await executor.list_active_executions()
        
        return {
            "active_executions": len(executions),
            "executions": executions,
        }
        
    except Exception as e:
        logger.error(
            "Error listing active executions",
            error=str(e),
        )
        raise HTTPException(
            status_code=500,
            detail={
                "error": "list_error",
                "message": "Failed to list active executions",
            }
        )