# Copyright (c) 2025 ByteDance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

"""Tool output truncation — keep the agent's context window under control.

⭐⭐⭐ feature: when a tool returns > N bytes / N lines, truncate the head
and tail and replace the middle with a `[... N bytes / N lines truncated ...]`
marker so the LLM can still reason about the result. A clear hint tells the
model how to fetch specific line ranges (``sed -n A,Bp file`` or
``head/tail``) instead of dumping the whole thing again.

Defaults:
    MAX_BYTES = 30 KiB
    MAX_LINES = 2000

Configurable via ``trae_config.yaml``:
    ```yaml
    tool_output_truncation:
      max_bytes: 30000
      max_lines: 2000
      head_lines: 100
      tail_lines: 100
    ```
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class TruncationConfig:
    max_bytes: int = 30000  # ~30 KiB
    max_lines: int = 2000
    head_lines: int = 100
    tail_lines: int = 100


_DEFAULT = TruncationConfig()


def truncate(
    text: str,
    config: TruncationConfig | None = None,
) -> str:
    """Truncate a tool result string for inclusion in an LLM message.

    Args:
        text: raw tool output. ``None``/empty is passed through unchanged.
        config: limits; uses ``_DEFAULT`` when ``None``.

    Returns:
        The original string if it fits within both ``max_bytes`` and
        ``max_lines``. Otherwise a head + truncation marker + tail view,
        with a hint about how to fetch specific line ranges.
    """
    if not text:
        return text or ""

    cfg = config or _DEFAULT

    # Cheap path: nothing to do.
    if len(text) <= cfg.max_bytes and text.count("\n") + 1 <= cfg.max_lines:
        return text

    lines = text.splitlines(keepends=True)
    total_lines = len(lines)
    total_bytes = len(text.encode("utf-8"))

    # Decide head/tail slices.
    head = lines[: cfg.head_lines]
    tail = lines[-cfg.tail_lines :] if cfg.tail_lines > 0 else []
    head_text = "".join(head)
    tail_text = "".join(tail)

    # Approximate skipped metrics (best-effort).
    skipped_lines = max(0, total_lines - len(head) - len(tail))
    skipped_bytes = max(0, total_bytes - len(head_text.encode("utf-8")) - len(tail_text.encode("utf-8")))

    marker = (
        f"\n\n[... {skipped_lines} lines / ~{skipped_bytes} bytes truncated; "
        f"total was {total_lines} lines / {total_bytes} bytes ...]\n\n"
    )
    hint = (
        "\n\n# Hint: to inspect a specific line range, use `sed -n A,Bp <file>` "
        "or `head -n A <file> | tail -n B`. Avoid re-running the full command "
        "that produced this output.\n"
    )

    return head_text + marker + tail_text + hint


def configure(
    max_bytes: int | None = None,
    max_lines: int | None = None,
    head_lines: int | None = None,
    tail_lines: int | None = None,
) -> None:
    """Override module defaults at runtime (called from config loader)."""
    global _DEFAULT
    _DEFAULT = TruncationConfig(
        max_bytes=max_bytes if max_bytes is not None else _DEFAULT.max_bytes,
        max_lines=max_lines if max_lines is not None else _DEFAULT.max_lines,
        head_lines=head_lines if head_lines is not None else _DEFAULT.head_lines,
        tail_lines=tail_lines if tail_lines is not None else _DEFAULT.tail_lines,
    )


def current_config() -> TruncationConfig:
    return _DEFAULT