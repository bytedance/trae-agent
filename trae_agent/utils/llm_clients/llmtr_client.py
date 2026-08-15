# Copyright (c) 2025 ByteDance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

"""LLMTR provider configuration and client.

LLMTR (https://llmtr.com) is an OpenAI-compatible AI gateway that serves both
Turkey-hosted and global models behind a single API key. Its catalogue mixes
models that speak ``/v1/chat/completions`` with models that only speak
``/v1/responses`` (for example ``openai/gpt-5.3-codex`` and the ``xai/grok-4.x``
family), so this client consults the public model catalogue and routes each
model to the endpoint it actually supports.
"""

import contextlib
import json
import time
from enum import Enum
from pathlib import Path
from typing import override

import openai
from openai.types.responses import (
    FunctionToolParam,
    ResponseFunctionToolCallParam,
    ResponseInputParam,
)
from openai.types.responses.response_input_param import FunctionCallOutput

from trae_agent.tools.base import Tool, ToolCall, ToolResult
from trae_agent.utils.config import ModelConfig
from trae_agent.utils.constants import LOCAL_STORAGE_PATH
from trae_agent.utils.llm_clients.base_client import BaseLLMClient
from trae_agent.utils.llm_clients.llm_basics import LLMMessage, LLMResponse, LLMUsage
from trae_agent.utils.llm_clients.openai_compatible_base import (
    OpenAICompatibleClient,
    ProviderConfig,
)
from trae_agent.utils.llm_clients.retry_utils import retry_with

LLMTR_BASE_URL = "https://llmtr.com/v1"

CHAT_COMPLETIONS_ENDPOINT = "/v1/chat/completions"
RESPONSES_ENDPOINT = "/v1/responses"

CATALOG_CACHE_PATH = LOCAL_STORAGE_PATH / "llmtr_models.json"
CATALOG_CACHE_TTL_SECONDS = 24 * 60 * 60

# Reasoning models reject explicit sampling parameters. Mirrors the guard in
# `openai_compatible_base._create_response` so both routes behave the same way.
_REASONING_MODEL_MARKERS = ("gpt-5", "o3", "o4-mini")


class LLMTRRoute(Enum):
    """The LLMTR endpoint family a model can be reached through."""

    CHAT_COMPLETIONS = "chat_completions"
    RESPONSES = "responses"
    UNSUPPORTED = "unsupported"


def normalise_model_name(model: str) -> str:
    """Strip the reasoning-effort slug suffix LLMTR accepts (e.g. ``gpt-5.3-codex:high``)."""
    return model.split(":", 1)[0]


def is_reasoning_model(model: str) -> bool:
    """Check whether sampling parameters should be omitted for this model."""
    return any(marker in normalise_model_name(model) for marker in _REASONING_MODEL_MARKERS)


