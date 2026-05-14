# Copyright (c) 2025 ByteDance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

"""Tool to resolve [lazy-ref:<hash>] placeholders back to full tool output."""

from typing import override

from trae_agent.tools.base import Tool, ToolCallArguments, ToolExecResult, ToolParameter


class ResolveLazyRefTool(Tool):
    """Resolve a [lazy-ref:<hash>] placeholder to its original full content.

    During micro-compression, large tool outputs (>1024 chars) are replaced
    with `[lazy-ref:<hash>]` placeholders.  This tool lets the model re-fetch
    the complete content on demand.
    """

    @override
    def get_name(self) -> str:
        return "resolve_lazy_ref"

    @override
    def get_description(self) -> str:
        return (
            "Resolve a [lazy-ref:<hash>] placeholder from a compressed summary "
            "to its original full content.  Pass the exact hash string (first 12+ "
            "hex characters) you see in the placeholder."
        )

    @override
    def get_parameters(self) -> list[ToolParameter]:
        return [
            ToolParameter(
                name="hash",
                type="string",
                description="The hex hash from the [lazy-ref:<hash>] placeholder (minimum 12 characters).",
                required=True,
            ),
        ]

    @override
    async def execute(self, arguments: ToolCallArguments) -> ToolExecResult:
        hash_key = str(arguments.get("hash", ""))
        if not hash_key:
            return ToolExecResult(error="Missing required argument: 'hash'", error_code=-1)

        if len(hash_key) < 12:
            return ToolExecResult(
                error=f"Hash too short ({len(hash_key)} chars); need at least 12 characters.",
                error_code=-1,
            )

        content = _resolve_lazy_ref(hash_key)
        if content is None:
            return ToolExecResult(
                error=f"No lazy-ref found matching hash prefix '{hash_key}'. "
                "The content may have expired or never been stored.",
                error_code=-1,
            )

        return ToolExecResult(output=content)


# ── In-memory lazy-ref store ────────────────────────────────────────────────

_LAZY_REF_STORE: dict[str, str] = {}


def register_lazy_ref(content: str) -> str:
    """Store content and return its full SHA256 hex key."""
    import hashlib

    key = hashlib.sha256(content.encode("utf-8")).hexdigest()
    _LAZY_REF_STORE[key] = content
    return key


def _resolve_lazy_ref(partial_key: str) -> str | None:
    """Look up content by full hash or prefix.

    Supports prefix matching (first N characters) so the tool works with
    the abbreviated ``[lazy-ref:{hash[:12]}]`` format shown in compressed
    summaries.
    """
    # Exact match first
    if partial_key in _LAZY_REF_STORE:
        return _LAZY_REF_STORE[partial_key]

    # Prefix match — find the first (and hopefully only) key starting with the given prefix
    matches = [k for k in _LAZY_REF_STORE if k.startswith(partial_key)]
    if len(matches) == 1:
        return _LAZY_REF_STORE[matches[0]]
    if len(matches) > 1:
        # Ambiguous — return a disambiguation hint
        return (
            f"Ambiguous hash prefix '{partial_key}' matched {len(matches)} entries. "
            f"Try a longer prefix. Candidates:\n"
            + "\n".join(f"  {m[:16]}...  ({len(_LAZY_REF_STORE[m])} bytes)" for m in matches[:5])
        )

    return None
