# Copyright (c) 2025 ByteDance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

import json
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

import httpx
from google import genai

from trae_agent.tools.base import ToolCall, ToolExecutor, ToolResult
from trae_agent.tools.json_edit_tool import JSONEditTool
from trae_agent.utils.config import ModelConfig, ModelProvider
from trae_agent.utils.llm_clients.google_client import GoogleClient
from trae_agent.utils.llm_clients.llm_basics import LLMMessage


class TestGoogleFunctionIds(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.config = ModelConfig(
            model="gemini-test",
            model_provider=ModelProvider(api_key="test-key", provider="google"),
            temperature=0,
            top_p=1,
            top_k=1,
            parallel_tool_calls=True,
            max_retries=0,
            max_tokens=100,
        )

    def make_client(self, handler):
        sdk = genai.Client(
            api_key="test-key",
            http_options={"client_args": {"transport": httpx.MockTransport(handler)}},
        )
        self.addCleanup(sdk._api_client._httpx_client.close)
        with patch("trae_agent.utils.llm_clients.google_client.genai.Client", return_value=sdk):
            return GoogleClient(self.config)

    async def test_same_named_calls_keep_ids_through_execution_and_sdk_serialization(self):
        requests = []
        with tempfile.TemporaryDirectory() as directory:
            files = [Path(directory) / name for name in ("first.json", "second.json")]
            for path, value in zip(files, ("first-result", "second-result"), strict=True):
                path.write_text(json.dumps({"value": value}), encoding="utf-8")

            def handler(request):
                body = json.loads(request.content)
                requests.append(body)
                if len(requests) == 1:
                    parts = [
                        {
                            "functionCall": {
                                "id": call_id,
                                "name": "json_edit_tool",
                                "args": {
                                    "operation": "view",
                                    "file_path": str(path),
                                    "json_path": "$.value",
                                },
                            }
                        }
                        for call_id, path in zip(
                            ("remote-first", "remote-second"), files, strict=True
                        )
                    ]
                else:
                    parts = [{"text": "Both results received."}]
                return httpx.Response(
                    200,
                    json={
                        "candidates": [
                            {"content": {"role": "model", "parts": parts}, "finishReason": "STOP"}
                        ]
                    },
                )

            client = self.make_client(handler)
            tool = JSONEditTool(model_provider="google")
            response = client.chat(
                [LLMMessage(role="user", content="Read both files.")], self.config, [tool]
            )
            self.assertIsNotNone(response.tool_calls)
            executor = ToolExecutor([tool])
            try:
                results = await executor.parallel_tool_call(response.tool_calls)
                self.assertTrue(all(result.success for result in results))
                # IDs must preserve correlation even when result messages arrive in reverse order.
                client.chat(
                    [LLMMessage(role="user", tool_result=result) for result in reversed(results)],
                    self.config,
                )
            finally:
                await executor.close_tools()

        self.assertEqual(len(requests), 2)
        self.assertEqual(
            [call.call_id for call in response.tool_calls], ["remote-first", "remote-second"]
        )
        serialized = [
            part["functionResponse"]
            for content in requests[1]["contents"]
            for part in content["parts"]
            if "functionResponse" in part
        ]
        self.assertEqual([part.get("id") for part in serialized], ["remote-second", "remote-first"])
        self.assertIn("second-result", serialized[0]["response"]["result"])
        self.assertIn("first-result", serialized[1]["response"]["result"])

    async def test_restored_history_keeps_provider_ids(self):
        client = self.make_client(lambda request: httpx.Response(500))
        call = ToolCall(
            name="read", call_id="remote-call", id="remote-call", arguments={"path": "a"}
        )
        result = ToolResult(
            name="read", call_id="remote-call", id="remote-call", success=True, result="data"
        )
        client.set_chat_history(
            [
                LLMMessage(role="assistant", tool_call=call),
                LLMMessage(role="user", tool_result=result),
            ]
        )
        self.assertEqual(client.message_history[0].parts[0].function_call.id, "remote-call")
        self.assertEqual(client.message_history[1].parts[0].function_response.id, "remote-call")

    async def test_legacy_calls_without_ids_keep_local_ids_off_the_wire(self):
        def handler(request):
            return httpx.Response(
                200,
                json={
                    "candidates": [
                        {
                            "content": {
                                "role": "model",
                                "parts": [
                                    {"functionCall": {"name": "json_edit_tool", "args": {}}},
                                    {"functionCall": {"name": "json_edit_tool", "args": {}}},
                                ],
                            },
                            "finishReason": "STOP",
                        }
                    ]
                },
            )

        client = self.make_client(handler)
        response = client.chat([LLMMessage(role="user", content="Read files.")], self.config)
        self.assertIsNotNone(response.tool_calls)
        calls = response.tool_calls
        self.assertNotEqual(calls[0].call_id, calls[1].call_id)
        for call in calls:
            uuid.UUID(call.call_id)
            self.assertIsNone(call.id)
            result = ToolResult(name=call.name, call_id=call.call_id, success=True, result="data")
            self.assertIsNone(client.parse_tool_call_result(result).function_response.id)

    async def test_failed_tool_result_keeps_provider_id(self):
        client = self.make_client(lambda request: httpx.Response(500))
        executor = ToolExecutor([])
        call = ToolCall(name="missing_tool", call_id="remote-failed", id="remote-failed")
        results = await executor.sequential_tool_call([call])
        self.assertFalse(results[0].success)
        part = client.parse_tool_call_result(results[0])
        self.assertEqual(part.function_response.id, "remote-failed")
        self.assertIn("not found", part.function_response.response["error"])


if __name__ == "__main__":
    unittest.main()
