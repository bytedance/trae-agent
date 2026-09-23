# Copyright (c) 2025 ByteDance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

"""Tests that an edit leaves the indentation of untouched lines alone.

The file is read back through ``read_text`` because line terminators are a separate
matter (the write translates them with ``os.linesep``); here only tabs are at stake.
"""

import tempfile
import unittest
from pathlib import Path

from trae_agent.tools.edit_tool import TextEditorTool, expanded_char_origins

GO_SOURCE = "\n".join(f'\tfmt.Println("line {i}")' for i in range(30)) + "\n"


class TestIndentationSurvivesAnEdit(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.tool = TextEditorTool()

    def _file(self, name: str, text: str) -> Path:
        path = Path(self.tmp.name) / name
        path.write_text(text, encoding="utf-8", newline="\n")
        return path

    async def _str_replace(self, path: Path, old_str: str, new_str: str) -> None:
        result = await self.tool.execute(
            {"command": "str_replace", "path": str(path), "old_str": old_str, "new_str": new_str}
        )
        self.assertIsNone(result.error, result.error)

    async def test_a_replacement_keeps_every_other_lines_tabs(self):
        path = self._file("main.go", GO_SOURCE)

        await self._str_replace(path, "line 7", "line seven")

        expected = GO_SOURCE.replace('"line 7"', '"line seven"')
        self.assertEqual(path.read_text(encoding="utf-8"), expected)

    async def test_an_insertion_keeps_every_other_lines_tabs(self):
        path = self._file("main.go", GO_SOURCE)

        result = await self.tool.execute(
            {"command": "insert", "path": str(path), "insert_line": 3, "new_str": "// added"},
        )
        self.assertIsNone(result.error, result.error)

        lines = GO_SOURCE.split("\n")
        expected = "\n".join(lines[:3] + ["// added"] + lines[3:])
        self.assertEqual(path.read_text(encoding="utf-8"), expected)

    async def test_the_model_can_still_match_on_the_expanded_view_it_was_shown(self):
        source = "def f():\n\treturn 1\n\tpass\n"
        path = self._file("tabs.py", source)

        # `view` expands tabs, so the model quotes the indentation it saw rather than the
        # file's own tabs. The match still has to work -- and must not re-indent the rest.
        await self._str_replace(path, "        return 1", "        return 2")

        self.assertEqual(path.read_text(encoding="utf-8"), "def f():\n        return 2\n\tpass\n")

    async def test_a_match_that_covers_half_a_tab_consumes_the_whole_tab(self):
        path = self._file("tabs.py", "if x:\n\tvalue = 1\n")

        await self._str_replace(path, "    value = 1", "    result = 1")

        self.assertEqual(path.read_text(encoding="utf-8"), "if x:\n    result = 1\n")

    async def test_new_text_is_still_expanded_the_way_it_was_before(self):
        """Deliberately unchanged by the splice: only text outside the edit is preserved."""
        path = self._file("tabs.py", "def f():\n    pass\n")

        await self._str_replace(path, "    pass", "\tpass")

        self.assertEqual(path.read_text(encoding="utf-8"), "def f():\n        pass\n")


class TestExpandedCharOrigins(unittest.TestCase):
    """The splice is only sound while the map holds exactly one entry per expanded character."""

    def test_the_map_is_as_long_as_the_expanded_text(self):
        for text in (
            GO_SOURCE,
            "a\tb",
            "\t\t\n\t",
            "if x:\n\ty = 1\r\n\tz = 2\n",
            "no tabs here",
            "",
        ):
            with self.subTest(text=text):
                self.assertEqual(len(expanded_char_origins(text)), len(text.expandtabs()))
