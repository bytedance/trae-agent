# Copyright (c) 2025 ByteDance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from trae_agent.tools.base import ToolCallArguments
from trae_agent.tools.edit_tool import TextEditorTool


class TestTextEditorTool(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tool = TextEditorTool()
        # Use a real temporary directory so tempfile.mkstemp works in write_file
        self._tmpdir = Path(tempfile.mkdtemp())
        self.test_dir = self._tmpdir / "test_dir"
        self.test_dir.mkdir(parents=True, exist_ok=True)  # ensure parent exists
        self.test_file = self.test_dir / "test_file.txt"

    def tearDown(self):
        import shutil

        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def mock_file_system(self, exists=True, is_dir=False, content=""):
        """Helper to mock file system operations"""
        patcher = patch("pathlib.Path.exists", return_value=exists)
        self.mock_exists = patcher.start()
        self.addCleanup(patcher.stop)

        patcher = patch("pathlib.Path.is_dir", return_value=is_dir)
        self.mock_is_dir = patcher.start()
        self.addCleanup(patcher.stop)

        patcher = patch("pathlib.Path.read_text", return_value=content)
        self.mock_read = patcher.start()
        self.addCleanup(patcher.stop)

        # Atomic write uses os.replace; mock it to avoid side effects
        patcher = patch("os.replace")
        self.mock_os_replace = patcher.start()
        self.addCleanup(patcher.stop)

    async def test_create_file(self):
        self.mock_file_system(exists=False)
        result = await self.tool.execute(
            ToolCallArguments(
                {
                    "command": "create",
                    "path": str(self.test_file),
                    "file_text": "new content",
                }
            )
        )
        self.mock_os_replace.assert_called_once()
        self.assertIn("created successfully", result.output)

    async def test_insert_line(self):
        self.mock_file_system(content="line1\nline3")
        result = await self.tool.execute(
            ToolCallArguments(
                {
                    "command": "insert",
                    "path": str(self.test_file),
                    "insert_line": 1,
                    "new_str": "line2",
                }
            )
        )
        self.mock_os_replace.assert_called_once()
        self.assertIn("edited", result.output)

    async def test_invalid_command(self):
        result = await self.tool.execute(
            ToolCallArguments({"command": "invalid", "path": str(self.test_file.absolute())})
        )
        self.assertEqual(result.error_code, -1)
        self.assertIn("Please provide a valid path", result.error)

    async def test_str_replace_multiple_occurrences(self):
        self.mock_file_system(content="dup\ndup\nline3")
        result = await self.tool.execute(
            ToolCallArguments(
                {
                    "command": "str_replace",
                    "path": str(self.test_file),
                    "old_str": "dup",
                    "new_str": "new",
                }
            )
        )
        self.assertEqual(result.error_code, -1)
        self.assertIn("Multiple occurrences", result.error or "")

    async def test_str_replace_success(self):
        self.mock_file_system(content="old_content\nline2")
        result = await self.tool.execute(
            ToolCallArguments(
                {
                    "command": "str_replace",
                    "path": str(self.test_file),
                    "old_str": "old_content",
                    "new_str": "new_content",
                }
            )
        )
        self.mock_os_replace.assert_called_once()
        self.assertIn("edited", result.output)

    async def test_view_directory(self):
        self.mock_file_system(exists=True, is_dir=True)
        with patch("trae_agent.tools.edit_tool.run", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = (0, "file1\nfile2", "")
            result = await self.tool.execute(
                ToolCallArguments({"command": "view", "path": str(self.test_dir)})
            )
        self.assertIn("files and directories", result.output)

    async def test_view_file(self):
        self.mock_file_system(exists=True, is_dir=False, content="line1\nline2\nline3")
        result = await self.tool.execute(
            ToolCallArguments({"command": "view", "path": str(self.test_file)})
        )
        self.assertRegex(result.output, r"\d+\s+line1")

    async def test_relative_path(self):
        result = await self.tool.execute(
            ToolCallArguments({"command": "view", "path": "relative/path"})
        )
        self.assertIn("absolute path", result.error)

    async def test_missing_parameters(self):
        result = await self.tool.execute(ToolCallArguments({"command": "create"}))
        self.assertIn("No path provided", result.error)

    async def test_search_replace_exact(self):
        """search_replace with exact match should work."""
        self.mock_file_system(content="def foo():\n    return 1\n\ndef bar():\n    return 2\n")
        result = await self.tool.execute(
            ToolCallArguments(
                {
                    "command": "search_replace",
                    "path": str(self.test_file),
                    "search_block": "def foo():\n    return 1",
                    "replace_block": "def foo():\n    return 42",
                    "match_mode": "auto",
                }
            )
        )
        self.mock_os_replace.assert_called_once()
        self.assertIn("edited", result.output)

    async def test_search_replace_no_match(self):
        """search_replace with no match should fail gracefully."""
        self.mock_file_system(content="def foo():\n    return 1\n")
        result = await self.tool.execute(
            ToolCallArguments(
                {
                    "command": "search_replace",
                    "path": str(self.test_file),
                    "search_block": "nonexistent_code_xyz",
                    "replace_block": "replacement",
                }
            )
        )
        self.assertEqual(result.error_code, -1)
        self.assertIn("No matching regions", result.error)

    async def test_write_command(self):
        """write command should overwrite file."""
        self.mock_file_system(exists=True, content="old content")
        result = await self.tool.execute(
            ToolCallArguments(
                {
                    "command": "write",
                    "path": str(self.test_file),
                    "file_text": "brand new content",
                }
            )
        )
        self.mock_os_replace.assert_called_once()
        self.assertIn("File written successfully", result.output)

    async def test_search_replace_missing_params(self):
        """search_replace with missing params should error."""
        self.mock_file_system(content="some content")
        result = await self.tool.execute(
            ToolCallArguments(
                {
                    "command": "search_replace",
                    "path": str(self.test_file),
                }
            )
        )
        self.assertEqual(result.error_code, -1)
        self.assertIn("search_block", result.error)


if __name__ == "__main__":
    unittest.main()
