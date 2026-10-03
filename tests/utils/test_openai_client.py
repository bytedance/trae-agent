# Copyright (c) 2025 ByteDance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

import json
import unittest
from typing import Any
from unittest.mock import patch

import httpx
import openai

from trae_agent.tools.base import ToolResult
from trae_agent.utils.config import ModelConfig, ModelProvider
from trae_agent.utils.llm_clients.llm_basics import LLMMessage
from trae_agent.utils.llm_clients.openai_client import OpenAIClient


class TestOpenAIClientHistory(unittest.TestCase):
    def setUp(self) -> None:
        self.model_config = ModelConfig(
            model="o3",
            model_provider=ModelProvider(provider="openai", api_key="test-dummy-api-key"),
            max_tokens=4096,
            temperature=0.5,
            top_p=1.0,
            top_k=0,
            parallel_tool_calls=True,
            max_retries=1,
        )
        self.requests: list[dict[str, Any]] = []
        self.outputs: list[list[dict[str, Any]]] = []
        sdk_client = openai.OpenAI(
            api_key="test-dummy-api-key",
            http_client=httpx.Client(transport=httpx.MockTransport(self.handle_request)),
        )
        self.addCleanup(sdk_client.close)
        with patch(
            "trae_agent.utils.llm_clients.openai_client.openai.OpenAI", return_value=sdk_client
        ):
            self.client = OpenAIClient(self.model_config)

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "id": f"resp_{len(self.requests)}",
                "object": "response",
                "created_at": 1,
                "model": self.model_config.model,
                "status": "completed",
                "output": self.outputs.pop(0),
                "usage": {
                    "input_tokens": 10,
                    "output_tokens": 20,
                    "total_tokens": 30,
                    "input_tokens_details": {"cached_tokens": 0},
                    "output_tokens_details": {"reasoning_tokens": 5},
                },
            },
        )

    @staticmethod
    def reasoning(item_id: str, encrypted_content: str | None = None) -> dict[str, Any]:
        item: dict[str, Any] = {"id": item_id, "type": "reasoning", "summary": []}
        if encrypted_content is not None:
            item["encrypted_content"] = encrypted_content
        return item

    @staticmethod
    def function_call(call_id: str) -> dict[str, Any]:
        return {
            "id": f"fc_{call_id}",
            "type": "function_call",
            "call_id": call_id,
            "name": "bash",
            "arguments": '{"command": "echo hello"}',
            "status": "completed",
        }

    @staticmethod
    def message(text: str, item_id: str = "msg_1") -> dict[str, Any]:
        return {
            "id": item_id,
            "type": "message",
            "role": "assistant",
            "status": "completed",
            "content": [{"type": "output_text", "text": text, "annotations": []}],
        }

    @staticmethod
    def tool_message(call_id: str) -> LLMMessage:
        return LLMMessage(
            role="user",
            tool_result=ToolResult(call_id=call_id, name="bash", success=True, result="hello"),
        )

    @staticmethod
    def tool_output(call_id: str) -> dict[str, str]:
        return {"type": "function_call_output", "call_id": call_id, "output": "hello"}

    def test_reasoning_survives_consecutive_tool_rounds(self) -> None:
        first_output = [self.reasoning("rs_1"), self.function_call("call_1")]
        second_output = [
            self.reasoning("rs_2", "opaque-test-payload"),
            self.function_call("call_2"),
        ]
        self.outputs = [first_output, second_output, [self.message("Finished")]]
        initial_messages = [LLMMessage(role="user", content="Inspect the project")]

        first_response = self.client.chat(initial_messages, self.model_config)
        second_response = self.client.chat([self.tool_message("call_1")], self.model_config)
        final_response = self.client.chat([self.tool_message("call_2")], self.model_config)

        initial_input = [{"role": "user", "content": "Inspect the project"}]
        self.assertEqual(
            self.requests[1]["input"], initial_input + first_output + [self.tool_output("call_1")]
        )
        self.assertEqual(
            self.requests[2]["input"],
            initial_input
            + first_output
            + [self.tool_output("call_1")]
            + second_output
            + [self.tool_output("call_2")],
        )
        assert first_response.tool_calls is not None
        assert second_response.tool_calls is not None
        self.assertEqual(first_response.tool_calls[0].call_id, "call_1")
        self.assertEqual(second_response.tool_calls[0].call_id, "call_2")
        self.assertEqual(final_response.content, "Finished")

    def test_mixed_output_preserves_order_and_message_fields(self) -> None:
        output = [
            self.reasoning("rs_1"),
            self.message("Inspecting files"),
            self.function_call("call_1"),
            self.function_call("call_2"),
        ]
        self.outputs = [output, [self.message("Finished", "msg_2")]]
        response = self.client.chat([LLMMessage(role="user", content="Inspect")], self.model_config)
        self.client.chat(
            [self.tool_message("call_1"), self.tool_message("call_2")], self.model_config
        )

        self.assertEqual(
            self.requests[1]["input"],
            [{"role": "user", "content": "Inspect"}]
            + output
            + [self.tool_output("call_1"), self.tool_output("call_2")],
        )
        self.assertEqual(response.content, "Inspecting files")
        assert response.tool_calls is not None
        self.assertEqual([call.call_id for call in response.tool_calls], ["call_1", "call_2"])

    def test_reuse_history_false_discards_previous_reasoning(self) -> None:
        first_output = [self.reasoning("rs_old"), self.message("Old answer")]
        second_output = [self.reasoning("rs_new"), self.message("New answer", "msg_2")]
        self.outputs = [first_output, second_output, [self.message("Follow-up", "msg_3")]]
        self.client.chat([LLMMessage(role="user", content="Old task")], self.model_config)
        self.client.chat(
            [LLMMessage(role="user", content="New task")], self.model_config, reuse_history=False
        )
        self.client.chat([LLMMessage(role="user", content="Continue")], self.model_config)

        new_input = [{"role": "user", "content": "New task"}]
        self.assertEqual(self.requests[1]["input"], new_input)
        self.assertEqual(
            self.requests[2]["input"],
            new_input + second_output + [{"role": "user", "content": "Continue"}],
        )

    def test_text_only_response_keeps_content_usage_and_history(self) -> None:
        self.model_config.model = "gpt-4o"
        output = [self.message("Hello")]
        self.outputs = [output, [self.message("Again", "msg_2")]]
        response = self.client.chat([LLMMessage(role="user", content="Hi")], self.model_config)
        self.client.chat([LLMMessage(role="user", content="Repeat")], self.model_config)

        self.assertEqual(response.content, "Hello")
        self.assertIsNone(response.tool_calls)
        assert response.usage is not None
        self.assertEqual(response.usage.input_tokens, 10)
        self.assertEqual(response.usage.output_tokens, 20)
        self.assertEqual(response.usage.reasoning_tokens, 5)
        self.assertEqual(
            self.requests[1]["input"],
            [{"role": "user", "content": "Hi"}] + output + [{"role": "user", "content": "Repeat"}],
        )

    def test_tool_outputs_remain_in_history_without_reasoning(self) -> None:
        first_output = [self.function_call("call_1")]
        second_output = [self.function_call("call_2")]
        self.outputs = [first_output, second_output, [self.message("Finished")]]
        self.client.chat([LLMMessage(role="user", content="Inspect")], self.model_config)
        self.client.chat([self.tool_message("call_1")], self.model_config)
        self.client.chat([self.tool_message("call_2")], self.model_config)

        self.assertEqual(
            self.requests[2]["input"],
            [{"role": "user", "content": "Inspect"}]
            + first_output
            + [self.tool_output("call_1")]
            + second_output
            + [self.tool_output("call_2")],
        )

    def test_reasoning_only_response_is_not_lost(self) -> None:
        output = [self.reasoning("rs_1", "opaque-test-payload")]
        self.outputs = [output, [self.message("Finished")]]
        response = self.client.chat([LLMMessage(role="user", content="Inspect")], self.model_config)
        self.client.chat([LLMMessage(role="user", content="Continue")], self.model_config)

        self.assertEqual(response.content, "")
        self.assertIsNone(response.tool_calls)
        self.assertEqual(
            self.requests[1]["input"],
            [{"role": "user", "content": "Inspect"}]
            + output
            + [{"role": "user", "content": "Continue"}],
        )

    def test_empty_output_does_not_add_an_assistant_message(self) -> None:
        self.outputs = [[], [self.message("Finished")]]
        response = self.client.chat([LLMMessage(role="user", content="Inspect")], self.model_config)
        self.client.chat([LLMMessage(role="user", content="Continue")], self.model_config)

        self.assertEqual(response.content, "")
        self.assertIsNone(response.tool_calls)
        self.assertEqual(
            self.requests[1]["input"],
            [{"role": "user", "content": "Inspect"}, {"role": "user", "content": "Continue"}],
        )
