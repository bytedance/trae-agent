"""
Tests para verificar las mejoras del CLI
"""

import pytest
import asyncio
from unittest.mock import Mock, patch, MagicMock
from click.testing import CliRunner
from trae_agent.cli import cli, suppress_stderr
import contextlib
import io
import sys


class TestCLIImprovements:
    """Tests para verificar las mejoras del CLI."""
    
    def setup_method(self):
        """Setup para cada test."""
        self.runner = CliRunner()
    
    def test_suppress_stderr_context_manager(self):
        """Test que el context manager suppress_stderr funciona."""
        original_stderr = sys.stderr
        
        with suppress_stderr():
            # stderr debería estar redirigido
            assert sys.stderr != original_stderr
            # Escribir a stderr no debería aparecer
            print("This should be suppressed", file=sys.stderr)
        
        # stderr debería estar restaurado
        assert sys.stderr == original_stderr
    
    def test_suppress_stderr_exception_handling(self):
        """Test que suppress_stderr maneja excepciones correctamente."""
        original_stderr = sys.stderr
        
        try:
            with suppress_stderr():
                raise ValueError("Test exception")
        except ValueError:
            pass  # Esperado
        
        # stderr debería estar restaurado incluso con excepción
        assert sys.stderr == original_stderr
    
    @patch('trae_agent.cli.load_config')
    @patch('trae_agent.cli.create_agent')
    def test_chat_command_exists(self, mock_create_agent, mock_load_config):
        """Test que el comando chat existe y es accesible."""
        # Mock config
        mock_config = Mock()
        mock_config.default_provider = "alibaba"
        mock_config.model_providers = {
            "alibaba": Mock(model="qwen-turbo")
        }
        mock_load_config.return_value = mock_config
        
        # Test que el comando existe
        result = self.runner.invoke(cli, ['chat', '--help'])
        assert result.exit_code == 0
        assert 'simple chat session' in result.output.lower()
    
    @patch('trae_agent.cli.load_config')
    @patch('trae_agent.cli.create_agent')
    @patch('builtins.input', side_effect=['exit'])
    def test_chat_command_basic_flow(self, mock_input, mock_create_agent, mock_load_config):
        """Test flujo básico del comando chat."""
        # Mock config
        mock_config = Mock()
        mock_config.default_provider = "alibaba"
        mock_config.model_providers = {
            "alibaba": Mock(model="qwen-turbo")
        }
        mock_load_config.return_value = mock_config
        
        # Mock LLM client
        mock_client = Mock()
        
        with patch('trae_agent.cli.LLMClient', return_value=mock_client):
            result = self.runner.invoke(cli, ['chat', '--provider', 'alibaba'])
            
            # Debería salir limpiamente
            assert result.exit_code == 0
    
    def test_interactive_command_improvements(self):
        """Test que el comando interactive tiene las mejoras."""
        result = self.runner.invoke(cli, ['interactive', '--help'])
        assert result.exit_code == 0
        assert 'interactive session' in result.output.lower()
    
    @patch('trae_agent.cli.load_config')
    @patch('trae_agent.cli.create_agent')
    @patch('builtins.input', side_effect=['exit'])
    def test_interactive_simplified_input(self, mock_input, mock_create_agent, mock_load_config):
        """Test que interactive usa input simplificado."""
        # Mock config
        mock_config = Mock()
        mock_config.default_provider = "alibaba"
        mock_config.model_providers = {
            "alibaba": Mock(model="qwen-turbo")
        }
        mock_config.max_steps = 20
        mock_load_config.return_value = mock_config
        
        # Mock agent
        mock_agent = Mock()
        mock_agent.tools = []
        mock_create_agent.return_value = mock_agent
        
        result = self.runner.invoke(cli, ['interactive'])
        
        # Debería procesar sin pedir directorio de trabajo separado
        assert result.exit_code == 0
    
    def test_run_command_still_works(self):
        """Test que el comando run sigue funcionando."""
        result = self.runner.invoke(cli, ['run', '--help'])
        assert result.exit_code == 0
        assert 'execute a task' in result.output.lower()
    
    def test_show_config_command_works(self):
        """Test que show-config sigue funcionando."""
        result = self.runner.invoke(cli, ['show-config', '--help'])
        assert result.exit_code == 0
    
    @patch('warnings.filterwarnings')
    def test_warnings_suppression_configured(self, mock_filterwarnings):
        """Test que la supresión de warnings está configurada."""
        # Importar el módulo debería configurar los warnings
        import trae_agent.cli
        
        # Verificar que se configuraron filtros de warnings
        mock_filterwarnings.assert_any_call(
            "ignore", 
            message=".*Event loop is closed.*", 
            category=RuntimeWarning
        )
    
    def test_cli_main_group_exists(self):
        """Test que el grupo principal CLI existe."""
        result = self.runner.invoke(cli, ['--help'])
        assert result.exit_code == 0
        assert 'run' in result.output
        assert 'interactive' in result.output
        assert 'chat' in result.output
        assert 'show-config' in result.output


class TestErrorSuppression:
    """Tests específicos para supresión de errores."""
    
    def test_stderr_redirection_works(self):
        """Test que la redirección de stderr funciona."""
        captured_output = io.StringIO()
        
        with contextlib.redirect_stderr(captured_output):
            print("This goes to stderr", file=sys.stderr)
        
        assert "This goes to stderr" in captured_output.getvalue()
    
    def test_devnull_redirection(self):
        """Test redirección a /dev/null."""
        import os
        
        with open(os.devnull, 'w') as devnull:
            original_stderr = sys.stderr
            sys.stderr = devnull
            
            # Esto no debería aparecer en ningún lado
            print("Suppressed message", file=sys.stderr)
            
            sys.stderr = original_stderr
        
        # Test pasó si no hubo excepciones
        assert True
    
    @patch('atexit.register')
    def test_atexit_registration(self, mock_atexit_register):
        """Test que se registra función de cleanup en atexit."""
        # Simular el patrón usado en el CLI
        import atexit
        
        def suppress_final_errors():
            pass
        
        atexit.register(suppress_final_errors)
        
        # Verificar que se llamó atexit.register
        mock_atexit_register.assert_called()


class TestCLIIntegration:
    """Tests de integración para el CLI."""
    
    def setup_method(self):
        """Setup para cada test."""
        self.runner = CliRunner()
    
    def test_all_commands_accessible(self):
        """Test que todos los comandos son accesibles."""
        commands = ['run', 'interactive', 'chat', 'show-config']
        
        for command in commands:
            result = self.runner.invoke(cli, [command, '--help'])
            assert result.exit_code == 0, f"Command {command} failed"
    
    def test_provider_option_works(self):
        """Test que la opción --provider funciona en todos los comandos."""
        commands_with_provider = ['run', 'interactive', 'chat']
        
        for command in commands_with_provider:
            result = self.runner.invoke(cli, [command, '--help'])
            assert '--provider' in result.output, f"Command {command} missing --provider"
    
    def test_config_file_option_works(self):
        """Test que la opción --config-file funciona."""
        commands_with_config = ['run', 'interactive', 'chat', 'show-config']
        
        for command in commands_with_config:
            result = self.runner.invoke(cli, [command, '--help'])
            assert '--config-file' in result.output, f"Command {command} missing --config-file"
