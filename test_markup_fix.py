#!/usr/bin/env python3
"""Test script to reproduce and verify the markup error fix."""

import sys
from rich.console import Console

console = Console()

def test_markup_error():
    """Test that demonstrates the original markup error issue."""
    try:
        # Simulate an exception message with square brackets
        raise Exception("Error in module [trae_agent.cli] at line 42")
    except Exception as e:
        # This should trigger the MarkupError
        console.print(f"[red]Error: {e}[/red]")

def test_markup_fix():
    """Test that verifies the fix works correctly."""
    try:
        # Simulate an exception message with square brackets
        raise Exception("Error in module [trae_agent.cli] at line 42")
    except Exception as e:
        # This should NOT trigger the MarkupError
        console.print(f"[red]Error: {e}[/red]", markup=False)

if __name__ == "__main__":
    print("Testing original behavior (should fail with MarkupError):")
    try:
        test_markup_error()
    except Exception as e:
        print(f"✗ Failed with: {type(e).__name__}: {e}")
    
    print("\nTesting fixed behavior (should work without error):")
    try:
        test_markup_fix()
        print("✓ Success! No MarkupError occurred.")
    except Exception as e:
        print(f"✗ Failed with: {type(e).__name__}: {e}")