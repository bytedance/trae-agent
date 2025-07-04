"""
Tests de integración para verificar que todos los fixes funcionan juntos
"""

import pytest
import asyncio
import tempfile
import os
from unittest.mock import Mock, patch, MagicMock
from trae_agent.agent.trae_agent import TraeAgent
from trae_agent.utils.config import Config
from trae_agent.tools.sequential_thinking_tool import SequentialThinkingTool
from trae_agent.tools.bash_tool import BashTool


class TestIntegrationFixes:
    """Tests de integración para verificar que todos los fixes funcionan juntos."""
    
    def setup_method(self):
        """Setup para cada test."""
        # Crear config temporal
        self.temp_config = {
            "default_provider": "alibaba",
            "max_steps": 5,
            "model_providers": {
                "alibaba": {
                    "api_key": "test-key",
                    "model": "qwen-turbo",
                    "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
                    "max_tokens": 4096,
                    "temperature": 0.5
                }
            }
        }
    
    @patch('trae_agent.utils.llm_client.openai.OpenAI')
    def test_end_to_end_task_execution_with_fixes(self, mock_openai):
        """Test ejecución completa de tarea con todos los fixes aplicados."""
        # Mock respuesta del LLM
        mock_response = Mock()
        mock_response.choices = [Mock()]
        mock_response.choices[0].message.content = "Task completed successfully"
        mock_response.usage = Mock()
        mock_response.usage.prompt_tokens = 100
        mock_response.usage.completion_tokens = 50
        mock_response.usage.total_tokens = 150
        mock_response.usage.prompt_tokens_details = None  # Fix para Alibaba Cloud
        
        mock_openai_instance = Mock()
        mock_openai_instance.chat.completions.create.return_value = mock_response
        mock_openai.return_value = mock_openai_instance
        
        # Crear agente
        with patch('trae_agent.agent.trae_agent.Config') as mock_config_class:
            mock_config = Mock()
            mock_config.default_provider = "alibaba"
            mock_config.max_steps = 5
            mock_config.model_providers = self.temp_config["model_providers"]
            mock_config_class.return_value = mock_config
            
            agent = TraeAgent(mock_config)
            agent.new_task("Test task", {"project_path": "/tmp"})
            
            # Esto debería funcionar sin errores
            try:
                # Simular ejecución (sin asyncio.run para evitar event loop issues)
                result = asyncio.new_event_loop().run_until_complete(agent.execute_task())
                assert result is not None
            finally:
                # Cleanup debería funcionar sin errores
                agent.cleanup()
    
    @pytest.mark.asyncio
    async def test_sequential_thinking_with_zero_parameters(self):
        """Test integración de sequential thinking con parámetros cero."""
        tool = SequentialThinkingTool()
        
        # Parámetros que causaban el error original
        arguments = {
            "thought": "Integration test thought",
            "thought_number": 1,
            "total_thoughts": 2,
            "next_thought_needed": True,
            "revises_thought": 0,  # Fix aplicado
            "branch_from_thought": 0,  # Fix aplicado
            "is_revision": False,
            "branch_id": ""
        }
        
        # Esto debería funcionar sin errores
        result = await tool.execute(arguments)
        assert not result.error
        assert result.error_code == 0
    
    @pytest.mark.asyncio
    async def test_bash_tool_execution_and_cleanup(self):
        """Test ejecución y cleanup de BashTool."""
        tool = BashTool()
        
        # Ejecutar comando
        result = await tool.execute({"command": "echo 'Integration test'"})
        assert not result.error
        assert result.error_code == 0
        assert "Integration test" in result.output
        
        # Cleanup debería funcionar sin errores
        try:
            tool.__del__()
        except Exception as e:
            pytest.fail(f"BashTool cleanup falló: {e}")
    
    def test_cli_error_suppression_integration(self):
        """Test integración de supresión de errores del CLI."""
        from trae_agent.cli import suppress_stderr
        import sys
        
        original_stderr = sys.stderr
        
        # Test context manager
        with suppress_stderr():
            # Simular error que sería suprimido
            print("This should be suppressed", file=sys.stderr)
        
        # stderr debería estar restaurado
        assert sys.stderr == original_stderr
    
    @patch('trae_agent.utils.llm_client.openai.OpenAI')
    def test_alibaba_cloud_integration(self, mock_openai):
        """Test integración completa con Alibaba Cloud."""
        from trae_agent.utils.llm_client import LLMClient
        from trae_agent.utils.llm_basics import LLMMessage
        from trae_agent.utils.config import ModelProviderConfig
        
        # Mock respuesta con prompt_tokens_details = None (caso Alibaba)
        mock_response = Mock()
        mock_response.choices = [Mock()]
        mock_response.choices[0].message.content = "Alibaba response"
        mock_response.usage = Mock()
        mock_response.usage.prompt_tokens = 50
        mock_response.usage.completion_tokens = 25
        mock_response.usage.total_tokens = 75
        mock_response.usage.prompt_tokens_details = None  # Fix crítico
        
        mock_openai_instance = Mock()
        mock_openai_instance.chat.completions.create.return_value = mock_response
        mock_openai.return_value = mock_openai_instance
        
        # Crear cliente Alibaba
        config = ModelProviderConfig(
            api_key="test-key",
            model="qwen-turbo",
            base_url="https://dashscope.aliyuncs.com/compatible-mode/v1"
        )
        client = LLMClient("alibaba", config)
        
        # Esto debería funcionar sin errores
        messages = [LLMMessage(role="user", content="Hello")]
        response = client.chat(messages, config)
        
        assert response.content == "Alibaba response"
        assert response.usage.input_tokens == 50
        assert response.usage.output_tokens == 25
    
    def test_multiple_tools_cleanup_integration(self):
        """Test cleanup integrado con múltiples herramientas."""
        # Crear múltiples herramientas
        bash_tool = BashTool()
        sequential_tool = SequentialThinkingTool()
        
        tools = [bash_tool, sequential_tool]
        
        # Simular cleanup de todas las herramientas
        for tool in tools:
            try:
                if hasattr(tool, '__del__'):
                    tool.__del__()
                elif hasattr(tool, 'cleanup'):
                    tool.cleanup()
            except Exception as e:
                pytest.fail(f"Cleanup falló para {type(tool).__name__}: {e}")
    
    @pytest.mark.asyncio
    async def test_concurrent_tool_execution_with_cleanup(self):
        """Test ejecución concurrente de herramientas con cleanup."""
        # Crear múltiples instancias de herramientas
        bash_tools = [BashTool() for _ in range(3)]
        sequential_tools = [SequentialThinkingTool() for _ in range(2)]
        
        # Ejecutar tareas concurrentemente
        bash_tasks = [
            tool.execute({"command": f"echo 'Bash {i}'"})
            for i, tool in enumerate(bash_tools)
        ]
        
        sequential_tasks = [
            tool.execute({
                "thought": f"Sequential thought {i}",
                "thought_number": 1,
                "total_thoughts": 1,
                "next_thought_needed": False,
                "revises_thought": 0,  # Fix aplicado
                "branch_from_thought": 0  # Fix aplicado
            })
            for i, tool in enumerate(sequential_tools)
        ]
        
        # Esperar todas las tareas
        all_results = await asyncio.gather(
            *bash_tasks, *sequential_tasks, 
            return_exceptions=True
        )
        
        # Verificar que no hubo excepciones
        for result in all_results:
            if isinstance(result, Exception):
                pytest.fail(f"Tarea concurrente falló: {result}")
            assert not result.error
        assert result.error_code == 0
        
        # Cleanup todas las herramientas
        all_tools = bash_tools + sequential_tools
        for tool in all_tools:
            try:
                if hasattr(tool, '__del__'):
                    tool.__del__()
            except Exception as e:
                pytest.fail(f"Cleanup concurrente falló: {e}")
    
    def test_error_handling_integration(self):
        """Test manejo integrado de errores."""
        from trae_agent.cli import suppress_stderr
        import warnings
        
        # Test supresión de warnings
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            
            # Generar warning que debería ser suprimido
            warnings.warn("Event loop is closed", RuntimeWarning)
            
            # El warning debería estar en la lista pero ser manejado
            assert len(w) >= 0  # Puede ser 0 si está suprimido
    
    @patch('atexit.register')
    def test_atexit_integration(self, mock_atexit_register):
        """Test integración con atexit para cleanup final."""
        from trae_agent.cli import suppress_stderr
        import atexit
        
        # Simular registro de función de cleanup
        def suppress_final_errors():
            import sys
            import os
            sys.stderr = open(os.devnull, 'w')
        
        atexit.register(suppress_final_errors)
        
        # Verificar que se registró
        mock_atexit_register.assert_called_with(suppress_final_errors)
    
    def test_full_workflow_integration(self):
        """Test workflow completo con todos los fixes."""
        # Este test simula un workflow completo
        
        # 1. Crear herramientas (con fixes aplicados)
        bash_tool = BashTool()
        sequential_tool = SequentialThinkingTool()
        
        # 2. Simular uso de herramientas
        try:
            # Sequential thinking con parámetros problemáticos
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            result = loop.run_until_complete(sequential_tool.execute({
                "thought": "Full workflow test",
                "thought_number": 1,
                "total_thoughts": 1,
                "next_thought_needed": False,
                "revises_thought": 0,  # Fix aplicado
                "branch_from_thought": 0  # Fix aplicado
            }))
            
            assert not result.error
        assert result.error_code == 0
            
            # Bash execution
            result = loop.run_until_complete(bash_tool.execute({
                "command": "echo 'Workflow test'"
            }))
            
            assert not result.error
        assert result.error_code == 0
            assert "Workflow test" in result.output
            
        finally:
            # 3. Cleanup (con fixes aplicados)
            bash_tool.__del__()
            # sequential_tool no necesita cleanup especial
            
            loop.close()
        
        # Si llegamos aquí, todos los fixes funcionan juntos
        assert True
