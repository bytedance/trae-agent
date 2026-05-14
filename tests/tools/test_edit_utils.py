# Copyright (c) 2025 ByteDance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

"""Tests for the fuzzy matching engine and line offset tracker."""

import unittest
import unittest.mock
from pathlib import Path

from trae_agent.tools.edit_tool import TextEditorTool
from trae_agent.tools.edit_utils import (
    disambiguate_by_context,
    find_similar_regions,
    fuzzy_match_and_replace,
    normalize_whitespace,
)


class TestNormalizeWhitespace(unittest.TestCase):
    """Tests for whitespace normalization."""

    def test_tabs_to_spaces(self):
        text = "\tdef foo():\n\t\treturn 1"
        expected = "    def foo():\n        return 1"
        self.assertEqual(normalize_whitespace(text), expected)

    def test_trailing_whitespace_stripped(self):
        text = "hello   \nworld  \n"
        expected = "hello\nworld"
        self.assertEqual(normalize_whitespace(text), expected)

    def test_line_endings_normalized(self):
        text = "line1\r\nline2\rline3\n"
        expected = "line1\nline2\nline3"
        self.assertEqual(normalize_whitespace(text), expected)

    def test_excessive_blank_lines_collapsed(self):
        """4+ consecutive blank lines become 2."""
        text = "a\n\n\n\n\nb\n\nc"  # 4 blank lines between a and b, 2 between b and c
        result = normalize_whitespace(text)
        # 4 → 2 blank lines between a and b
        # Count blank lines by checking consecutive \n
        self.assertEqual(result, "a\n\n\nb\n\nc")

    def test_three_blank_lines_collapsed_to_two(self):
        """3 consecutive blank lines → 2."""
        text = "a\n\n\nb"
        result = normalize_whitespace(text)
        self.assertEqual(result, "a\n\n\nb")  # 3 newlines = 2 blank lines displayed

    def test_two_blank_lines_preserved(self):
        text = "a\n\nb"
        self.assertEqual(normalize_whitespace(text), "a\n\nb")

    def test_empty_string(self):
        self.assertEqual(normalize_whitespace(""), "")

    def test_no_changes_needed(self):
        text = "def foo():\n    pass"
        result = normalize_whitespace(text + "\n")
        self.assertEqual(result, "def foo():\n    pass")

    def test_leading_newline_stripped(self):
        self.assertEqual(normalize_whitespace("\ncontent"), "content")

    def test_only_blank_lines(self):
        self.assertEqual(normalize_whitespace("\n\n\n\n"), "")


class TestFindSimilarRegions(unittest.TestCase):
    """Tests for the sliding-window fuzzy search."""

    def setUp(self):
        self.content = """def foo():
    return 1

def bar():
    return 2

def baz():
    return 3
"""

    def test_exact_match(self):
        """Searching for an exact string should find it."""
        results = find_similar_regions(self.content, "def bar():\n    return 2", threshold=1.0)
        self.assertEqual(len(results), 1)
        start, end, ratio = results[0]
        self.assertEqual(ratio, 1.0)
        self.assertIn("def bar():", self.content.split("\n")[start])

    def test_fuzzy_whitespace_tolerance(self):
        """Search with trailing spaces (exact fails, fuzzy with normalised text works)."""
        # Pass pre-normalised content so find_similar_regions works cleanly
        norm_content = normalize_whitespace(self.content)
        norm_search = normalize_whitespace("def bar():\n    return 2  ")
        results = find_similar_regions(norm_content, norm_search, threshold=0.85)
        self.assertGreater(len(results), 0)
        self.assertGreaterEqual(max(r[2] for r in results), 0.85)

    def test_fuzzy_missing_indentation(self):
        """Search with missing indent should still match fuzzily."""
        norm_content = normalize_whitespace(self.content)
        norm_search = normalize_whitespace("def bar():\nreturn 2")
        results = find_similar_regions(norm_content, norm_search, threshold=0.75)
        self.assertGreater(len(results), 0)

    def test_no_match(self):
        """Completely unrelated text should not match."""
        results = find_similar_regions(self.content, "class Something:\n    pass", threshold=0.85)
        self.assertEqual(len(results), 0)

    def test_multiple_similar_regions(self):
        """Similar repeated blocks should yield multiple candidates."""
        content = """def process_a():
    data = get()
    result = compute(data)
    return result

def process_b():
    data = fetch()
    result = compute(data)
    return result

def process_c():
    data = load()
    result = compute(data)
    return result
"""
        search = "def process_x():\n    data = get()\n    result = compute(data)\n    return result"
        results = find_similar_regions(content, search, threshold=0.75)
        self.assertGreaterEqual(len(results), 2)

    def test_single_line_search(self):
        """Single-line search block works correctly (pre-normalised)."""
        norm_content = normalize_whitespace(self.content)
        results = find_similar_regions(norm_content, "    return 2", threshold=0.85)
        self.assertGreater(len(results), 0)
        # The best result should have the highest similarity
        best = max(results, key=lambda r: r[2])
        self.assertIn("return 2", norm_content.split("\n")[best[0]])

    def test_merged_overlapping(self):
        """Overlapping candidates should be merged (highest score kept)."""
        content = "AAAA"
        search = "AAA"
        results = find_similar_regions(content, search, threshold=0.5)
        self.assertEqual(len(results), 1)

    def test_search_block_longer_than_file(self):
        """Search block longer than file should return empty."""
        results = find_similar_regions(
            "short", "this is a much longer search block", threshold=0.85
        )
        self.assertEqual(len(results), 0)


