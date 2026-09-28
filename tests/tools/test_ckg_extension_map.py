# Copyright (c) 2025 ByteDance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

"""Tests for the file-extension side of the CKG build.

`CKGDatabase._construct_ckg` walks `extension_to_language` and skips every file whose
extension is not a key of that mapping. The skip is silent -- no error, no log line -- so
`ckg_tool` answers a query about such a file with "No functions named <identifier> found.",
which is a false negative whenever the file does declare that identifier.
"""

import gc
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from trae_agent.tools.ckg import ckg_database as ckg_module
from trae_agent.tools.ckg.base import extension_to_language

# The arms of the `match language:` block in CKGDatabase._construct_ckg. A language outside
# this set reaches `case _: continue` and is dropped without a trace.
SUPPORTED_LANGUAGES = frozenset({"python", "java", "cpp", "c", "typescript", "javascript"})

CPP_TEMPLATE = """int {prefix}_free(int x) {{
    return x + 1;
}}

class {capital}Class {{
public:
    int {prefix}_method(int s) {{
        return s + 1;
    }}
}};
"""

JS_TEMPLATE = """export class {capital}Class {{
    {prefix}Method(a) {{
        return a;
    }}
}}
"""

CJS_TEMPLATE = """class {capital}Class {{
    {prefix}Method(a) {{
        return a;
    }}
}}

module.exports = {{ {capital}Class }};
"""

TS_TEMPLATE = """export class {capital}Class {{
    {prefix}Method(a: number): number {{
        return a;
    }}
}}
"""

# Each unmapped extension is paired with a mapped twin of the same language and the same
# shape, so an identifier found in the twin but not in the alias can only be explained by
# the extension -- not by the grammar, the visitor, or the query.
#
# filename -> (template, prefix, capital, method name, free function name or None)
FIXTURES: dict[str, tuple[str, str, str, str, str | None]] = {
    "Widget.hh": (CPP_TEMPLATE, "hh", "Hh", "hh_method", "hh_free"),
    "Widget.hpp": (CPP_TEMPLATE, "hpp", "Hpp", "hpp_method", "hpp_free"),
    "Vector.hxx": (CPP_TEMPLATE, "hxx", "Hxx", "hxx_method", "hxx_free"),
    "Mask.tcc": (CPP_TEMPLATE, "tcc", "Tcc", "tcc_method", "tcc_free"),
    "Entry.mjs": (JS_TEMPLATE, "mjs", "Mjs", "mjsMethod", None),
    "Entry.js": (JS_TEMPLATE, "js", "Js", "jsMethod", None),
    "Legacy.cjs": (CJS_TEMPLATE, "cjs", "Cjs", "cjsMethod", None),
    "Config.mts": (TS_TEMPLATE, "mts", "Mts", "mtsMethod", None),
    "Config.ts": (TS_TEMPLATE, "ts", "Ts", "tsMethod", None),
    "Module.cts": (TS_TEMPLATE, "cts", "Cts", "ctsMethod", None),
}


class ExtensionLanguageMappingTest(unittest.TestCase):
    """The mapping itself, before any file is read."""

    def test_cpp_header_aliases_reach_the_cpp_parser(self):
        for extension in (".hh", ".hxx", ".tcc"):
            with self.subTest(extension=extension):
                self.assertEqual(extension_to_language.get(extension), "cpp")

    def test_javascript_module_extensions_reach_the_javascript_parser(self):
        for extension in (".mjs", ".cjs"):
            with self.subTest(extension=extension):
                self.assertEqual(extension_to_language.get(extension), "javascript")

    def test_typescript_module_extensions_reach_the_typescript_parser(self):
        for extension in (".mts", ".cts"):
            with self.subTest(extension=extension):
                self.assertEqual(extension_to_language.get(extension), "typescript")

    def test_every_entry_names_a_language_the_graph_can_walk(self):
        unwalkable = sorted(set(extension_to_language.values()) - SUPPORTED_LANGUAGES)
        self.assertEqual(unwalkable, [])

    def test_every_key_is_a_lowercase_dotted_suffix(self):
        for extension in extension_to_language:
            with self.subTest(extension=extension):
                self.assertTrue(extension.startswith("."), extension)
                self.assertEqual(extension, extension.lower())


class CkgBuildsFromAliasedExtensionsTest(unittest.TestCase):
    """End to end: a codebase of aliased files, queried through the real database."""

    _tmp: Path
    _db: ckg_module.CKGDatabase

    @classmethod
    def setUpClass(cls):
        cls._tmp = Path(tempfile.mkdtemp(prefix="ckg_extension_aliases_"))
        codebase = cls._tmp / "codebase"
        codebase.mkdir()
        for name, (template, prefix, capital, _, _) in FIXTURES.items():
            (codebase / name).write_text(
                template.format(prefix=prefix, capital=capital), encoding="utf-8"
            )
        # Keep the generated database out of ~/.trae-agent and out of the developer's cache.
        cache = cls._tmp / "ckg_cache"
        cache.mkdir()
        with (
            mock.patch.object(ckg_module, "CKG_DATABASE_PATH", cache),
            mock.patch.object(ckg_module, "CKG_STORAGE_INFO_FILE", cache / "storage_info.json"),
        ):
            cls._db = ckg_module.CKGDatabase(codebase)

    @classmethod
    def tearDownClass(cls):
        # Dropping the attribute releases the only reference, so CKGDatabase.__del__ closes
        # the sqlite connection once and the temporary directory is deletable on Windows.
        del cls._db
        gc.collect()
        shutil.rmtree(cls._tmp, ignore_errors=True)

    def _indexed_files(self) -> set[str]:
        rows = self._db._db_connection.execute("SELECT DISTINCT file_path FROM classes").fetchall()
        return {Path(str(row[0])).name for row in rows}

    def test_aliased_files_reach_the_graph(self):
        indexed = self._indexed_files()
        for name in FIXTURES:
            with self.subTest(file=name):
                self.assertIn(name, indexed)

    def test_class_declared_in_an_aliased_file_is_found(self):
        for name, (_, _, capital, _, _) in FIXTURES.items():
            with self.subTest(file=name, identifier=f"{capital}Class"):
                entries = self._db.query_class(f"{capital}Class")
                self.assertEqual([Path(str(e.file_path)).name for e in entries], [name])

    def test_method_declared_in_an_aliased_file_is_found(self):
        for name, (_, _, _, method, _) in FIXTURES.items():
            with self.subTest(file=name, identifier=method):
                entries = self._db.query_function(method, entry_type="class_method")
                self.assertEqual([Path(str(e.file_path)).name for e in entries], [name])

    def test_free_function_declared_in_an_aliased_header_is_found(self):
        for name, (_, _, _, _, free_function) in FIXTURES.items():
            if free_function is None:
                continue
            with self.subTest(file=name, identifier=free_function):
                entries = self._db.query_function(free_function, entry_type="function")
                self.assertEqual([Path(str(e.file_path)).name for e in entries], [name])


if __name__ == "__main__":
    unittest.main()
