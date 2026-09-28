# Copyright (c) 2025 ByteDance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

"""The standalone JSON edit CLI must accept the null value it documents.

`--value` is parsed with `json.loads`, so a JSON null arrives as Python `None` -- the same object the
code used for "the flag was not passed". Every `set`/`add` call that asked to write null was then
reported as a call that forgot `--value`, with the identical message. The CLI is what the frozen
`json_edit_tool` binary is built from, so this is the answer the agent gets in Docker mode.
"""

import asyncio
import contextlib
import io
import json
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from trae_agent.tools.json_edit_tool_cli import amain


class JsonEditCliValueTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = TemporaryDirectory(prefix="json-edit-cli-")

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _file(self, payload: dict) -> Path:
        path = Path(self._tmp.name) / "state.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        return path

    def _run(self, argv: list[str]) -> tuple[int, str]:
        """Drive the CLI entry point with the given arguments, returning exit code and stderr."""
        errors = io.StringIO()
        with (
            mock.patch.object(sys, "argv", ["json_edit_tool", *argv]),
            contextlib.redirect_stdout(io.StringIO()),
            contextlib.redirect_stderr(errors),
        ):
            try:
                asyncio.run(amain())
            except SystemExit as exit_:
                return int(exit_.code or 0), errors.getvalue()
        raise AssertionError(f"the CLI did not exit: {argv}")

    def _set(self, value_arg: str | None, path: Path) -> tuple[int, str]:
        argv = ["--operation", "set", "--file_path", str(path), "--json_path", "$.name"]
        if value_arg is not None:
            argv += ["--value", value_arg]
        return self._run(argv)

    def test_null_is_written(self):
        path = self._file({"name": "old", "other": 1})
        code, _ = self._set("null", path)
        self.assertEqual(0, code)
        self.assertEqual({"name": None, "other": 1}, json.loads(path.read_text(encoding="utf-8")))

    def test_omitted_value_is_still_an_error(self):
        path = self._file({"name": "old", "other": 1})
        code, err = self._set(None, path)
        self.assertEqual(1, code)
        self.assertIn("--value are required", err)
        self.assertEqual({"name": "old", "other": 1}, json.loads(path.read_text(encoding="utf-8")))

    def test_other_json_values_are_unaffected(self):
        for value_arg, expected in [('"new"', "new"), ("0", 0), ("false", False)]:
            with self.subTest(value=value_arg):
                path = self._file({"name": "old", "other": 1})
                code, _ = self._set(value_arg, path)
                self.assertEqual(0, code)
                payload = json.loads(path.read_text(encoding="utf-8"))
                self.assertEqual(expected, payload["name"])

    def test_add_accepts_null(self):
        path = self._file({"name": "old"})
        code, _ = self._run(
            [
                "--operation",
                "add",
                "--file_path",
                str(path),
                "--json_path",
                "$.extra",
                "--value",
                "null",
            ]
        )
        self.assertEqual(0, code)
        self.assertEqual(
            {"name": "old", "extra": None}, json.loads(path.read_text(encoding="utf-8"))
        )


if __name__ == "__main__":
    unittest.main()
