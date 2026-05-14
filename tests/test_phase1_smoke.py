"""Phase 1 smoke tests — find_safe_cut atomicity & GlobalStateSchema.from_markdown multi-line."""

from trae_agent.compression.global_state import GlobalStateManager, GlobalStateSchema
from trae_agent.compression.types import find_safe_cut
from trae_agent.tools.base import ToolCall, ToolResult
from trae_agent.utils.llm_clients.llm_basics import LLMMessage

pass_count = 0
fail_count = 0


def check(description: str, ok: bool) -> None:
    global pass_count, fail_count
    if ok:
        pass_count += 1
        print(f"  [PASS] {description}")
    else:
        fail_count += 1
        print(f"  [FAIL] {description}")


# ═══════════════════════════════════════════════════════════════════════════
# 1. find_safe_cut — tool_call / tool_result atomicity (review 2.2)
# ═══════════════════════════════════════════════════════════════════════════

def test_find_safe_cut() -> None:
    """Build a message list with interleaved tool_result/tool_call pairs."""
    msgs = [
        LLMMessage(role="system", content="sys"),
        LLMMessage(role="user", content="hello"),
        LLMMessage(
            role="user",
            tool_result=ToolResult(call_id="1", name="bash", success=True, result="out"),
        ),
        LLMMessage(role="user", content="intermediate"),
        LLMMessage(
            role="assistant", content="", tool_call=ToolCall(name="bash", call_id="1")
        ),
        LLMMessage(
            role="user",
            tool_result=ToolResult(call_id="2", name="bash", success=True, result="out2"),
        ),
    ]

    c = find_safe_cut(msgs, tail_target=3, min_head=1)
    check("never lands on tool_result", msgs[c].tool_result is None)
    check("never lands on tool_call", msgs[c].tool_call is None)
    check("min_head respected", c >= 1)

    # All-tool tail edge case
    tool_only = [
        LLMMessage(role="system", content="sys"),
        LLMMessage(
            role="user",
            tool_result=ToolResult(call_id="1", name="bash", success=True, result="out"),
        ),
        LLMMessage(
            role="user",
            tool_result=ToolResult(call_id="2", name="bash", success=True, result="out2"),
        ),
    ]
    c2 = find_safe_cut(tool_only, tail_target=1, min_head=1)
    check("all-tool tail clamps to min_head", c2 == 1)

    # Empty-ish message list
    c3 = find_safe_cut([LLMMessage(role="system", content="sys")], tail_target=5, min_head=1)
    check("small list returns min_head", c3 == 1)

    # Tail lands exactly on min_head (all messages are tool-related)
    all_tool_and_call = [
        LLMMessage(role="system", content="sys"),
        LLMMessage(
            role="assistant", content="", tool_call=ToolCall(name="bash", call_id="1")
        ),
        LLMMessage(
            role="user",
            tool_result=ToolResult(call_id="1", name="bash", success=True, result="out"),
        ),
    ]
    c4 = find_safe_cut(all_tool_and_call, tail_target=2, min_head=1)
    check("only tool messages clamps to min_head", c4 == 1)


# ═══════════════════════════════════════════════════════════════════════════
# 2. GlobalStateSchema.from_markdown — multi-line sections (review 2.3)
# ═══════════════════════════════════════════════════════════════════════════

def test_from_markdown_multiline() -> None:
    multi_line_md = """# WORKSPACE STATE
- **Task**: Fix bug
- **Project**: /repo

## Architecture Analysis
Root cause: off-by-one in loop boundary.
The index variable exceeds array length when n=0.
This affects all callers in the module.

## Plan
1. Fix boundary check in process_items()
2. Add edge-case test for n=0
3. Run full test suite

Key files:
- src/core.py: the fix
- tests/test_core.py: new tests

## Progress Log
- analysis done
- coding complete

## Design Decisions
- use ValueError instead of AssertionError

## Review Verdict
Approved with minor concerns.
Edge case for n=0 is well-handled.
"""

    state = GlobalStateSchema.from_markdown(multi_line_md)

    check(
        "plan is multi-line",
        "1. Fix boundary check" in state.plan
        and "Run full test suite" in state.plan
        and "Key files:" in state.plan,
    )
    check(
        "architecture_analysis is multi-line",
        "Root cause: off-by-one" in state.architecture_analysis
        and "affects all callers" in state.architecture_analysis,
    )
    check(
        "review_verdict is multi-line",
        "Approved with minor concerns" in state.review_verdict
        and "well-handled" in state.review_verdict,
    )
    check("progress_log parsed", len(state.progress_log) == 2)
    check("design_decisions parsed", len(state.design_decisions) == 1)
    check("task parsed", state.task == "Fix bug")


