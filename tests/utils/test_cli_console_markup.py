# Copyright (c) 2025 ByteDance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

"""Console rendering must survive arbitrary text that looks like Rich markup.

Model output, tool arguments, tool results and the user's own task description
all reach the console verbatim. Rich parses `[...]` in a plain string as console
markup and raises `MarkupError` for anything shaped like a closing tag, so
rendering such content used to crash the CLI instead of displaying it.
"""

import unittest

from rich.console import Console

from trae_agent.agent.agent_basics import AgentStep, AgentStepState
from trae_agent.tools.base import ToolCall, ToolResult
from trae_agent.utils.cli.cli_console import generate_agent_step_table
from trae_agent.utils.llm_clients.llm_basics import LLMResponse

# Real-world samples from the bug report: text that Rich reads as a closing tag.
MARKUP_LIKE = "parsed: [/'A', 1, /'B']"
MARKUP_LIKE_2 = r"[/\-\\+.$%*@?|]"


def render(renderable) -> str:
    """Render to a string buffer the same way the console would to a terminal."""
    console = Console(file=None, width=120, record=True)
    console.begin_capture()
    console.print(renderable)
    return console.end_capture()


class TestAgentStepTableMarkup(unittest.TestCase):
    def test_llm_response_with_markup_like_text(self):
        step = AgentStep(
            step_number=1,
            state=AgentStepState.THINKING,
            llm_response=LLMResponse(content=MARKUP_LIKE),
        )

        output = render(generate_agent_step_table(step))

        self.assertIn("/'A'", output)

    def test_tool_result_with_markup_like_text(self):
        step = AgentStep(
            step_number=2,
            state=AgentStepState.CALLING_TOOL,
            tool_calls=[ToolCall(name="bash", call_id="c1", arguments={"command": "cat g.py"})],
            tool_results=[
                ToolResult(call_id="c1", name="bash", success=True, result=MARKUP_LIKE_2),
            ],
        )

        output = render(generate_agent_step_table(step))

        self.assertIn("bash", output)

    def test_tool_arguments_with_markup_like_text(self):
        step = AgentStep(
            step_number=3,
            state=AgentStepState.CALLING_TOOL,
            tool_calls=[ToolCall(name="bash", call_id="c1", arguments={"command": MARKUP_LIKE})],
            tool_results=[ToolResult(call_id="c1", name="bash", success=True, result="ok")],
        )

        output = render(generate_agent_step_table(step))

        self.assertIn("bash", output)

    def test_error_with_markup_like_text(self):
        step = AgentStep(step_number=4, state=AgentStepState.ERROR, error=MARKUP_LIKE)

        output = render(generate_agent_step_table(step))

        self.assertIn("/'A'", output)

    def test_reflection_with_markup_like_text(self):
        step = AgentStep(step_number=5, state=AgentStepState.REFLECTING, reflection=MARKUP_LIKE)

        output = render(generate_agent_step_table(step))

        self.assertIn("/'A'", output)

    def test_status_row_still_styled(self):
        """Escaping content must not escape the markup the table itself emits."""
        step = AgentStep(step_number=6, state=AgentStepState.COMPLETED, error=MARKUP_LIKE)

        output = render(generate_agent_step_table(step))

        # The literal style tag must have been consumed as markup, not printed.
        self.assertNotIn("[green]", output)
        self.assertIn("Completed", output)


if __name__ == "__main__":
    unittest.main()