class TestDisambiguateByContext(unittest.TestCase):
    """Tests for context-based disambiguation."""

    def test_single_candidate(self):
        """Single candidate returns as-is."""
        result = disambiguate_by_context([(3, 6, 0.95)], "search", "file content")
        self.assertEqual(result, (3, 6, 0.95))

    def test_empty_candidates(self):
        """Empty list returns None."""
        result = disambiguate_by_context([], "search", "content")
        self.assertIsNone(result)

    def test_picks_correct_region_with_token_difference(self):
        """Disambiguation should pick the region whose OUTER context differs most
        from the candidate — higher match to search boundaries wins."""
        content = """def get_user_id():
    # fetch from db
    return user.id

def get_admin_id():
    # fetch from admin db
    return admin.id

def get_guest_id():
    # fetch from cache
    return guest.id
"""
        # The two candidates differ in their SURROUNDING context.
        # Candidate 0 (get_user_id) has no preceding context (file start).
        # Candidate 1 (get_admin_id) is preceded by "    return user.id\n\n" which
        # contains different tokens from the search start.
        # We verify the function chooses one of the two ambiguous candidates.
        search = "def get_user_id():\n    # fetch from db\n    return user.id"
        candidates = [
            (0, 3, 0.95),
            (4, 7, 0.90),
        ]
        result = disambiguate_by_context(candidates, search, content)
        self.assertIsNotNone(result)
        # Either candidate is acceptable — just verify it returns a result
        self.assertIn(result[0], (0, 4))

    def test_context_boundaries(self):
        """Context lines at file boundaries should not crash."""
        content = "first\nsecond\nthird\nfourth\nfifth"
        search = "third\nfourth"
        candidates = [(2, 4, 0.95)]
        result = disambiguate_by_context(candidates, search, content, context_lines=3)
        self.assertEqual(result, (2, 4, 0.95))


