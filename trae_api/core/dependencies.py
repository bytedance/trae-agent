"""
Application dependencies with Taskiq integration.

Following best practices for dependency injection with FastAPI and Taskiq:
- Use TaskiqDepends for parameters that need to work in both FastAPI and Taskiq
- Use Annotated for better type hinting
- Provide proper fallbacks for testing
"""

from typing import Annotated, Any, Dict

from fastapi import Request
from taskiq import TaskiqDepends


async def get_app_state(request: Annotated[Request, TaskiqDepends()]) -> Dict[str, Any]:
    """
    Get application state from FastAPI request.

    This dependency works in both FastAPI handlers and Taskiq tasks.
    In Taskiq tasks, the request object is a worker-wide singleton,
    not the actual HTTP request.

    Args:
        request: FastAPI request object (injected via TaskiqDepends)

    Returns:
        dict: Application state dictionary
    """
    # Handle missing request or app gracefully
    if not request or not hasattr(request, "app"):
        return {}
    
    # Get the state object
    state = getattr(request.app, "state", None)
    if not state:
        return {}
    
    # Check if state has _state attribute (Starlette's internal structure)
    if hasattr(state, "_state") and isinstance(state._state, dict):
        return state._state
    
    # Fallback to __dict__ if no _state
    return getattr(state, "__dict__", {})


async def get_settings(request: Annotated[Request, TaskiqDepends()]) -> Dict[str, Any]:
    """
    Get application settings from FastAPI request.

    Args:
        request: FastAPI request object (injected via TaskiqDepends)

    Returns:
        dict: Settings dictionary
    """
    app_state = await get_app_state(request)
    return app_state.get("settings", {})


# Type aliases for cleaner usage
AppState = Annotated[Dict[str, Any], TaskiqDepends(get_app_state)]
Settings = Annotated[Dict[str, Any], TaskiqDepends(get_settings)]
