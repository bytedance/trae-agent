# Copyright (c) 2025 ByteDance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT


from dataclasses import dataclass


# Define dataclasses for CKG entries
@dataclass
class FunctionEntry:
    """
    dataclass for function entry.
    """

    name: str
    file_path: str
    body: str
    start_line: int
    end_line: int
    parent_function: str | None = None
    parent_class: str | None = None


@dataclass
class ClassEntry:
    """
    dataclass for class entry.
    """

    name: str
    file_path: str
    body: str
    start_line: int
    end_line: int
    fields: str | None = None
    methods: str | None = None


# We need a mapping from file extension to tree-sitter language name to parse files and build the graph
extension_to_language = {
    ".py": "python",
    ".java": "java",
    ".cpp": "cpp",
    ".hpp": "cpp",
    ".c++": "cpp",
    ".cxx": "cpp",
    ".cc": "cpp",
    ".c": "c",
    ".h": "c",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".js": "javascript",
    ".jsx": "javascript",
}
