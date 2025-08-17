import uuid

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from starlette import status


@pytest.mark.anyio
async def test_echo(fastapi_app: FastAPI, client: AsyncClient) -> None:
    """
    Tests that echo route works.

    :param fastapi_app: current application.
    :param client: client for the app.
    """
    url = fastapi_app.url_path_for("send_echo_message")
    message = uuid.uuid4().hex
    response = await client.post(url, json={"message": message})
    assert response.status_code == status.HTTP_200_OK
    # Middleware should add correlation header
    assert "x-correlation-id" in response.headers
    assert response.json()["message"] == message


@pytest.mark.anyio
@pytest.mark.parametrize(
    "payload",
    [
        {"message": 123},  # wrong type
        {},  # missing field
    ],
)
async def test_echo_invalid_payload_returns_422(
    fastapi_app: FastAPI, client: AsyncClient, payload: dict,
) -> None:
    """Invalid payloads should trigger FastAPI/Pydantic validation errors (422)."""
    url = fastapi_app.url_path_for("send_echo_message")
    response = await client.post(url, json=payload)
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
