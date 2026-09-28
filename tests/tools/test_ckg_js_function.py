# Copyright (c) 2025 ByteDance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

"""`function foo() {}` is a `function_declaration` in tree-sitter's JavaScript and TypeScript grammars.

Both JS visitors only matched `class_declaration` and `method_definition`, so a named function in a
`.js` or `.ts` file was never inserted and the `ckg` tool answered "No functions named foo found."
for code that is plainly in the codebase. The module docstring lists anonymous and arrow functions
as unparsed; a named declaration is not one of those, and Python, Java, C and C++ all index theirs.

The codebase is a temp directory and the CKG cache is pointed into that same directory, so there is
no git history, no network and no key involved.
"""

import contextlib
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from trae_agent.tools.base import ToolCallArguments
from trae_agent.tools.ckg import ckg_database as ckg_module
from trae_agent.tools.ckg.ckg_database import CKGDatabase
from trae_agent.tools.ckg_tool import CKGTool

JS_FUNCTION = "function topSum(a, b) {\n  return a + b;\n}\n"
JS_EXPORT = "export function exportedSum(a) {\n  return a;\n}\n"
JS_ARROW = "const arrowSum = (a, b) => a + b;\n"
JS_CLASS = "class Calc {\n  add(a, b) {\n    return a + b;\n  }\n}\n"
TS_NAMED = (
    "export function tsNamed(a: number): number {\n  return a;\n}\n\n"
    "function tsLocal(): number {\n  return 1;\n}\n"
)


class TestCKGJSFunctionDeclaration(unittest.IsolatedAsyncioTestCase):
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

    def write(self, filename: str, source: str) -> Path:
        path = self.codebase / filename
        path.write_text(source, encoding="utf-8")
        return path

    def build(self) -> CKGDatabase:
        database = CKGDatabase(self.codebase)
        # Windows refuses to remove the temp tree while the sqlite handle is open.
        self.addCleanup(database._db_connection.close)
        return database

    def test_a_javascript_function_declaration_is_indexed(self) -> None:
        js_file = self.write("sum.js", JS_FUNCTION)

        entries = self.build().query_function("topSum")

        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].file_path, js_file.absolute().as_posix())
        self.assertEqual((entries[0].start_line, entries[0].end_line), (1, 3))
        self.assertIn("return a + b", entries[0].body)
        self.assertIsNone(entries[0].parent_class)

    def test_an_exported_javascript_function_is_indexed(self) -> None:
        self.write("exported.js", JS_EXPORT)

        self.assertEqual(len(self.build().query_function("exportedSum")), 1)

    def test_a_typescript_function_declaration_is_indexed(self) -> None:
        self.write("named.ts", TS_NAMED)

        database = self.build()
        self.assertEqual(len(database.query_function("tsNamed")), 1)
        self.assertEqual(len(database.query_function("tsLocal")), 1)

    def test_a_javascript_class_and_method_survive_the_change(self) -> None:
        self.write("calc.js", JS_CLASS)

        database = self.build()
        self.assertEqual(len(database.query_class("Calc")), 1)
        methods = database.query_function("add", entry_type="class_method")
        self.assertEqual(len(methods), 1)
        self.assertEqual(methods[0].parent_class, "Calc")

    def test_an_arrow_function_stays_out_of_scope(self) -> None:
        self.write("arrow.js", JS_ARROW)

        # Known issue 3 in the module docstring: arrow functions are not parsed. This pins that
        # boundary so the fix is not mistaken for full JavaScript coverage.
        self.assertEqual(len(self.build().query_function("arrowSum")), 0)

    async def test_the_ckg_tool_finds_a_javascript_function(self) -> None:
        self.write("sum.js", JS_FUNCTION)

        tool = CKGTool()
        self.addCleanup(self.close_databases, tool)
        result = await tool.execute(
            ToolCallArguments(
                {
                    "command": "search_function",
                    "path": str(self.codebase),
                    "identifier": "topSum",
                }
            )
        )

        self.assertIsNone(result.error)
        output = result.output or ""
        self.assertIn("Found 1 functions named topSum:", output)

    def close_databases(self, tool: CKGTool) -> None:
        for database in tool._ckg_databases.values():
            with contextlib.suppress(Exception):
                database._db_connection.close()


if __name__ == "__main__":
    unittest.main()
