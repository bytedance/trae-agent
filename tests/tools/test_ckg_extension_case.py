# Copyright (c) 2025 ByteDance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

"""`Path.suffix` keeps the case stored on disk, while `extension_to_language` is keyed lowercase.

The CKG walk compared the two directly, so `Utils.PY` was never parsed and the `ckg` tool
answered "No functions named X found." for a function that is in the codebase. These tests
index files that differ only in the case of their extension, in a temp codebase with the CKG
cache pointed at that same temp directory: no git history, no network, no key.
"""

import contextlib
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from trae_agent.tools.base import ToolCallArguments
from trae_agent.tools.ckg import ckg_database as ckg_module
from trae_agent.tools.ckg.ckg_database import CKGDatabase, extension_to_language
from trae_agent.tools.ckg_tool import CKGTool

PY_FUNCTION = "def {name}():\n    return 1\n"
PY_CLASS = "class {name}:\n    pass\n"
JS_CLASS = "class {name} {{}}\n"


class TestCKGFileExtensionCase(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self._tmp_dir: str = tempfile.mkdtemp()
        self.tmp = Path(self._tmp_dir)
        self.codebase = self.tmp / "codebase"
        self.codebase.mkdir()
        self.cache = self.tmp / "ckg_cache"
        self.cache.mkdir()
        self._patches = [
            mock.patch.object(ckg_module, "CKG_DATABASE_PATH", self.cache),
            mock.patch.object(
                ckg_module, "CKG_STORAGE_INFO_FILE", self.cache / "storage_info.json"
            ),
        ]
        for patcher in self._patches:
            patcher.start()
        self.addCleanup(self.stop_patches)
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def stop_patches(self) -> None:
        for patcher in self._patches:
            patcher.stop()

    def write(self, filename: str, template: str, symbol: str) -> Path:
        path = self.codebase / filename
        path.write_text(template.format(name=symbol), encoding="utf-8")
        return path

    def build(self) -> CKGDatabase:
        database = CKGDatabase(self.codebase)
        self.addCleanup(database._db_connection.close)
        return database

    def test_python_function_indexes_whatever_the_extension_case(self) -> None:
        self.write("alpha_lower.py", PY_FUNCTION, "alpha_lower")
        self.write("alpha_upper.PY", PY_FUNCTION, "alpha_upper")

        database = self.build()

        self.assertEqual(len(database.query_function("alpha_lower")), 1)
        self.assertEqual(len(database.query_function("alpha_upper")), 1)

    def test_python_class_indexes_whatever_the_extension_case(self) -> None:
        self.write("beta_lower.py", PY_CLASS, "BetaLower")
        self.write("beta_upper.PY", PY_CLASS, "BetaUpper")

        database = self.build()

        self.assertEqual(len(database.query_class("BetaLower")), 1)
        self.assertEqual(len(database.query_class("BetaUpper")), 1)

    def test_javascript_class_indexes_whatever_the_extension_case(self) -> None:
        self.write("gamma_lower.js", JS_CLASS, "GammaLower")
        self.write("gamma_upper.JS", JS_CLASS, "GammaUpper")

        database = self.build()

        self.assertEqual(len(database.query_class("GammaLower")), 1)
        self.assertEqual(len(database.query_class("GammaUpper")), 1)

    async def test_the_tool_reports_the_symbol_from_a_mixed_case_file(self) -> None:
        self.write("delta_upper.PY", PY_FUNCTION, "delta_upper")

        tool = CKGTool()
        arguments: ToolCallArguments = {
            "command": "search_function",
            "path": str(self.codebase),
            "identifier": "delta_upper",
        }
        result = await tool.execute(arguments)
        for database in tool._ckg_databases.values():
            with contextlib.suppress(Exception):
                database._db_connection.close()

        self.assertIsNone(result.error)
        self.assertIn("Found 1 functions named delta_upper", result.output or "")
        self.assertIn("delta_upper.PY", result.output or "")

    def test_every_extension_key_is_already_lowercase(self) -> None:
        # The walk matches a normalised suffix, so a mixed-case key could never be found.
        self.assertIn(".py", extension_to_language)
        for extension in extension_to_language:
            self.assertEqual(extension, extension.lower())


if __name__ == "__main__":
    unittest.main()
