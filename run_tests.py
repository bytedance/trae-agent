#!/usr/bin/env python3
"""
Script para ejecutar todos los tests de los fixes implementados
"""

import subprocess
import sys
import os
from pathlib import Path


def run_command(command, description):
    """Ejecutar comando y mostrar resultado."""
    print(f"\n{'='*60}")
    print(f"🧪 {description}")
    print(f"{'='*60}")
    
    try:
        result = subprocess.run(
            command, 
            shell=True, 
            capture_output=True, 
            text=True,
            cwd=Path(__file__).parent
        )
        
        if result.returncode == 0:
            print(f"✅ {description} - PASSED")
            if result.stdout:
                print(f"📊 Output:\n{result.stdout}")
        else:
            print(f"❌ {description} - FAILED")
            if result.stderr:
                print(f"🚨 Error:\n{result.stderr}")
            if result.stdout:
                print(f"📊 Output:\n{result.stdout}")
        
        return result.returncode == 0
        
    except Exception as e:
        print(f"❌ {description} - ERROR: {e}")
        return False


def main():
    """Ejecutar todos los tests."""
    print("🚀 Ejecutando Tests de Fixes de Trae Agent")
    print("=" * 60)
    
    # Verificar que pytest está instalado
    try:
        import pytest
        print(f"✅ pytest encontrado: {pytest.__version__}")
    except ImportError:
        print("❌ pytest no encontrado. Instalando...")
        subprocess.run([sys.executable, "-m", "pip", "install", "pytest", "pytest-asyncio"])
    
    # Lista de tests a ejecutar
    test_suites = [
        {
            "command": "python -m pytest tests/test_llm_client_fix.py -v",
            "description": "Tests de Fix LLM Client (Alibaba Cloud)"
        },
        {
            "command": "python -m pytest tests/test_sequential_thinking_fix.py -v",
            "description": "Tests de Fix Sequential Thinking Tool"
        },
        {
            "command": "python -m pytest tests/test_bash_tool_cleanup.py -v",
            "description": "Tests de Fix Bash Tool Cleanup"
        },
        {
            "command": "python -m pytest tests/test_cli_improvements.py -v",
            "description": "Tests de Mejoras CLI"
        },
        {
            "command": "python -m pytest tests/test_agent_cleanup.py -v",
            "description": "Tests de Agent Cleanup"
        },
        {
            "command": "python -m pytest tests/test_integration_fixes.py -v",
            "description": "Tests de Integración de Todos los Fixes"
        }
    ]
    
    # Ejecutar tests individuales
    results = []
    for test_suite in test_suites:
        success = run_command(test_suite["command"], test_suite["description"])
        results.append((test_suite["description"], success))
    
    # Ejecutar todos los tests juntos
    print(f"\n{'='*60}")
    print("🧪 Ejecutando TODOS los tests juntos")
    print(f"{'='*60}")
    
    all_tests_success = run_command(
        "python -m pytest tests/ -v --tb=short",
        "Todos los Tests de Fixes"
    )
    
    # Resumen final
    print(f"\n{'='*60}")
    print("📊 RESUMEN DE RESULTADOS")
    print(f"{'='*60}")
    
    passed = 0
    failed = 0
    
    for description, success in results:
        status = "✅ PASSED" if success else "❌ FAILED"
        print(f"{status} - {description}")
        if success:
            passed += 1
        else:
            failed += 1
    
    print(f"\n📈 Estadísticas:")
    print(f"   ✅ Tests Pasados: {passed}")
    print(f"   ❌ Tests Fallidos: {failed}")
    print(f"   📊 Total: {len(results)}")
    
    if all_tests_success and failed == 0:
        print(f"\n🎉 ¡TODOS LOS FIXES FUNCIONAN CORRECTAMENTE!")
        print("✅ El agente Trae está listo para uso productivo")
        return 0
    else:
        print(f"\n⚠️  Algunos tests fallaron. Revisar los errores arriba.")
        return 1


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
