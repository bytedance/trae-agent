# Copyright (c) 2025 ByteDance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

import hashlib
import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Literal

from tree_sitter import Node, Parser
from tree_sitter_languages import get_parser

from ...utils.constants import LOCAL_STORAGE_PATH
from .base import ClassEntry, FunctionEntry, extension_to_language

CKG_DATABASE_PATH = LOCAL_STORAGE_PATH / "ckg"
CKG_STORAGE_INFO_FILE = CKG_DATABASE_PATH / "storage_info.json"
CKG_DATABASE_EXPIRY_TIME = 60 * 60 * 24 * 7  # 1 week in seconds


"""
Known issues:
1. When a subdirectory of a codebase that has already been indexed, the CKG is built again for this subdirectory.
2. The rebuilding logic can be improved by only rebuilding for files that have been modified.
3. For JavaScript and TypeScript, the AST is not complete: anonymous functions, arrow functions, etc., are not parsed.
"""


def get_ckg_database_path(codebase_snapshot_hash: str) -> Path:
    """Get the path to the CKG database for a codebase path."""
    return CKG_DATABASE_PATH / f"{codebase_snapshot_hash}.db"


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


SQL_LIST = {
    "functions": """
    CREATE TABLE IF NOT EXISTS functions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        file_path TEXT NOT NULL,
        body TEXT NOT NULL,
        start_line INTEGER NOT NULL,
        end_line INTEGER NOT NULL,
        parent_function TEXT,
        parent_class TEXT
    )""",
    "classes": """
    CREATE TABLE IF NOT EXISTS classes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        file_path TEXT NOT NULL,
        body TEXT NOT NULL,
        fields TEXT,
        methods TEXT,
        start_line INTEGER NOT NULL,
        end_line INTEGER NOT NULL
    )""",
}


