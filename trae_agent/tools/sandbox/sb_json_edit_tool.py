import json
from typing import override

from daytona import Sandbox
from daytona_api_client import FileInfo
from jsonpath_ng import Fields, Index
from jsonpath_ng import parse as jsonpath_parse
from jsonpath_ng.exceptions import JSONPathError

from trae_agent.tools.json_edit_tool import JSONEditTool

from ...tools.base import ToolCallArguments, ToolError, ToolExecResult, ToolParameter
from ..sandbox_base import SandboxToolBase


class SandboxJSONEditTool(SandboxToolBase):
    """
    same as JSONEditTool, but run in sandbox
    """

    def __init__(self, model_provider: str | None = None, sandbox: Sandbox | None = None):
        super().__init__(model_provider, sandbox)
        self._json_editor_tool = JSONEditTool(model_provider)

    @override
    def get_name(self) -> str:
        return "sandbox_json_edit_tool"

    @override
    def get_description(self) -> str:
        return self._json_editor_tool.get_description()

    @override
    def get_parameters(self) -> list[ToolParameter]:
        return self._json_editor_tool.get_parameters()

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

            file_path = file_path_str

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

    async def _file_exists(self, path: str) -> bool | FileInfo:
        """Check if a file exists in the sandbox"""
        try:
            return await self._sandbox.fs.get_file_info(path)
        except Exception:
            return False

    async def read_file(self, path: str) -> str:
        """Read the content of a file from a given path; raise a ToolError if an error occurs."""
        try:
            return await self._sandbox.fs.download_file(path).decode()
        except Exception as e:
            raise ToolError(f"Ran into {e} while trying to read {path}") from None

    async def write_file(self, path: str, file: str):
        """Write the content of a file to a given path; raise a ToolError if an error occurs."""
        try:
            parent_dir = "/".join(path.split("/")[:-1])
            if parent_dir:
                await self._sandbox.fs.create_folder(parent_dir, "755")
            await self._sandbox.fs.upload_file(file.encode(), path)
        except Exception as e:
            raise ToolError(f"Ran into {e} while trying to write to {path}") from None

    async def _load_json_file(self, file_path: str) -> dict | list:
        """Load and parse JSON file."""
        file_info = await self._file_exists(file_path)
        if not file_info:
            raise ToolError(f"File does not exist: {file_path}")

        try:
            content = (await self.read_file(file_path)).strip()
            if not content:
                raise ToolError(f"File is empty: {file_path}")
            return json.loads(content)
        except json.JSONDecodeError as e:
            raise ToolError(f"Invalid JSON in file {file_path}: {str(e)}") from e
        except Exception as e:
            raise ToolError(f"Error reading file {file_path}: {str(e)}") from e

    async def _save_json_file(
        self, file_path: str, data: dict | list, pretty_print: bool = True
    ) -> None:
        """Save JSON data to file."""
        try:
            if pretty_print:
                await self.write_file(file_path, json.dumps(data, indent=2, ensure_ascii=False))
            else:
                await self.write_file(file_path, json.dumps(data, ensure_ascii=False))
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
        self, file_path: str, json_path_str: str | None, pretty_print: bool
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
        self, file_path: str, json_path_str: str, value, pretty_print: bool
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
        self, file_path: str, json_path_str: str, value, pretty_print: bool
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
        self, file_path: str, json_path_str: str, pretty_print: bool
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
