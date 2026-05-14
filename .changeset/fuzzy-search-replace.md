---
"trae-agent": minor
---

## Tool Schema — Minor expansion

### New commands

- **`search_replace`** — A SEARCH/REPLACE edit command using a fuzzy matching engine. Uses `difflib.SequenceMatcher` sliding-window search with context-based disambiguation. Supports three match modes:
  - `auto` (default): exact match first, falls back to fuzzy
  - `exact`: strict exact match only, no fallback
  - `fuzzy`: skip exact, directly use fuzzy matching

- **`write`** — Full-file overwrite command (replaces entire file contents atomically).

### Schema changes

Added parameters:
| Command | Parameter | Type | Description |
|---------|-----------|------|-------------|
| `search_replace` | `search_block` | `string` | The text to search for |
| `search_replace` | `replace_block` | `string` | Replacement text |
| `search_replace` | `match_mode` | `"auto" \| "exact" \| "fuzzy"` | Matching strategy |

### Deprecations

- **`str_replace`** — Kept for backward compatibility but deprecated; callers should migrate to `search_replace`.

### Internal improvements

- **Fuzzy matching engine** (`edit_utils.py`):
  - `normalize_whitespace()` — Normalizes tabs→4 spaces, CRLF→LF, strips trailing whitespace, collapses 3+ blank lines→2
  - `find_similar_regions()` — Sliding-window `SequenceMatcher` search; uses step=3 for files >1 MB, skips entirely for files >10 MB
  - `disambiguate_by_context()` — Resolves multiple fuzzy candidates by comparing surrounding context lines with search-block boundaries
  - `fuzzy_match_and_replace()` — Orchestrates exact→fuzzy→replace pipeline; returns line-count deltas

- **Line offset tracker** — `TextEditorTool._line_offset_tracker` maps old line numbers to new positions after edits, so `view_range` stays correct across multiple modifications.

- **Bug fix**: `view_range` with `final_line=-1` (view-to-end sentinel) no longer incorrectly adjusted by line offset tracker.

- **Atomic file writes**: All file modifications use `tempfile.mkstemp(dir=parent)` + `os.replace` for crash-safe writes.
