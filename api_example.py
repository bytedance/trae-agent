#!/usr/bin/env python3
"""Concise API E2E test - essential functionality only."""

import tempfile
import subprocess
from pathlib import Path
from datetime import datetime
import requests


def test_api():
    """Test API: create file, verify content, execute."""
    base_url = "http://127.0.0.1:8000"
    
    # 1. Health check
    try:
        health = requests.get(f"{base_url}/api/agent/health", timeout=3).json()
        print(f"✅ API ready | Slots: {health.get('available_slots', 0)}")
    except:
        print("❌ API not running. Start with: make run-api")
        return False
    
    # 2. Create & verify file
    with tempfile.TemporaryDirectory() as tmpdir:
        timestamp = datetime.now().strftime("%H%M%S")
        filename = f"test_{timestamp}.py"
        
        # Request file creation
        resp = requests.post(f"{base_url}/api/agent/run", json={
            "task": f'Create {filename} with:\nprint("Works! {timestamp}")',
            "provider": "google",
            "model": "gemini-2.0-flash-exp",
            "working_dir": tmpdir,
            "timeout": 30,
            "max_steps": 5
        }, timeout=35)
        
        if resp.status_code != 200 or not resp.json().get("success"):
            print(f"❌ Task failed: {resp.status_code}")
            return False
        
        # 3. Verify file exists & execute
        file_path = Path(tmpdir) / filename
        if not file_path.exists():
            print(f"❌ File not created")
            return False
        
        # Execute and check output
        result = subprocess.run(
            ["python", str(file_path)], 
            capture_output=True, 
            text=True
        )
        
        if f"Works! {timestamp}" in result.stdout:
            print(f"✅ Test passed! Output: {result.stdout.strip()}")
            return True
        else:
            print(f"❌ Wrong output: {result.stdout}")
            return False


if __name__ == "__main__":
    success = test_api()
    exit(0 if success else 1)