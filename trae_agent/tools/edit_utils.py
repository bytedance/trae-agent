# Copyright (c) 2025 ByteDance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

"""Text normalization and fuzzy matching utilities for the edit tool."""

import difflib

# Threshold for fuzzy similarity matching
FUZZY_MATCH_THRESHOLD: float = 0.85

# Files larger than this (in bytes) use a larger sliding-window step
LARGE_FILE_THRESHOLD: int = 1_000_000  # 1 MB

# Files larger than this skip fuzzy matching entirely
VERY_LARGE_FILE_THRESHOLD: int = 10_000_000  # 10 MB

# Number of context lines to examine during disambiguation
CONTEXT_LINES: int = 3


def normalize_whitespace(text: str) -> str:
    """Normalize whitespace for resilient comparison.

    - Tabs → 4 spaces
    - Windows/Mac line endings → \\n
    - Strip trailing newline so split doesn't produce empty final line
    - Strip trailing whitespace per line
    - Collapse 3+ consecutive blank lines into 2
    """
    # Tab expansion
    text = text.expandtabs(4)
    # Line ending normalization
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    # Strip leading/trailing newlines so split gives clean line list
    text = text.strip("\n")
    # Strip trailing whitespace per line
    lines = text.split("\n")
    lines = [line.rstrip() for line in lines]
    # Collapse 3+ consecutive blank lines into 2
    result = []
    empty_run = 0
    for line in lines:
        if line == "":
            empty_run += 1
            if empty_run <= 2:
                result.append(line)
        else:
            empty_run = 0
            result.append(line)
    text = "\n".join(result)
    return text


def _is_large_file(content: str) -> bool:
    """Check if file content is large enough to warrant step-size adjustments."""
    return len(content.encode("utf-8")) > LARGE_FILE_THRESHOLD


def _is_very_large_file(content: str) -> bool:
    """Check if file content is too large for fuzzy matching."""
    return len(content.encode("utf-8")) > VERY_LARGE_FILE_THRESHOLD


def find_similar_regions(
    file_content: str,
    search_block: str,
    threshold: float = FUZZY_MATCH_THRESHOLD,
) -> list[tuple[int, int, float]]:
    """Use a sliding window to find regions in *file_content* similar to *search_block*.

    Returns a list of ``(start_line_0based, end_line_0based, similarity_ratio)``
    tuples, ordered by position.  Overlapping or adjacent candidates are merged
    keeping the one with the highest score.

    For files > 1 MB the window step is increased to 3 lines as a performance
    safeguard.  Files > 10 MB skip fuzzy matching entirely.
    """
    if _is_very_large_file(file_content):
        return []

    file_lines = file_content.split("\n")
    search_lines = search_block.split("\n")
    window_size = len(search_lines)

    if window_size == 0 or len(file_lines) < window_size:
        return []

    step = 3 if _is_large_file(file_content) else 1
    search_text = "\n".join(search_lines)

    raw_candidates: list[tuple[int, int, float]] = []

    for i in range(0, len(file_lines) - window_size + 1, step):
        window_text = "\n".join(file_lines[i : i + window_size])
        ratio = difflib.SequenceMatcher(None, window_text, search_text).ratio()
        if ratio >= threshold:
            raw_candidates.append((i, i + window_size, ratio))

    if not raw_candidates:
        return []

    # Merge overlapping / adjacent candidates, keeping the highest score
    merged: list[tuple[int, int, float]] = [raw_candidates[0]]
    for cand in raw_candidates[1:]:
        prev = merged[-1]
        if cand[0] <= prev[1]:
            if cand[2] > prev[2]:
                merged[-1] = cand
        else:
            merged.append(cand)

    return merged


def disambiguate_by_context(
    candidates: list[tuple[int, int, float]],
    search_block: str,
    file_content: str,
    context_lines: int = CONTEXT_LINES,
) -> tuple[int, int, float] | None:
    """Resolve ambiguous matches by comparing surrounding context.

    For each candidate, the *context_lines* lines immediately before and after
    the matched region are compared with the first / last *context_lines* of
    *search_block*.  The candidate whose context best matches wins.
    """
    if not candidates:
        return None
    if len(candidates) == 1:
        return candidates[0]

    file_lines = file_content.split("\n")
    search_lines = search_block.split("\n")

    search_start = "\n".join(search_lines[:context_lines])
    search_end = "\n".join(search_lines[-context_lines:])

    best_candidate: tuple[int, int, float] | None = None
    best_score = float("inf")  # lower is better

    for start_line, end_line, ratio in candidates:
        # Context before the candidate
        before_start = max(0, start_line - context_lines)
        context_before = "\n".join(file_lines[before_start:start_line])

        # Context after the candidate
        after_end = min(len(file_lines), end_line + context_lines)
        context_after = "\n".join(file_lines[end_line:after_end])

        # Inverted similarity → distance (0 = identical, 1 = completely different)
        score_before = 1.0 - difflib.SequenceMatcher(None, context_before, search_start).ratio()
        score_after = 1.0 - difflib.SequenceMatcher(None, context_after, search_end).ratio()

        total = score_before + score_after
        if total < best_score:
            best_score = total
            best_candidate = (start_line, end_line, ratio)

    return best_candidate


def fuzzy_match_and_replace(
    file_content: str,
    search_block: str,
    replace_block: str,
    match_mode: str = "auto",
) -> tuple[str, bool, str, int, int]:
    """Fuzzy-match *search_block* in *file_content* and replace with *replace_block*.

    Strategy (``match_mode == "auto"``, the default):
    1. Normalise whitespace for both sides.
    2. Attempt an exact normalised match.
    3. If that fails (or produces multiple hits), fall back to the sliding-window
       fuzzy search + context disambiguation.

    Returns ``(new_content, success, message, removed_line_count, added_line_count)``.
    """
    norm_content = normalize_whitespace(file_content)
    norm_search = normalize_whitespace(search_block)
    norm_replace = normalize_whitespace(replace_block) if replace_block else ""

    # ── Strategy 1: exact normalised match ──────────────────────────────
    if match_mode != "fuzzy":
        occurrences = norm_content.count(norm_search)
        if occurrences == 1:
            new_content = norm_content.replace(norm_search, norm_replace, 1)
            removed = norm_search.count("\n") + 1
            added = norm_replace.count("\n") + 1
            return new_content, True, "Exact match after normalisation", removed, added
        if occurrences > 1 and match_mode == "exact":
            return (
                file_content,
                False,
                f"Multiple occurrences ({occurrences}) of search_block after normalisation.",
                0,
                0,
            )

    # ── Strategy 2: fuzzy sliding-window search ─────────────────────────
    if match_mode == "exact":
        return file_content, False, "No exact match found after normalisation.", 0, 0

    candidates = find_similar_regions(norm_content, norm_search)
    if not candidates:
        return file_content, False, "No matching regions found in file.", 0, 0

    best = disambiguate_by_context(candidates, norm_search, norm_content)
    if best is None:
        return file_content, False, "Could not disambiguate between similar regions.", 0, 0

    start_line, end_line, ratio = best

    file_lines = norm_content.split("\n")
    replace_lines = norm_replace.split("\n")

    new_lines = file_lines[:start_line] + replace_lines + file_lines[end_line:]
    new_content = "\n".join(new_lines)

    removed = end_line - start_line
    added = len(replace_lines)

    msg = f"Fuzzy matched region with similarity {ratio:.1%}"
    return new_content, True, msg, removed, added
