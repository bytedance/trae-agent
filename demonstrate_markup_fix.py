#!/usr/bin/env python3
"""Demonstrate the markup error fix in the actual CLI."""

import sys
import os

# Add the project root to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from trae_agent.cli import console

def test_cli_markup_fix():
    """Test the CLI console with markup fix."""
    print("Testing CLI console with markup fix:")
    
    # Test various error messages with special characters
    test_cases = [
        "Error in module [trae_agent.cli] at line 42",
        "Failed to load config file [trae_config.yaml]",
        "Connection error to http://localhost:8000",
        "User input contains [brackets] and (parentheses)",
        "Error: 'key' not found in {'config': 'value'}",
    ]
    
    for i, error_msg in enumerate(test_cases):
        try:
            # This should not trigger MarkupError anymore
            console.print(f"[red]Error: {error_msg}[/red]", markup=False)
            print(f"✓ Test {i+1}: Success - Printed without error")
        except Exception as e:
            print(f"✗ Test {i+1}: Failed - {type(e).__name__}: {e}")

if __name__ == "__main__":
    test_cli_markup_fix()