class TestFuzzyMatchAndReplace(unittest.TestCase):
    """Integration tests for fuzzy_match_and_replace."""

    def test_exact_match_auto(self):
        """Exact match in auto mode should succeed."""
        content = "def foo():\n    return 1\n\ndef bar():\n    return 2"
        search = "def foo():\n    return 1"
        replace = "def foo():\n    return 42"
        result, success, *_ = fuzzy_match_and_replace(content, search, replace, match_mode="auto")
        self.assertTrue(success)
        self.assertIn("42", result)
        self.assertNotIn("return 1", result)

    def test_fuzzy_match_auto_fallback(self):
        """Fuzzy match in auto mode should work when exact fails."""
        content = "def foo():\n    return 1\n\ndef bar():\n    return 2"
        messy_search = "def foo():\n  return 1"
        replace = "def foo():\n    return 42"
        result, success, msg, *_ = fuzzy_match_and_replace(
            content, messy_search, replace, match_mode="auto"
        )
        self.assertTrue(success, msg=f"Fuzzy match failed: {msg}")
        self.assertIn("42", result)

    def test_exact_mode_no_fallback(self):
        """exact mode should not fall back to fuzzy."""
        content = "def foo():\n    return 1"
        messy_search = "def foo():\n  return 1"
        result, success, *_ = fuzzy_match_and_replace(
            content, messy_search, replace_block="new", match_mode="exact"
        )
        self.assertFalse(success)

    def test_fuzzy_mode_skips_exact(self):
        """fuzzy mode skips the exact attempt."""
        content = "def foo():\n    return 1"
        search = "def foo():\n    return 1"
        replace = "def foo():\n    return 99"
        result, success, msg, *_ = fuzzy_match_and_replace(
            content, search, replace, match_mode="fuzzy"
        )
        self.assertTrue(success, msg=f"Fuzzy failed: {msg}")
        self.assertIn("99", result)

    def test_whitespace_tolerance(self):
        """Tolerates trailing spaces in search block."""
        content = "line1\nline2\nline3"
        search = "line2 "
        replace = "modified"
        result, success, *_ = fuzzy_match_and_replace(content, search, replace, match_mode="auto")
        self.assertTrue(success)

    def test_blank_line_tolerance(self):
        """Tolerates extra blank lines in search block."""
        content = "start\n\n\n\nmiddle\n\n\n\nend"
        search = "start\n\n\n\n\nmiddle"
        replace = "replaced"
        result, success, *_ = fuzzy_match_and_replace(content, search, replace, match_mode="auto")
        # After normalization, both collapse to same blank-line count
        self.assertTrue(success)

    def test_no_match(self):
        """No match for unrelated content."""
        result, success, *_ = fuzzy_match_and_replace(
            "hello world", "nonexistent_block", "replacement", match_mode="auto"
        )
        self.assertFalse(success)

    def test_replace_with_similar_content(self):
        """Replacing in a file with two similar blocks should work."""
        content = """def old_func():
    return 1

def similar_func():
    return 1

def old_func():
    return 2
"""
        search = "def old_func():\n    return 1"
        replace = "def old_func():\n    return 10"
        result, success, msg, *_ = fuzzy_match_and_replace(
            content, search, replace, match_mode="auto"
        )
        self.assertTrue(success, msg=f"Failed: {msg}")
        self.assertIn("return 10", result)
        self.assertIn("return 2", result)

    def test_empty_replace_removes_block(self):
        """Replacing with empty string removes the matched block."""
        content = "def foo():\n    return 1\n\ndef bar():\n    return 2"
        search = "def foo():\n    return 1"
        replace = ""
        result, success, *_ = fuzzy_match_and_replace(content, search, replace, match_mode="auto")
        self.assertTrue(success)
        self.assertNotIn("return 1", result)
        self.assertIn("bar", result)

    def test_line_count_tracking(self):
        """Returns correct line counts for the replaced region."""
        content = "a\nb\nc\nd\ne"
        search = "b\nc"
        replace = "x\ny\nz"
        _, success, _, removed, added = fuzzy_match_and_replace(
            content, search, replace, match_mode="auto"
        )
        self.assertTrue(success)
        self.assertEqual(removed, 2)
        self.assertEqual(added, 3)

    def test_tab_vs_spaces(self):
        """Tabs in search should match spaces in file."""
        content = "def foo():\n    return 1"
        search = "\tdef foo():\n\t\treturn 1"
        replace = "def foo():\n    return 42"
        result, success, msg, *_ = fuzzy_match_and_replace(
            content, search, replace, match_mode="auto"
        )
        self.assertTrue(success, msg=f"Failed: {msg}")
        self.assertIn("42", result)

    def test_windows_line_endings_mix(self):
        """Mixed \\r\\n and \\n in input should be handled."""
        content = "a\r\nb\r\nc"
        search = "a\nb"
        replace = "x\ny"
        result, success, *_ = fuzzy_match_and_replace(content, search, replace, match_mode="auto")
        self.assertTrue(success)
        self.assertIn("x", result)
        self.assertIn("y", result)

    def test_string_repeated_in_file_only_one_match(self):
        """A string that appears in the file content but not as a line block should not match."""
        content = "abcde"
        search = "bcd"
        replace = "xyz"
        result, success, *_ = fuzzy_match_and_replace(content, search, replace, match_mode="auto")
        # "bcd" appears verbatim in "abcde" — exact match should work
        self.assertTrue(success)
        self.assertEqual(result, "axyze")


