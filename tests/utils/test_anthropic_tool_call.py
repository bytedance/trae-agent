# Copyright (c) 2025 ByteDance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

"""parse_tool_call must pass tool arguments as a dict, not a JSON string."""

import unittest

from trae_agent.tools.base import ToolCall
from trae_agent.utils.llm_clients.anthropic_client import AnthropicClient


class TestParseToolCallInput(unittest.TestCase):
    """The Anthropic tool_use block's input field must be a JSON object (dict).

    The old code called json.dumps on the arguments, producing a JSON string
    where the API expects a dict.
    """

    def test_input_is_dict_not_json_string(self):
        tc = ToolCall(name="test_tool", call_id="call_1", arguments={"key": "value", "num": 42})
        result = AnthropicClient.parse_tool_call(None, tc)
        self.assertIsInstance(result["input"], dict)
        self.assertEqual(result["input"], {"key": "value", "num": 42})
        self.assertEqual(result["id"], "call_1")
        self.assertEqual(result["name"], "test_tool")

    def test_input_empty_arguments(self):
        tc = ToolCall(name="test_tool", call_id="call_2", arguments={})
        result = AnthropicClient.parse_tool_call(None, tc)
        self.assertIsInstance(result["input"], dict)
        self.assertEqual(result["input"], {})

    def test_input_nested_arguments(self):
        tc = ToolCall(
            name="test_tool",
            call_id="call_3",
            arguments={"outer": {"inner": [1, 2]}, "flag": True},
        )
        result = AnthropicClient.parse_tool_call(None, tc)
        self.assertIsInstance(result["input"], dict)
        self.assertEqual(result["input"]["outer"]["inner"], [1, 2])
        self.assertEqual(result["input"]["flag"], True)


if __name__ == "__main__":
    unittest.main()
