# Copyright (c) 2025 ByteDance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

"""Tests for JSONEditTool."""

import json
import subprocess
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import mock_open, patch

import pytest

from trae_agent.tools.base import ToolCallArguments
from trae_agent.tools.json_edit_tool import JSONEditTool


@pytest.mark.parametrize(
    ("original", "json_path", "expected"),
    [
        ({"remove": 1, "keep": 2}, "$.remove", {"keep": 2}),
        ([1, 2, 3], "$[0]", [2, 3]),
        ({"items": [1, 2, 3]}, "$.items[0]", {"items": [2, 3]}),
        ({"items": [1, 2, 3]}, "$.items[*]", {"items": []}),
    ],
)
def test_cli_removes_selected_elements_once(tmp_path, original, json_path, expected):
    path = tmp_path / "data.json"
    path.write_text(json.dumps(original), encoding="utf-8")
    script = Path(__file__).resolve().parents[2] / "trae_agent/tools/json_edit_tool_cli.py"

    result = subprocess.run(
        [
            sys.executable,
            "-B",
            str(script),
            "--operation",
            "remove",
            "--file_path",
            str(path),
            "--json_path",
            json_path,
        ],
        capture_output=True,
        text=True,
        timeout=10,
    )

    assert result.returncode == 0, result.stderr
    assert json.loads(path.read_text(encoding="utf-8")) == expected


def test_cli_rejects_removing_document_root_without_writing(tmp_path):
    path = tmp_path / "data.json"
    original = '{"keep": 1}\n'
    path.write_text(original, encoding="utf-8")
    script = Path(__file__).resolve().parents[2] / "trae_agent/tools/json_edit_tool_cli.py"

    result = subprocess.run(
        [
            sys.executable,
            "-B",
            str(script),
            "--operation",
            "remove",
            "--file_path",
            str(path),
            "--json_path",
            "$",
        ],
        capture_output=True,
        text=True,
        timeout=10,
    )

    assert result.returncode == 1
    assert "document root" in result.stderr
    assert path.read_text(encoding="utf-8") == original


