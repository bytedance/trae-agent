# Copyright (c) 2025 ByteDance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

import hashlib
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Literal, override

from tree_sitter import Node, Parser
from tree_sitter_languages import get_parser

from trae_agent.tools.run import MAX_RESPONSE_LEN

from ..db.ckg import CKGStorage, ClassEntry, FunctionEntry
from ..db.db import DB
from ..utils.constants import CKG_DATABASE_EXPIRY_TIME, CKG_DATABASE_PATH, get_ckg_database_path
from .base import Tool, ToolCallArguments, ToolExecResult, ToolParameter

CKGToolCommands = ["search_function", "search_class", "search_class_method"]

# We need a mapping from file extension to tree-sitter language name to parse files and build the graph
extension_to_language = {
    ".py": "python",
    ".java": "java",
    ".cpp": "cpp",
    ".c": "c",
    ".h": "c",
}

EntryType = Literal["functions", "classes", "class_methods"]


def get_folder_snapshot_hash(folder_path: Path) -> str:
    """Get the hash of the folder snapshot, to make sure that the CKG is up to date."""
    hash_md5 = hashlib.md5()

    for file in folder_path.glob("**/*"):
        if file.is_file() and not file.name.startswith("."):
            stat = file.stat()
            hash_md5.update(file.name.encode())
            hash_md5.update(str(stat.st_mtime).encode())  # modification time
            hash_md5.update(str(stat.st_size).encode())  # file size

    return hash_md5.hexdigest()


def recursive_visit_python(
    root_node: Node,
    db: DB,
    file_path: str,
    parent_class: ClassEntry | None = None,
    parent_function: FunctionEntry | None = None,
):
    """Recursively visit the Python AST and insert the entries into the database."""
    if root_node.type == "function_definition":
        function_name_node = root_node.child_by_field_name("name")
        if function_name_node:
            function_entry = FunctionEntry(
                name=function_name_node.text.decode(),
                file_path=file_path,
                body=root_node.text.decode(),
                start_line=root_node.start_point[0] + 1,
                end_line=root_node.end_point[0] + 1,
            )
            if parent_function and parent_class:
                # determine if the function is a method of the class or a function within a function
                if (
                    parent_function.start_line >= parent_class.start_line
                    and parent_function.end_line <= parent_class.end_line
                ):
                    function_entry.parent_function = parent_function
                else:
                    function_entry.parent_class = parent_class
            elif parent_function:
                function_entry.parent_function = parent_function
            elif parent_class:
                function_entry.parent_class = parent_class
            db.insert_entry(function_entry)
            parent_function = function_entry
    elif root_node.type == "class_definition":
        class_name_node = root_node.child_by_field_name("name")
        if class_name_node:
            class_body_node = root_node.child_by_field_name("body")
            class_methods: list[str] = []
            class_entry = ClassEntry(
                name=class_name_node.text.decode(),
                file_path=file_path,
                body=root_node.text.decode(),
                fields=[],
                methods=[],
                start_line=root_node.start_point[0] + 1,
                end_line=root_node.end_point[0] + 1,
            )
            if class_body_node:
                for child in class_body_node.children:
                    if child.type == "function_definition":
                        method_name_node = child.child_by_field_name("name")
                        if method_name_node:
                            parameters_node = child.child_by_field_name("parameters")
                            return_type_node = child.child_by_field_name("return_type")

                            class_method_info = method_name_node.text.decode()
                            if parameters_node:
                                class_method_info += f"{parameters_node.text.decode()}"
                            if return_type_node:
                                class_method_info += f" -> {return_type_node.text.decode()}"
                            class_methods.append(class_method_info)
            class_entry.methods = class_methods
            parent_class = class_entry
            db.insert_entry(class_entry)

    if len(root_node.children) != 0:
        for child in root_node.children:
            recursive_visit_python(child, db, file_path, parent_class, parent_function)


def construct_ckg(db: DB, codebase_path: Path) -> None:
    """Initialise the code knowledge graph."""

    # lazy load the parsers for the languages when needed
    language_to_parser: dict[str, Parser] = {}
    for file in codebase_path.glob("**/*"):
        # skip hidden files and files in a hidden directory
        if (
            file.is_file()
            and not file.name.startswith(".")
            and "/." not in file.absolute().as_posix()
        ):
            extension = file.suffix
            # ignore files with unknown extensions
            if extension not in extension_to_language:
                continue
            language = extension_to_language[extension]

            language_parser = language_to_parser.get(language)
            if not language_parser:
                language_parser = get_parser(language)
                language_to_parser[language] = language_parser

            tree = language_parser.parse(file.read_bytes())
            root_node = tree.root_node

            match language:
                case "python":
                    recursive_visit_python(root_node, db, file.absolute().as_posix())
                case _:
                    continue


