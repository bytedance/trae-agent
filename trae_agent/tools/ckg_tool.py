# Copyright (c) 2025 ByteDance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

import hashlib
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from sqlite3 import Connection
from typing import Literal, override

from tree_sitter import Node, Parser
from tree_sitter_languages import get_parser

from ..utils.constants import CKG_DATABASE_PATH, get_ckg_database_path
from .base import Tool, ToolCallArguments, ToolExecResult, ToolParameter

CKGToolCommands = [
    "search_function",
    "search_class",
]

# We need a mapping from file extension to tree-sitter language name to parse files and build the graph
extension_to_language = {
    ".py": "python",
    ".java": "java",
    ".cpp": "cpp",
    ".c": "c",
    ".h": "c",
}

# As tree-sitter uses different names for functions and classes for different programming languages, we define a unified mapping here
function_types: dict[str, list[str]] = {
    "python": ["function_definition"],
    "java": ["method_declaration"],
    "cpp": ["function_definition"],
    "c": ["function_definition"],
}

class_types: dict[str, list[str]] = {
    "python": ["class_definition"],
    "java": ["class_declaration"],
    "cpp": ["class_definition"],
    "c": ["class_definition"],
}


@dataclass
class CKGEntry:
    type: Literal["function", "class"]
    name: str
    file_path: str
    body: str
    start_line: int
    end_line: int


@dataclass
class CKGStorage:
    db_connection: sqlite3.Connection
    codebase_snapshot_hash: str


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


def initialise_db(codebase_snapshot_hash: str) -> sqlite3.Connection:
    """Initialise the code knowledge graph database. The function creates two tables, one for functions and one for classes."""

    if not CKG_DATABASE_PATH.exists():
        CKG_DATABASE_PATH.mkdir(parents=True, exist_ok=True)

    database_path = get_ckg_database_path(codebase_snapshot_hash)
    db_connection: Connection = sqlite3.connect(database_path)
    db_connection.execute("""
        CREATE TABLE IF NOT EXISTS functions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            file_path TEXT NOT NULL,
            body TEXT NOT NULL,
            start_line INTEGER NOT NULL,
            end_line INTEGER NOT NULL,
        );
        CREATE TABLE IF NOT EXISTS classes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            file_path TEXT NOT NULL,
            body TEXT NOT NULL,
            start_line INTEGER NOT NULL,
            end_line INTEGER NOT NULL,
        )""")
    db_connection.commit()
    return db_connection


def construct_ckg(db_connection: sqlite3.Connection, codebase_path: Path) -> None:
    """Initialise the code knowledge graph."""

    # lazy load the parsers for the languages when needed
    language_to_parser: dict[str, Parser] = {}
    for file in codebase_path.glob("**/*"):
        # skip hidden files
        if file.is_file() and not file.name.startswith("."):
            extension = file.suffix
            # ignore files with unknown extensions
            if extension not in extension_to_language:
                continue
            language = extension_to_language[extension]

            language_parser = language_to_parser.get(language)
            if not language_parser:
                language_parser = get_parser(language)
                language_to_parser[language] = language_parser

            # recursively visit the AST and insert the entries into the database
            def recursive_visit(node: Node, file_name: str, file_language: str):
                if node.type in function_types[file_language]:
                    function_name_node = node.child_by_field_name("name")
                    if function_name_node:
                        function_entry = CKGEntry(
                            type="function",
                            name=function_name_node.text.decode(),
                            file_path=file_name,
                            body=node.text.decode(),
                            start_line=node.start_point[0] + 1,
                            end_line=node.end_point[0] + 1,
                        )
                        insert_entry(db_connection, function_entry)
                elif node.type in class_types[file_language]:
                    class_name_node = node.child_by_field_name("name")
                    if class_name_node:
                        class_entry = CKGEntry(
                            type="class",
                            name=class_name_node.text.decode(),
                            file_path=file_name,
                            body=node.text.decode(),
                            start_line=node.start_point[0],
                            end_line=node.end_point[0],
                        )
                        insert_entry(db_connection, class_entry)

                if len(node.children) != 0:
                    for child in node.children:
                        recursive_visit(child, file_name, file_language)

            tree = language_parser.parse(file.read_bytes())
            root_node = tree.root_node

            recursive_visit(root_node, file.name, language)


def insert_entry(db_connection: sqlite3.Connection, entry: CKGEntry):
    """Insert a function into the code knowledge graph."""
    db_connection.execute(
        f"""
        INSERT INTO {entry.type}s (name, file_path, body, start_line, end_line)
        VALUES (?, ?, ?, ?, ?)
    """,
        (entry.name, entry.file_path, entry.body, entry.start_line, entry.end_line),
    )
    db_connection.commit()


def search_entry(
    db_connection: sqlite3.Connection, entry_type: Literal["function", "class"], entry_name: str
) -> list[CKGEntry]:
    """Search for a function or class in the code knowledge graph."""
    cursor = db_connection.execute(
        f"""
            SELECT name, file_path, body, start_line, end_line FROM {entry_type}s WHERE name = ?
        """,
        (entry_name,),
    )
    return [
        CKGEntry(
            type=entry_type,
            name=row[0],
            file_path=row[1],
            body=row[2],
            start_line=row[3],
            end_line=row[4],
        )
        for row in cursor.fetchall()
    ]


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
* If a `command` generates a long output, it will be truncated and marked with `<response clipped>`
* If multiple entries are found, the tool will return all of them until the truncation is reached.
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
                return ToolExecResult(output=self._search_function(ckg_connection, identifier))
            case "search_class":
                return ToolExecResult(output=self._search_class(ckg_connection, identifier))
            case _:
                return ToolExecResult(error=f"Invalid command: {command}", error_code=-1)

    def _get_or_construct_ckg(self, codebase_path: Path) -> sqlite3.Connection:
        """Get the CKG for a codebase path, or construct it if it doesn't exist."""

        codebase_snapshot_hash = get_folder_snapshot_hash(codebase_path)

        if codebase_path not in self._ckg_path:
            # no previous hash, so we need to initialise the database and construct the CKG
            db_connection = initialise_db(codebase_snapshot_hash)
            construct_ckg(db_connection, codebase_path)
            self._ckg_path[codebase_path] = CKGStorage(db_connection, codebase_snapshot_hash)
            return db_connection
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
                db_connection = initialise_db(codebase_snapshot_hash)
                construct_ckg(db_connection, codebase_path)
                self._ckg_path[codebase_path] = CKGStorage(db_connection, codebase_snapshot_hash)
            return self._ckg_path[codebase_path].db_connection

    def _search_function(self, ckg_connection: sqlite3.Connection, identifier: str) -> str:
        """Search for a function in the codebase."""
        entries = search_entry(ckg_connection, "function", identifier)
        return "\n".join(
            [
                f"{entry.file_path}:{entry.start_line}-{entry.end_line}: {entry.body}"
                for entry in entries
            ]
        )

    def _search_class(self, ckg_connection: sqlite3.Connection, identifier: str) -> str:
        """Search for a class in the codebase."""
        entries = search_entry(ckg_connection, "class", identifier)
        return "\n".join(
            [
                f"{entry.file_path}:{entry.start_line}-{entry.end_line}: {entry.body}"
                for entry in entries
            ]
        )