class LLMTRModelCatalog:
    """Cached view of the LLMTR model catalogue (``GET /v1/models``).

    The endpoint is public — no API key required — so the catalogue can be
    consulted before the first billable request in order to route the model and
    to fail fast on models that cannot serve a chat at all.
    """

    def __init__(
        self,
        api_key: str,
        base_url: str | None,
        cache_path: Path | None = None,
        ttl_seconds: int = CATALOG_CACHE_TTL_SECONDS,
    ):
        self.api_key: str = api_key
        self.base_url: str = base_url or LLMTR_BASE_URL
        self.cache_path: Path = cache_path if cache_path is not None else CATALOG_CACHE_PATH
        self.ttl_seconds: int = ttl_seconds
        self._endpoints: dict[str, list[str]] | None = None

    def endpoints(self) -> dict[str, list[str]]:
        """Return a ``{model_id: [supported endpoints]}`` mapping, using the cache when fresh."""
        if self._endpoints is not None:
            return self._endpoints

        cached, fetched_at = self._read_cache()
        if cached is not None and (time.time() - fetched_at) < self.ttl_seconds:
            self._endpoints = cached
            return self._endpoints

        try:
            fetched = self._fetch()
        except Exception:
            # Never let catalogue problems block a run: fall back to a stale
            # cache when there is one, otherwise to an empty catalogue which
            # makes every model route optimistically to chat completions.
            self._endpoints = cached if cached is not None else {}
            return self._endpoints

        self._write_cache(fetched)
        self._endpoints = fetched
        return self._endpoints

    def refresh(self) -> dict[str, list[str]]:
        """Force a catalogue re-fetch, bypassing the cache."""
        self._endpoints = None
        with contextlib.suppress(OSError):
            self.cache_path.unlink(missing_ok=True)
        return self.endpoints()

    def supported_endpoints(self, model: str) -> list[str] | None:
        """Return the endpoints a model supports, or ``None`` when it is not in the catalogue."""
        return self.endpoints().get(normalise_model_name(model))

    def route_for(self, model: str) -> LLMTRRoute:
        """Pick the endpoint family to use for a model."""
        endpoints = self.supported_endpoints(model)
        if endpoints is None:
            # Unknown model: stay optimistic. The gateway reports an
            # `endpoint_mismatch` error that `LLMTRClient` recovers from.
            return LLMTRRoute.CHAT_COMPLETIONS
        if CHAT_COMPLETIONS_ENDPOINT in endpoints:
            return LLMTRRoute.CHAT_COMPLETIONS
        if RESPONSES_ENDPOINT in endpoints:
            return LLMTRRoute.RESPONSES
        return LLMTRRoute.UNSUPPORTED

    def chat_capable_models(self, owner_prefix: str | None = None) -> list[str]:
        """List models that can serve a chat, optionally limited to one owner prefix."""
        models = [
            model_id
            for model_id, endpoints in self.endpoints().items()
            if CHAT_COMPLETIONS_ENDPOINT in endpoints or RESPONSES_ENDPOINT in endpoints
        ]
        if owner_prefix:
            models = [model_id for model_id in models if model_id.startswith(f"{owner_prefix}/")]
        return sorted(models)

    def _fetch(self) -> dict[str, list[str]]:
        # `api_key` is irrelevant for this public endpoint but the SDK requires one.
        client = openai.OpenAI(api_key=self.api_key or "llmtr", base_url=self.base_url)
        return {
            model.id: list(getattr(model, "supported_endpoints", None) or [])
            for model in client.models.list()
        }

    def _read_cache(self) -> tuple[dict[str, list[str]] | None, float]:
        try:
            with open(self.cache_path, "r", encoding="utf-8") as f:
                payload = json.load(f)
            models = payload["models"]
            if not isinstance(models, dict):
                return None, 0.0
            return models, float(payload.get("fetched_at", 0.0))
        except (OSError, ValueError, KeyError, TypeError):
            return None, 0.0

    def _write_cache(self, models: dict[str, list[str]]) -> None:
        try:
            self.cache_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.cache_path, "w", encoding="utf-8") as f:
                json.dump({"fetched_at": time.time(), "models": models}, f)
        except OSError:
            # A non-writable cache location must not break the run.
            pass


class LLMTRProvider(ProviderConfig):
    """LLMTR provider configuration for the chat completions route."""

    @override
    def create_client(
        self, api_key: str, base_url: str | None, api_version: str | None
    ) -> openai.OpenAI:
        """Create OpenAI client with the LLMTR base URL."""
        return openai.OpenAI(api_key=api_key, base_url=base_url or LLMTR_BASE_URL)

    @override
    def get_service_name(self) -> str:
        """Get the service name for retry logging."""
        return "LLMTR"

    @override
    def get_provider_name(self) -> str:
        """Get the provider name for trajectory recording."""
        return "llmtr"

    @override
    def get_extra_headers(self) -> dict[str, str]:
        """Get LLMTR-specific headers (none needed)."""
        return {}

    @override
    def supports_tool_calling(self, model_name: str) -> bool:
        """Check if the model supports tool calling.

        LLMTR model ids are ``owner/model`` slugs that do not encode
        capabilities, and the catalogue does not publish a tool-calling flag, so
        no name-based heuristic is applied here. The few models that lack native
        function calling - search models such as ``perplexity/sonar-*`` and some
        small local models - reply with plain text instead of tool calls.
        """
        return True


class LLMTRChatCompletionsClient(OpenAICompatibleClient):
    """LLMTR client for models served over ``/v1/chat/completions``."""

    def __init__(self, model_config: ModelConfig):
        super().__init__(model_config, LLMTRProvider())


