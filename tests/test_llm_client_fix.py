"""
Tests para verificar el fix del LLM Client con Alibaba Cloud
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from trae_agent.utils.llm_client import LLMClient
from trae_agent.utils.llm_basics import LLMMessage, LLMResponse, LLMUsage
from trae_agent.utils.config import ModelProviderConfig


class TestLLMClientFix:
    """Tests para verificar que el fix de PromptTokensDetails funciona correctamente."""
    
    def setup_method(self):
        """Setup para cada test."""
        self.config = ModelProviderConfig(
            api_key="test-key",
            model="qwen-turbo",
            base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
            max_tokens=4096,
            temperature=0.5
        )
        self.client = LLMClient("alibaba", self.config)
    
    @patch('openai.OpenAI')
    def test_chat_with_usage_prompt_tokens_details_none(self, mock_openai):
        """Test que el cliente maneja correctamente usage.prompt_tokens_details = None."""
        # Mock response con prompt_tokens_details = None
        mock_response = Mock()
        mock_response.choices = [Mock()]
        mock_response.choices[0].message.content = "Test response"
        mock_response.usage = Mock()
        mock_response.usage.prompt_tokens = 100
        mock_response.usage.completion_tokens = 50
        mock_response.usage.total_tokens = 150
        mock_response.usage.prompt_tokens_details = None  # Esto causaba el error
        
        mock_openai_instance = Mock()
        mock_openai_instance.chat.completions.create.return_value = mock_response
        mock_openai.return_value = mock_openai_instance
        
        messages = [LLMMessage(role="user", content="Hello")]
        
        # Esto no debería fallar
        response = self.client.chat(messages, self.config)
        
        assert isinstance(response, LLMResponse)
        assert response.content == "Test response"
        assert response.usage.input_tokens == 100
        assert response.usage.output_tokens == 50
        assert response.usage.total_tokens == 150
    
    @patch('openai.OpenAI')
    def test_chat_with_usage_prompt_tokens_details_present(self, mock_openai):
        """Test que el cliente maneja correctamente usage.prompt_tokens_details cuando está presente."""
        # Mock response con prompt_tokens_details presente
        mock_response = Mock()
        mock_response.choices = [Mock()]
        mock_response.choices[0].message.content = "Test response"
        mock_response.usage = Mock()
        mock_response.usage.prompt_tokens = 100
        mock_response.usage.completion_tokens = 50
        mock_response.usage.total_tokens = 150
        mock_response.usage.prompt_tokens_details = Mock()
        mock_response.usage.prompt_tokens_details.cached_tokens = 20
        
        mock_openai_instance = Mock()
        mock_openai_instance.chat.completions.create.return_value = mock_response
        mock_openai.return_value = mock_openai_instance
        
        messages = [LLMMessage(role="user", content="Hello")]
        
        response = self.client.chat(messages, self.config)
        
        assert isinstance(response, LLMResponse)
        assert response.content == "Test response"
        assert response.usage.input_tokens == 100
        assert response.usage.output_tokens == 50
    
    @patch('openai.OpenAI')
    def test_chat_without_usage(self, mock_openai):
        """Test que el cliente maneja correctamente respuestas sin usage."""
        mock_response = Mock()
        mock_response.choices = [Mock()]
        mock_response.choices[0].message.content = "Test response"
        mock_response.usage = None
        
        mock_openai_instance = Mock()
        mock_openai_instance.chat.completions.create.return_value = mock_response
        mock_openai.return_value = mock_openai_instance
        
        messages = [LLMMessage(role="user", content="Hello")]
        
        response = self.client.chat(messages, self.config)
        
        assert isinstance(response, LLMResponse)
        assert response.content == "Test response"
        assert response.usage is None
    
    def test_alibaba_client_initialization(self):
        """Test que el cliente de Alibaba se inicializa correctamente."""
        assert self.client.provider == "alibaba"
        assert self.client.config.model == "qwen-turbo"
        assert "aliyuncs.com" in self.client.config.base_url
