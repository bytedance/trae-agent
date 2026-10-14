# Copyright (c) 2025 ByteDance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

"""Regression tests for CKG extension gating (#510 case, #524 aliases)."""

from __future__ import annotations

import tempfile
from collections.abc import Iterator
from pathlib import Path

import pytest

import trae_agent.tools.ckg.ckg_database as ckg_database
from trae_agent.tools.ckg.base import extension_to_language
from trae_agent.tools.ckg.ckg_database import CKGDatabase


@pytest.fixture()
def ckg_tmpdir(monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """Point CKG cache at a temp dir so tests never touch ~/.trae-agent."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        db_root = root / "ckg_cache"
        db_root.mkdir()
        monkeypatch.setattr(ckg_database, "CKG_DATABASE_PATH", db_root)
        monkeypatch.setattr(ckg_database, "CKG_STORAGE_INFO_FILE", db_root / "storage_info.json")
        yield root


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


class TestExtensionCaseSensitivity:
    """#510: on-disk case must not decide whether a file is indexed."""

    def test_uppercase_python_extension_is_indexed(self, ckg_tmpdir: Path) -> None:
        codebase = ckg_tmpdir / "case_py"
        _write(codebase / "a_lower.py", "def alpha_lower():\n    return 1\n")
        _write(codebase / "a_upper.PY", "def alpha_upper():\n    return 2\n")

        db = CKGDatabase(codebase)
        assert len(db.query_function("alpha_lower")) == 1
        assert len(db.query_function("alpha_upper")) == 1

    def test_uppercase_javascript_extension_is_indexed(self, ckg_tmpdir: Path) -> None:
        codebase = ckg_tmpdir / "case_js"
        # JS/TS visitors index class_declaration / method_definition, not free functions.
        _write(codebase / "c_lower.js", "class GammaLower {}\n")
        _write(codebase / "c_upper.JS", "class DeltaUpper {}\n")

        db = CKGDatabase(codebase)
        assert len(db.query_class("GammaLower")) == 1
        assert len(db.query_class("DeltaUpper")) == 1

    def test_mixed_case_header_extension_is_indexed(self, ckg_tmpdir: Path) -> None:
        codebase = ckg_tmpdir / "case_h"
        _write(codebase / "lower.h", "int lower_fn(void) { return 1; }\n")
        _write(codebase / "upper.H", "int upper_fn(void) { return 2; }\n")

        db = CKGDatabase(codebase)
        assert len(db.query_function("lower_fn")) == 1
        assert len(db.query_function("upper_fn")) == 1


class TestExtensionAliases:
    """#524: common alternate spellings of already-supported languages."""

    def test_cpp_header_aliases_reach_the_graph(self, ckg_tmpdir: Path) -> None:
        codebase = ckg_tmpdir / "alias_cpp"
        _write(
            codebase / "Widget.hh",
            "int hh_free() { return 1; }\n"
            "class HhClass {\npublic:\n  int hh_method() { return 2; }\n};\n",
        )
        _write(
            codebase / "Vector.hxx",
            "int hxx_free() { return 1; }\n"
            "class HxxClass {\npublic:\n  int hxx_method() { return 2; }\n};\n",
        )
        _write(
            codebase / "Mask.tcc",
            "int tcc_free() { return 1; }\n"
            "class TccClass {\npublic:\n  int tcc_method() { return 2; }\n};\n",
        )
        # twin that was already mapped
        _write(
            codebase / "Twin.hpp",
            "int hpp_free() { return 1; }\n"
            "class HppClass {\npublic:\n  int hpp_method() { return 2; }\n};\n",
        )

        db = CKGDatabase(codebase)
        for name in ("hh_free", "hxx_free", "tcc_free", "hpp_free"):
            assert len(db.query_function(name)) == 1, name
        for name in ("HhClass", "HxxClass", "TccClass", "HppClass"):
            assert len(db.query_class(name)) == 1, name
        for name in ("hh_method", "hxx_method", "tcc_method", "hpp_method"):
            assert len(db.query_function(name, entry_type="class_method")) == 1, name

    def test_javascript_module_extensions_reach_the_graph(self, ckg_tmpdir: Path) -> None:
        codebase = ckg_tmpdir / "alias_js"
        _write(codebase / "Entry.mjs", "class MjsClass { mjsMethod() { return 1; } }\n")
        _write(codebase / "Legacy.cjs", "class CjsClass { cjsMethod() { return 1; } }\n")
        _write(codebase / "Twin.js", "class JsClass { jsMethod() { return 1; } }\n")

        db = CKGDatabase(codebase)
        for name in ("MjsClass", "CjsClass", "JsClass"):
            assert len(db.query_class(name)) == 1, name
        for name in ("mjsMethod", "cjsMethod", "jsMethod"):
            assert len(db.query_function(name, entry_type="class_method")) == 1, name

    def test_typescript_module_extensions_reach_the_graph(self, ckg_tmpdir: Path) -> None:
        codebase = ckg_tmpdir / "alias_ts"
        _write(codebase / "Config.mts", "class MtsClass { mtsMethod() { return 1; } }\n")
        _write(codebase / "Module.cts", "class CtsClass { ctsMethod() { return 1; } }\n")
        _write(codebase / "Twin.ts", "class TsClass { tsMethod() { return 1; } }\n")

        db = CKGDatabase(codebase)
        for name in ("MtsClass", "CtsClass", "TsClass"):
            assert len(db.query_class(name)) == 1, name
        for name in ("mtsMethod", "ctsMethod", "tsMethod"):
            assert len(db.query_function(name, entry_type="class_method")) == 1, name


class TestExtensionMapInvariants:
    def test_every_extension_key_is_lowercase(self) -> None:
        for key in extension_to_language:
            assert key == key.lower()
            assert key.startswith(".")

    def test_every_language_is_walkable(self) -> None:
        allowed = {"python", "java", "cpp", "c", "typescript", "javascript"}
        assert set(extension_to_language.values()) <= allowed

    def test_alias_keys_present(self) -> None:
        expected = {
            ".hh": "cpp",
            ".hxx": "cpp",
            ".tcc": "cpp",
            ".mjs": "javascript",
            ".cjs": "javascript",
            ".mts": "typescript",
            ".cts": "typescript",
        }
        for key, language in expected.items():
            assert extension_to_language.get(key) == language
