# Copyright (c) 2025 ByteDance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT


"""
dataclass for ckg_tool
"""

import sqlite3
from dataclasses import dataclass


@dataclass
class FunctionEntry:
    name: str
    file_path: str
    body: str
    start_line: int
    end_line: int
    parent_function: "FunctionEntry | None" = None
    parent_class: "ClassEntry | None" = None


@dataclass
class ClassEntry:
    name: str
    file_path: str
    body: str
    fields: list[str]
    methods: list[str]
    start_line: int
    end_line: int


@dataclass
class CKGStorage:
    db_connection: sqlite3.Connection
    codebase_snapshot_hash: str
