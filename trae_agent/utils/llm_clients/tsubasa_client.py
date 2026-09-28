# SPDX-License-Identifier: MIT

"""Tsubasa configuration for the shared chat-completions client."""

import openai

from trae_agent.utils.config import ModelConfig
from trae_agent.utils.llm_clients.openai_compatible_base import (
    OpenAICompatibleClient,
    ProviderConfig,
)


class TsubasaProvider(ProviderConfig):
    def create_client(
        self, api_key: str, base_url: str | None, api_version: str | None
    ) -> openai.OpenAI:
        return openai.OpenAI(api_key=api_key, base_url=base_url)

    def get_service_name(self) -> str:
        return "Tsubasa"

    def get_provider_name(self) -> str:
        return "tsubasa"

    def get_extra_headers(self) -> dict[str, str]:
        return {}

    def supports_tool_calling(self, model_name: str) -> bool:
        return model_name in {"tsubasa-fast", "tsubasa-pro"}


class TsubasaClient(OpenAICompatibleClient):
    def __init__(self, model_config: ModelConfig):
        if not model_config.model_provider.base_url:
            model_config.model_provider.base_url = "https://api.tsubasa.sh/v1"
        super().__init__(model_config, TsubasaProvider())
