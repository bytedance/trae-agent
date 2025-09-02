import argparse
import asyncio
import json
import sys
from pathlib import Path

from jsonpath_ng import Fields, Index
from jsonpath_ng import parse as jsonpath_parse
from jsonpath_ng.exceptions import JSONPathError


def override(f):
    """A no-op decorator to satisfy the @override syntax."""
    return f


class Tool:
    """A minimal base class to satisfy 'class JSONEditTool(Tool):'."""

    def __init__(self, model_provider: str | None = None) -> None:
        self._model_provider = model_provider


ToolCallArguments = dict


class ToolError(Exception):
    """Custom exception for tool-related errors."""

    pass


class ToolExecResult:
    """A class to encapsulate the result of a tool execution."""

    def __init__(self, output: str | None = None, error: str | None = None, error_code: int = 0):
        self.output = output
        self.error = error
        self.error_code = error_code


class ToolParameter:
    """A dummy class to allow the get_parameters method to exist without error."""

    def __init__(self, name: str, type: str, description: str, required: bool = False, **kwargs):
        pass


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
        return """..."""

    @override
    def get_parameters(self) -> list[ToolParameter]:
        return []

    @override
    async def execute(self, arguments: ToolCallArguments) -> ToolExecResult:
        raise NotImplementedError("This method is not used in CLI mode.")

    async def _load_json_file(self, file_path: Path) -> dict | list:
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
        try:
            with open(file_path, "w", encoding="utf-8") as f:
                if pretty_print:
                    json.dump(data, f, indent=2, ensure_ascii=False)
                else:
                    json.dump(data, f, ensure_ascii=False)
        except Exception as e:
            raise ToolError(f"Error writing to file {file_path}: {str(e)}") from e

    def _parse_jsonpath(self, json_path_str: str):
        try:
            return jsonpath_parse(json_path_str)
        except JSONPathError as e:
            raise ToolError(f"Invalid JSONPath expression '{json_path_str}': {str(e)}") from e
        except Exception as e:
            raise ToolError(f"Error parsing JSONPath '{json_path_str}': {str(e)}") from e

    async def _view_json(
        self, file_path: Path, json_path_str: str | None, pretty_print: bool
    ) -> ToolExecResult:
        data = await self._load_json_file(file_path)
        if json_path_str:
            jsonpath_expr = self._parse_jsonpath(json_path_str)
            matches = jsonpath_expr.find(data)
            if not matches:
                return ToolExecResult(output=f"No matches found for JSONPath: {json_path_str}")
            result_data = [match.value for match in matches]
            if len(result_data) == 1:
                result_data = result_data[0]
            output = json.dumps(result_data, indent=2 if pretty_print else None, ensure_ascii=False)
            return ToolExecResult(output=f"JSONPath '{json_path_str}' matches:\n{output}")
        else:
            output = json.dumps(data, indent=2 if pretty_print else None, ensure_ascii=False)
            return ToolExecResult(output=f"JSON content of {file_path}:\n{output}")

    async def _set_json_value(
        self, file_path: Path, json_path_str: str, value, pretty_print: bool
    ) -> ToolExecResult:
        data = await self._load_json_file(file_path)
        jsonpath_expr = self._parse_jsonpath(json_path_str)
        matches = jsonpath_expr.find(data)
        if not matches:
            return ToolExecResult(
                error=f"No matches found for JSONPath: {json_path_str}", error_code=-1
            )
        updated_data = jsonpath_expr.update(data, value)
        await self._save_json_file(file_path, updated_data, pretty_print)
        return ToolExecResult(
            output=f"Successfully updated {len(matches)} location(s) at JSONPath '{json_path_str}'"
        )

    async def _add_json_value(
        self, file_path: Path, json_path_str: str, value, pretty_print: bool
    ) -> ToolExecResult:
        data = await self._load_json_file(file_path)
        jsonpath_expr = self._parse_jsonpath(json_path_str)
        parent_path, target = jsonpath_expr.left, jsonpath_expr.right
        parent_matches = parent_path.find(data)
        if not parent_matches:
            return ToolExecResult(error=f"Parent path not found: {parent_path}", error_code=-1)
        for match in parent_matches:
            parent_obj = match.value
            if isinstance(target, Fields):
                if not isinstance(parent_obj, dict):
                    return ToolExecResult(
                        error=f"Cannot add key to non-object at path: {parent_path}", error_code=-1
                    )
                parent_obj[target.fields[0]] = value
            elif isinstance(target, Index):
                if not isinstance(parent_obj, list):
                    return ToolExecResult(
                        error=f"Cannot add element to non-array at path: {parent_path}",
                        error_code=-1,
                    )
                parent_obj.insert(target.index, value)
            else:
                return ToolExecResult(
                    error=f"Unsupported add operation for path type: {type(target)}", error_code=-1
                )
        await self._save_json_file(file_path, data, pretty_print)
        return ToolExecResult(output=f"Successfully added value at JSONPath '{json_path_str}'")

    async def _remove_json_value(
        self, file_path: Path, json_path_str: str, pretty_print: bool
    ) -> ToolExecResult:
        data = await self._load_json_file(file_path)
        jsonpath_expr = self._parse_jsonpath(json_path_str)
        matches = jsonpath_expr.find(data)
        if not matches:
            return ToolExecResult(
                error=f"No matches found for JSONPath: {json_path_str}", error_code=-1
            )
        match_count = len(matches)
        jsonpath_expr.filter(
            lambda v: True, data
        )  # This is a conceptual way to remove, actual removal is more complex
        # A more robust remove logic:
        for match in reversed(matches):
            parent_path = match.full_path.left
            target = match.path
            for parent_match in parent_path.find(data):
                parent_obj = parent_match.value
                try:
                    if isinstance(target, Fields):
                        del parent_obj[target.fields[0]]
                    elif isinstance(target, Index):
                        parent_obj.pop(target.index)
                except (KeyError, IndexError):
                    pass
        await self._save_json_file(file_path, data, pretty_print)
        return ToolExecResult(
            output=f"Successfully removed {match_count} element(s) at JSONPath '{json_path_str}'"
        )


