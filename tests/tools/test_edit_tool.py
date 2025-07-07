import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../")))

import unittest
from pathlib import Path
from unittest.mock import patch

from trae_agent.tools.base import ToolCallArguments, ToolError
from trae_agent.tools.edit_tool import TextEditorTool

from trae_agent.tools.base import ToolError


class TestTextEditorTool(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tool = TextEditorTool()
        # Use current working directory for test paths
        self.test_dir = Path.cwd() / "test_dir"
        self.test_file = self.test_dir / "test_file.txt"

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

        patcher = patch("pathlib.Path.write_text")
        self.mock_write = patcher.start()
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
        self.mock_write.assert_called_once_with("new content")
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
        self.mock_write.assert_called_once()
        self.assertIn("edited", result.output)

    async def test_invalid_command(self):
        result = await self.tool.execute(
            ToolCallArguments(
                {"command": "invalid", "path": str(self.test_file.absolute())}
            )
        )
        self.assertEqual(result.error_code, -1)
        self.assertIn("Unrecognized command", result.error)

    async def test_str_replace_multiple_occurrences(self):
        self.mock_file_system(content="dup\ndup\nline3")
        with self.assertRaises(ToolError) as cm:
            await self.tool.execute(
                ToolCallArguments(
                    {
                        "command": "str_replace",
                        "path": str(self.test_file),
                        "old_str": "dup",
                        "new_str": "new",
                    }
                )
            )
        self.assertIn("Multiple occurrences", str(cm.exception))

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
        self.mock_write.assert_called_once()
        self.assertIn("edited", result.output)

    async def test_view_directory(self):
        self.mock_file_system(exists=True, is_dir=True)
        with patch("trae_agent.tools.run") as mock_run:
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


if __name__ == "__main__":
    unittest.main()
