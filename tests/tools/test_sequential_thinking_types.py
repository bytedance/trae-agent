import pytest

from trae_agent.tools.sequential_thinking_tool import SequentialThinkingTool


@pytest.mark.parametrize(
    "field", ["thought_number", "total_thoughts", "revises_thought", "branch_from_thought"]
)
@pytest.mark.parametrize("value", [True, False])
def test_boolean_is_not_a_thought_number(field, value):
    tool = SequentialThinkingTool()
    arguments = {
        "thought": "test",
        "thought_number": 1,
        "total_thoughts": 1,
        "next_thought_needed": False,
    }
    arguments[field] = value
    with pytest.raises(ValueError):
        tool._validate_thought_data(arguments)


@pytest.mark.parametrize("field", ["is_revision", "needs_more_thoughts"])
@pytest.mark.parametrize("value", ["false", 1, [], {}])
def test_optional_flags_require_booleans(field, value):
    tool = SequentialThinkingTool()
    arguments = {
        "thought": "test",
        "thought_number": 1,
        "total_thoughts": 1,
        "next_thought_needed": False,
        field: value,
    }
    with pytest.raises(ValueError):
        tool._validate_thought_data(arguments)


@pytest.mark.parametrize("field", ["is_revision", "needs_more_thoughts"])
@pytest.mark.parametrize("value", [True, False, None])
def test_optional_flags_keep_valid_values(field, value):
    arguments = {
        "thought": "test",
        "thought_number": 1,
        "total_thoughts": 1,
        "next_thought_needed": False,
        field: value,
    }
    assert getattr(SequentialThinkingTool()._validate_thought_data(arguments), field) is value
