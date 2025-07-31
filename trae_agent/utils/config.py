# Copyright (c) 2025 ByteDance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

from dataclasses import dataclass, field

import yaml

from .legacy_config import LegacyConfig


class ConfigError(Exception):
    pass


@dataclass
class ModelProvider:
    """
    Model provider configuration. For official model providers such as OpenAI and Anthropic,
    the base_url is optional. api_version is required for Azure.
    """

    api_key: str
    provider: str
    base_url: str | None = None
    api_version: str | None = None


@dataclass
class ModelConfig:
    """
    Model configuration.
    """

    model: str
    model_provider: ModelProvider
    max_tokens: int
    temperature: float
    top_p: float
    top_k: int
    parallel_tool_calls: bool
    max_retries: int
    supports_tool_calling: bool = True
    candidate_count: int | None = None  # Gemini specific field
    stop_sequences: list[str] | None = None


@dataclass
class AgentConfig:
    """
    Base class for agent configurations.
    """

    max_steps: int
    model: ModelConfig
    tools: list[str]


@dataclass
class TraeAgentConfig(AgentConfig):
    """
    Trae agent configuration.
    """

    enable_lakeview: bool = True
    tools: list[str] = field(
        default_factory=lambda: [
            "bash",
            "str_replace_based_edit_tool",
            "sequentialthinking",
            "task_done",
        ]
    )


@dataclass
class LakeviewConfig:
    """
    Lakeview configuration.
    """

    model: ModelConfig


@dataclass
class Config:
    """
    Configuration class for agents, models and model providers.
    """

    lakeview: LakeviewConfig | None = None
    model_providers: dict[str, ModelProvider] | None = None
    models: dict[str, ModelConfig] | None = None

    trae_agent: TraeAgentConfig | None = None

    @classmethod
    def create(cls, config_file: str | None = None, config_string: str | None = None) -> "Config":
        if config_file and config_string:
            raise ConfigError("Only one of config_file or config_string should be provided")

        # Parse YAML config from file or string
        try:
            if config_file is not None:
                with open(config_file, "r") as f:
                    yaml_config = yaml.safe_load(f)
            elif config_string is not None:
                yaml_config = yaml.safe_load(config_string)
            else:
                raise ConfigError("No config file or config string provided")
        except yaml.YAMLError as e:
            raise ConfigError(f"Error parsing YAML config: {e}") from e

        config = cls()

        # Parse model providers
        model_providers = yaml_config.get("model_providers", None)
        if model_providers is not None and len(model_providers.keys()) > 0:
            config_model_providers = {}
            for model_provider_name, model_provider_config in model_providers.items():
                config_model_providers[model_provider_name] = ModelProvider(**model_provider_config)
            config.model_providers = config_model_providers
        else:
            raise ConfigError("No model providers provided")

        # Parse models and populate model_provider fields
        models = yaml_config.get("models", None)
        if models is not None and len(models.keys()) > 0:
            config_models: dict[str, ModelConfig] = {}
            for model_name, model_config in models.items():
                if model_config["model_provider"] not in config_model_providers:
                    raise ConfigError(f"Model provider {model_config['model_provider']} not found")
                config_models[model_name] = ModelConfig(**model_config)
                config_models[model_name].model_provider = model_providers[
                    model_config["model_provider"]
                ]
            config.models = config_models
        else:
            raise ConfigError("No models provided")

        # Parse lakeview config
        lakeview = yaml_config.get("lakeview", None)
        if lakeview is not None:
            lakeview_model_name = lakeview.get("model", None)
            if lakeview_model_name is None:
                raise ConfigError("No model provided for lakeview")
            lakeview_model = config_models[lakeview_model_name]
            config.lakeview = LakeviewConfig(
                model=lakeview_model,
            )
        else:
            config.lakeview = None

        # Parse agents
        agents = yaml_config.get("agents", None)
        if agents is not None and len(agents.keys()) > 0:
            for agent_name, agent_config in agents.items():
                agent_model_name = agent_config.get("model", None)
                if agent_model_name is None:
                    raise ConfigError(f"No model provided for {agent_name}")
                try:
                    agent_model = config_models[agent_model_name]
                except KeyError as e:
                    raise ConfigError(f"Model {agent_model_name} not found") from e
                match agent_name:
                    case "trae_agent":
                        trae_agent_config = TraeAgentConfig(**agent_config)
                        trae_agent_config.model = agent_model
                        if trae_agent_config.enable_lakeview and config.lakeview is None:
                            raise ConfigError("Lakeview is enabled but no lakeview config provided")
                        config.trae_agent = trae_agent_config
                    case _:
                        raise ConfigError(f"Unknown agent: {agent_name}")
        else:
            raise ConfigError("No agent configs provided")
        return config

    @classmethod
    def from_legacy_config(cls, legacy_config: LegacyConfig) -> "Config":
        model_provider = ModelProvider(
            api_key=legacy_config.model_providers[legacy_config.default_provider].api_key,
            base_url=legacy_config.model_providers[legacy_config.default_provider].base_url,
            api_version=legacy_config.model_providers[legacy_config.default_provider].api_version,
            provider=legacy_config.default_provider,
        )

        model_config = ModelConfig(
            model=legacy_config.model_providers[legacy_config.default_provider].model,
            model_provider=model_provider,
            max_tokens=legacy_config.model_providers[legacy_config.default_provider].max_tokens,
            temperature=legacy_config.model_providers[legacy_config.default_provider].temperature,
            top_p=legacy_config.model_providers[legacy_config.default_provider].top_p,
            top_k=legacy_config.model_providers[legacy_config.default_provider].top_k,
            parallel_tool_calls=legacy_config.model_providers[
                legacy_config.default_provider
            ].parallel_tool_calls,
            max_retries=legacy_config.model_providers[legacy_config.default_provider].max_retries,
            candidate_count=legacy_config.model_providers[
                legacy_config.default_provider
            ].candidate_count,
            stop_sequences=legacy_config.model_providers[
                legacy_config.default_provider
            ].stop_sequences,
        )

        trae_agent_config = TraeAgentConfig(
            max_steps=legacy_config.max_steps,
            enable_lakeview=legacy_config.enable_lakeview,
            model=model_config,
        )

        if trae_agent_config.enable_lakeview:
            lakeview_config = LakeviewConfig(
                model=model_config,
            )
        else:
            lakeview_config = None

        return cls(
            trae_agent=trae_agent_config,
            lakeview=lakeview_config,
            model_providers={
                legacy_config.default_provider: model_provider,
            },
            models={
                "default_model": model_config,
            },
        )
