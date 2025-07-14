# Copyright (c) 2025 ByteDance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

"""JSON editing tool for structured JSON file modifications."""

import json
from pathlib import Path
from typing import override

from jsonpath_ng import Fields, Index
from jsonpath_ng import parse as jsonpath_parse
from jsonpath_ng.exceptions import JSONPathError

from .base import Tool, ToolCallArguments, ToolError, ToolExecResult, ToolParameter


class JSONEditTool(Tool):
    """Tool for editing JSON files using JSONPath expressions."""

    def __init__(self, model_provider: str | None = None) -> None:
        super().__init__(model_provider)

    @override
    def get_model_provider(self) -> str | None:
        return self._model_provider

    @override
    def get_name(self) -> str:
        return "json_edit_tool"

    @override
    def get_description(self) -> str:
        return """Tool for editing JSON files with JSONPath expressions
* Supports targeted modifications to JSON structures using JSONPath syntax
* Operations: view, set, add, remove
* JSONPath examples: '$.users[0].name', '$.config.database.host', '$.items[*].price'
* Safe JSON parsing and validation with detailed error messages
* Preserves JSON formatting where possible

Operation details:
- `view`: Display JSON content or specific paths
- `set`: Update existing values at specified paths
- `add`: Add new key-value pairs (for objects) or append to arrays
- `remove`: Delete elements at specified paths

JSONPath syntax supported:
- `$` - root element
- `.key` - object property access
- `[index]` - array index access
- `[*]` - all elements in array/object
- `..key` - recursive descent (find key at any level)
- `[start:end]` - array slicing
"""

    @override
    def get_parameters(self) -> list[ToolParameter]:
        """Get the parameters for the JSON edit tool."""
        return [
            ToolParameter(
                name="operation",
                type="string",
                description="The operation to perform on the JSON file.",
                required=True,
                enum=["view", "set", "add", "remove"],
            ),
            ToolParameter(
                name="file_path",
                type="string",
                description="The full, ABSOLUTE path to the JSON file to edit. You MUST combine the [Project root path] with the file's relative path to construct this. Relative paths are NOT allowed.",
                required=True,
            ),
            ToolParameter(
                name="json_path",
                type="string",
                description="JSONPath expression to specify the target location (e.g., '$.users[0].name', '$.config.database'). Required for set, add, and remove operations. Optional for view to show specific paths.",
                required=False,
            ),
            ToolParameter(
                name="value",
                type="object",
                description="The value to set or add. Must be JSON-serializable. Required for set and add operations.",
                required=False,
            ),
            ToolParameter(
                name="pretty_print",
                type="boolean",
                description="Whether to format the JSON output with proper indentation. Defaults to true.",
                required=False,
            ),
        ]

    @override
    async def execute(self, arguments: ToolCallArguments) -> ToolExecResult:
        """Execute the JSON edit operation."""
        try:
            operation = str(arguments.get("operation", "")).lower()
            if not operation:
                return ToolExecResult(error="Operation parameter is required", error_code=-1)

            file_path_str = str(arguments.get("file_path", ""))
            if not file_path_str:
                return ToolExecResult(error="file_path parameter is required", error_code=-1)

            file_path = Path(file_path_str)
            if not file_path.is_absolute():
                return ToolExecResult(
                    error=f"File path must be absolute: {file_path}", error_code=-1
                )

            json_path_arg = arguments.get("json_path")
            if json_path_arg is not None and not isinstance(json_path_arg, str):
                return ToolExecResult(error="json_path parameter must be a string.", error_code=-1)

            value = arguments.get("value")

            pretty_print_arg = arguments.get("pretty_print", True)
            if not isinstance(pretty_print_arg, bool):
                return ToolExecResult(
                    error="pretty_print parameter must be a boolean.", error_code=-1
                )

            if operation == "view":
                return await self._view_json(file_path, json_path_arg, pretty_print_arg)

            if not isinstance(json_path_arg, str):
                return ToolExecResult(
                    error=f"json_path parameter is required and must be a string for the '{operation}' operation.",
                    error_code=-1,
                )

            if operation in ["set", "add"]:
                if value is None:
                    return ToolExecResult(
                        error=f"A 'value' parameter is required for the '{operation}' operation.",
                        error_code=-1,
                    )
                if operation == "set":
                    return await self._set_json_value(
                        file_path, json_path_arg, value, pretty_print_arg
                    )
                else:  # operation == "add"
                    return await self._add_json_value(
                        file_path, json_path_arg, value, pretty_print_arg
                    )

            if operation == "remove":
                return await self._remove_json_value(file_path, json_path_arg, pretty_print_arg)

            return ToolExecResult(
                error=f"Unknown operation: {operation}. Supported operations: view, set, add, remove",
                error_code=-1,
            )

        except Exception as e:
            return ToolExecResult(error=f"JSON edit tool error: {str(e)}", error_code=-1)

    async def _load_json_file(self, file_path: Path) -> dict | list:
        """Load and parse JSON file."""
        if not file_path.exists():
            raise ToolError(f"File does not exist: {file_path}")

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read().strip()
                if not content:
                    raise ToolError(f"File is empty: {file_path}")
                return json.loads(content)
        except json.JSONDecodeError as e:
            raise ToolError(f"Invalid JSON in file {file_path}: {str(e)}") from e
        except Exception as e:
            raise ToolError(f"Error reading file {file_path}: {str(e)}") from e

    async def _save_json_file(
        self, file_path: Path, data: dict | list, pretty_print: bool = True
    ) -> None:
        """Save JSON data to file."""
        try:
            with open(file_path, "w", encoding="utf-8") as f:
                if pretty_print:
                    json.dump(data, f, indent=2, ensure_ascii=False)
                else:
                    json.dump(data, f, ensure_ascii=False)
        except Exception as e:
            raise ToolError(f"Error writing to file {file_path}: {str(e)}") from e

    def _parse_jsonpath(self, json_path_str: str):
        """Parse JSONPath expression with error handling."""
        try:
            return jsonpath_parse(json_path_str)
        except JSONPathError as e:
            raise ToolError(f"Invalid JSONPath expression '{json_path_str}': {str(e)}") from e
        except Exception as e:
            raise ToolError(f"Error parsing JSONPath '{json_path_str}': {str(e)}") from e

    async def _view_json(
        self, file_path: Path, json_path_str: str | None, pretty_print: bool
    ) -> ToolExecResult:
        """View JSON file content or specific paths."""
        data = await self._load_json_file(file_path)

        if json_path_str:
            jsonpath_expr = self._parse_jsonpath(json_path_str)
            matches = jsonpath_expr.find(data)

            if not matches:
                return ToolExecResult(output=f"No matches found for JSONPath: {json_path_str}")

            result_data = [match.value for match in matches]
            if len(result_data) == 1:
                result_data = result_data[0]

            if pretty_print:
                output = json.dumps(result_data, indent=2, ensure_ascii=False)
            else:
                output = json.dumps(result_data, ensure_ascii=False)

            return ToolExecResult(output=f"JSONPath '{json_path_str}' matches:\n{output}")
        else:
            if pretty_print:
                output = json.dumps(data, indent=2, ensure_ascii=False)
            else:
                output = json.dumps(data, ensure_ascii=False)

            return ToolExecResult(output=f"JSON content of {file_path}:\n{output}")

    async def _set_json_value(
        self, file_path: Path, json_path_str: str, value, pretty_print: bool
    ) -> ToolExecResult:
        """Set value at specified JSONPath."""
        data = await self._load_json_file(file_path)
        jsonpath_expr = self._parse_jsonpath(json_path_str)

        matches = jsonpath_expr.find(data)
        if not matches:
            return ToolExecResult(
                error=f"No matches found for JSONPath: {json_path_str}", error_code=-1
            )

        updated_data = jsonpath_expr.update(data, value)
        await self._save_json_file(file_path, updated_data, pretty_print)

        match_count = len(matches)
        return ToolExecResult(
            output=f"Successfully updated {match_count} location(s) at JSONPath '{json_path_str}' with value: {json.dumps(value)}"
        )

    async def _add_json_value(
        self, file_path: Path, json_path_str: str, value, pretty_print: bool
    ) -> ToolExecResult:
        """Add value at specified JSONPath."""
        data = await self._load_json_file(file_path)
        jsonpath_expr = self._parse_jsonpath(json_path_str)

        parent_path = jsonpath_expr.left
        target = jsonpath_expr.right

        parent_matches = parent_path.find(data)
        if not parent_matches:
            return ToolExecResult(error=f"Parent path not found: {parent_path}", error_code=-1)

        for match in parent_matches:
            parent_obj = match.value
            if isinstance(target, Fields):
                if not isinstance(parent_obj, dict):
                    return ToolExecResult(
                        error=f"Cannot add key to non-object at path: {parent_path}",
                        error_code=-1,
                    )
                key_to_add = target.fields[0]
                parent_obj[key_to_add] = value
            elif isinstance(target, Index):
                if not isinstance(parent_obj, list):
                    return ToolExecResult(
                        error=f"Cannot add element to non-array at path: {parent_path}",
                        error_code=-1,
                    )
                index_to_add = target.index
                parent_obj.insert(index_to_add, value)
            else:
                return ToolExecResult(
                    error=f"Unsupported add operation for path type: {type(target)}. Path must end in a key or array index.",
                    error_code=-1,
                )

        await self._save_json_file(file_path, data, pretty_print)
        return ToolExecResult(output=f"Successfully added value at JSONPath '{json_path_str}'")

    async def _remove_json_value(
        self, file_path: Path, json_path_str: str, pretty_print: bool
    ) -> ToolExecResult:
        """Remove value at specified JSONPath."""
        data = await self._load_json_file(file_path)
        jsonpath_expr = self._parse_jsonpath(json_path_str)

        matches = jsonpath_expr.find(data)
        if not matches:
            return ToolExecResult(
                error=f"No matches found for JSONPath: {json_path_str}", error_code=-1
            )
        match_count = len(matches)

        for match in reversed(matches):
            parent_path = match.full_path.left
            target = match.path

            parent_matches = parent_path.find(data)
            if not parent_matches:
                continue

            for parent_match in parent_matches:
                parent_obj = parent_match.value
                try:
                    if isinstance(target, Fields):
                        key_to_remove = target.fields[0]
                        if isinstance(parent_obj, dict) and key_to_remove in parent_obj:
                            del parent_obj[key_to_remove]
                    elif isinstance(target, Index):
                        index_to_remove = target.index
                        if isinstance(parent_obj, list) and -len(
                            parent_obj
                        ) <= index_to_remove < len(parent_obj):
                            parent_obj.pop(index_to_remove)
                except (KeyError, IndexError):
                    pass

        await self._save_json_file(file_path, data, pretty_print)
        return ToolExecResult(
            output=f"Successfully removed {match_count} element(s) at JSONPath '{json_path_str}'"
        )
