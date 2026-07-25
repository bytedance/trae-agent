# Copyright (c) 2025 ByteDance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

"""Conversation export — render a saved trajectory as Markdown or HTML.

⭐⭐⭐ feature: `trae-cli trajectory export <file> [--format md|html]`
takes the JSON trajectory produced by TrajectoryRecorder and renders a
readable, shareable document showing:
  - the original task
  - each step in order, with the LLM response, tool calls, tool results
  - the final result
"""

from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any


def _md_escape(text: str | None) -> str:
    if text is None:
        return ""
    return text.replace("\r\n", "\n")


def render_markdown(traj_data: dict[str, Any]) -> str:
    """Render a trajectory dict as Markdown."""
    task = traj_data.get("task", "(no task)")
    provider = traj_data.get("provider", "")
    model = traj_data.get("model", "")
    success = traj_data.get("success", False)
    final = traj_data.get("final_result", "") or ""
    start = traj_data.get("start_time", "")
    end = traj_data.get("end_time", "")
    duration = traj_data.get("execution_time", 0)
    steps = traj_data.get("agent_steps", []) or []

    lines: list[str] = []
    lines.append(f"# Trajectory — {task!r}")
    lines.append("")
    lines.append(f"- **Provider:** `{provider}`")
    lines.append(f"- **Model:** `{model}`")
    lines.append(f"- **Status:** {'✓ success' if success else '✗ failed'}")
    if start:
        lines.append(f"- **Started:** {start}")
    if end:
        lines.append(f"- **Ended:** {end}")
    lines.append(f"- **Duration:** {duration:.1f}s")
    lines.append(f"- **Steps:** {len(steps)}")
    lines.append("")
    if final:
        lines.append("## Final Result")
        lines.append("")
        lines.append(_md_escape(final))
        lines.append("")

    lines.append("## Steps")
    for step in steps:
        n = step.get("step_number", "?")
        state = step.get("state", "")
        ts = step.get("timestamp", "")
        lines.append(f"### Step {n} — `{state}`")
        if ts:
            lines.append(f"_{ts}_")
        lines.append("")

        llm_resp = step.get("llm_response")
        if llm_resp:
            content = llm_resp.get("content") or ""
            if content:
                lines.append("**Assistant:**")
                lines.append("")
                lines.append("```")
                lines.append(_md_escape(content))
                lines.append("```")
                lines.append("")

        tool_calls = step.get("tool_calls") or []
        tool_results = step.get("tool_results") or []
        for i, tc in enumerate(tool_calls):
            name = tc.get("name", "?")
            args = tc.get("arguments", {})
            lines.append(f"**Tool call** `{name}`:")
            lines.append("")
            lines.append("```json")
            try:
                lines.append(json.dumps(args, indent=2, ensure_ascii=False))
            except (TypeError, ValueError):
                lines.append(str(args))
            lines.append("```")
            lines.append("")
            if i < len(tool_results):
                tr = tool_results[i]
                ok = "✓" if tr.get("success") else "✗"
                lines.append(f"**Tool result** {ok}:")
                lines.append("")
                result_text = tr.get("result") or ""
                if result_text:
                    lines.append("```")
                    lines.append(_md_escape(result_text))
                    lines.append("```")
                if tr.get("error"):
                    lines.append("Error:")
                    lines.append("")
                    lines.append("```")
                    lines.append(_md_escape(tr["error"]))
                    lines.append("```")
                lines.append("")

        reflection = step.get("reflection")
        if reflection:
            lines.append("**Reflection:**")
            lines.append("")
            lines.append(_md_escape(reflection))
            lines.append("")
        err = step.get("error")
        if err:
            lines.append(f"**Error:** `{_md_escape(err)}`")
            lines.append("")

    return "\n".join(lines)


def render_html(traj_data: dict[str, Any]) -> str:
    """Render a trajectory dict as a self-contained HTML page."""
    md = render_markdown(traj_data)
    body = md.replace("```", "<pre><code>").replace("\n", "</code></pre>\n", 1)
    return (
        "<!doctype html>\n"
        "<html lang=\"en\"><head>\n"
        "  <meta charset=\"utf-8\">\n"
        "  <title>Trajectory</title>\n"
        "  <style>\n"
        "    body { font-family: -apple-system, system-ui, sans-serif;\n"
        "           max-width: 880px; margin: 2em auto; padding: 0 1em;\n"
        "           line-height: 1.55; color: #1a1a1a; }\n"
        "    pre { background: #f4f4f6; padding: 0.75em; border-radius: 6px;\n"
        "          overflow-x: auto; }\n"
        "    code { font-family: ui-monospace, Menlo, Consolas, monospace; }\n"
        "    h1, h2, h3 { line-height: 1.2; }\n"
        "    h1 { border-bottom: 2px solid #eee; padding-bottom: 0.3em; }\n"
        "    h3 { margin-top: 2em; padding: 0.4em 0.6em; background: #f8f8fb;\n"
        "         border-left: 4px solid #6366f1; border-radius: 4px; }\n"
        "  </style>\n"
        "</head><body>\n"
        f"<pre>{html.escape(md)}</pre>\n"
        "</body></html>\n"
    )


def export(traj_path: str | Path, output: str | Path, fmt: str = "md") -> Path:
    """Load a trajectory file and write it as Markdown or HTML.

    Args:
        traj_path: source trajectory JSON file.
        output: destination path. ``.md`` or ``.html`` extension is
            recommended; the format is inferred from the explicit ``fmt``
            argument, otherwise from the extension.
        fmt: ``"md"`` (default) or ``"html"``.

    Returns:
        The resolved Path of the written file.
    """
    src = Path(traj_path)
    data = json.loads(src.read_text(encoding="utf-8"))

    out = Path(output)
    if fmt not in {"md", "html"}:
        # Infer from extension when fmt is ambiguous.
        fmt = "html" if out.suffix.lower() in {".html", ".htm"} else "md"

    if fmt == "html":
        out.write_text(render_html(data), encoding="utf-8")
    else:
        out.write_text(render_markdown(data), encoding="utf-8")
    return out