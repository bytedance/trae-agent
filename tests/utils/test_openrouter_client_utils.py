"""
This file provides basic testing with openrouter client. This purpose of the test is to check if it run properly

Currently, we only test init, chat and set chat history
WARNING: This Open router test should not be used in the GitHub Actions workflow cause it will require API key to test.

setting: to avoid
"""

import os
import unittest

from trae_agent.utils.config import ModelParameters
from trae_agent.utils.llm_basics import LLMMessage
from trae_agent.utils.openrouter_client import OpenRouterClient

TEST_MODEL = "mistralai/mistral-small-3.2-24b-instruct:free"


@unittest.skipIf(
    os.getenv("SKIP_OPENROUTER_TEST", "").lower() == "true",
    "Open router tests skipped due to SKIP_OPENROUTER_TEST environment variable",
)
class TestOpenRouterClient(unittest.TestCase):
    """
    Open router client init function
    """

    def test_OpenRouterClient_init(self):
        model_parameters = ModelParameters(
            TEST_MODEL,
            os.getenv("OPENROUTER_API_KEY"),
            1000,
            0.8,
            7.0,
            8,
            False,
            1,
            "https://openrouter.ai/api/v1",
            None,
        )
        openrouter_client = OpenRouterClient(model_parameters)
        self.assertEqual(openrouter_client.base_url, "https://openrouter.ai/api/v1")

    def test_set_chat_history(self):
        model_parameters = ModelParameters(
            TEST_MODEL,
            os.getenv("OPENROUTER_API_KEY"),
            1000,
            0.8,
            7.0,
            8,
            False,
            1,
            "https://openrouter.ai/api/v1",
            None,
        )
        openrouter_client = OpenRouterClient(model_parameters)
        message = LLMMessage("user", "this is a test message")
        openrouter_client.set_chat_history(messages=[message])
        self.assertTrue(True)  # runnable

    def test_openrouter_chat(self):
        """
        There is nothing we have to assert for this test case just see if it can run
        """
        model_parameters = ModelParameters(
            TEST_MODEL,
            os.getenv("OPENROUTER_API_KEY"),
            1000,
            0.8,
            7.0,
            8,
            False,
            1,
            "https://openrouter.ai/api/v1",
            None,
        )
        openrouter_client = OpenRouterClient(model_parameters)
        message = LLMMessage("user", "this is a test message")
        openrouter_client.chat(messages=[message], model_parameters=model_parameters)
        self.assertTrue(True)  # runnable

    def test_supports_tool_calling(self):
        """
        A test case to check the support tool calling function
        """
        model_parameters = ModelParameters(
            TEST_MODEL,
            os.getenv("OPENROUTER_API_KEY"),
            1000,
            0.8,
            7.0,
            8,
            False,
            1,
            "https://openrouter.ai/api/v1",
            None,
        )
        openrouter_client = OpenRouterClient(model_parameters)
        self.assertEqual(
            openrouter_client.supports_tool_calling(model_parameters), True
        )
        model_parameters.model = "no such model"
        self.assertEqual(
            openrouter_client.supports_tool_calling(model_parameters), False
        )


if __name__ == "__main__":
    unittest.main()