class LLMTRResponsesClient(BaseLLMClient):
    """LLMTR client for models served only over ``/v1/responses``."""

    def __init__(self, model_config: ModelConfig):
        super().__init__(model_config)
        self.client: openai.OpenAI = openai.OpenAI(
            api_key=self.api_key, base_url=self.base_url or LLMTR_BASE_URL
        )
        self.message_history: ResponseInputParam = []

    @override
    def set_chat_history(self, messages: list[LLMMessage]) -> None:
        """Set the chat history."""
        self.message_history = self.parse_messages(messages)

    def _create_response(
        self,
        model_config: ModelConfig,
        tool_schemas: list[FunctionToolParam] | None,
    ):
        """Create a response using the Responses API. Decorated with retry logic."""
        sampling_params = {}
        if not is_reasoning_model(model_config.model):
            sampling_params["temperature"] = model_config.temperature
            sampling_params["top_p"] = model_config.top_p

        return self.client.responses.create(
            model=model_config.model,
            input=self.message_history,
            tools=tool_schemas if tool_schemas else openai.NOT_GIVEN,
            max_output_tokens=model_config.get_max_tokens_param(),
            store=False,
            **sampling_params,
        )

    @override
    def chat(
        self,
        messages: list[LLMMessage],
        model_config: ModelConfig,
        tools: list[Tool] | None = None,
        reuse_history: bool = True,
    ) -> LLMResponse:
        """Send chat messages with optional tool support."""
        parsed_messages = self.parse_messages(messages)
        if reuse_history:
            self.message_history = self.message_history + parsed_messages
        else:
            self.message_history = parsed_messages

        tool_schemas = None
        if tools:
            tool_schemas = [
                FunctionToolParam(
                    name=tool.get_name(),
                    description=tool.get_description(),
                    parameters=tool.get_input_schema(),
                    # Trae tool schemas do not satisfy OpenAI strict mode, which
                    # requires every property to be required and additionalProperties
                    # to be false.
                    strict=False,
                    type="function",
                )
                for tool in tools
            ]

        retry_decorator = retry_with(
            func=self._create_response,
            provider_name="LLMTR",
            max_retries=model_config.max_retries,
        )
        response = retry_decorator(model_config, tool_schemas)

        content = ""
        tool_calls: list[ToolCall] = []
        for item in response.output:
            match item.type:
                case "function_call":
                    tool_calls.append(
                        ToolCall(
                            name=item.name,
                            call_id=item.call_id,
                            arguments=json.loads(item.arguments) if item.arguments else {},
                            id=item.id,
                        )
                    )
                case "message":
                    for part in item.content:
                        if part.type == "output_text":
                            content += part.text
                case _:
                    # Reasoning and provider-specific items carry no state we can
                    # replay without `store=True`, so they are dropped.
                    continue

        llm_response = LLMResponse(
            content=content,
            tool_calls=tool_calls if tool_calls else None,
            finish_reason=self._finish_reason(response, bool(tool_calls)),
            model=response.model,
            usage=self._parse_usage(response),
        )

        # Update message history with the assistant turn.
        if content:
            self.message_history.append({"role": "assistant", "content": content})
        for tool_call in tool_calls:
            self.message_history.append(
                ResponseFunctionToolCallParam(
                    call_id=tool_call.call_id,
                    name=tool_call.name,
                    arguments=json.dumps(tool_call.arguments),
                    type="function_call",
                )
            )

        if self.trajectory_recorder:
            self.trajectory_recorder.record_llm_interaction(
                messages=messages,
                response=llm_response,
                provider="llmtr",
                model=model_config.model,
                tools=tools,
            )

        return llm_response

    @staticmethod
    def _finish_reason(response, has_tool_calls: bool) -> str | None:
        """Map a Responses API status onto the chat completions style finish reason."""
        if response.status == "incomplete":
            reason = getattr(response.incomplete_details, "reason", None)
            return "length" if reason == "max_output_tokens" else reason
        if has_tool_calls:
            return "tool_calls"
        return "stop" if response.status == "completed" else response.status

    @staticmethod
    def _parse_usage(response) -> LLMUsage | None:
        """Translate Responses API usage into the shared usage format."""
        usage = response.usage
        if usage is None:
            return None
        return LLMUsage(
            input_tokens=usage.input_tokens or 0,
            output_tokens=usage.output_tokens or 0,
            cache_read_input_tokens=getattr(usage.input_tokens_details, "cached_tokens", 0) or 0,
            reasoning_tokens=getattr(usage.output_tokens_details, "reasoning_tokens", 0) or 0,
        )

    def parse_messages(self, messages: list[LLMMessage]) -> ResponseInputParam:
        """Parse LLM messages into Responses API input items."""
        response_messages: ResponseInputParam = []
        for msg in messages:
            if msg.tool_result:
                response_messages.append(self.parse_tool_call_result(msg.tool_result))
            elif msg.tool_call:
                response_messages.append(self.parse_tool_call(msg.tool_call))
            else:
                if not msg.content:
                    raise ValueError("Message content is required")
                if msg.role not in ("system", "user", "assistant"):
                    raise ValueError(f"Invalid message role: {msg.role}")
                response_messages.append({"role": msg.role, "content": msg.content})
        return response_messages

    def parse_tool_call(self, tool_call: ToolCall) -> ResponseFunctionToolCallParam:
        """Parse the tool call from the LLM response."""
        return ResponseFunctionToolCallParam(
            call_id=tool_call.call_id,
            name=tool_call.name,
            arguments=json.dumps(tool_call.arguments),
            type="function_call",
        )

    def parse_tool_call_result(self, tool_call_result: ToolResult) -> FunctionCallOutput:
        """Parse the tool call result from the LLM response."""
        result: str = ""
        if tool_call_result.result:
            result = result + tool_call_result.result + "\n"
        if tool_call_result.error:
            result += "Tool call failed with error:\n"
            result += tool_call_result.error
        result = result.strip()

        return FunctionCallOutput(
            call_id=tool_call_result.call_id,
            output=result,
            type="function_call_output",
        )


