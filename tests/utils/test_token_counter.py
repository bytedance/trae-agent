# Copyright (c) 2025 ByteDance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

import unittest

from trae_agent.utils.token_counter import count_tokens, count_messages_tokens, get_model_context_limit


class TestCountTokens(unittest.TestCase):
    def test_empty_string(self):
        self.assertEqual(count_tokens(""), 0)

    def test_normal_text(self):
        tokens = count_tokens("Hello, world!")
        self.assertGreater(tokens, 0)

    def test_with_gpt4_model(self):
        tokens = count_tokens("Hello, world!", model="gpt-4")
        self.assertGreater(tokens, 0)

    def test_with_gpt35_model(self):
        tokens = count_tokens("Hello, world!", model="gpt-3.5-turbo")
        self.assertGreater(tokens, 0)

    def test_with_unknown_model_fallback(self):
        tokens = count_tokens("Hello, world!", model="unknown-model-xyz")
        self.assertGreater(tokens, 0)

    def test_with_none_model(self):
        tokens = count_tokens("test text", model=None)
        self.assertGreater(tokens, 0)


class TestCountMessagesTokens(unittest.TestCase):
    def test_empty_messages(self):
        self.assertEqual(count_messages_tokens([]), 2)  # priming tokens

    def test_single_message(self):
        messages = [{"role": "user", "content": "Hello"}]
        tokens = count_messages_tokens(messages)
        self.assertGreater(tokens, 0)

    def test_multiple_messages(self):
        messages = [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "What is 2+2?"},
            {"role": "assistant", "content": "4"},
        ]
        tokens = count_messages_tokens(messages)
        self.assertGreater(tokens, 0)

    def test_with_model(self):
        messages = [{"role": "user", "content": "Hello"}]
        tokens = count_messages_tokens(messages, model="gpt-4")
        self.assertGreater(tokens, 0)

    def test_none_content_treated_as_empty(self):
        messages = [{"role": "user", "content": None}]
        tokens = count_messages_tokens(messages)
        self.assertGreater(tokens, 0)  # role tokens + overhead + priming


class TestGetModelContextLimit(unittest.TestCase):
    def test_gpt4(self):
        self.assertEqual(get_model_context_limit("gpt-4"), 8192)

    def test_gpt4o(self):
        self.assertEqual(get_model_context_limit("gpt-4o"), 128000)

    def test_gpt35_turbo(self):
        self.assertEqual(get_model_context_limit("gpt-3.5-turbo"), 16385)

    def test_claude3_opus(self):
        self.assertEqual(get_model_context_limit("claude-3-opus"), 200000)

    def test_prefix_match(self):
        self.assertEqual(get_model_context_limit("gpt-4o-2024-05-13"), 128000)

    def test_unknown_model_returns_default(self):
        self.assertEqual(get_model_context_limit("totally-unknown-model"), 128000)

    def test_none_returns_default(self):
        self.assertEqual(get_model_context_limit(None), 128000)


if __name__ == "__main__":
    unittest.main()
