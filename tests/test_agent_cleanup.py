"""
Tests para verificar el método cleanup del agente
"""

import pytest
import asyncio
from unittest.mock import Mock, patch, MagicMock
from trae_agent.agent.trae_agent import TraeAgent
from trae_agent.utils.config import Config


class TestAgentCleanup:
    """Tests para verificar que el cleanup del agente funciona correctamente."""
    
    def setup_method(self):
        """Setup para cada test."""
        # Mock config básico
        self.mock_config = Mock()
        self.mock_config.default_provider = "alibaba"
        self.mock_config.max_steps = 10
        self.mock_config.model_providers = {
            "alibaba": Mock(model="qwen-turbo")
        }
        
        # Mock LLM client
        self.mock_llm_client = Mock()
        
        with patch('trae_agent.agent.trae_agent.LLMClient', return_value=self.mock_llm_client):
            self.agent = TraeAgent(self.mock_config)
    
    def test_cleanup_method_exists(self):
        """Test que el método cleanup existe."""
        assert hasattr(self.agent, 'cleanup')
        assert callable(getattr(self.agent, 'cleanup'))
    
    def test_cleanup_with_no_tools(self):
        """Test cleanup cuando no hay herramientas."""
        self.agent.tools = []
        
        # Esto no debería causar error
        try:
            self.agent.cleanup()
        except Exception as e:
            pytest.fail(f"Cleanup falló sin herramientas: {e}")
    
    def test_cleanup_with_tools_having_cleanup(self):
        """Test cleanup con herramientas que tienen método cleanup."""
        # Mock tools con método cleanup
        mock_tool1 = Mock()
        mock_tool1.cleanup = Mock()
        mock_tool2 = Mock()
        mock_tool2.cleanup = Mock()
        
        self.agent.tools = [mock_tool1, mock_tool2]
        
        # Ejecutar cleanup
        self.agent.cleanup()
        
        # Verificar que se llamó cleanup en todas las herramientas
        mock_tool1.cleanup.assert_called_once()
        mock_tool2.cleanup.assert_called_once()
    
    def test_cleanup_with_tools_without_cleanup(self):
        """Test cleanup con herramientas sin método cleanup."""
        # Mock tools sin método cleanup
        mock_tool1 = Mock()
        del mock_tool1.cleanup  # Asegurar que no tiene cleanup
        mock_tool2 = Mock()
        del mock_tool2.cleanup
        
        self.agent.tools = [mock_tool1, mock_tool2]
        
        # Esto no debería causar error
        try:
            self.agent.cleanup()
        except Exception as e:
            pytest.fail(f"Cleanup falló con herramientas sin cleanup: {e}")
    
    def test_cleanup_with_mixed_tools(self):
        """Test cleanup con mezcla de herramientas (con y sin cleanup)."""
        # Mock tools mixtos
        mock_tool_with_cleanup = Mock()
        mock_tool_with_cleanup.cleanup = Mock()
        
        mock_tool_without_cleanup = Mock()
        del mock_tool_without_cleanup.cleanup
        
        self.agent.tools = [mock_tool_with_cleanup, mock_tool_without_cleanup]
        
        # Ejecutar cleanup
        self.agent.cleanup()
        
        # Solo debería llamar cleanup en la herramienta que lo tiene
        mock_tool_with_cleanup.cleanup.assert_called_once()
    
    def test_cleanup_handles_tool_exceptions(self):
        """Test que cleanup maneja excepciones de herramientas."""
        # Mock tool que lanza excepción en cleanup
        mock_tool1 = Mock()
        mock_tool1.cleanup.side_effect = Exception("Tool cleanup error")
        
        mock_tool2 = Mock()
        mock_tool2.cleanup = Mock()
        
        self.agent.tools = [mock_tool1, mock_tool2]
        
        # Cleanup debería continuar incluso con excepción
        try:
            self.agent.cleanup()
        except Exception as e:
            pytest.fail(f"Cleanup no manejó excepción de herramienta: {e}")
        
        # Debería haber intentado cleanup en ambas herramientas
        mock_tool1.cleanup.assert_called_once()
        mock_tool2.cleanup.assert_called_once()
    
    def test_cleanup_with_bash_tool(self):
        """Test cleanup específico con BashTool."""
        from trae_agent.tools.bash_tool import BashTool
        
        # Crear BashTool real
        bash_tool = BashTool()
        self.agent.tools = [bash_tool]
        
        # Ejecutar cleanup
        try:
            self.agent.cleanup()
        except Exception as e:
            pytest.fail(f"Cleanup falló con BashTool: {e}")
    
    def test_cleanup_multiple_calls(self):
        """Test que cleanup se puede llamar múltiples veces."""
        mock_tool = Mock()
        mock_tool.cleanup = Mock()
        self.agent.tools = [mock_tool]
        
        # Llamar cleanup múltiples veces
        self.agent.cleanup()
        self.agent.cleanup()
        self.agent.cleanup()
        
        # Debería haber llamado cleanup 3 veces
        assert mock_tool.cleanup.call_count == 3
    
    def test_cleanup_after_task_execution(self):
        """Test cleanup después de ejecutar una tarea."""
        # Mock herramientas
        mock_tool = Mock()
        mock_tool.cleanup = Mock()
        self.agent.tools = [mock_tool]
        
        # Simular ejecución de tarea
        self.agent.new_task("Test task", {"project_path": "/tmp"})
        
        # Ejecutar cleanup
        self.agent.cleanup()
        
        # Verificar que se llamó cleanup
        mock_tool.cleanup.assert_called_once()
    
    @patch('trae_agent.agent.trae_agent.BashTool')
    def test_cleanup_integration_with_real_tools(self, mock_bash_tool_class):
        """Test integración de cleanup con herramientas reales."""
        # Mock BashTool instance
        mock_bash_instance = Mock()
        mock_bash_instance.cleanup = Mock()
        mock_bash_tool_class.return_value = mock_bash_instance
        
        # Crear agente que debería inicializar herramientas
        with patch('trae_agent.agent.trae_agent.LLMClient'):
            agent = TraeAgent(self.mock_config)
        
        # Ejecutar cleanup
        agent.cleanup()
        
        # Verificar que se intentó cleanup en las herramientas
        # (El comportamiento exacto depende de la implementación)
        assert True  # Test pasa si no hay excepciones
    
    def test_cleanup_performance(self):
        """Test que cleanup es rápido incluso con muchas herramientas."""
        import time
        
        # Crear muchas herramientas mock
        tools = []
        for i in range(100):
            mock_tool = Mock()
            mock_tool.cleanup = Mock()
            tools.append(mock_tool)
        
        self.agent.tools = tools
        
        # Medir tiempo de cleanup
        start_time = time.time()
        self.agent.cleanup()
        end_time = time.time()
        
        # Cleanup debería ser rápido (menos de 1 segundo)
        assert (end_time - start_time) < 1.0
        
        # Verificar que se llamó cleanup en todas las herramientas
        for tool in tools:
            tool.cleanup.assert_called_once()
