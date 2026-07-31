# Copyright (c) 2025 ByteDance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

"""Token counting utility using tiktoken."""

import logging
from typing import Any

import tiktoken

logger = logging.getLogger(__name__)

# Default encoding fallback
_DEFAULT_ENCODING = "cl100k_base"


def count_tokens(text: str, model: str | None = None) -> int:
    """Count the number of tokens in a text string.

    Args:
        text: The text to count tokens for.
        model: Optional model name to use for encoding selection.

    Returns:
        Number of tokens in the text.
    """
    if not text:
        return 0

    try:
        encoding = tiktoken.encoding_for_model(model) if model else tiktoken.get_encoding(_DEFAULT_ENCODING)
    except (KeyError, ValueError):
        encoding = tiktoken.get_encoding(_DEFAULT_ENCODING)

    return len(encoding.encode(text))


def count_messages_tokens(messages: list[dict[str, Any]], model: str | None = None) -> int:
    """Count total tokens across all messages in a conversation.

    Args:
        messages: List of message dicts with 'role' and 'content' keys.
        model: Optional model name for encoding selection.

    Returns:
        Total token count across all messages.
    """
    total = 0
    for msg in messages:
        content = msg.get("content") or ""
        role = msg.get("role", "")
        # Each message has overhead for role tokens
        total += count_tokens(content, model) + count_tokens(role, model) + 4  # message overhead
    total += 2  # priming tokens
    return total


def get_model_context_limit(model: str | None = None) -> int:
    """Get the context window limit for a model.

    Args:
        model: Model name.

    Returns:
        Context window size in tokens.
    """
    # Common model context limits
    model_limits = {
        "gpt-4": 8192,
        "gpt-4-32k": 32768,
        "gpt-4-turbo": 128000,
        "gpt-4o": 128000,
        "gpt-4o-mini": 128000,
        "gpt-3.5-turbo": 16385,
        "claude-3-opus": 200000,
        "claude-3-sonnet": 200000,
        "claude-3-haiku": 200000,
        "claude-3-5-sonnet": 200000,
        "claude-3-5-haiku": 200000,
    }

    if not model:
        return 128000  # default

    # Check exact match first
    if model in model_limits:
        return model_limits[model]

    # Check prefix match
    for prefix, limit in model_limits.items():
        if model.startswith(prefix):
            return limit

    return 128000  # default
