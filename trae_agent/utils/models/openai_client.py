# Copyright (c) 2025 ByteDance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT
import json
import random
import time
from typing import Tuple

import openai
from openai.types.responses import (
    FunctionToolParam,
    ResponseFunctionToolCallParam,
    ResponseInputParam,
)
from openai.types.responses.response_input_param import FunctionCallOutput

from ...tools.base import Tool, ToolCall, ToolResult
from ...utils.config import ModelParameters
from ...utils.trajectory_recorder import TrajectoryRecorder
from ..llm_basics import LLMMessage, LLMResponse, LLMUsage


def chat(
    messages: list[LLMMessage],
    model_parameters: ModelParameters,
    client: openai.OpenAI,
    tools: list[Tool] | None = None,
    reuse_history: bool = True,
    message_history: ResponseInputParam | None = None,
    trajectory_recorder: TrajectoryRecorder | None = None,
) -> Tuple[LLMResponse, ResponseInputParam]:
    """Send chat messages to OpenAI with optional tool support."""
    openai_messages: ResponseInputParam = parse_messages(messages)

    tool_schemas = None
    if tools:
        tool_schemas = [
            FunctionToolParam(
                name=tool.name,
                description=tool.description,
                parameters=tool.get_input_schema(),
                strict=True,
                type="function",
            )
            for tool in tools
        ]

    api_call_input: ResponseInputParam = []
    if reuse_history:
        api_call_input.extend(message_history)
    api_call_input.extend(openai_messages)

    response = None
    error_message = ""
    for i in range(model_parameters.max_retries):
        try:
            response = client.responses.create(
                input=api_call_input,
                model=model_parameters.model,
                tools=tool_schemas if tool_schemas else openai.NOT_GIVEN,
                temperature=model_parameters.temperature
                if "o3" not in model_parameters.model and "o4-mini" not in model_parameters.model
                else openai.NOT_GIVEN,
                top_p=model_parameters.top_p,
                max_output_tokens=model_parameters.max_tokens,
            )
            break
        except Exception as e:
            this_error_message = str(e)
            error_message += f"Error {i + 1}: {this_error_message}\n"
            sleep_time = random.randint(3, 30)
            print(
                f"OpenAI API call failed: {this_error_message} will sleep for {sleep_time} seconds and will retry."
            )
            # Randomly sleep for 3-30 seconds
            time.sleep(sleep_time)

    if response is None:
        raise ValueError(f"Failed to get response from OpenAI after max retries: {error_message}")

    message_history = api_call_input + response.output

    content = ""
    tool_calls: list[ToolCall] = []
    for output_block in response.output:
        if output_block.type == "function_call":
            tool_calls.append(
                ToolCall(
                    call_id=output_block.call_id,
                    name=output_block.name,
                    arguments=json.loads(output_block.arguments) if output_block.arguments else {},
                    id=output_block.id,
                )
            )
        elif output_block.type == "message":
            content = "".join(
                content_block.text
                for content_block in output_block.content
                if content_block.type == "output_text"
            )

    usage = None
    if response.usage:
        usage = LLMUsage(
            input_tokens=response.usage.input_tokens or 0,
            output_tokens=response.usage.output_tokens or 0,
            cache_read_input_tokens=response.usage.input_tokens_details.cached_tokens or 0,
            reasoning_tokens=response.usage.output_tokens_details.reasoning_tokens or 0,
        )

    llm_response = LLMResponse(
        content=content,
        usage=usage,
        model=response.model,
        finish_reason=response.status,
        tool_calls=tool_calls if len(tool_calls) > 0 else None,
    )

    # Record trajectory if recorder is available
    if trajectory_recorder:
        trajectory_recorder.record_llm_interaction(
            messages=messages,
            response=llm_response,
            provider="openai",
            model=model_parameters.model,
            tools=tools,
        )

    return llm_response, message_history


def supports_tool_calling(model_parameters: ModelParameters) -> bool:
    if "o1-mini" in model_parameters.model:
        return False

    tool_capable_models = [
        "gpt-4-turbo",
        "gpt-4o",
        "gpt-4o-mini",
        "gpt-4.1",
        "gpt-4.5",
        "o1",
        "o3",
        "o3-mini",
        "o4-mini",
    ]
    return any(model in model_parameters.model for model in tool_capable_models)


def parse_messages(messages: list[LLMMessage]) -> ResponseInputParam:
    """
    parse the message based on openai
    """
    openai_messages: ResponseInputParam = []
    for msg in messages:
        if msg.tool_result:
            openai_messages.append(parse_tool_call_result(msg.tool_result))
        elif msg.tool_call:
            openai_messages.append(parse_tool_call(msg.tool_call))
        else:
            if not msg.content:
                raise ValueError("Message content is required")
            if msg.role == "system":
                openai_messages.append({"role": "system", "content": msg.content})
            elif msg.role == "user":
                openai_messages.append({"role": "user", "content": msg.content})
            elif msg.role == "assistant":
                openai_messages.append({"role": "assistant", "content": msg.content})
            else:
                raise ValueError(f"Invalid message role: {msg.role}")
    return openai_messages


def parse_tool_call(tool_call: ToolCall) -> ResponseFunctionToolCallParam:
    return ResponseFunctionToolCallParam(
        call_id=tool_call.call_id,
        name=tool_call.name,
        arguments=json.dumps(tool_call.arguments),
        type="function_call",
    )


def parse_tool_call_result(tool_call_result: ToolResult) -> FunctionCallOutput:
    """Parse the tool call result from the LLM response to FunctionCallOutput format."""
    result_content: str = ""
    if tool_call_result.result is not None:
        result_content += str(tool_call_result.result)
    if tool_call_result.error:
        result_content += f"\nError: {tool_call_result.error}"
    result_content = result_content.strip()

    return FunctionCallOutput(
        type="function_call_output",  # Explicitly set the type field
        call_id=tool_call_result.call_id,
        output=result_content,
    )