class TestJSONEditTool(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        """Set up the test environment."""
        self.tool = JSONEditTool()
        self.test_file_path = "/test_dir/test_file.json"

        # Default sample data
        self.sample_data = {
            "users": [{"id": 1, "name": "Alice"}, {"id": 2, "name": "Bob"}],
            "config": {"enabled": True},
        }

    async def test_remove_root_children(self):
        cases = [
            ({"remove": 1, "keep": 2}, "$.remove", {"keep": 2}),
            ({"a": 1, "b": 2}, "$.*", {}),
            (["first", "second", "third"], "$[0]", ["second", "third"]),
            ([1, 2, 3], "$[*]", []),
            ([1, 2, 3, 4], "$[1:3]", [1, 4]),
            ({"a.b": 1, "keep": 2}, "$['a.b']", {"keep": 2}),
            ({"items": [{"x": 1}, {"x": 2}]}, "$.items[*].x", {"items": [{}, {}]}),
        ]
        for original, json_path, expected in cases:
            with self.subTest(json_path=json_path), TemporaryDirectory() as directory:
                path = Path(directory) / "data.json"
                path.write_text(json.dumps(original), encoding="utf-8")

                result = await self.tool.execute(
                    {"operation": "remove", "file_path": str(path), "json_path": json_path}
                )

                self.assertEqual(result.error_code, 0, result.error)
                self.assertEqual(json.loads(path.read_text(encoding="utf-8")), expected)

    async def test_remove_document_root_preserves_file(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "data.json"
            original = '{"keep": 1}\n'
            path.write_text(original, encoding="utf-8")

            result = await self.tool.execute(
                {"operation": "remove", "file_path": str(path), "json_path": "$"}
            )

            self.assertEqual(result.error_code, -1)
            self.assertIn("document root", result.error)
            self.assertEqual(path.read_text(encoding="utf-8"), original)

    def mock_file_read(self, json_data=None):
        """Helper to mock file reading operations."""
        if json_data is None:
            json_data = self.sample_data

        read_content = json.dumps(json_data)
        m_open = mock_open(read_data=read_content)

        # Patch open and path checks
        self.open_patcher = patch("builtins.open", m_open)
        self.exists_patcher = patch("pathlib.Path.exists", return_value=True)
        self.is_absolute_patcher = patch("pathlib.Path.is_absolute", return_value=True)

        self.open_patcher.start()
        self.exists_patcher.start()
        self.is_absolute_patcher.start()

        self.addCleanup(self.open_patcher.stop)
        self.addCleanup(self.exists_patcher.stop)
        self.addCleanup(self.is_absolute_patcher.stop)

    @patch("json.dump")
    async def test_set_config_value(self, mock_json_dump):
        """Test setting a simple configuration value."""
        self.mock_file_read()
        result = await self.tool.execute(
            ToolCallArguments(
                {
                    "operation": "set",
                    "file_path": self.test_file_path,
                    "json_path": "$.config.enabled",
                    "value": False,
                }
            )
        )
        self.assertEqual(result.error_code, 0)

        # Verify that json.dump was called with the correct data
        mock_json_dump.assert_called_once()
        written_data = mock_json_dump.call_args[0][0]
        self.assertFalse(written_data["config"]["enabled"])

    @patch("json.dump")
    async def test_update_user_name(self, mock_json_dump):
        """Test updating a name in a list of objects."""
        self.mock_file_read()
        result = await self.tool.execute(
            ToolCallArguments(
                {
                    "operation": "set",
                    "file_path": self.test_file_path,
                    "json_path": "$.users[0].name",
                    "value": "Alicia",
                }
            )
        )
        self.assertEqual(result.error_code, 0)

        mock_json_dump.assert_called_once()
        written_data = mock_json_dump.call_args[0][0]
        self.assertEqual(written_data["users"][0]["name"], "Alicia")

    @patch("json.dump")
    async def test_add_new_user(self, mock_json_dump):
        """Test adding a new object to a list (by inserting at the end)."""
        self.mock_file_read()
        result = await self.tool.execute(
            ToolCallArguments(
                {
                    "operation": "add",
                    "file_path": self.test_file_path,
                    "json_path": "$.users[2]",  # Inserting at index 2 (end of list)
                    "value": {"id": 3, "name": "Charlie"},
                }
            )
        )
        self.assertEqual(result.error_code, 0)

        mock_json_dump.assert_called_once()
        written_data = mock_json_dump.call_args[0][0]
        self.assertEqual(len(written_data["users"]), 3)
        self.assertEqual(written_data["users"][2]["name"], "Charlie")

    @patch("json.dump")
    async def test_add_new_config_key(self, mock_json_dump):
        """Test adding a new key-value pair to an object."""
        self.mock_file_read()
        result = await self.tool.execute(
            ToolCallArguments(
                {
                    "operation": "add",
                    "file_path": self.test_file_path,
                    "json_path": "$.config.version",
                    "value": "1.1.0",
                }
            )
        )
        self.assertEqual(result.error_code, 0)

        mock_json_dump.assert_called_once()
        written_data = mock_json_dump.call_args[0][0]
        self.assertEqual(written_data["config"]["version"], "1.1.0")

    @patch("json.dump")
    async def test_remove_user_by_index(self, mock_json_dump):
        """Test removing an element from a list by its index."""
        self.mock_file_read()
        result = await self.tool.execute(
            ToolCallArguments(
                {
                    "operation": "remove",
                    "file_path": self.test_file_path,
                    "json_path": "$.users[0]",
                }
            )
        )
        self.assertEqual(result.error_code, 0)

        mock_json_dump.assert_called_once()
        written_data = mock_json_dump.call_args[0][0]
        self.assertEqual(len(written_data["users"]), 1)
        self.assertEqual(written_data["users"][0]["name"], "Bob")

    @patch("json.dump")
    async def test_remove_config_key(self, mock_json_dump):
        """Test removing a key from an object."""
        self.mock_file_read()
        result = await self.tool.execute(
            ToolCallArguments(
                {
                    "operation": "remove",
                    "file_path": self.test_file_path,
                    "json_path": "$.config.enabled",
                }
            )
        )
        self.assertEqual(result.error_code, 0)

        mock_json_dump.assert_called_once()
        written_data = mock_json_dump.call_args[0][0]
        self.assertNotIn("enabled", written_data["config"])

    async def test_view_operation(self):
        """Test the view operation to ensure it reads and returns content."""
        self.mock_file_read()
        result = await self.tool.execute(
            ToolCallArguments(
                {
                    "operation": "view",
                    "file_path": self.test_file_path,
                    "json_path": "$.users[0]",
                }
            )
        )
        self.assertEqual(result.error_code, 0)
        self.assertIn('"id": 1', result.output)
        self.assertIn('"name": "Alice"', result.output)

    async def test_error_file_not_found(self):
        """Test error handling when the file does not exist."""
        # Mock Path.exists to return False
        with (
            patch("pathlib.Path.exists", return_value=False),
            patch("pathlib.Path.is_absolute", return_value=True),
        ):
            result = await self.tool.execute(
                ToolCallArguments(
                    {
                        "operation": "view",
                        "file_path": "/nonexistent/file.json",
                    }
                )
            )
            self.assertEqual(result.error_code, -1)
            self.assertIn("File does not exist", result.error)


if __name__ == "__main__":
    unittest.main()
