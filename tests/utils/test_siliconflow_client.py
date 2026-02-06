# Copyright (c) 2025 ByteDance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

import pytest
from unittest.mock import Mock, patch

from trae_agent.utils.config import ModelParameters
from trae_agent.utils.siliconflow_client import SiliconFlowClient
from trae_agent.utils.models.siliconflow import SiliconFlowProvider


class TestSiliconFlowClient:
    """Test cases for SiliconFlowClient."""

    def test_siliconflow_client_init(self):
        """Test SiliconFlowClient initialization."""
        model_params = ModelParameters(
            api_key="test_key",
            base_url="https://api.siliconflow.cn/v1",
            model="deepseek-v3",
            max_tokens=8192,
            temperature=0.5,
            top_p=1.0,
            top_k=0,
            parallel_tool_calls=False,
            max_retries=10,
        )
        
        with patch('openai.OpenAI'):
            client = SiliconFlowClient(model_params)
            assert client is not None
            assert isinstance(client.provider_config, SiliconFlowProvider)

    def test_siliconflow_provider_config(self):
        """Test SiliconFlowProvider configuration."""
        provider = SiliconFlowProvider()
        
        assert provider.get_service_name() == "SiliconFlow"
        assert provider.get_provider_name() == "siliconflow"
        assert provider.get_extra_headers() == {}
        assert provider.supports_tool_calling("deepseek-v3") is True
        
        with patch('openai.OpenAI') as mock_openai:
            client = provider.create_client("test_key", "https://api.siliconflow.cn/v1", None)
            mock_openai.assert_called_once_with(
                base_url="https://api.siliconflow.cn/v1",
                api_key="test_key"
            )

    def test_siliconflow_supports_tool_calling(self):
        """Test that SiliconFlow supports tool calling."""
        model_params = ModelParameters(
            api_key="test_key",
            base_url="https://api.siliconflow.cn/v1",
            model="deepseek-v3",
            max_tokens=8192,
            temperature=0.5,
            top_p=1.0,
            top_k=0,
            parallel_tool_calls=False,
            max_retries=10,
        )
        
        with patch('openai.OpenAI'):
            client = SiliconFlowClient(model_params)
            assert client.supports_tool_calling(model_params) is True