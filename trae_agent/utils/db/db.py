# Copyright (c) 2025 ByteDance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

import sqlite3
from pathlib import Path

from ..constants import LOCAL_STORAGE_PATH
from .ckg import ClassEntry, FunctionEntry

CKG_DATABASE_PATH = LOCAL_STORAGE_PATH / "ckg"
CKG_DATABASE_EXPIRY_TIME = 60 * 60 * 24 * 7  # 1 week in seconds


def get_ckg_database_path(codebase_snapshot_hash: str) -> Path:
    """Get the path to the CKG database for a codebase path."""
    return CKG_DATABASE_PATH / f"{codebase_snapshot_hash}.db"


class DB:
    def __init__(self):
        self.db_connection: sqlite3.Connection
        self.sql_list: list[str] = [FUNCTION_SQL, CLASS_SQL, CLASS_METHOD_SQL]

    def init_db(self, codebase_snapshot_hash: str) -> sqlite3.Connection:
        """
        This function initialize the database.

        Args:
            codebase_snapshot_hash: code base snapshot.

        Return:
            a sqlite connection
        """
        if not CKG_DATABASE_PATH.exists():
            CKG_DATABASE_PATH.mkdir(parents=True, exist_ok=True)

        database_path: Path = get_ckg_database_path(codebase_snapshot_hash)
        self.db_connection = sqlite3.connect(database_path)

        for sql in self.sql_list:
            self.db_connection.execute(sql)

        self.db_connection.commit()

        return self.db_connection

    def insert_entry(self, entry: FunctionEntry | ClassEntry) -> None:
        """
        Insert entry into db.

        Args:
            entry: the entry to insert

        Returns:
            None
        #TODO: add try catch block to avoid connection problem.
        """
        match entry:
            case FunctionEntry():
                self._insert_function_handler(entry)

            case ClassEntry():
                self._insert_class_handler(entry)

        self.db_connection.commit()

    def _insert_function_handler(self, entry: FunctionEntry) -> None:
        """
        Insert function entry including functions and class methodsinto db.

        Args:
            entry: the entry to insert

        Returns:
            None
        """
        if entry.parent_class:
            # if the entry has a parent class, we need to insert a class method
            self.db_connection.execute(
                """
                    INSERT INTO class_methods (name, class_name, file_path, body, start_line, end_line)
                    VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    entry.name,
                    entry.parent_class.name,
                    entry.file_path,
                    entry.body,
                    entry.start_line,
                    entry.end_line,
                ),
            )
        else:
            # no parent class, so we need to insert a function
            self.db_connection.execute(
                """
                    INSERT INTO functions (name, file_path, body, start_line, end_line)
                    VALUES (?, ?, ?, ?, ?)
                """,
                (entry.name, entry.file_path, entry.body, entry.start_line, entry.end_line),
            )

    def _insert_class_handler(self, entry: ClassEntry) -> None:
        class_fields: str = "\n".join(entry.fields)
        class_methods: str = "\n".join(entry.methods)
        self.db_connection.execute(
            """
                INSERT INTO classes (name, file_path, body, fields, methods, start_line, end_line)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                entry.name,
                entry.file_path,
                entry.body,
                class_fields,
                class_methods,
                entry.start_line,
                entry.end_line,
            ),
        )


FUNCTION_SQL = """
    CREATE TABLE IF NOT EXISTS functions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        file_path TEXT NOT NULL,
        body TEXT NOT NULL,
        start_line INTEGER NOT NULL,
        end_line INTEGER NOT NULL
    )"""

CLASS_SQL = """
    CREATE TABLE IF NOT EXISTS classes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        file_path TEXT NOT NULL,
        body TEXT NOT NULL,
        fields TEXT NOT NULL,
        methods TEXT NOT NULL,
        start_line INTEGER NOT NULL,
        end_line INTEGER NOT NULL
    )"""

CLASS_METHOD_SQL = """
    CREATE TABLE IF NOT EXISTS class_methods (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        class_name TEXT NOT NULL,
        file_path TEXT NOT NULL,
        body TEXT NOT NULL,
        start_line INTEGER NOT NULL,
        end_line INTEGER NOT NULL
    )"""
