# Copyright (c) 2025 ByteDance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

"""`Tool.get_input_schema()` makes every optional parameter required and nullable for the `openai`
provider, so `pretty_print` is a parameter a strict-mode model must send and may send as `null` --
while `JSONEditTool.execute` answered that exact value with `pretty_print parameter must be a
boolean.` and `error_code=-1`, failing the whole edit. Absent and `null` now both mean the
documented default (`true`); a non-boolean that is not `null` is still rejected.

These cases use a real temp file instead of `mock_open`, so the written bytes are checked too.
"""

import json
import shutil
import tempfile
import unittest
from pathlib import Path
from typing import cast

from trae_agent.tools.base import ToolCallArguments, ToolExecResult
from trae_agent.tools.json_edit_tool import JSONEditTool

INDENT_MARK = "\n  "
SAMPLE = {"config": {"enabled": True}, "users": [{"id": 1, "name": "Alice"}]}


class TestJSONEditPrettyPrintNull(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.path = self.tmp / "data.json"
        self.path.write_text(json.dumps(SAMPLE, indent=2), encoding="utf-8")

    def tool(self, model_provider: str | None = None) -> JSONEditTool:
        return JSONEditTool(model_provider=model_provider)

    def param_schema(self, instance: JSONEditTool, name: str) -> dict[str, object]:
        properties = cast(dict[str, dict[str, object]], instance.get_input_schema()["properties"])
        return properties[name]

    def required_names(self, instance: JSONEditTool) -> list[str]:
        return cast(list[str], instance.get_input_schema()["required"])

    async def invoke(
        self, instance: JSONEditTool, extra: ToolCallArguments | None = None
    ) -> ToolExecResult:
        arguments = ToolCallArguments({"operation": "view", "file_path": str(self.path)})
        if extra is not None:
            arguments.update(extra)
        return await instance.execute(arguments)

    def test_the_openai_schema_requires_pretty_print_and_allows_null(self) -> None:
        """This is the premise of the bug: the schema we hand to OpenAI invites a null."""
        instance = self.tool(model_provider="openai")
        self.assertIn("pretty_print", self.required_names(instance))
        self.assertEqual(["boolean", "null"], self.param_schema(instance, "pretty_print")["type"])

    def test_the_default_schema_leaves_pretty_print_optional_and_non_nullable(self) -> None:
        instance = self.tool()
        self.assertNotIn("pretty_print", self.required_names(instance))
        self.assertEqual("boolean", self.param_schema(instance, "pretty_print")["type"])

    async def test_view_with_null_pretty_print_keeps_the_documented_default(self) -> None:
        result = await self.invoke(
            self.tool(model_provider="openai"), ToolCallArguments({"pretty_print": None})
        )
        self.assertIsNone(result.error)
        self.assertEqual(0, result.error_code)
        self.assertIn(INDENT_MARK, result.output or "")

    async def test_set_with_null_pretty_print_keeps_the_documented_default(self) -> None:
        """The rejection is not view-specific: every operation failed on the same check."""
        instance = self.tool(model_provider="openai")
        result = await self.invoke(
            instance,
            ToolCallArguments(
                {
                    "operation": "set",
                    "json_path": "$.config.enabled",
                    "value": False,
                    "pretty_print": None,
                }
            ),
        )
        self.assertIsNone(result.error)
        self.assertEqual(0, result.error_code)
        self.assertIs(json.loads(self.path.read_text(encoding="utf-8"))["config"]["enabled"], False)
        self.assertIn(INDENT_MARK, self.path.read_text(encoding="utf-8"))

    async def test_view_with_omitted_pretty_print_is_indented(self) -> None:
        """Pinned so the null branch cannot be widened into always compacting."""
        result = await self.invoke(self.tool(model_provider="openai"))
        self.assertIsNone(result.error)
        self.assertIn(INDENT_MARK, result.output or "")

    async def test_view_with_explicit_true_is_indented(self) -> None:
        result = await self.invoke(
            self.tool(model_provider="openai"), ToolCallArguments({"pretty_print": True})
        )
        self.assertIsNone(result.error)
        self.assertIn(INDENT_MARK, result.output or "")

    async def test_view_with_explicit_false_is_compact(self) -> None:
        result = await self.invoke(
            self.tool(model_provider="openai"), ToolCallArguments({"pretty_print": False})
        )
        self.assertIsNone(result.error)
        self.assertNotIn(INDENT_MARK, result.output or "")

    async def test_a_string_pretty_print_is_still_rejected(self) -> None:
        """Only null changed meaning; a non-boolean that is not null stays an error."""
        result = await self.invoke(
            self.tool(model_provider="openai"), ToolCallArguments({"pretty_print": "false"})
        )
        self.assertEqual("pretty_print parameter must be a boolean.", result.error)
        self.assertEqual(-1, result.error_code)


if __name__ == "__main__":
    unittest.main()
