from typing import Any, AsyncGenerator, Generator

import httpx
import pytest
import taskiq_fastapi
from fastapi import FastAPI
from httpx import AsyncClient

from trae_api.core.application import get_app
from trae_api.tasks.broker import broker


@pytest.fixture(scope="session")
def anyio_backend() -> str:
    """
    Backend for anyio pytest plugin.

    :return: backend name.
    """
    return "asyncio"


@pytest.fixture
def fastapi_app() -> FastAPI:
    """
    Fixture for creating FastAPI app.

    :return: fastapi app with mocked dependencies.
    """
    application = get_app()
    return application  # noqa: RET504


@pytest.fixture
async def client(
    fastapi_app: FastAPI,
    anyio_backend: Any,
) -> AsyncGenerator[AsyncClient, None]:
    """
    Fixture that creates client for requesting server.

    :param fastapi_app: the application.
    :yield: client for the app.
    """
    async with AsyncClient(
        transport=httpx.ASGITransport(app=fastapi_app),
        base_url="http://test",
        timeout=2.0,
    ) as ac:
        yield ac


@pytest.fixture(autouse=True)
def setup_taskiq_dependencies(fastapi_app: FastAPI) -> Generator[None, None, None]:
    """
    Setup Taskiq dependency context for testing.

    This fixture automatically runs before each test to ensure
    that InMemoryBroker has access to FastAPI dependencies.

    Following best practices from Taskiq documentation for testing.
    """
    # Populate dependency context for InMemoryBroker
    taskiq_fastapi.populate_dependency_context(broker, fastapi_app)

    yield

    # Clean up custom dependencies after test
    broker.custom_dependency_context = {}