# ═══════════════════════════════════════════════════════════════════════════
# 3. from_markdown — error recovery
# ═══════════════════════════════════════════════════════════════════════════

def test_from_markdown_errors() -> None:
    state = GlobalStateSchema.from_markdown("")
    check("empty input returns blank schema", isinstance(state, GlobalStateSchema))

    state = GlobalStateSchema.from_markdown("totally invalid [[[ ...")
    check("malformed input does not crash", isinstance(state, GlobalStateSchema))

    # Partially truncated
    partial = """# WORKSPACE STATE
- **Task**: Partial
- **Project**: /p

## Plan
This section is not closed
"""
    state = GlobalStateSchema.from_markdown(partial)
    check("truncated input does not crash", state.task == "Partial")
    check("truncated plan still captured", bool(state.plan))


# ═══════════════════════════════════════════════════════════════════════════
# 4. Round-trip: to_markdown -> from_markdown -> to_markdown
# ═══════════════════════════════════════════════════════════════════════════

def test_roundtrip() -> None:
    gsm = GlobalStateManager()
    gsm.initialize("Fix bug #42", "/home/user/project")
    gsm.update_section(
        "architecture_analysis",
        "Root cause: off-by-one\nIn function process_items()",
        phase="planning",
    )
    gsm.update_section("plan", "1. Fix it\n2. Test it\n3. Ship it", phase="planning")
    gsm.log_progress("Analysis complete", phase="planning")
    gsm.update_section("design_decisions", "Use ValueError", phase="coding")
    gsm.update_section(
        "review_verdict",
        "Changes look good\nMinor formatting issues",
        phase="reviewing",
    )

    md = gsm.get_full_state().to_markdown()
    parsed = GlobalStateSchema.from_markdown(md)

    check("task preserved", parsed.task == "Fix bug #42")
    check("project_path preserved", parsed.project_path == "/home/user/project")
    check(
        "architecture_analysis multi-line",
        "Root cause: off-by-one" in parsed.architecture_analysis
        and "In function process_items()" in parsed.architecture_analysis,
    )
    check(
        "plan multi-line",
        "1. Fix it" in parsed.plan and "3. Ship it" in parsed.plan,
    )
    check(
        "review_verdict multi-line",
        "Changes look good" in parsed.review_verdict
        and "Minor formatting issues" in parsed.review_verdict,
    )


# ═══════════════════════════════════════════════════════════════════════════
# 5. Regression: single-line sections still work
# ═══════════════════════════════════════════════════════════════════════════

def test_regression_simple() -> None:
    simple_md = """# WORKSPACE STATE
- **Task**: Simple
- **Project**: /p

## Architecture Analysis
Single line analysis

## Plan
Single line plan

## Progress Log
- done

## Design Decisions
- use X

## Review Verdict
Approved
"""
    state = GlobalStateSchema.from_markdown(simple_md)
    check("simple plan", state.plan == "Single line plan")
    check("simple analysis", state.architecture_analysis == "Single line analysis")
    check("simple verdict", state.review_verdict == "Approved")


# ═══════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    test_find_safe_cut()
    test_from_markdown_multiline()
    test_from_markdown_errors()
    test_roundtrip()
    test_regression_simple()

    print(f"\nResults: {pass_count} passed, {fail_count} failed")
    raise SystemExit(0 if fail_count == 0 else 1)
