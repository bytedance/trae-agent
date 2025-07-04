"""
Tests para verificar el fix de Sequential Thinking Tool
"""

import pytest
import asyncio
from trae_agent.tools.sequential_thinking_tool import SequentialThinkingTool


class TestSequentialThinkingFix:
    """Tests para verificar que el fix de validación de parámetros funciona."""
    
    def setup_method(self):
        """Setup para cada test."""
        self.tool = SequentialThinkingTool()
    
    @pytest.mark.asyncio
    async def test_valid_basic_thought(self):
        """Test con parámetros básicos válidos."""
        arguments = {
            "thought": "This is a test thought",
            "thought_number": 1,
            "total_thoughts": 3,
            "next_thought_needed": True
        }
        
        result = await self.tool.execute(arguments)
        
        assert not result.error
        assert result.error_code == 0
        assert "thought_number" in result.output
        assert "1" in result.output
    
    @pytest.mark.asyncio
    async def test_revises_thought_zero_handled_correctly(self):
        """Test que revises_thought=0 se maneja como None (no revisar)."""
        arguments = {
            "thought": "This is a revision test",
            "thought_number": 2,
            "total_thoughts": 3,
            "next_thought_needed": True,
            "revises_thought": 0,  # Esto causaba el error antes
            "is_revision": False
        }
        
        # Esto no debería fallar
        result = await self.tool.execute(arguments)
        
        assert not result.error
        assert result.error_code == 0
        # Verificar que se procesó correctamente
        assert "thought_number" in result.output
    
    @pytest.mark.asyncio
    async def test_branch_from_thought_zero_handled_correctly(self):
        """Test que branch_from_thought=0 se maneja como None (no branch)."""
        arguments = {
            "thought": "This is a branch test",
            "thought_number": 2,
            "total_thoughts": 3,
            "next_thought_needed": True,
            "branch_from_thought": 0,  # Esto causaba el error antes
            "branch_id": ""
        }
        
        # Esto no debería fallar
        result = await self.tool.execute(arguments)
        
        assert not result.error
        assert result.error_code == 0
        assert "thought_number" in result.output
    
    @pytest.mark.asyncio
    async def test_both_zero_parameters(self):
        """Test con ambos parámetros en 0 (caso real del error)."""
        arguments = {
            "thought": "Test with both zero parameters",
            "thought_number": 1,
            "total_thoughts": 2,
            "next_thought_needed": True,
            "revises_thought": 0,
            "branch_from_thought": 0,
            "is_revision": False,
            "branch_id": ""
        }
        
        # Este era el caso que fallaba antes del fix
        result = await self.tool.execute(arguments)
        
        assert not result.error
        assert result.error_code == 0
        assert "thought_number" in result.output
    
    @pytest.mark.asyncio
    async def test_valid_positive_revises_thought(self):
        """Test con revises_thought positivo válido."""
        arguments = {
            "thought": "This revises thought 1",
            "thought_number": 2,
            "total_thoughts": 3,
            "next_thought_needed": True,
            "revises_thought": 1,  # Valor positivo válido
            "is_revision": True
        }
        
        result = await self.tool.execute(arguments)
        
        assert not result.error
        assert result.error_code == 0
        assert "thought_number" in result.output
    
    @pytest.mark.asyncio
    async def test_valid_positive_branch_from_thought(self):
        """Test con branch_from_thought positivo válido."""
        arguments = {
            "thought": "This branches from thought 1",
            "thought_number": 2,
            "total_thoughts": 3,
            "next_thought_needed": True,
            "branch_from_thought": 1,  # Valor positivo válido
            "branch_id": "branch_a"
        }
        
        result = await self.tool.execute(arguments)
        
        assert not result.error
        assert result.error_code == 0
        assert "thought_number" in result.output
    
    @pytest.mark.asyncio
    async def test_invalid_negative_revises_thought(self):
        """Test que valores negativos siguen siendo inválidos."""
        arguments = {
            "thought": "Test negative revises_thought",
            "thought_number": 1,
            "total_thoughts": 2,
            "next_thought_needed": True,
            "revises_thought": -1  # Valor inválido
        }
        
        # Debería manejar gracefully (convertir a None)
        result = await self.tool.execute(arguments)
        
        # Debería procesar sin error, ignorando el valor inválido
        assert not result.error
        assert result.error_code == 0
    
    @pytest.mark.asyncio
    async def test_string_zero_parameters(self):
        """Test con parámetros como string '0'."""
        arguments = {
            "thought": "Test with string zero",
            "thought_number": 1,
            "total_thoughts": 2,
            "next_thought_needed": True,
            "revises_thought": "0",  # String zero
            "branch_from_thought": "0"  # String zero
        }
        
        result = await self.tool.execute(arguments)
        
        assert not result.error
        assert result.error_code == 0
        assert "thought_number" in result.output
    
    def test_validation_method_directly(self):
        """Test del método de validación directamente."""
        # Test con parámetros que causaban error
        arguments = {
            "thought": "Direct validation test",
            "thought_number": 1,
            "total_thoughts": 2,
            "next_thought_needed": True,
            "revises_thought": 0,
            "branch_from_thought": 0,
            "is_revision": False,
            "branch_id": ""
        }
        
        # Esto no debería lanzar excepción
        thought_data = self.tool._validate_thought_data(arguments)
        
        assert thought_data.thought == "Direct validation test"
        assert thought_data.thought_number == 1
        assert thought_data.revises_thought is None  # 0 convertido a None
        assert thought_data.branch_from_thought is None  # 0 convertido a None
