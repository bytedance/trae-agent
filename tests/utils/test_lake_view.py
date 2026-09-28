# Copyright (c) 2025 ByteDance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

"""Lakeview prompts the model about the trajectory so far, so the trajectory has to be there.

These tests replace only the lakeview LLM client with a recorder and assert what the two
prompts actually contain. No network, API key, or Docker daemon is involved.
"""

import re
import unittest

from trae_agent.agent.agent_basics import AgentStep, AgentStepState
from trae_agent.utils.config import LakeviewConfig, ModelConfig, ModelProvider
from trae_agent.utils.lake_view import LakeView
from trae_agent.utils.llm_clients.llm_basics import LLMMessage, LLMResponse

PREVIOUS_STEP_RE = re.compile(r"<previous_step>(.*?)</previous_step>", re.DOTALL)
STEP_BLOCK_RE = re.compile(r'<step id="(\d+)">\n(.*?)\n</step>', re.DOTALL)
CURRENT_STEP_RE = re.compile(r"<current_step>(.*?)</current_step>", re.DOTALL)

# Satisfies both parsers at once: the extractor needs <task>/<details>, the tagger needs <tags>.
CANNED_RESPONSE = (
    "<task>The agent is reading a file.</task>"
    "<details>It opened utils.py.</details>"
    "<tags>EXAMINE_CODE</tags>"
)


class RecordingLLMClient:
    """Keeps every prompt lakeview sends, in call order: extractor, tagger, extractor, ..."""

    def __init__(self) -> None:
        self.prompts: list[str] = []

    def chat(
        self,
        messages: list[LLMMessage],
        model_config: ModelConfig,  # noqa: ARG002
        reuse_history: bool = False,  # noqa: ARG002
    ) -> LLMResponse:
        self.prompts.append(messages[0].content or "")
        return LLMResponse(content=CANNED_RESPONSE)


class TestLakeViewTrajectory(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        model_config = ModelConfig(
            model="gpt-4",
            model_provider=ModelProvider(
                provider="openai",
                api_key="not-a-real-key",
                base_url="http://127.0.0.1:1/v1",
                api_version=None,
            ),
            temperature=0.8,
            top_p=0.7,
            top_k=8,
            parallel_tool_calls=False,
            max_retries=1,
        )
        self.lake_view = LakeView(LakeviewConfig(model=model_config))
        self.recorder = RecordingLLMClient()
        self.lake_view.lakeview_llm_client = self.recorder

    def agent_step(self, number: int, content: str) -> AgentStep:
        return AgentStep(
            step_number=number,
            state=AgentStepState.COMPLETED,
            llm_response=LLMResponse(content=content),
        )

    def extractor_prompt(self, step_index: int) -> str:
        return self.recorder.prompts[step_index * 2]

    def tagger_prompt(self, step_index: int) -> str:
        return self.recorder.prompts[step_index * 2 + 1]

    async def record(self, *steps: AgentStep):
        for step in steps:
            await self.lake_view.create_lakeview_step(step)

    async def test_the_extractor_sees_the_step_before_this_one(self):
        first = self.agent_step(1, "opened utils.py")
        second = self.agent_step(2, "added an import to utils.py")

        await self.record(first, second)

        self.assertEqual(PREVIOUS_STEP_RE.search(self.extractor_prompt(0)).group(1), "(none)")
        self.assertEqual(
            PREVIOUS_STEP_RE.search(self.extractor_prompt(1)).group(1),
            "opened utils.py",
            "the second step must be described against the first one, not against '(none)'",
        )

    async def test_the_tagger_is_told_about_every_step_so_far(self):
        first = self.agent_step(1, "opened utils.py")
        second = self.agent_step(2, "added an import to utils.py")
        third = self.agent_step(3, "ran the test suite")

        await self.record(first, second, third)

        self.assertEqual(len(STEP_BLOCK_RE.findall(self.tagger_prompt(0))), 0)
        self.assertEqual(
            STEP_BLOCK_RE.findall(self.tagger_prompt(1)),
            [("1", "opened utils.py")],
        )
        self.assertEqual(
            STEP_BLOCK_RE.findall(self.tagger_prompt(2)),
            [("1", "opened utils.py"), ("2", "added an import to utils.py")],
            "the tagger prompt claims every earlier step is marked with a <step> tag",
        )

    async def test_the_current_step_is_not_also_in_the_trajectory(self):
        first = self.agent_step(1, "opened utils.py")
        second = self.agent_step(2, "added an import to utils.py")

        await self.record(first, second)

        prompt = self.tagger_prompt(1)
        self.assertEqual(CURRENT_STEP_RE.search(prompt).group(1), "added an import to utils.py")
        self.assertNotIn("added an import to utils.py", prompt.split("<current_step>")[0])

    async def test_a_step_the_agent_said_nothing_about_is_not_recorded(self):
        await self.record(self.agent_step(1, "opened utils.py"))
        self.assertEqual(len(self.lake_view.steps), 1)

        silent = AgentStep(step_number=2, state=AgentStepState.COMPLETED, llm_response=None)
        before = len(self.recorder.prompts)

        self.assertIsNone(await self.lake_view.create_lakeview_step(silent))
        self.assertEqual(
            len(self.lake_view.steps), 1, "an empty step must not enter the trajectory"
        )
        self.assertEqual(
            len(self.recorder.prompts),
            before,
            "a step with nothing in it must not cost two model calls",
        )

    async def test_an_empty_step_does_not_break_the_next_ones_previous_step(self):
        await self.record(self.agent_step(1, "opened utils.py"))
        self.assertIsNone(
            await self.lake_view.create_lakeview_step(
                AgentStep(step_number=2, state=AgentStepState.COMPLETED, llm_response=None)
            )
        )

        await self.record(self.agent_step(3, "ran the test suite"))

        self.assertEqual(
            PREVIOUS_STEP_RE.search(self.extractor_prompt(1)).group(1),
            "opened utils.py",
            "step 3 follows step 1 in the recorded trajectory, since step 2 contributed nothing",
        )


if __name__ == "__main__":
    unittest.main()
