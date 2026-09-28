# Copyright (c) 2025 ByteDance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

"""`ToolParameter.required` defaults to `True`, so the five conditional fields of the sequential
thinking tool (`is_revision`, `revises_thought`, `branch_from_thought`, `branch_id`,
`needs_more_thoughts`) were published as required for every provider -- non-nullable even for
`openai`, whose strict-mode generator only makes a parameter nullable if it says `required=False`.

The tool description documents them as conditional ("If is_revision is true, which thought number
is being reconsidered", "Branch identifier ... (if any)") and `_validate_thought_data()` already
accepts an absent value or `null` for each, so a strict-mode model had no legal way to say "this
thought revises nothing": it had to invent integers and identifiers, which the tool then recorded
as real branches.

Marking them `required=False` moves them out of `required` for ordinary providers and makes them
nullable for OpenAI, while leaving the strict-mode rule (every property listed in `required`)
intact.
"""

import unittest
from typing import cast

from trae_agent.tools.base import ToolCallArguments, ToolExecResult
from trae_agent.tools.sequential_thinking_tool import SequentialThinkingTool, ThoughtData

CONDITIONAL = {
    "is_revision": "boolean",
    "revises_thought": "integer",
    "branch_from_thought": "integer",
    "branch_id": "string",
    "needs_more_thoughts": "boolean",
}
ALWAYS_REQUIRED = ["thought", "next_thought_needed", "thought_number", "total_thoughts"]


class TestSequentialThinkingOptionalFields(unittest.IsolatedAsyncioTestCase):
    def schema(self, model_provider: str | None = None) -> dict[str, object]:
        return SequentialThinkingTool(model_provider=model_provider).get_input_schema()

    def required_names(self, schema: dict[str, object]) -> list[str]:
        return cast(list[str], schema["required"])

    def param_type(self, schema: dict[str, object], name: str) -> object:
        properties = cast(dict[str, dict[str, object]], schema["properties"])
        return properties[name]["type"]

    def base_arguments(self) -> ToolCallArguments:
        return ToolCallArguments(
            {
                "thought": "first step",
                "next_thought_needed": True,
                "thought_number": 1,
                "total_thoughts": 3,
            }
        )

    async def invoke(
        self, instance: SequentialThinkingTool, extra: dict[str, object]
    ) -> ToolExecResult:
        arguments = self.base_arguments()
        arguments.update(cast(ToolCallArguments, extra))
        return await instance.execute(arguments)

    def test_these_five_fields_are_not_required_for_an_ordinary_provider(self) -> None:
        """The bug: `required` defaulted to True, so the schema demanded them for every provider."""
        schema = self.schema()
        required = self.required_names(schema)
        for name in CONDITIONAL:
            self.assertNotIn(name, required)
        self.assertEqual(sorted(ALWAYS_REQUIRED), sorted(required))

    def test_these_five_fields_are_nullable_for_openai(self) -> None:
        """Strict mode keeps every property in `required`; `required=False` is what makes one
        nullable, which is the only legal way for a model to say 'not applicable here'."""
        schema = self.schema("openai")
        for name, base_type in CONDITIONAL.items():
            self.assertEqual([base_type, "null"], self.param_type(schema, name))

    def test_openai_strict_mode_shape_survives_the_change(self) -> None:
        """Guard against the wrong fix: dropping these from `required` would break strict mode."""
        schema = self.schema("openai")
        required = self.required_names(schema)
        property_types = cast(dict[str, dict[str, object]], schema["properties"])
        for name in CONDITIONAL:
            self.assertIn(name, required)
            self.assertEqual([CONDITIONAL[name], "null"], property_types[name]["type"])
        self.assertIs(False, schema["additionalProperties"])
        for name in ALWAYS_REQUIRED:
            self.assertNotIn("null", cast(list[object], property_types[name]["type"]))

    def test_the_always_required_fields_keep_their_types(self) -> None:
        schema = self.schema("openai")
        self.assertEqual("string", self.param_type(schema, "thought"))
        self.assertEqual("boolean", self.param_type(schema, "next_thought_needed"))
        self.assertEqual("integer", self.param_type(schema, "thought_number"))
        self.assertEqual("integer", self.param_type(schema, "total_thoughts"))

    async def test_a_plain_thought_with_the_conditional_fields_null_records_no_branch(
        self,
    ) -> None:
        """The value the nullable schema now invites is already handled by the reader."""
        instance = SequentialThinkingTool(model_provider="openai")
        result = await self.invoke(instance, dict.fromkeys(CONDITIONAL))
        self.assertIsNone(result.error)
        self.assertEqual(0, result.error_code)
        self.assertEqual([], list(instance.branches.keys()))

    async def test_a_plain_thought_without_the_conditional_fields_still_works(self) -> None:
        instance = SequentialThinkingTool(model_provider="openai")
        result = await self.invoke(instance, {})
        self.assertIsNone(result.error)
        self.assertEqual([], list(instance.branches.keys()))

    async def test_a_revision_records_the_thought_it_revises(self) -> None:
        instance = SequentialThinkingTool(model_provider="openai")
        result = await self.invoke(
            instance,
            {
                "is_revision": True,
                "revises_thought": 1,
                "branch_from_thought": None,
                "branch_id": None,
                "needs_more_thoughts": None,
            },
        )
        self.assertIsNone(result.error)
        thought = cast(ThoughtData, instance.thought_history[-1])
        self.assertIs(True, thought.is_revision)
        self.assertEqual(1, thought.revises_thought)
        self.assertIsNone(thought.branch_id)

    async def test_an_actual_branch_is_recorded(self) -> None:
        instance = SequentialThinkingTool(model_provider="openai")
        result = await self.invoke(
            instance,
            {
                "is_revision": None,
                "revises_thought": None,
                "branch_from_thought": 1,
                "branch_id": "alt",
                "needs_more_thoughts": None,
            },
        )
        self.assertIsNone(result.error)
        self.assertEqual(["alt"], list(instance.branches.keys()))

    async def test_a_thought_number_below_one_is_still_rejected(self) -> None:
        instance = SequentialThinkingTool(model_provider="openai")
        arguments = self.base_arguments()
        arguments.update(cast(ToolCallArguments, {"thought_number": 0}))
        result = await instance.execute(arguments)
        self.assertIsNotNone(result.error)
        self.assertEqual(-1, result.error_code)


if __name__ == "__main__":
    unittest.main()
