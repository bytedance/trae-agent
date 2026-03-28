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

import json
from pathlib import Path
from typing import override

from trae_agent.tools.base import Tool, ToolCallArguments, ToolError, ToolExecResult, ToolParameter
from trae_agent.tools.run import maybe_truncate, run

EditToolSubCommands = [
    "view",
    "create",
    "str_replace",
    "insert",
]
SNIPPET_LINES: int = 4


class TextEditorTool(Tool):
    """Tool to replace a string in a file."""

    def __init__(self, model_provider: str | None = None) -> None:
        super().__init__(model_provider)

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
* If `path` is a Jupyter notebook (.ipynb), `view` displays the notebook cells with their types and source content, and `str_replace` edits cell source
* The `create` command cannot be used if the specified `path` already exists as a file !!! If you know that the `path` already exists, please remove it first and then perform the `create` operation!
* If a `command` generates a long output, it will be truncated and marked with `<response clipped>`

Notes for using the `str_replace` command:
* The `old_str` parameter should match EXACTLY one or more consecutive lines from the original file. Be mindful of whitespaces!
* If the `old_str` parameter is not unique in the file, the replacement will not be performed. Make sure to include enough context in `old_str` to make it unique
* The `new_str` parameter should contain the edited lines that should replace the `old_str`
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
                description="Required parameter of `create` command, with the content of the file to be created.",
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
                description="Required parameter of `str_replace` command containing the string in `path` to replace.",
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
        if not path.exists() and command != "create":
            raise ToolError(f"The path {path} does not exist. Please provide a valid path.")
        if path.exists() and command == "create":
            raise ToolError(
                f"File already exists at: {path}. Cannot overwrite files using command `create`."
            )
        # Check if the path points to a directory
        if path.is_dir() and command != "view":
            raise ToolError(
                f"The path {path} is a directory and only the `view` command can be used on directories"
            )

    def _is_notebook(self, path: Path) -> bool:
        """Check if the file is a Jupyter notebook."""
        return path.suffix == ".ipynb"

    def _read_notebook(self, path: Path) -> dict:
        """Read and parse a Jupyter notebook file."""
        try:
            content = path.read_text()
            return json.loads(content)
        except json.JSONDecodeError as e:
            raise ToolError(f"Invalid JSON in notebook file {path}: {e}") from None
        except Exception as e:
            raise ToolError(f"Error reading notebook {path}: {e}") from None

    def _write_notebook(self, path: Path, notebook: dict) -> None:
        """Write a Jupyter notebook to file."""
        try:
            path.write_text(json.dumps(notebook, indent=1, ensure_ascii=False) + "\n")
        except Exception as e:
            raise ToolError(f"Error writing notebook {path}: {e}") from None

    def _notebook_cells_to_text(self, notebook: dict) -> str:
        """Convert notebook cells to a readable text representation.

        Each cell is shown with a header indicating its type and index,
        followed by the cell source joined into lines.
        """
        lines: list[str] = []
        for i, cell in enumerate(notebook.get("cells", [])):
            cell_type = cell.get("cell_type", "unknown")
            source = cell.get("source", [])
            if isinstance(source, list):
                source_text = "".join(source)
            else:
                source_text = str(source)

            lines.append(f"{'─' * 40}")
            lines.append(f"Cell [{i + 1}] ({cell_type}):")
            lines.append(f"{'─' * 40}")
            lines.append(source_text)

        # Add execution count info for code cells
        lines.append(f"{'─' * 40}")
        lines.append(
            f"Total cells: {len(notebook.get('cells', []))}"
        )
        return "\n".join(lines)

    def _notebook_to_source_text(self, notebook: dict) -> str:
        """Convert notebook cells to a flat text representation for editing.

        Each cell's source is concatenated with a cell marker comment
        that identifies the cell type and index.  This allows the agent
        to use str_replace on the textual representation.
        """
        lines: list[str] = []
        for i, cell in enumerate(notebook.get("cells", [])):
            cell_type = cell.get("cell_type", "unknown")
            source = cell.get("source", [])
            if isinstance(source, list):
                source_lines = source
            else:
                source_lines = str(source).splitlines(keepends=True)

            lines.append(f"# %% Cell {i + 1} ({cell_type})\n")
            lines.extend(source_lines)
            if source_lines and not source_lines[-1].endswith("\n"):
                lines[-1] += "\n"
        return "".join(lines)

    def _apply_str_replace_to_notebook(
        self, path: Path, old_str: str, new_str: str | None
    ) -> ToolExecResult:
        """Apply str_replace on the concatenated source of all cells in a notebook."""
        notebook = self._read_notebook(path)
        full_text = self._notebook_to_source_text(notebook)

        occurrences = full_text.count(old_str)
        if occurrences == 0:
            raise ToolError(
                f"No replacement was performed, old_str `{old_str}` did not appear verbatim in notebook {path}."
            )
        elif occurrences > 1:
            full_text_lines = full_text.split("\n")
            matching_lines = [
                idx + 1 for idx, line in enumerate(full_text_lines) if old_str in line
            ]
            raise ToolError(
                f"No replacement was performed. Multiple occurrences of old_str `{old_str}` in lines {matching_lines}. Please ensure it is unique"
            )

        replacement = new_str if new_str is not None else ""
        new_full_text = full_text.replace(old_str, replacement)

        # Reconstruct notebook cells from the modified text
        self._reconstruct_notebook_from_text(notebook, new_full_text)
        self._write_notebook(path, notebook)

        # Build a snippet around the replacement
        replacement_line = full_text.split(old_str)[0].count("\n")
        start_line = max(0, replacement_line - SNIPPET_LINES)
        end_line = replacement_line + SNIPPET_LINES + replacement.count("\n")
        snippet = "\n".join(new_full_text.split("\n")[start_line : end_line + 1])

        success_msg = f"The notebook {path} has been edited. "
        success_msg += self._make_output(snippet, f"a snippet of {path}", start_line + 1)
        success_msg += "Review the changes and make sure they are as expected. Edit the file again if necessary."

        return ToolExecResult(output=success_msg)

    def _reconstruct_notebook_from_text(self, notebook: dict, text: str) -> None:
        """Reconstruct notebook cell sources from flat text with cell markers."""
        cells = notebook.get("cells", [])
        sections: list[tuple[int, list[str]]] = []

        current_cell_idx = -1
        current_lines: list[str] = []

        for line in text.split("\n"):
            # Check for cell marker: "# %% Cell N (type)"
            if line.startswith("# %% Cell "):
                if current_cell_idx >= 0 and current_cell_idx < len(cells):
                    sections.append((current_cell_idx, current_lines))
                try:
                    # Parse "# %% Cell N (type)"
                    rest = line[len("# %% Cell "):]
                    paren_idx = rest.index("(")
                    cell_num = int(rest[:paren_idx].strip())
                    current_cell_idx = cell_num - 1  # Convert to 0-indexed
                except (ValueError, IndexError):
                    current_cell_idx = -1
                current_lines = []
            else:
                current_lines.append(line)

        # Don't forget the last section
        if current_cell_idx >= 0 and current_cell_idx < len(cells):
            sections.append((current_cell_idx, current_lines))

        # Apply reconstructed source back to cells
        for cell_idx, source_lines in sections:
            if cell_idx < len(cells):
                # Re-add newlines that were stripped by split("\n")
                rebuilt = [ln + "\n" for ln in source_lines]
                if rebuilt:
                    rebuilt[-1] = rebuilt[-1].rstrip("\n")
                cells[cell_idx]["source"] = rebuilt

    async def _view(self, path: Path, view_range: list[int] | None = None) -> ToolExecResult:
        """Implement the view command"""
        if path.is_dir():
            if view_range:
                raise ToolError(
                    "The `view_range` parameter is not allowed when `path` points to a directory."
                )

            return_code, stdout, stderr = await run(rf"find {path} -maxdepth 2 -not -path '*/\.*'")
            if not stderr:
                stdout = f"Here's the files and directories up to 2 levels deep in {path}, excluding hidden items:\n{stdout}\n"
            return ToolExecResult(error_code=return_code, output=stdout, error=stderr)

        # Handle Jupyter notebooks specially
        if self._is_notebook(path):
            notebook = self._read_notebook(path)
            content = self._notebook_cells_to_text(notebook)
            return ToolExecResult(
                output=f"Here's the content of the Jupyter notebook {path}:\n{content}\n"
            )

        file_content = self.read_file(path)
        init_line = 1
        if view_range:
            if len(view_range) != 2 or not all(isinstance(i, int) for i in view_range):  # pyright: ignore[reportUnnecessaryIsInstance]
                raise ToolError("Invalid `view_range`. It should be a list of two integers.")
            file_lines = file_content.split("\n")
            n_lines_file = len(file_lines)
            init_line, final_line = view_range
            if init_line < 1 or init_line > n_lines_file:
                raise ToolError(
                    f"Invalid `view_range`: {view_range}. Its first element `{init_line}` should be within the range of lines of the file: {[1, n_lines_file]}"
                )
            if final_line > n_lines_file:
                raise ToolError(
                    f"Invalid `view_range`: {view_range}. Its second element `{final_line}` should be smaller than the number of lines in the file: `{n_lines_file}`"
                )
            if final_line != -1 and final_line < init_line:
                raise ToolError(
                    f"Invalid `view_range`: {view_range}. Its second element `{final_line}` should be larger or equal than its first `{init_line}`"
                )

            if final_line == -1:
                file_content = "\n".join(file_lines[init_line - 1 :])
            else:
                file_content = "\n".join(file_lines[init_line - 1 : final_line])

        return ToolExecResult(
            output=self._make_output(file_content, str(path), init_line=init_line)
        )

    def str_replace(self, path: Path, old_str: str, new_str: str | None) -> ToolExecResult:
        """Implement the str_replace command, which replaces old_str with new_str in the file content"""
        # Read the file content
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

        # Write the new content to the file
        self.write_file(path, new_file_content)

        # Create a snippet of the edited section
        replacement_line = file_content.split(old_str)[0].count("\n")
        start_line = max(0, replacement_line - SNIPPET_LINES)
        end_line = replacement_line + SNIPPET_LINES + new_str.count("\n")
        snippet = "\n".join(new_file_content.split("\n")[start_line : end_line + 1])

        # Prepare the success message
        success_msg = f"The file {path} has been edited. "
        success_msg += self._make_output(snippet, f"a snippet of {path}", start_line + 1)
        success_msg += "Review the changes and make sure they are as expected. Edit the file again if necessary."

        return ToolExecResult(
            output=success_msg,
        )

    def _insert(self, path: Path, insert_line: int, new_str: str) -> ToolExecResult:
        """Implement the insert command, which inserts new_str at the specified line in the file content."""
        file_text = self.read_file(path).expandtabs()
        new_str = new_str.expandtabs()
        file_text_lines = file_text.split("\n")
        n_lines_file = len(file_text_lines)

        if insert_line < 0 or insert_line > n_lines_file:
            raise ToolError(
                f"Invalid `insert_line` parameter: {insert_line}. It should be within the range of lines of the file: {[0, n_lines_file]}"
            )

        new_str_lines = new_str.split("\n")
        new_file_text_lines = (
            file_text_lines[:insert_line] + new_str_lines + file_text_lines[insert_line:]
        )
        snippet_lines = (
            file_text_lines[max(0, insert_line - SNIPPET_LINES) : insert_line]
            + new_str_lines
            + file_text_lines[insert_line : insert_line + SNIPPET_LINES]
        )

        new_file_text = "\n".join(new_file_text_lines)
        snippet = "\n".join(snippet_lines)

        self.write_file(path, new_file_text)

        success_msg = f"The file {path} has been edited. "
        success_msg += self._make_output(
            snippet,
            "a snippet of the edited file",
            max(1, insert_line - SNIPPET_LINES + 1),
        )
        success_msg += "Review the changes and make sure they are as expected (correct indentation, no duplicate lines, etc). Edit the file again if necessary."
        return ToolExecResult(
            output=success_msg,
        )

    # Note: undo_edit method is not implemented in this version as it was removed

    def read_file(self, path: Path):
        """Read the content of a file from a given path; raise a ToolError if an error occurs."""
        try:
            return path.read_text()
        except Exception as e:
            raise ToolError(f"Ran into {e} while trying to read {path}") from None

    def write_file(self, path: Path, file: str):
        """Write the content of a file to a given path; raise a ToolError if an error occurs."""
        try:
            _ = path.write_text(file)
        except Exception as e:
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
        # Handle Jupyter notebooks specially
        if self._is_notebook(_path):
            return self._apply_str_replace_to_notebook(_path, old_str, new_str)
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
