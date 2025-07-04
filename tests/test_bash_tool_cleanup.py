"""
Tests para verificar el fix del Bash Tool cleanup
"""

import pytest
import asyncio
import time
from unittest.mock import Mock, patch
from trae_agent.tools.bash_tool import BashTool


class TestBashToolCleanup:
    """Tests para verificar que el cleanup del BashTool funciona correctamente."""
    
    def setup_method(self):
        """Setup para cada test."""
        self.tool = BashTool()
    
    @pytest.mark.asyncio
    async def test_simple_command_execution(self):
        """Test ejecución básica de comando."""
        result = await self.tool.execute({"command": "echo 'Hello World'"})
        
        assert not result.error
        assert result.error_code == 0
        assert "Hello World" in result.output
    
    @pytest.mark.asyncio
    async def test_command_with_cleanup(self):
        """Test que el comando se ejecuta y limpia correctamente."""
        # Ejecutar comando que crea proceso
        result = await self.tool.execute({"command": "sleep 0.1 && echo 'Done'"})
        
        assert not result.error
        assert result.error_code == 0
        assert "Done" in result.output
        
        # Verificar que el proceso se limpió
        if hasattr(self.tool, '_process') and self.tool._process:
            assert self.tool._process.returncode is not None
    
    @pytest.mark.asyncio
    async def test_long_running_command_cleanup(self):
        """Test cleanup de comando de larga duración."""
        # Comando que toma tiempo pero termina
        result = await self.tool.execute({
            "command": "for i in {1..3}; do echo $i; sleep 0.1; done"
        })
        
        assert not result.error
        assert result.error_code == 0
        assert "1" in result.output
        assert "3" in result.output
    
    def test_destructor_with_no_process(self):
        """Test que el destructor maneja correctamente cuando no hay proceso."""
        tool = BashTool()
        
        # Esto no debería causar error
        try:
            tool.__del__()
        except Exception as e:
            pytest.fail(f"Destructor falló sin proceso: {e}")
    
    def test_destructor_with_finished_process(self):
        """Test destructor con proceso ya terminado."""
        tool = BashTool()
        
        # Simular proceso terminado
        mock_process = Mock()
        mock_process.returncode = 0  # Proceso ya terminado
        tool._process = mock_process
        
        # Esto no debería causar error
        try:
            tool.__del__()
        except Exception as e:
            pytest.fail(f"Destructor falló con proceso terminado: {e}")
    
    @patch('os.kill')
    def test_destructor_with_running_process(self, mock_kill):
        """Test destructor con proceso corriendo."""
        tool = BashTool()
        
        # Simular proceso corriendo
        mock_process = Mock()
        mock_process.returncode = None  # Proceso corriendo
        mock_process.pid = 12345
        mock_process.terminate = Mock()
        tool._process = mock_process
        
        # Ejecutar destructor
        tool.__del__()
        
        # Verificar que se intentó terminar el proceso
        mock_process.terminate.assert_called_once()
    
    @patch('os.kill')
    def test_destructor_handles_exceptions(self, mock_kill):
        """Test que el destructor maneja excepciones gracefully."""
        tool = BashTool()
        
        # Simular proceso que causa excepción al terminar
        mock_process = Mock()
        mock_process.returncode = None
        mock_process.pid = 12345
        mock_process.terminate.side_effect = Exception("Process error")
        tool._process = mock_process
        
        # Esto no debería propagar la excepción
        try:
            tool.__del__()
        except Exception as e:
            pytest.fail(f"Destructor no manejó excepción: {e}")
    
    @pytest.mark.asyncio
    async def test_multiple_commands_cleanup(self):
        """Test cleanup con múltiples comandos."""
        tool1 = BashTool()
        tool2 = BashTool()
        
        # Ejecutar comandos en paralelo
        results = await asyncio.gather(
            tool1.execute({"command": "echo 'Tool 1'"}),
            tool2.execute({"command": "echo 'Tool 2'"})
        )
        
        assert all(r.success for r in results)
        assert "Tool 1" in results[0].output
        assert "Tool 2" in results[1].output
        
        # Cleanup manual
        tool1.__del__()
        tool2.__del__()
    
    @pytest.mark.asyncio
    async def test_error_command_cleanup(self):
        """Test cleanup cuando comando falla."""
        result = await self.tool.execute({"command": "exit 1"})
        
        # El comando falló pero el tool debería manejar cleanup
        assert result.error is not None or result.error_code != 0
        
        # Verificar que cleanup funciona incluso con error
        try:
            self.tool.__del__()
        except Exception as e:
            pytest.fail(f"Cleanup falló después de error: {e}")
    
    def test_cleanup_method_exists(self):
        """Test que el método cleanup existe y es callable."""
        tool = BashTool()
        
        assert hasattr(tool, '__del__')
        assert callable(getattr(tool, '__del__'))
    
    @pytest.mark.asyncio
    async def test_concurrent_execution_cleanup(self):
        """Test cleanup con ejecución concurrente."""
        tools = [BashTool() for _ in range(3)]
        
        # Ejecutar comandos concurrentemente
        tasks = [
            tool.execute({"command": f"echo 'Concurrent {i}'"}) 
            for i, tool in enumerate(tools)
        ]
        
        results = await asyncio.gather(*tasks)
        
        # Verificar resultados
        for i, result in enumerate(results):
            assert not result.error
            assert result.error_code == 0
            assert f"Concurrent {i}" in result.output
        
        # Cleanup todos los tools
        for tool in tools:
            try:
                tool.__del__()
            except Exception as e:
                pytest.fail(f"Cleanup concurrente falló: {e}")