def clear_older_ckg():
    """Iterate over all the files in the CKG storage directory and delete the ones that are older than 1 week."""
    for file in CKG_DATABASE_PATH.glob("**/*"):
        if (
            file.is_file()
            and not file.name.startswith(".")
            and file.name.endswith(".db")
            and file.stat().st_mtime < datetime.now().timestamp() - CKG_DATABASE_EXPIRY_TIME
        ):
            try:
                file.unlink()
            except Exception as e:
                print(f"error deleting older CKG database - {file.absolute().as_posix()}: {e}")


class CKGTool(Tool):
    """Tool to construct and query the code knowledge graph of a codebase."""

    def __init__(self, model_provider: str | None = None) -> None:
        super().__init__(model_provider)

        # We store the codebase path with built CKG in the following format:
        # {
        #     "codebase_path": {
        #         "db_connection": sqlite3.Connection,
        #         "codebase_snapshot_hash": str,
        #     }
        # }
        self._ckg_path: dict[Path, CKGStorage] = {}
        # TODO better ways ?
        self.db = DB()
        self.db_connection = self.db.db_connection

    @override
    def get_model_provider(self) -> str | None:
        return self._model_provider

    @override
    def get_name(self) -> str:
        return "ckg"

    @override
    def get_description(self) -> str:
        return """Query the code knowledge graph of a codebase.
* State is persistent across command calls and discussions with the user
* The `search_function` command searches for functions in the codebase
* The `search_class` command searches for classes in the codebase
* The `search_class_method` command searches for class methods in the codebase
* If a `command` generates a long output, it will be truncated and marked with `<response clipped>`
* If multiple entries are found, the tool will return all of them until the truncation is reached.
* By default, the tool will print function or class bodies as well as the file path and line number of the function or class. You can disable this by setting the `print_body` parameter to `false`.
"""

    @override
    def get_parameters(self) -> list[ToolParameter]:
        return [
            ToolParameter(
                name="command",
                type="string",
                description=f"The command to run. Allowed options are {', '.join(CKGToolCommands)}.",
                required=True,
                enum=CKGToolCommands,
            ),
            ToolParameter(
                name="path",
                type="string",
                description="The path to the codebase.",
                required=True,
            ),
            ToolParameter(
                name="identifier",
                type="string",
                description="The identifier of the function or class to search for in the code knowledge graph.",
                required=True,
            ),
            ToolParameter(
                name="print_body",
                type="boolean",
                description="Whether to print the body of the function or class. This is enabled by default.",
                required=False,
            ),
        ]

    @override
    async def execute(self, arguments: ToolCallArguments) -> ToolExecResult:
        command = str(arguments.get("command")) if "command" in arguments else None
        if command is None:
            return ToolExecResult(
                error=f"No command provided for the {self.get_name()} tool",
                error_code=-1,
            )
        path = str(arguments.get("path")) if "path" in arguments else None
        if path is None:
            return ToolExecResult(
                error=f"No path provided for the {self.get_name()} tool",
                error_code=-1,
            )
        identifier = str(arguments.get("identifier")) if "identifier" in arguments else None
        if identifier is None:
            return ToolExecResult(
                error=f"No identifier provided for the {self.get_name()} tool",
                error_code=-1,
            )
        print_body = bool(arguments.get("print_body")) if "print_body" in arguments else True

        codebase_path = Path(path)
        if not codebase_path.exists():
            return ToolExecResult(
                error=f"Codebase path {path} does not exist",
                error_code=-1,
            )
        if not codebase_path.is_dir():
            return ToolExecResult(
                error=f"Codebase path {path} is not a directory",
                error_code=-1,
            )

        ckg_connection = self._get_or_construct_ckg(codebase_path)

        match command:
            case "search_function":
                return ToolExecResult(
                    output=self._search_function(ckg_connection, identifier, print_body)
                )
            case "search_class":
                return ToolExecResult(
                    output=self._search_class(ckg_connection, identifier, print_body)
                )
            case "search_class_method":
                return ToolExecResult(
                    output=self._search_class_method(ckg_connection, identifier, print_body)
                )
            case _:
                return ToolExecResult(error=f"Invalid command: {command}", error_code=-1)

    def _get_or_construct_ckg(self, codebase_path: Path) -> sqlite3.Connection:
        """Get the CKG for a codebase path, or construct it if it doesn't exist."""

        codebase_snapshot_hash = get_folder_snapshot_hash(codebase_path)

        if codebase_path not in self._ckg_path:
            # no previous hash, so we need to check if a previously built ckg exists or otherwise initialise the database and construct the CKG
            if get_ckg_database_path(codebase_snapshot_hash).exists():
                self.db_connection = sqlite3.connect(get_ckg_database_path(codebase_snapshot_hash))
                self._ckg_path[codebase_path] = CKGStorage(
                    self.db_connection, codebase_snapshot_hash
                )
                return self.db_connection
            else:
                self.db_connection = self.db.init_db(codebase_snapshot_hash)
                construct_ckg(self.db, codebase_path)
                self._ckg_path[codebase_path] = CKGStorage(
                    self.db_connection, codebase_snapshot_hash
                )
                return self.db_connection
        else:
            # the codebase has a previously built CKG, so we need to check if it has changed
            if self._ckg_path[codebase_path].codebase_snapshot_hash != codebase_snapshot_hash:
                # the codebase has changed, so we need to delete the old database and update the database
                self._ckg_path[codebase_path].db_connection.close()
                old_database_path = get_ckg_database_path(
                    self._ckg_path[codebase_path].codebase_snapshot_hash
                )
                if old_database_path.exists():
                    old_database_path.unlink()
                self.db_connection = self.db.init_db(codebase_snapshot_hash)

                construct_ckg(self.db, codebase_path)

                self._ckg_path[codebase_path] = CKGStorage(
                    self.db_connection, codebase_snapshot_hash
                )
            return self._ckg_path[codebase_path].db_connection

    def _search_function(
        self, ckg_connection: sqlite3.Connection, identifier: str, print_body: bool = True
    ) -> str:
        """Search for a function in the ckg database."""

        entries = ckg_connection.execute(
            """
            SELECT file_path, start_line, end_line, body FROM functions WHERE name = ?
            """,
            (identifier,),
        ).fetchall()

        if len(entries) == 0:
            return f"No functions named {identifier} found."

        output = ""
        for entry in entries:
            output += f"{entry[0]}:{entry[1]}-{entry[2]}\n"
            if print_body:
                output += f"{entry[3]}\n\n"

            if len(output) > MAX_RESPONSE_LEN:
                output = output[:MAX_RESPONSE_LEN] + "\n<response clipped>"
                break

        return output

    def _search_class(
        self, ckg_connection: sqlite3.Connection, identifier: str, print_body: bool = True
    ) -> str:
        """Search for a class in the ckg database."""

        entries = ckg_connection.execute(
            """
            SELECT file_path, start_line, end_line, fields, methods, body FROM classes WHERE name = ?
            """,
            (identifier,),
        ).fetchall()

        if len(entries) == 0:
            return f"No classes named {identifier} found."

        output = ""
        for entry in entries:
            output += (
                f"{entry[0]}:{entry[1]}-{entry[2]}\nFields:\n{entry[3]}\nMethods:\n{entry[4]}\n"
            )
            if print_body:
                output += f"{entry[5]}\n\n"

            if len(output) > MAX_RESPONSE_LEN:
                output = output[:MAX_RESPONSE_LEN] + "\n<response clipped>"
                break

        return output

    def _search_class_method(
        self, ckg_connection: sqlite3.Connection, identifier: str, print_body: bool = True
    ) -> str:
        """Search for a class method in the ckg database."""

        entries = ckg_connection.execute(
            """
            SELECT file_path, start_line, end_line, body, class_name FROM class_methods WHERE name = ?
            """,
            (identifier,),
        ).fetchall()

        if len(entries) == 0:
            return f"No class methods named {identifier} found."

        output = ""
        for entry in entries:
            output += f"{entry[0]}:{entry[1]}-{entry[2]} Within class {entry[4]}\n"
            if print_body:
                output += f"{entry[3]}\n\n"

            if len(output) > MAX_RESPONSE_LEN:
                output = output[:MAX_RESPONSE_LEN] + "\n<response clipped>"
                break

        return output