class LLMTRClient(BaseLLMClient):
    """LLMTR client that routes each model to the endpoint family it supports."""

    def __init__(self, model_config: ModelConfig):
        if (
            model_config.model_provider.base_url is None
            or model_config.model_provider.base_url == ""
        ):
            model_config.model_provider.base_url = LLMTR_BASE_URL
        super().__init__(model_config)

        self.catalog: LLMTRModelCatalog = LLMTRModelCatalog(self.api_key, self.base_url)
        self.route: LLMTRRoute = self._resolve_route(model_config.model)
        if self.route is LLMTRRoute.UNSUPPORTED:
            raise ValueError(self._unsupported_model_message(model_config.model))

        self.client: BaseLLMClient = self._build_client(self.route, model_config)
        self._seeded_history: list[LLMMessage] | None = None
        self._completed_exchanges: int = 0

    def _resolve_route(self, model: str) -> LLMTRRoute:
        """Resolve the endpoint family, refreshing the catalogue once for unknown models."""
        route = self.catalog.route_for(model)
        if self.catalog.supported_endpoints(model) is None:
            # The model is missing from the cached catalogue - it may have been
            # added since the cache was written. Re-fetch before deciding.
            self.catalog.refresh()
            route = self.catalog.route_for(model)
        return route

    def _build_client(self, route: LLMTRRoute, model_config: ModelConfig) -> BaseLLMClient:
        if route is LLMTRRoute.RESPONSES:
            return LLMTRResponsesClient(model_config)
        return LLMTRChatCompletionsClient(model_config)

    def _unsupported_model_message(self, model: str) -> str:
        endpoints = self.catalog.supported_endpoints(model) or []
        owner = normalise_model_name(model).split("/", 1)[0]
        suggestions = self.catalog.chat_capable_models(owner_prefix=owner)[:5]
        message = (
            f"LLMTR model '{model}' cannot be used for chat: it only supports "
            f"{', '.join(endpoints) or 'no chat endpoint'}. "
            f"Trae Agent needs a model served over {CHAT_COMPLETIONS_ENDPOINT} "
            f"or {RESPONSES_ENDPOINT}."
        )
        if suggestions:
            message += f" Chat-capable '{owner}' models include: {', '.join(suggestions)}."
        return message

    @override
    def set_trajectory_recorder(self, recorder) -> None:
        """Set the trajectory recorder for this client and the delegate."""
        super().set_trajectory_recorder(recorder)
        self.client.set_trajectory_recorder(recorder)

    @override
    def set_chat_history(self, messages: list[LLMMessage]) -> None:
        """Set the chat history."""
        self._seeded_history = list(messages)
        self.client.set_chat_history(messages)

    @override
    def chat(
        self,
        messages: list[LLMMessage],
        model_config: ModelConfig,
        tools: list[Tool] | None = None,
        reuse_history: bool = True,
    ) -> LLMResponse:
        """Send chat messages, switching endpoint families if the gateway asks for it."""
        try:
            response = self.client.chat(messages, model_config, tools, reuse_history)
        except Exception as e:
            if not self._can_switch_to_responses(e):
                raise
            self._switch_to_responses(model_config)
            response = self.client.chat(messages, model_config, tools, reuse_history)

        self._completed_exchanges += 1
        return response

    def _can_switch_to_responses(self, error: Exception) -> bool:
        """Detect the gateway's `endpoint_mismatch` error on the first exchange."""
        if self.route is not LLMTRRoute.CHAT_COMPLETIONS or self._completed_exchanges > 0:
            return False
        return "endpoint_mismatch" in str(error) or RESPONSES_ENDPOINT in str(error)

    def _switch_to_responses(self, model_config: ModelConfig) -> None:
        """Rebuild the delegate against the Responses API, preserving seeded history."""
        self.catalog.refresh()
        self.route = LLMTRRoute.RESPONSES
        self.client = LLMTRResponsesClient(model_config)
        self.client.set_trajectory_recorder(self.trajectory_recorder)
        if self._seeded_history is not None:
            self.client.set_chat_history(self._seeded_history)

    @override
    def supports_tool_calling(self, model_config: ModelConfig) -> bool:
        """Check if the current model supports tool calling."""
        return self.client.supports_tool_calling(model_config)
