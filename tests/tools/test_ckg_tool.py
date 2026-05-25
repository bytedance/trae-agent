# Copyright (c) 2025 ByteDance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock, patch

from trae_agent.tools.base import ToolCallArguments
from trae_agent.tools.ckg_tool import CKGTool


class TestCKGTool(unittest.IsolatedAsyncioTestCase):
    async def test_execute_accepts_file_path_inside_codebase(self):
        with TemporaryDirectory() as tmpdir:
            code_file = Path(tmpdir) / "example.py"
            code_file.write_text("def target():\n    return 1\n")

            ckg_database = MagicMock()
            ckg_database.query_function.return_value = []

            with patch(
                "trae_agent.tools.ckg_tool.CKGDatabase", return_value=ckg_database
            ) as ckg_database_cls:
                result = await CKGTool().execute(
                    ToolCallArguments(
                        {
                            "command": "search_function",
                            "path": str(code_file),
                            "identifier": "target",
                            "print_body": False,
                        }
                    )
                )

            self.assertIsNone(result.error)
            self.assertEqual(result.output, "No functions named target found.")
            ckg_database_cls.assert_called_once_with(code_file.parent)

    async def test_execute_uses_git_root_for_file_path(self):
        with TemporaryDirectory() as tmpdir:
            codebase_root = Path(tmpdir)
            nested_dir = codebase_root / "pkg"
            nested_dir.mkdir()
            code_file = nested_dir / "example.py"
            code_file.write_text("def target():\n    return 1\n")

            ckg_database = MagicMock()
            ckg_database.query_function.return_value = []
            git_result = MagicMock(returncode=0, stdout=f"{codebase_root}\n")

            with (
                patch("trae_agent.tools.ckg_tool.subprocess.run", return_value=git_result),
                patch(
                    "trae_agent.tools.ckg_tool.CKGDatabase", return_value=ckg_database
                ) as ckg_database_cls,
            ):
                result = await CKGTool().execute(
                    ToolCallArguments(
                        {
                            "command": "search_function",
                            "path": str(code_file),
                            "identifier": "target",
                        }
                    )
                )

            self.assertIsNone(result.error)
            ckg_database_cls.assert_called_once_with(codebase_root)


if __name__ == "__main__":
    unittest.main()
