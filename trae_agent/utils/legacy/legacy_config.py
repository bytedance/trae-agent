# Copyright (c) 2025 ByteDance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

# TODO: remove these annotations by defining fine-grained types
# pyright: reportAny=false
# pyright: reportUnannotatedClassAttribute=false
# pyright: reportUnknownMemberType=false
# pyright: reportUnknownArgumentType=false
# pyright: reportUnknownVariableType=false

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, override


# data class for model parameters
@dataclass
class ModelParameters:
    """Model parameters for a model provider."""

    model: str
    api_key: str
    max_tokens: int
    temperature: float
    top_p: float
    top_k: int
    parallel_tool_calls: bool
    max_retries: int
    base_url: str | None = None
    api_version: str | None = None
    candidate_count: int | None = None  # Gemini specific field
    stop_sequences: list[str] | None = None


@dataclass
class LakeviewConfig:
    """Configuration for Lakeview."""

    model_provider: str
    model_name: str


@dataclass
class MCPServerConfig:
    # For stdio transport
    command: str | None = None
    args: list[str] | None = None
    env: dict[str, str] | None = None
    cwd: str | None = None

    # For sse transport
    url: str | None = None

    # For streamable http transport
    http_url: str | None = None
    headers: dict[str, str] | None = None

    # For websocket transport
    tcp: str | None = None

    # Common
    timeout: int | None = None
    trust: bool | None = None

    # Metadata
    description: str | None = None


@dataclass
class LegacyConfig:
    """Configuration manager for Trae Agent."""

    default_provider: str
    max_steps: int
    model_providers: dict[str, ModelParameters]
    mcp_servers: dict[str, MCPServerConfig]
    lakeview_config: LakeviewConfig | None = None
    enable_lakeview: bool = True
    allow_mcp_servers: list[str] = field(default_factory=list)

    def __init__(self, config_or_config_file: str | dict = "trae_config.json"):  # pyright: ignore[reportMissingTypeArgument, reportUnknownParameterType]
        # Accept either file path or direct config dict
        if isinstance(config_or_config_file, dict):
            self._config = config_or_config_file
        else:
            config_path = Path(config_or_config_file)
            if config_path.exists():
                try:
                    with open(config_path, "r") as f:
                        self._config = json.load(f)
                except Exception as e:
                    print(f"Warning: Could not load config file {config_or_config_file}: {e}")
                    self._config = {}
            else:
                self._config = {}

        self.default_provider = self._config.get("default_provider", "anthropic")
        self.max_steps = self._config.get("max_steps", 20)
        self.model_providers = {}
        self.enable_lakeview = self._config.get("enable_lakeview", True)
        self.mcp_servers = {
            k: MCPServerConfig(**v) for k, v in self._config.get("mcp_servers", {}).items()
        }
        self.allow_mcp_servers = self._config.get("allow_mcp_servers", [])

        if len(self._config.get("model_providers", [])) == 0:
            self.model_providers = {
                "anthropic": ModelParameters(
                    model="claude-sonnet-4-20250514",
                    api_key="",
                    base_url="https://api.anthropic.com",
                    max_tokens=4096,
                    temperature=0.5,
                    top_p=1,
                    top_k=0,
                    parallel_tool_calls=False,
                    max_retries=10,
                ),
            }
        else:
            for provider in self._config.get("model_providers", {}):
                provider_config: dict[str, Any] = self._config.get("model_providers", {}).get(
                    provider, {}
                )

                candidate_count = provider_config.get("candidate_count")
                self.model_providers[provider] = ModelParameters(
                    model=str(provider_config.get("model", "")),
                    api_key=str(provider_config.get("api_key", "")),
                    base_url=str(provider_config.get("base_url"))
                    if "base_url" in provider_config
                    else None,
                    max_tokens=int(provider_config.get("max_tokens", 1000)),
                    temperature=float(provider_config.get("temperature", 0.5)),
                    top_p=float(provider_config.get("top_p", 1)),
                    top_k=int(provider_config.get("top_k", 0)),
                    max_retries=int(provider_config.get("max_retries", 10)),
                    parallel_tool_calls=bool(provider_config.get("parallel_tool_calls", False)),
                    api_version=str(provider_config.get("api_version"))
                    if "api_version" in provider_config
                    else None,
                    candidate_count=int(candidate_count) if candidate_count is not None else None,
                    stop_sequences=provider_config.get("stop_sequences")
                    if "stop_sequences" in provider_config
                    else None,
                )

        # Configure lakeview_config - default to using default_provider settings
        lakeview_config_data = self._config.get("lakeview_config", {})
        if self.enable_lakeview:
            model_provider = lakeview_config_data.get("model_provider", None)
            model_name = lakeview_config_data.get("model_name", None)

            if model_provider is None:
                model_provider = self.default_provider

            if model_name is None:
                model_name = self.model_providers[model_provider].model

            self.lakeview_config = LakeviewConfig(
                model_provider=str(model_provider),
                model_name=str(model_name),
            )

        return

    @override
    def __str__(self) -> str:
        return f"Config(default_provider={self.default_provider}, max_steps={self.max_steps}, model_providers={self.model_providers})"
