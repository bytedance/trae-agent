"""Dependencies for agent API endpoints."""

from functools import lru_cache

from trae_api.api.agent.services.executor import AgentExecutorService
from trae_api.api.agent.services.streaming import StreamingService


@lru_cache()
def get_agent_executor_service() -> AgentExecutorService:
    """Get a singleton instance of AgentExecutorService."""
    return AgentExecutorService()


@lru_cache()
def get_streaming_service() -> StreamingService:
    """Get a singleton instance of StreamingService."""
    executor_service = get_agent_executor_service()
    return StreamingService(executor_service)


async def get_executor_service() -> AgentExecutorService:
    """FastAPI dependency for getting the agent executor service."""
    return get_agent_executor_service()