"""
Configuración de pytest para los tests de Trae Agent
"""

import pytest
import asyncio
import warnings
import sys
import os

# Agregar el directorio raíz al path para imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Suprimir warnings específicos durante tests
warnings.filterwarnings("ignore", message=".*Event loop is closed.*", category=RuntimeWarning)
warnings.filterwarnings("ignore", message=".*coroutine.*was never awaited.*", category=RuntimeWarning)


@pytest.fixture(scope="session")
def event_loop():
    """Crear event loop para toda la sesión de tests."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def mock_config():
    """Fixture para configuración mock."""
    from unittest.mock import Mock
    
    config = Mock()
    config.default_provider = "alibaba"
    config.max_steps = 10
    config.model_providers = {
        "alibaba": Mock(
            api_key="test-key",
            model="qwen-turbo",
            base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
            max_tokens=4096,
            temperature=0.5
        )
    }
    return config


@pytest.fixture
def mock_llm_response():
    """Fixture para respuesta mock del LLM."""
    from unittest.mock import Mock
    
    response = Mock()
    response.content = "Mock LLM response"
    response.usage = Mock()
    response.usage.input_tokens = 100
    response.usage.output_tokens = 50
    response.usage.total_tokens = 150
    return response


@pytest.fixture
def temp_directory():
    """Fixture para directorio temporal."""
    import tempfile
    import shutil
    
    temp_dir = tempfile.mkdtemp()
    yield temp_dir
    shutil.rmtree(temp_dir, ignore_errors=True)


def pytest_configure(config):
    """Configuración de pytest."""
    # Configurar markers personalizados
    config.addinivalue_line(
        "markers", "integration: marca tests de integración"
    )
    config.addinivalue_line(
        "markers", "slow: marca tests lentos"
    )


def pytest_collection_modifyitems(config, items):
    """Modificar items de la colección de tests."""
    # Agregar marker 'slow' a tests que toman tiempo
    for item in items:
        if "integration" in item.nodeid or "concurrent" in item.nodeid:
            item.add_marker(pytest.mark.slow)


@pytest.fixture(autouse=True)
def cleanup_after_test():
    """Cleanup automático después de cada test."""
    yield
    
    # Cleanup de event loops residuales
    try:
        loop = asyncio.get_event_loop()
        if not loop.is_closed():
            # Cancelar tareas pendientes
            pending = asyncio.all_tasks(loop)
            for task in pending:
                task.cancel()
            
            # Esperar un poco para cleanup
            if pending:
                loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
    except RuntimeError:
        pass  # No hay event loop activo


class TestHelper:
    """Clase helper para tests."""
    
    @staticmethod
    def create_mock_tool_result(success=True, output="Mock output"):
        """Crear resultado mock de herramienta."""
        from unittest.mock import Mock
        
        result = Mock()
        result.success = success
        result.output = output
        return result
    
    @staticmethod
    def suppress_stderr_for_test():
        """Context manager para suprimir stderr en tests."""
        import contextlib
        import os
        
        return contextlib.redirect_stderr(open(os.devnull, 'w'))
