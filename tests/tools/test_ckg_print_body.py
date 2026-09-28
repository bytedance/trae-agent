# Copyright (c) 2025 ByteDance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

"""`Tool.get_input_schema()` makes every optional parameter required and nullable for the `openai`
provider, so `print_body` is a parameter a strict-mode model must send and may send as `null`.
`CKGTool.execute` read it with `bool(...)`, which turns that legal `null` into `False` and a string
`"false"` into `True` -- in both directions the tool ignores what the caller asked for, and returns
`error=None` while doing it.

The codebase is a temp directory and the CKG cache is pointed into that same directory, so there is
no git history, no network and no key involved.
"""

import contextlib
import shutil
import tempfile
import unittest
from pathlib import Path
from typing import cast
from unittest import mock

from trae_agent.tools.base import ToolCallArguments, ToolExecResult
from trae_agent.tools.ckg import ckg_database as ckg_module
from trae_agent.tools.ckg_tool import CKGTool

PYTHON_SOURCE = "def topSum(a, b):\n    return a + b\n"
BODY_MARK = "def topSum"


class TestCKGPrintBodyDefault(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self._tmp_dir: str = tempfile.mkdtemp()
        self.tmp = Path(self._tmp_dir)
        self.codebase = self.tmp / "codebase"
        self.codebase.mkdir()
        self.cache = self.tmp / "ckg_cache"
        self.cache.mkdir()
        (self.codebase / "sample.py").write_text(PYTHON_SOURCE, encoding="utf-8")
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

    def tool(self, model_provider: str | None = None) -> CKGTool:
        instance = CKGTool(model_provider=model_provider)
        # Windows refuses to remove the temp tree while the sqlite handle is open.
        self.addCleanup(self.close_databases, instance)
        return instance

    def close_databases(self, instance: CKGTool) -> None:
        for database in instance._ckg_databases.values():
            with contextlib.suppress(Exception):
                database._db_connection.close()

    def param_schema(self, instance: CKGTool, name: str) -> dict[str, object]:
        properties = cast(dict[str, dict[str, object]], instance.get_input_schema()["properties"])
        return properties[name]

    def required_names(self, instance: CKGTool) -> list[str]:
        return cast(list[str], instance.get_input_schema()["required"])

    async def search(
        self, instance: CKGTool, extra: ToolCallArguments | None = None
    ) -> ToolExecResult:
        arguments = ToolCallArguments(
            {"command": "search_function", "path": str(self.codebase), "identifier": "topSum"}
        )
        if extra is not None:
            arguments.update(extra)
        return await instance.execute(arguments)

    def test_the_openai_schema_requires_print_body_and_allows_null(self) -> None:
        """This is the premise of the bug: the schema we hand to OpenAI invites a null."""
        instance = self.tool(model_provider="openai")
        self.assertIn("print_body", self.required_names(instance))
        self.assertEqual(["boolean", "null"], self.param_schema(instance, "print_body")["type"])

    def test_the_default_schema_leaves_print_body_optional_and_non_nullable(self) -> None:
        instance = self.tool()
        self.assertNotIn("print_body", self.required_names(instance))
        self.assertEqual("boolean", self.param_schema(instance, "print_body")["type"])

    async def test_an_omitted_print_body_prints_the_body(self) -> None:
        result = await self.search(self.tool(model_provider="openai"))
        self.assertIsNone(result.error)
        self.assertIn(BODY_MARK, result.output or "")

    async def test_a_null_print_body_keeps_the_documented_default(self) -> None:
        """The description says bodies are printed by default; null must not switch them off."""
        result = await self.search(
            self.tool(model_provider="openai"), ToolCallArguments({"print_body": None})
        )
        self.assertIsNone(result.error)
        self.assertIn(BODY_MARK, result.output or "")

    async def test_an_explicit_true_prints_the_body(self) -> None:
        result = await self.search(
            self.tool(model_provider="openai"), ToolCallArguments({"print_body": True})
        )
        self.assertIsNone(result.error)
        self.assertIn(BODY_MARK, result.output or "")

    async def test_an_explicit_false_hides_the_body(self) -> None:
        """Pinned so the fix cannot over-correct into always printing."""
        result = await self.search(
            self.tool(model_provider="openai"), ToolCallArguments({"print_body": False})
        )
        self.assertIsNone(result.error)
        self.assertNotIn(BODY_MARK, result.output or "")
        self.assertIn("topSum", result.output or "")

    async def test_a_string_value_is_reported_instead_of_guessed(self) -> None:
        result = await self.search(
            self.tool(model_provider="openai"), ToolCallArguments({"print_body": "false"})
        )
        self.assertEqual("print_body parameter must be a boolean.", result.error)
        self.assertEqual(-1, result.error_code)

    async def test_an_integer_value_is_reported_instead_of_guessed(self) -> None:
        result = await self.search(
            self.tool(model_provider="openai"), ToolCallArguments({"print_body": 0})
        )
        self.assertEqual("print_body parameter must be a boolean.", result.error)
        self.assertEqual(-1, result.error_code)


if __name__ == "__main__":
    unittest.main()