async def amain():
    parser = argparse.ArgumentParser(description="A CLI wrapper for the JSONEditTool.")
    parser.add_argument(
        "--operation",
        required=True,
        choices=["view", "set", "add", "remove"],
        help="The operation to perform.",
    )
    parser.add_argument("--file_path", required=True, help="Absolute path to the JSON file.")
    parser.add_argument("--json_path", help="JSONPath expression for the target.")
    parser.add_argument(
        "--value",
        help="The value to set or add, as a JSON string (e.g., '\"a string\"', '123', '{\"key\":\"val\"}').",
    )
    parser.add_argument(
        "--pretty_print",
        type=lambda v: v.lower() == "true",
        default=True,
        help="Pretty print the output JSON. Defaults to True.",
    )

    args = parser.parse_args()

    tool = JSONEditTool()

    file_path = Path(args.file_path)

    parsed_value = None
    if args.value is not None:
        try:
            parsed_value = json.loads(args.value)
        except json.JSONDecodeError:
            print(
                f"Error: The provided --value is not a valid JSON string: {args.value}",
                file=sys.stderr,
            )
            sys.exit(1)

    try:
        if not file_path.is_absolute():
            raise ToolError(f"File path must be absolute: {file_path}")

        result = None
        if args.operation == "view":
            result = await tool._view_json(file_path, args.json_path, args.pretty_print)
        elif args.operation == "set":
            if args.json_path is None or parsed_value is None:
                raise ToolError("--json_path and --value are required for 'set' operation.")
            result = await tool._set_json_value(
                file_path, args.json_path, parsed_value, args.pretty_print
            )
        elif args.operation == "add":
            if args.json_path is None or parsed_value is None:
                raise ToolError("--json_path and --value are required for 'add' operation.")
            result = await tool._add_json_value(
                file_path, args.json_path, parsed_value, args.pretty_print
            )
        elif args.operation == "remove":
            if args.json_path is None:
                raise ToolError("--json_path is required for 'remove' operation.")
            result = await tool._remove_json_value(file_path, args.json_path, args.pretty_print)

        if result.error:
            print(f"Error: {result.error}", file=sys.stderr)
            sys.exit(1)
        else:
            print(result.output)
            sys.exit(0)

    except ToolError as e:
        print(f"An error occurred: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(amain())
