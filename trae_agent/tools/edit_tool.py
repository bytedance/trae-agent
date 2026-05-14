# Copyright (c) 2023 Anthropic
# Copyright (c) 2025 ByteDance Ltd. and/or its affiliates.
# SPDX-License-Identifier: MIT
#
# This file has been modified by ByteDance Ltd. and/or its affiliates. on 13 June 2025
#
# Original file was released under MIT License, with the full license text
# available at https://github.com/anthropics/anthropic-quickstarts/blob/main/LICENSE
#
# This modified file is released under the same license.

import os
import tempfile
from contextlib import suppress
from pathlib import Path
from typing import override

from trae_agent.tools.base import Tool, ToolCallArguments, ToolError, ToolExecResult, ToolParameter
from trae_agent.tools.edit_utils import fuzzy_match_and_replace
from trae_agent.tools.run import maybe_truncate, run

EditToolSubCommands = [
    "view",
    "create",
    "str_replace",
    "insert",
    "search_replace",
    "write",
]
SNIPPET_LINES: int = 4


class TextEditorTool(Tool):
    """Tool to view, create and edit files."""

    def __init__(self, model_provider: str | None = None) -> None:
        super().__init__(model_provider)
        # Tracks line-count changes per file path so that LLM-provided line
        # numbers (from a previous *view*) can be mapped to the current state.
        #   path -> list of (edit_start_line_1based, delta)
        self._line_offset_tracker: dict[str, list[tuple[int, int]]] = {}

    @override
    def get_model_provider(self) -> str | None:
        return self._model_provider

    @override
    def get_name(self) -> str:
        return "str_replace_based_edit_tool"

    @override
    def get_description(self) -> str:
        return """Custom editing tool for viewing, creating and editing files
* State is persistent across command calls and discussions with the user
* If `path` is a file, `view` displays the result of applying `cat -n`. If `path` is a directory, `view` lists non-hidden files and directories up to 2 levels deep
* The `create` command cannot be used if the specified `path` already exists as a file !!! If you know that the `path` already exists, please remove it first and then perform the `create` operation!
* If a `command` generates a long output, it will be truncated and marked with `<response clipped>`

Notes for using the `str_replace` command (deprecated, use `search_replace` instead):
* The `old_str` parameter should match EXACTLY one or more consecutive lines from the original file. Be mindful of whitespaces!
* If the `old_str` parameter is not unique in the file, the replacement will not be performed. Make sure to include enough context in `old_str` to make it unique
* The `new_str` parameter should contain the edited lines that should replace the `old_str`

Notes for using the `search_replace` command (recommended):
* The `search_block` parameter is matched fuzzily against the file content, meaning minor whitespace differences (indentation, trailing spaces, blank-line count) are tolerated
* By default the engine tries an exact normalised match first, then falls back to fuzzy similarity (SequenceMatcher, threshold >= 85 %)
* If `match_mode` is set to ``"exact"``, only exact normalised matches are accepted; ``"fuzzy"`` skips the exact attempt and goes straight to fuzzy
* When multiple similar regions exist, the one whose surrounding context best matches the boundaries of `search_block` is selected automatically
"""

    @override
    def get_parameters(self) -> list[ToolParameter]:
        """Get the parameters for the str_replace_based_edit_tool."""
        return [
            ToolParameter(
                name="command",
                type="string",
                description=f"The commands to run. Allowed options are: {', '.join(EditToolSubCommands)}.",
                required=True,
                enum=EditToolSubCommands,
            ),
            ToolParameter(
                name="file_text",
                type="string",
                description="Required parameter of `create` and `write` commands, with the content of the file to be created / written.",
            ),
            ToolParameter(
                name="insert_line",
                type="integer",
                description="Required parameter of `insert` command. The `new_str` will be inserted AFTER the line `insert_line` of `path`.",
            ),
            ToolParameter(
                name="new_str",
                type="string",
                description="Optional parameter of `str_replace` command containing the new string (if not given, no string will be added). Required parameter of `insert` command containing the string to insert.",
            ),
            ToolParameter(
                name="old_str",
                type="string",
                description="(Deprecated) Required parameter of `str_replace` command containing the string in `path` to replace.",
            ),
            ToolParameter(
                name="path",
                type="string",
                description="Absolute path to file or directory, e.g. `/repo/file.py` or `/repo`.",
                required=True,
            ),
            ToolParameter(
                name="view_range",
                type="array",
                description="Optional parameter of `view` command when `path` points to a file. If none is given, the full file is shown. If provided, the file will be shown in the indicated line number range, e.g. [11, 12] will show lines 11 and 12. Indexing at 1 to start. Setting `[start_line, -1]` shows all lines from `start_line` to the end of the file.",
                items={"type": "integer"},
            ),
            # --- search_replace parameters ---
            ToolParameter(
                name="search_block",
                type="string",
                description="Required parameter of `search_replace` command. The block of text to search for (fuzzy-matched).",
            ),
            ToolParameter(
                name="replace_block",
                type="string",
                description="Required parameter of `search_replace` command. The replacement text.",
            ),
            ToolParameter(
                name="match_mode",
                type="string",
                description="Optional parameter of `search_replace` command. One of `auto` (default), `exact`, or `fuzzy`.",
                enum=["auto", "exact", "fuzzy"],
            ),
        ]

    @override
    async def execute(self, arguments: ToolCallArguments) -> ToolExecResult:
        """Execute the str_replace_editor tool."""
        command = str(arguments["command"]) if "command" in arguments else None
        if command is None:
            return ToolExecResult(
                error=f"No command provided for the {self.get_name()} tool",
                error_code=-1,
            )
        path = str(arguments["path"]) if "path" in arguments else None
        if path is None:
            return ToolExecResult(
                error=f"No path provided for the {self.get_name()} tool", error_code=-1
            )
        _path = Path(path)
        try:
            self.validate_path(command, _path)
            match command:
                case "view":
                    return await self._view_handler(arguments, _path)
                case "create":
                    return self._create_handler(arguments, _path)
                case "str_replace":
                    return self._str_replace_handler(arguments, _path)
                case "insert":
                    return self._insert_handler(arguments, _path)
                case "search_replace":
                    return self._search_replace_handler(arguments, _path)
                case "write":
                    return self._write_handler(arguments, _path)
                case _:
                    return ToolExecResult(
                        error=f"Unrecognized command {command}. The allowed commands for the {self.name} tool are: {', '.join(EditToolSubCommands)}",
                        error_code=-1,
                    )
        except ToolError as e:
            return ToolExecResult(error=str(e), error_code=-1)

    def validate_path(self, command: str, path: Path):
        """Validate the path for the str_replace_editor tool."""
        if not path.is_absolute():
            suggested_path = Path("/") / path
            raise ToolError(
                f"The path {path} is not an absolute path, it should start with `/`. Maybe you meant {suggested_path}?"
            )
        # Check if path exists
        if not path.exists() and command not in ("create", "write"):
            raise ToolError(f"The path {path} does not exist. Please provide a valid path.")
        if path.exists() and command == "create":
            raise ToolError(
                f"File already exists at: {path}. Cannot overwrite files using command `create`. Use `write` instead."
            )
        # Check if the path points to a directory
        if path.is_dir() and command not in ("view", "write"):
            raise ToolError(
                f"The path {path} is a directory and only the `view` command can be used on directories"
            )

    # ── Line offset tracking ────────────────────────────────────────────

    def _record_line_change(self, path: str, start_line: int, delta: int) -> None:
        """Record a line-count change starting at *start_line* (1-based).

        *delta* is positive for insertions, negative for deletions.
        """
        if path not in self._line_offset_tracker:
            self._line_offset_tracker[path] = []
        self._line_offset_tracker[path].append((start_line, delta))

    def _adjust_line_number(self, path: str, original_line: int) -> int:
        """Map an LLM-provided (1-based) line number to the current file state.

        Applies all tracked offsets whose edit-start line is <= the target line.
        """
        for edit_line, delta in self._line_offset_tracker.get(path, []):
            if edit_line <= original_line:
                original_line += delta
        return max(1, original_line)

    def _adjust_view_range(self, path: str, view_range: list[int]) -> list[int]:
        """Adjust both bounds of a view range for tracked line offsets.

        A ``final_line`` of -1 (view to end of file) is preserved unchanged.
        """
        adjusted_start = self._adjust_line_number(path, view_range[0])
        adjusted_end = (
            view_range[1] if view_range[1] == -1 else self._adjust_line_number(path, view_range[1])
        )
        return [adjusted_start, adjusted_end]

    # ── View ────────────────────────────────────────────────────────────

    async def _view(self, path: Path, view_range: list[int] | None = None) -> ToolExecResult:
        """Implement the view command."""
        path_str = str(path)

        if path.is_dir():
            if view_range:
                raise ToolError(
                    "The `view_range` parameter is not allowed when `path` points to a directory."
                )

            return_code, stdout, stderr = await run(rf"find {path} -maxdepth 2 -not -path '*/\.*'")
            if not stderr:
                stdout = f"Here's the files and directories up to 2 levels deep in {path}, excluding hidden items:\n{stdout}\n"
            return ToolExecResult(error_code=return_code, output=stdout, error=stderr)

        file_content = self.read_file(path)
        init_line = 1
        if view_range:
            if len(view_range) != 2 or not all(isinstance(i, int) for i in view_range):
                raise ToolError("Invalid `view_range`. It should be a list of two integers.")

            # Adjust line numbers from LLM reference frame to current state
            adjusted_range = self._adjust_view_range(path_str, view_range)
            adjusted_start, adjusted_end = adjusted_range

            file_lines = file_content.split("\n")
            n_lines_file = len(file_lines)

            if adjusted_start < 1 or adjusted_start > n_lines_file:
                raise ToolError(
                    f"Invalid `view_range`: {view_range}. Its first element `{view_range[0]}` should be within the range of lines of the file: {[1, n_lines_file]}"
                )

            init_line = adjusted_start

            if adjusted_end == -1:
                # Show from start to end of file
                file_content = "\n".join(file_lines[adjusted_start - 1 :])
            else:
                if adjusted_end > n_lines_file:
                    raise ToolError(
                        f"Invalid `view_range`: {view_range}. Its second element `{view_range[1]}` should be smaller than the number of lines in the file: `{n_lines_file}`"
                    )
                if adjusted_end < adjusted_start:
                    raise ToolError(
                        f"Invalid `view_range`: {view_range}. Its second element `{view_range[1]}` should be larger or equal than its first `{view_range[0]}`"
                    )
                file_content = "\n".join(file_lines[adjusted_start - 1 : adjusted_end])

        return ToolExecResult(
            output=self._make_output(file_content, str(path), init_line=init_line)
        )

    # ── str_replace (deprecated) ────────────────────────────────────────

    # TODO(): Remove once all callers migrate to search_replace
    def str_replace(self, path: Path, old_str: str, new_str: str | None) -> ToolExecResult:
        """Implement the str_replace command (deprecated, use search_replace instead)."""
        file_content = self.read_file(path).expandtabs()
        old_str = old_str.expandtabs()
        new_str = new_str.expandtabs() if new_str is not None else ""

        # Check if old_str is unique in the file
        occurrences = file_content.count(old_str)
        if occurrences == 0:
            raise ToolError(
                f"No replacement was performed, old_str `{old_str}` did not appear verbatim in {path}."
            )
        elif occurrences > 1:
            file_content_lines = file_content.split("\n")
            lines = [idx + 1 for idx, line in enumerate(file_content_lines) if old_str in line]
            raise ToolError(
                f"No replacement was performed. Multiple occurrences of old_str `{old_str}` in lines {lines}. Please ensure it is unique"
            )

        # Replace old_str with new_str
        new_file_content = file_content.replace(old_str, new_str)

        # Track offset: find the first line where the replacement happens
        replacement_line_0based = file_content.split(old_str)[0].count("\n")
        old_line_count = old_str.count("\n") + 1
        new_line_count = new_str.count("\n") + 1
        delta = new_line_count - old_line_count
        if delta != 0:
            self._record_line_change(str(path), replacement_line_0based + 1, delta)

        self.write_file(path, new_file_content)

        # Create a snippet of the edited section
        start_line = max(0, replacement_line_0based - SNIPPET_LINES)
        end_line = replacement_line_0based + SNIPPET_LINES + new_str.count("\n")
        snippet = "\n".join(new_file_content.split("\n")[start_line : end_line + 1])

        success_msg = f"The file {path} has been edited. "
        success_msg += self._make_output(snippet, f"a snippet of {path}", start_line + 1)
        success_msg += "Review the changes and make sure they are as expected. Edit the file again if necessary."

        return ToolExecResult(output=success_msg)

    # ── search_replace (new) ────────────────────────────────────────────

    def _search_replace_handler(self, arguments: ToolCallArguments, _path: Path) -> ToolExecResult:
        search_block = arguments.get("search_block")
        replace_block = arguments.get("replace_block")

        if not isinstance(search_block, str):
            return ToolExecResult(
                error="Parameter `search_block` is required and must be a string for command: search_replace",
                error_code=-1,
            )
        if not isinstance(replace_block, str):
            return ToolExecResult(
                error="Parameter `replace_block` is required and must be a string for command: search_replace",
                error_code=-1,
            )

        match_mode = arguments.get("match_mode", "auto")
        if match_mode not in ("auto", "exact", "fuzzy"):
            match_mode = "auto"

        file_content = self.read_file(_path)
        new_content, success, msg, removed, added = fuzzy_match_and_replace(
            file_content,
            search_block,
            replace_block,
            match_mode,  # type: ignore[arg-type]
        )

        if not success:
            return ToolExecResult(error=msg, error_code=-1)

        # Track line offset for the replacement
        delta = added - removed
        if delta != 0:
            # Estimate the start line from the diff between original and new content
            # Find the first differing line between old and new content at the
            # replacement site
            old_lines = file_content.split("\n")
            new_lines = new_content.split("\n")
            for i, (o, n) in enumerate(zip(old_lines, new_lines, strict=False)):
                if o != n:
                    self._record_line_change(str(_path), i + 1, delta)
                    break

        self.write_file(_path, new_content)

        success_msg = f"The file {_path} has been edited. {msg}\n"
        snippet_lines = new_content.split("\n")
        snippet_len = min(SNIPPET_LINES * 2 + added, len(snippet_lines))
        snippet = "\n".join(snippet_lines[:snippet_len])
        success_msg += self._make_output(snippet, f"a snippet of {_path}", init_line=1)
        success_msg += "Review the changes and make sure they are as expected. Edit the file again if necessary."
        return ToolExecResult(output=success_msg)

    # ── write (new, full-file overwrite) ────────────────────────────────

    def _write_handler(self, arguments: ToolCallArguments, _path: Path) -> ToolExecResult:
        file_text = arguments.get("file_text")
        if not isinstance(file_text, str):
            return ToolExecResult(
                error="Parameter `file_text` is required and must be a string for command: write",
                error_code=-1,
            )
        # Full overwrite invalidates any previous line tracking
        self._line_offset_tracker.pop(str(_path), None)
        self.write_file(_path, file_text)
        return ToolExecResult(output=f"File written successfully at: {_path}")

    # ── insert ──────────────────────────────────────────────────────────

    def _insert(self, path: Path, insert_line: int, new_str: str) -> ToolExecResult:
        """Implement the insert command."""
        path_str = str(path)

        # Adjust the LLM-provided line number for previous edits
        adjusted_line = self._adjust_line_number(path_str, insert_line)

        file_text = self.read_file(path).expandtabs()
        new_str = new_str.expandtabs()
        file_text_lines = file_text.split("\n")
        n_lines_file = len(file_text_lines)

        if adjusted_line < 0 or adjusted_line > n_lines_file:
            raise ToolError(
                f"Invalid `insert_line` parameter: {insert_line} (adjusted to {adjusted_line}). It should be within the range of lines of the file: {[0, n_lines_file]}"
            )

        new_str_lines = new_str.split("\n")
        new_file_text_lines = (
            file_text_lines[:adjusted_line] + new_str_lines + file_text_lines[adjusted_line:]
        )
        snippet_lines = (
            file_text_lines[max(0, adjusted_line - SNIPPET_LINES) : adjusted_line]
            + new_str_lines
            + file_text_lines[adjusted_line : adjusted_line + SNIPPET_LINES]
        )

        new_file_text = "\n".join(new_file_text_lines)
        snippet = "\n".join(snippet_lines)

        # Track offset
        delta = len(new_str_lines)
        if delta != 0:
            self._record_line_change(path_str, adjusted_line + 1, delta)

        self.write_file(path, new_file_text)

        success_msg = f"The file {path} has been edited. "
        success_msg += self._make_output(
            snippet,
            "a snippet of the edited file",
            max(1, adjusted_line - SNIPPET_LINES + 1),
        )
        success_msg += "Review the changes and make sure they are as expected (correct indentation, no duplicate lines, etc). Edit the file again if necessary."
        return ToolExecResult(output=success_msg)

    # Note: undo_edit method is not implemented in this version as it was removed

    def read_file(self, path: Path) -> str:
        """Read the content of a file from a given path; raise a ToolError if an error occurs."""
        try:
            return path.read_text()
        except Exception as e:
            raise ToolError(f"Ran into {e} while trying to read {path}") from None

    def write_file(self, path: Path, file: str) -> None:
        """Atomically write content to a file using a temporary file + os.replace().

        This prevents partial writes from corrupting the file in case of an
        interruption during the write.
        """
        fd, tmp_path_str = tempfile.mkstemp(dir=str(path.parent), prefix=f".{path.name}.")
        os.close(fd)
        tmp_path = Path(tmp_path_str)
        try:
            tmp_path.write_text(file)
            os.replace(str(tmp_path), str(path))
        except Exception as e:
            with suppress(Exception):
                tmp_path.unlink()
            raise ToolError(f"Ran into {e} while trying to write to {path}") from None

    def _make_output(
        self,
        file_content: str,
        file_descriptor: str,
        init_line: int = 1,
        expand_tabs: bool = True,
    ):
        """Generate output for the CLI based on the content of a file."""
        file_content = maybe_truncate(file_content)
        if expand_tabs:
            file_content = file_content.expandtabs()
        file_content = "\n".join(
            [f"{i + init_line:6}\t{line}" for i, line in enumerate(file_content.split("\n"))]
        )
        return (
            f"Here's the result of running `cat -n` on {file_descriptor}:\n" + file_content + "\n"
        )

    async def _view_handler(self, arguments: ToolCallArguments, _path: Path) -> ToolExecResult:
        view_range = arguments.get("view_range", None)
        if view_range is None:
            return await self._view(_path, None)
        if not (isinstance(view_range, list) and all(isinstance(i, int) for i in view_range)):
            return ToolExecResult(
                error="Parameter `view_range` should be a list of integers.",
                error_code=-1,
            )
        view_range_int: list[int] = [i for i in view_range if isinstance(i, int)]
        return await self._view(_path, view_range_int)

    def _create_handler(self, arguments: ToolCallArguments, _path: Path) -> ToolExecResult:
        file_text = arguments.get("file_text", None)
        if not isinstance(file_text, str):
            return ToolExecResult(
                error="Parameter `file_text` is required and must be a string for command: create",
                error_code=-1,
            )
        self.write_file(_path, file_text)
        return ToolExecResult(output=f"File created successfully at: {_path}")

    # TODO(): Remove once all callers migrate to search_replace
    def _str_replace_handler(self, arguments: ToolCallArguments, _path: Path) -> ToolExecResult:
        old_str = arguments.get("old_str") if "old_str" in arguments else None
        if not isinstance(old_str, str):
            return ToolExecResult(
                error="Parameter `old_str` is required and should be a string for command: str_replace",
                error_code=-1,
            )
        new_str = arguments.get("new_str") if "new_str" in arguments else None
        if not (new_str is None or isinstance(new_str, str)):
            return ToolExecResult(
                error="Parameter `new_str` should be a string or null for command: str_replace",
                error_code=-1,
            )
        return self.str_replace(_path, old_str, new_str)

    def _insert_handler(self, arguments: ToolCallArguments, _path: Path) -> ToolExecResult:
        insert_line = arguments.get("insert_line") if "insert_line" in arguments else None
        if not isinstance(insert_line, int):
            return ToolExecResult(
                error="Parameter `insert_line` is required and should be integer for command: insert",
                error_code=-1,
            )
        new_str_to_insert = arguments.get("new_str") if "new_str" in arguments else None
        if not isinstance(new_str_to_insert, str):
            return ToolExecResult(
                error="Parameter `new_str` is required for command: insert",
                error_code=-1,
            )
        return self._insert(_path, insert_line, new_str_to_insert)