class CKGDatabase:
    def __init__(self, codebase_path: Path):
        self._db_connection: sqlite3.Connection
        self._codebase_path: Path = codebase_path

        if not CKG_DATABASE_PATH.exists():
            CKG_DATABASE_PATH.mkdir(parents=True, exist_ok=True)

        ckg_storage_info: dict[str, str] = {}

        # to save time and storage, we try to reuse the existing database if the codebase snapshot hash is the same
        # get the existing codebase snapshot hash from the storage info file
        if CKG_STORAGE_INFO_FILE.exists():
            with open(CKG_STORAGE_INFO_FILE, "r") as f:
                ckg_storage_info = json.load(f)
                if codebase_path.absolute().as_posix() in ckg_storage_info:
                    existing_codebase_snapshot_hash = ckg_storage_info[
                        codebase_path.absolute().as_posix()
                    ]
                else:
                    existing_codebase_snapshot_hash = ""
        else:
            existing_codebase_snapshot_hash = ""

        current_codebase_snapshot_hash = get_folder_snapshot_hash(codebase_path)
        if existing_codebase_snapshot_hash == current_codebase_snapshot_hash:
            # we can reuse the existing database
            database_path = get_ckg_database_path(existing_codebase_snapshot_hash)
        else:
            # we need to create a new database and delete the old one
            database_path = get_ckg_database_path(existing_codebase_snapshot_hash)
            if database_path.exists():
                database_path.unlink()
            database_path = get_ckg_database_path(current_codebase_snapshot_hash)

            ckg_storage_info[codebase_path.absolute().as_posix()] = current_codebase_snapshot_hash
            with open(CKG_STORAGE_INFO_FILE, "w") as f:
                json.dump(ckg_storage_info, f)

        if database_path.exists():
            # reuse existing database
            self._db_connection = sqlite3.connect(database_path)
        else:
            # create new database with tables and build the CKG
            self._db_connection = sqlite3.connect(database_path)
            for sql in SQL_LIST.values():
                self._db_connection.execute(sql)
            self._db_connection.commit()
            self._construct_ckg()

    def __del__(self):
        self._db_connection.close()

    def update(self):
        """Update the CKG database."""
        self._construct_ckg()

    def _recursive_visit_python(
        self,
        root_node: Node,
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
                        function_entry.parent_function = parent_function.name
                    else:
                        function_entry.parent_class = parent_class.name
                elif parent_function:
                    function_entry.parent_function = parent_function.name
                elif parent_class:
                    function_entry.parent_class = parent_class.name
                self._insert_entry(function_entry)
                parent_function = function_entry
        elif root_node.type == "class_definition":
            class_name_node = root_node.child_by_field_name("name")
            if class_name_node:
                class_body_node = root_node.child_by_field_name("body")
                class_methods = ""
                class_entry = ClassEntry(
                    name=class_name_node.text.decode(),
                    file_path=file_path,
                    body=root_node.text.decode(),
                    start_line=root_node.start_point[0] + 1,
                    end_line=root_node.end_point[0] + 1,
                )
                if class_body_node:
                    for child in class_body_node.children:
                        function_definition_node = None
                        if child.type == "decorated_definition":
                            function_definition_node = child.child_by_field_name("definition")
                        elif child.type == "function_definition":
                            function_definition_node = child
                        if function_definition_node:
                            method_name_node = function_definition_node.child_by_field_name("name")
                            if method_name_node:
                                parameters_node = function_definition_node.child_by_field_name(
                                    "parameters"
                                )
                                return_type_node = child.child_by_field_name("return_type")

                                class_method_info = method_name_node.text.decode()
                                if parameters_node:
                                    class_method_info += f"{parameters_node.text.decode()}"
                                if return_type_node:
                                    class_method_info += f" -> {return_type_node.text.decode()}"
                                class_methods += f"- {class_method_info}\n"
                class_entry.methods = class_methods.strip() if class_methods != "" else None
                parent_class = class_entry
                self._insert_entry(class_entry)

        if len(root_node.children) != 0:
            for child in root_node.children:
                self._recursive_visit_python(child, file_path, parent_class, parent_function)

    def _recursive_visit_java(
        self,
        root_node: Node,
        file_path: str,
        parent_class: ClassEntry | None = None,
        parent_function: FunctionEntry | None = None,
    ):
        """Recursively visit the Java AST and insert the entries into the database."""
        if root_node.type == "class_declaration":
            class_name_node = root_node.child_by_field_name("name")
            if class_name_node:
                class_entry = ClassEntry(
                    name=class_name_node.text.decode(),
                    file_path=file_path,
                    body=root_node.text.decode(),
                    start_line=root_node.start_point[0] + 1,
                    end_line=root_node.end_point[0] + 1,
                )
                class_body_node = root_node.child_by_field_name("body")
                class_methods = ""
                class_fields = ""
                if class_body_node:
                    for child in class_body_node.children:
                        if child.type == "field_declaration":
                            class_fields += f"- {child.text.decode()}\n"
                        if child.type == "method_declaration":
                            method_builder = ""
                            for method_property in child.children:
                                if method_property.type == "block":
                                    break
                                method_builder += f"{method_property.text.decode()} "
                            method_builder = method_builder.strip()
                            class_methods += f"- {method_builder}\n"
                class_entry.methods = class_methods.strip() if class_methods != "" else None
                class_entry.fields = class_fields.strip() if class_fields != "" else None
                parent_class = class_entry
                self._insert_entry(class_entry)
        elif root_node.type == "method_declaration":
            method_name_node = root_node.child_by_field_name("name")
            if method_name_node:
                method_entry = FunctionEntry(
                    name=method_name_node.text.decode(),
                    file_path=file_path,
                    body=root_node.text.decode(),
                    start_line=root_node.start_point[0] + 1,
                    end_line=root_node.end_point[0] + 1,
                )
                if parent_class:
                    method_entry.parent_class = parent_class.name
                self._insert_entry(method_entry)

        if len(root_node.children) != 0:
            for child in root_node.children:
                self._recursive_visit_java(child, file_path, parent_class, parent_function)

    def _recursive_visit_cpp(
        self,
        root_node: Node,
        file_path: str,
        parent_class: ClassEntry | None = None,
        parent_function: FunctionEntry | None = None,
    ):
        """Recursively visit the C++ AST and insert the entries into the database."""
        if root_node.type == "class_specifier":
            class_name_node = root_node.child_by_field_name("name")
            if class_name_node:
                class_entry = ClassEntry(
                    name=class_name_node.text.decode(),
                    file_path=file_path,
                    body=root_node.text.decode(),
                    start_line=root_node.start_point[0] + 1,
                    end_line=root_node.end_point[0] + 1,
                )
                class_body_node = root_node.child_by_field_name("body")
                class_methods = ""
                class_fields = ""
                if class_body_node:
                    for child in class_body_node.children:
                        if child.type == "function_definition":
                            method_builder = ""
                            for method_property in child.children:
                                if method_property.type == "compound_statement":
                                    break
                                method_builder += f"{method_property.text.decode()} "
                            method_builder = method_builder.strip()
                            class_methods += f"- {method_builder}\n"
                        if child.type == "field_declaration":
                            child_is_property = True
                            for child_property in child.children:
                                if child_property.type == "function_declarator":
                                    child_is_property = False
                                    break
                            if child_is_property:
                                class_fields += f"- {child.text.decode()}\n"
                            else:
                                class_methods += f"- {child.text.decode()}\n"
                class_entry.methods = class_methods.strip() if class_methods != "" else None
                class_entry.fields = class_fields.strip() if class_fields != "" else None
                parent_class = class_entry
                self._insert_entry(class_entry)
        elif root_node.type == "function_definition":
            function_declarator_node = root_node.child_by_field_name("declarator")
            if function_declarator_node:
                function_name_node = function_declarator_node.child_by_field_name("declarator")
                if function_name_node:
                    function_entry = FunctionEntry(
                        name=function_name_node.text.decode(),
                        file_path=file_path,
                        body=root_node.text.decode(),
                        start_line=root_node.start_point[0] + 1,
                        end_line=root_node.end_point[0] + 1,
                    )
                    if parent_class:
                        function_entry.parent_class = parent_class.name
                    self._insert_entry(function_entry)

        if len(root_node.children) != 0:
            for child in root_node.children:
                self._recursive_visit_cpp(child, file_path, parent_class, parent_function)

    def _recursive_visit_c(
        self,
        root_node: Node,
        file_path: str,
        parent_class: ClassEntry | None = None,
        parent_function: FunctionEntry | None = None,
    ):
        """Recursively visit the C AST and insert the entries into the database."""
        if root_node.type == "function_definition":
            function_declarator_node = root_node.child_by_field_name("declarator")
            if function_declarator_node:
                function_name_node = function_declarator_node.child_by_field_name("declarator")
                if function_name_node:
                    function_entry = FunctionEntry(
                        name=function_name_node.text.decode(),
                        file_path=file_path,
                        body=root_node.text.decode(),
                        start_line=root_node.start_point[0] + 1,
                        end_line=root_node.end_point[0] + 1,
                    )
                    self._insert_entry(function_entry)

        if len(root_node.children) != 0:
            for child in root_node.children:
                self._recursive_visit_c(child, file_path, parent_class, parent_function)

    def _recursive_visit_typescript(
        self,
        root_node: Node,
        file_path: str,
        parent_class: ClassEntry | None = None,
        parent_function: FunctionEntry | None = None,
    ):
        if root_node.type == "class_declaration":
            class_name_node = root_node.child_by_field_name("name")
            if class_name_node:
                class_entry = ClassEntry(
                    name=class_name_node.text.decode(),
                    file_path=file_path,
                    body=root_node.text.decode(),
                    start_line=root_node.start_point[0] + 1,
                    end_line=root_node.end_point[0] + 1,
                )
                methods = ""
                fields = ""
                class_body_node = root_node.child_by_field_name("body")
                if class_body_node:
                    for child in class_body_node.children:
                        if child.type == "method_definition":
                            method_builder = ""
                            for method_property in child.children:
                                if method_property.type == "statement_block":
                                    break
                                method_builder += f"{method_property.text.decode()} "
                            method_builder = method_builder.strip()
                            methods += f"- {method_builder}\n"
                        elif child.type == "public_field_definition":
                            fields += f"- {child.text.decode()}\n"
                class_entry.methods = methods.strip() if methods != "" else None
                class_entry.fields = fields.strip() if fields != "" else None
                parent_class = class_entry
                self._insert_entry(class_entry)
        elif root_node.type == "method_definition":
            method_name_node = root_node.child_by_field_name("name")
            if method_name_node:
                method_entry = FunctionEntry(
                    name=method_name_node.text.decode(),
                    file_path=file_path,
                    body=root_node.text.decode(),
                    start_line=root_node.start_point[0] + 1,
                    end_line=root_node.end_point[0] + 1,
                )
                if parent_class:
                    method_entry.parent_class = parent_class.name
                self._insert_entry(method_entry)

        if len(root_node.children) != 0:
            for child in root_node.children:
                self._recursive_visit_typescript(child, file_path, parent_class, parent_function)

    def _recursive_visit_javascript(
        self,
        root_node: Node,
        file_path: str,
        parent_class: ClassEntry | None = None,
        parent_function: FunctionEntry | None = None,
    ):
        """Recursively visit the JavaScript AST and insert the entries into the database."""
        if root_node.type == "class_declaration":
            class_name_node = root_node.child_by_field_name("name")
            if class_name_node:
                class_entry = ClassEntry(
                    name=class_name_node.text.decode(),
                    file_path=file_path,
                    body=root_node.text.decode(),
                    start_line=root_node.start_point[0] + 1,
                    end_line=root_node.end_point[0] + 1,
                )
                methods = ""
                fields = ""
                class_body_node = root_node.child_by_field_name("body")
                if class_body_node:
                    for child in class_body_node.children:
                        if child.type == "method_definition":
                            method_builder = ""
                            for method_property in child.children:
                                if method_property.type == "statement_block":
                                    break
                                method_builder += f"{method_property.text.decode()} "
                            method_builder = method_builder.strip()
                            methods += f"- {method_builder}\n"
                        elif child.type == "public_field_definition":
                            fields += f"- {child.text.decode()}\n"
                class_entry.methods = methods.strip() if methods != "" else None
                class_entry.fields = fields.strip() if fields != "" else None
                parent_class = class_entry
                self._insert_entry(class_entry)
        elif root_node.type == "method_definition":
            method_name_node = root_node.child_by_field_name("name")
            if method_name_node:
                method_entry = FunctionEntry(
                    name=method_name_node.text.decode(),
                    file_path=file_path,
                    body=root_node.text.decode(),
                    start_line=root_node.start_point[0] + 1,
                    end_line=root_node.end_point[0] + 1,
                )
                if parent_class:
                    method_entry.parent_class = parent_class.name
                self._insert_entry(method_entry)

        if len(root_node.children) != 0:
            for child in root_node.children:
                self._recursive_visit_javascript(child, file_path, parent_class, parent_function)

    def _construct_ckg(self) -> None:
        """Initialise the code knowledge graph."""

        # lazy load the parsers for the languages when needed
        language_to_parser: dict[str, Parser] = {}
        for file in self._codebase_path.glob("**/*"):
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
                        self._recursive_visit_python(root_node, file.absolute().as_posix())
                    case "java":
                        self._recursive_visit_java(root_node, file.absolute().as_posix())
                    case "cpp":
                        self._recursive_visit_cpp(root_node, file.absolute().as_posix())
                    case "c":
                        self._recursive_visit_c(root_node, file.absolute().as_posix())
                    case "typescript":
                        self._recursive_visit_typescript(root_node, file.absolute().as_posix())
                    case "javascript":
                        self._recursive_visit_javascript(root_node, file.absolute().as_posix())
                    case _:
                        continue

    def _insert_entry(self, entry: FunctionEntry | ClassEntry) -> None:
        """
        Insert entry into db.

        Args:
            entry: the entry to insert

        Returns:
            None
        """
        # TODO: add try catch block to avoid connection problem.
        match entry:
            case FunctionEntry():
                self._insert_function(entry)

            case ClassEntry():
                self._insert_class(entry)

        self._db_connection.commit()

    def _insert_function(self, entry: FunctionEntry) -> None:
        """
        Insert function entry including functions and class methodsinto db.

        Args:
            entry: the entry to insert

        Returns:
            None
        """
        self._db_connection.execute(
            """
                INSERT INTO functions (name, file_path, body, start_line, end_line, parent_function, parent_class)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                entry.name,
                entry.file_path,
                entry.body,
                entry.start_line,
                entry.end_line,
                entry.parent_function,
                entry.parent_class,
            ),
        )

    def _insert_class(self, entry: ClassEntry) -> None:
        """
        Insert class entry into db.

        Args:
            entry: the entry to insert

        Returns:
            None
        """
        self._db_connection.execute(
            """
                INSERT INTO classes (name, file_path, body, fields, methods, start_line, end_line)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                entry.name,
                entry.file_path,
                entry.body,
                entry.fields,
                entry.methods,
                entry.start_line,
                entry.end_line,
            ),
        )

    def query_function(
        self, identifier: str, entry_type: Literal["function", "class_method"] = "function"
    ) -> list[FunctionEntry]:
        """
        Search for a function in the database.

        Args:
            identifier: the identifier of the function to search for

        Returns:
            a list of function entries
        """
        records = self._db_connection.execute(
            """SELECT name, file_path, body, start_line, end_line, parent_function, parent_class FROM functions WHERE name = ?""",
            (identifier,),
        ).fetchall()
        function_entries: list[FunctionEntry] = []
        for record in records:
            match entry_type:
                case "function":
                    if record[6] is None:
                        function_entries.append(
                            FunctionEntry(
                                name=record[0],
                                file_path=record[1],
                                body=record[2],
                                start_line=record[3],
                                end_line=record[4],
                                parent_function=record[5],
                                parent_class=record[6],
                            )
                        )
                case "class_method":
                    if record[6] is not None:
                        function_entries.append(
                            FunctionEntry(
                                name=record[0],
                                file_path=record[1],
                                body=record[2],
                                start_line=record[3],
                                end_line=record[4],
                                parent_function=record[5],
                                parent_class=record[6],
                            )
                        )
        return function_entries

    def query_class(self, identifier: str) -> list[ClassEntry]:
        """
        Search for a class in the database.

        Args:
            identifier: the identifier of the class to search for

        Returns:
            a list of class entries
        """
        records = self._db_connection.execute(
            """SELECT name, file_path, body, fields, methods, start_line, end_line FROM classes WHERE name = ?""",
            (identifier,),
        ).fetchall()
        class_entries: list[ClassEntry] = []
        for record in records:
            class_entries.append(
                ClassEntry(
                    name=record[0],
                    file_path=record[1],
                    body=record[2],
                    fields=record[3],
                    methods=record[4],
                    start_line=record[5],
                    end_line=record[6],
                )
            )
        return class_entries