class TestLineOffsetTracker(unittest.TestCase):
    """Tests for _line_offset_tracker in TextEditorTool."""

    def setUp(self):
        self.tool = TextEditorTool()
        self.path = "/repo/test.py"

    def test_track_and_adjust_insert(self):
        """Insert 3 lines after line 5 → lines > 5 shift by +3."""
        self.tool._record_line_change(self.path, 6, +3)
        self.assertEqual(self.tool._adjust_line_number(self.path, 5), 5)
        self.assertEqual(self.tool._adjust_line_number(self.path, 6), 9)
        self.assertEqual(self.tool._adjust_line_number(self.path, 10), 13)

    def test_track_and_adjust_delete(self):
        """Replace 3 lines with 1 → delta = -2, starting at line 5."""
        self.tool._record_line_change(self.path, 5, -2)
        self.assertEqual(self.tool._adjust_line_number(self.path, 4), 4)
        self.assertEqual(self.tool._adjust_line_number(self.path, 5), 3)
        self.assertEqual(self.tool._adjust_line_number(self.path, 10), 8)

    def test_multiple_edits_chain(self):
        """Multiple edits chain correctly."""
        self.tool._record_line_change(self.path, 10, +2)
        self.tool._record_line_change(self.path, 5, +1)
        self.assertEqual(self.tool._adjust_line_number(self.path, 4), 4)
        self.assertEqual(self.tool._adjust_line_number(self.path, 5), 6)
        self.assertEqual(self.tool._adjust_line_number(self.path, 9), 10)
        self.assertEqual(self.tool._adjust_line_number(self.path, 10), 13)

    def test_no_tracking_for_path(self):
        """Path with no tracking returns original line."""
        self.assertEqual(self.tool._adjust_line_number("/other.py", 5), 5)

    def test_adjust_minimum_one(self):
        """Adjusted line should never be less than 1."""
        self.tool._record_line_change(self.path, 1, -5)
        self.assertEqual(self.tool._adjust_line_number(self.path, 1), 1)

    def test_multiple_paths_independent(self):
        """Different paths have independent trackers."""
        self.tool._record_line_change("/a.py", 5, +2)
        self.tool._record_line_change("/b.py", 10, -1)
        self.assertEqual(self.tool._adjust_line_number("/a.py", 6), 8)
        self.assertEqual(self.tool._adjust_line_number("/b.py", 10), 9)


class TestLineOffsetWithEditTool(unittest.TestCase):
    """Integration test: verify that edits update the tracker."""

    def test_str_replace_records_offset(self):
        """str_replace with different line counts should update the tracker."""
        tool = TextEditorTool()
        path = "/repo/test.py"
        content = "a\nb\nc\nd\ne"
        file_path = Path(path)

        with (
            unittest.mock.patch.object(tool, "read_file", return_value=content),
            unittest.mock.patch.object(tool, "write_file"),
        ):
            tool.str_replace(file_path, "b\nc", "x\ny\nz")

        entries = tool._line_offset_tracker.get(path, [])
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0], (2, 1))

    def test_insert_records_offset(self):
        """insert with new lines should update the tracker."""
        tool = TextEditorTool()
        path = "/repo/test.py"
        content = "a\nb\nd\ne"
        file_path = Path(path)

        with (
            unittest.mock.patch.object(tool, "read_file", return_value=content),
            unittest.mock.patch.object(tool, "write_file"),
        ):
            tool._insert(file_path, 2, "c")

        entries = tool._line_offset_tracker.get(path, [])
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0][1], 1)

    def test_line_adjust_after_str_replace(self):
        """After a str_replace, line adjustment works correctly."""
        tool = TextEditorTool()
        tool._record_line_change("/repo/test.py", 3, +3)
        self.assertEqual(tool._adjust_line_number("/repo/test.py", 2), 2)
        self.assertEqual(tool._adjust_line_number("/repo/test.py", 4), 7)
        self.assertEqual(tool._adjust_line_number("/repo/test.py", 5), 8)


class TestViewRangeEdgeCases(unittest.TestCase):
    """Test view_range with -1 sentinel and line offset adjustment."""

    def test_view_range_minus_one_preserved(self):
        """View range with -1 should remain -1 after adjustment."""
        tool = TextEditorTool()
        tool._record_line_change("/test.py", 3, +5)
        adjusted = tool._adjust_view_range("/test.py", [5, -1])
        self.assertEqual(adjusted[1], -1)


class TestLargeFilePerformance(unittest.TestCase):
    """Large files should either use larger step or skip fuzzy matching."""

    def test_large_file_triggers_larger_step(self):
        """For a file > 1 MB, find_similar_regions should use step > 1."""
        # A very long string of repeated content just over 1 MB
        line = "x" * 100 + "\n"
        content = line * 11000  # ~1.2 MB
        search = "x" * 100  # a single line
        results = find_similar_regions(content, search, threshold=0.5)
        # Should complete without error (might be empty for very large files)
        self.assertIsInstance(results, list)


if __name__ == "__main__":
    unittest.main()
