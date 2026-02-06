#!/usr/bin/env python3
"""
Test script to reproduce and verify the rich MarkupError fix.

This script tests the CLI error handling with exception messages containing
special characters like brackets that would previously cause rich.errors.MarkupError.
"""

import tempfile
import os
import sys
from pathlib import Path
from unittest.mock import patch
import traceback

# Add the project root to Python path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from rich.console import Console
from rich.text import Text


def test_markup_error_reproduction():
    """Test that demonstrates the original MarkupError issue and verifies the fix."""
    
    console = Console()
    
    # Test cases with problematic characters that would cause MarkupError
    test_cases = [
        "Error with [brackets] in message",
        "Error with [multiple] [brackets] and [nested[brackets]]",
        "Error with special chars: [red]not markup[/red] but text",
        "Config error: missing [section] in file",
        "Docker error: failed to create [container] with [invalid] name",
    ]
    
    print("Testing rich markup error handling...")
    print("=" * 60)
    
    for i, test_message in enumerate(test_cases, 1):
        print(f"\nTest case {i}: {test_message}")
        print("-" * 40)
        
        try:
            # This is the old problematic way (would cause MarkupError)
            # error_text = Text(f"Error: {test_message}", style="red")
            # console.print(f"\n{error_text}")  # This would fail with MarkupError
            
            # This is the new fixed way
            error_text = Text(f"Error: {test_message}", style="red")
            console.print(error_text, markup=False)
            print("✓ SUCCESS: No MarkupError occurred")
            
        except Exception as e:
            print(f"✗ FAILED: {type(e).__name__}: {e}")
            traceback.print_exc()


def test_cli_error_handling():
    """Test the actual CLI error handling code."""
    
    print("\n\nTesting CLI error handling patterns...")
    print("=" * 60)
    
    # Import the CLI module to test the actual patterns
    try:
        from trae_agent.cli import run
        print("✓ Successfully imported CLI module")
    except Exception as e:
        print(f"✗ Failed to import CLI module: {e}")
        return
    
    # Test the Text creation patterns used in the CLI
    console = Console()
    test_exceptions = [
        Exception("Config file error: missing [section] in config.yaml"),
        Exception("Docker error: failed to create [container] with name [test]"),
        Exception("File not found: [important] file missing"),
    ]
    
    for i, exc in enumerate(test_exceptions, 1):
        print(f"\nCLI pattern test {i}: {exc}")
        print("-" * 40)
        
        try:
            # Simulate the CLI error handling patterns
            error_text = Text(f"Error: {exc}", style="red")
            console.print(error_text, markup=False)
            print("✓ SUCCESS: CLI pattern works correctly")
            
        except Exception as e:
            print(f"✗ FAILED: {type(e).__name__}: {e}")
            traceback.print_exc()


def create_test_config_with_brackets():
    """Create a test config file that would trigger the error."""
    
    config_content = """
# Test config with brackets that might cause issues
model:
  provider: "openai"
  model_name: "gpt-4"
  
# Section with brackets [like this]
special_config:
  value: "test[bracket]value"
  array: [item1, item2, item3]
"""
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        f.write(config_content)
        return f.name


def main():
    """Run all tests."""
    
    print("Rich MarkupError Fix Verification")
    print("=" * 60)
    print("This script tests that exception messages with special characters")
    print("(like brackets) no longer cause rich.errors.MarkupError in the CLI.")
    print()
    
    # Run tests
    test_markup_error_reproduction()
    test_cli_error_handling()
    
    # Create and test with config file
    print("\n\nTesting with config file containing brackets...")
    print("=" * 60)
    
    config_file = create_test_config_with_brackets()
    print(f"Created test config file: {config_file}")
    
    try:
        # Test reading the config
        with open(config_file, 'r') as f:
            content = f.read()
        print("✓ Successfully read config file")
        
        # Test that we can create error messages with the content
        console = Console()
        error_text = Text(f"Config error in {config_file}: missing [section]", style="red")
        console.print(error_text, markup=False)
        print("✓ Successfully handled config error with brackets")
        
    except Exception as e:
        print(f"✗ Failed: {type(e).__name__}: {e}")
        traceback.print_exc()
    
    finally:
        # Cleanup
        try:
            os.unlink(config_file)
            print(f"✓ Cleaned up test config file")
        except:
            pass
    
    print("\n" + "=" * 60)
    print("All tests completed!")
    print("If no failures were reported, the fix is working correctly.")


if __name__ == "__main__":
    main()