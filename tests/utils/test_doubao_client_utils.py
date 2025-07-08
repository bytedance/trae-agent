"""
This test file is for the purpose to check if Doubao client is functioning.
The purpose of this test file is to ensure it is funtionable from the doubao client
"""

import os
import sys
import unittest


from trae_agent.utils.config import ModelParameters
from trae_agent.utils.doubao_client import DoubaoClient
from trae_agent.utils.llm_basics import LLMMessage

TEST_MODEL = "doubao-1.5-pro-32k-250115"
BASE_URL = "https://ark.cn-beijing.volces.com/api/v3/"
API_KEY = os.getenv("DOUBAO_API_KEY", "DOUBAO_API_KEY_NOT_FOUND")

MODEL_PARAMETERS = ModelParameters(
    TEST_MODEL,
    API_KEY,
    1000,
    0.8,
    7.0,
    8,
    False,
    1,
    BASE_URL,
    None,
)


class TestDouBaoClient(unittest.TestCase):
    """
    Doubao client test cases
    """

    def DoubaoClient_init(self):
        client = DoubaoClient(MODEL_PARAMETERS)
        self.assertEqual(client.base_url, BASE_URL)

    def test_set_chat_history(self):
        client = DoubaoClient(MODEL_PARAMETERS)
        message = LLMMessage("user", "this is a test message")
        client.set_chat_history(messages=[message])
        self.assertTrue(True)  # runnable

    def test_doubao_chat(self):
        """
        There is nothing we have to assert for this test case just see if it can run
        """
        client = DoubaoClient(MODEL_PARAMETERS)
        message = LLMMessage("user", "this is a test message")
        client.chat(messages=[message], model_parameters=MODEL_PARAMETERS)
        self.assertTrue(True)  # runnable

    def test_supports_tool_calling(self):
        """
        A test case to check the support tool calling function
        """
        client = DoubaoClient(MODEL_PARAMETERS)
        self.assertEqual(client.supports_tool_calling(MODEL_PARAMETERS), True)
        MODEL_PARAMETERS.model = "no such model"
        self.assertEqual(client.supports_tool_calling(MODEL_PARAMETERS), False)


if __name__ == "__main__":
    unittest.main()
