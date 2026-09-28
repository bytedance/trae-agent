# Copyright (c) 2025 ByteDance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

"""The retry loop must stop at answers that cannot change, not retry them.

Nothing here sleeps or reaches a network: `time.sleep` is patched, and the decorated function
is a stub that raises a canned error. What is under test is only how many times the decorator
chooses to call it again.
"""

import unittest
from collections.abc import Callable
from unittest.mock import patch

from trae_agent.utils.llm_clients.retry_utils import is_permanent_failure, retry_with


class StatusError(Exception):
    """Stands in for the SDK errors that carry an HTTP status."""

    def __init__(self, status_code: object, message: str = "boom") -> None:
        super().__init__(message)
        self.status_code = status_code


def counted_failer(error: Exception, max_retries: int) -> tuple[Callable[[], str], list[int]]:
    calls: list[int] = []

    def func() -> str:
        calls.append(1)
        raise error

    decorated = retry_with(func, provider_name="Test", max_retries=max_retries)
    return decorated, calls


class TestPermanentFailuresAreNotRetried(unittest.TestCase):
    def test_a_rejected_key_fails_on_the_first_attempt(self):
        for status_code in (400, 401, 403, 404, 413, 422):
            with (
                self.subTest(status_code=status_code),
                patch("trae_agent.utils.llm_clients.retry_utils.time.sleep") as sleep,
            ):
                error = StatusError(status_code)
                decorated, calls = counted_failer(error, max_retries=5)
                with self.assertRaises(StatusError) as raised:
                    decorated()
                self.assertIs(raised.exception, error)
                self.assertEqual(len(calls), 1)
                sleep.assert_not_called()

    def test_a_rate_limit_is_still_retried(self):
        for status_code in (408, 409, 425, 429):
            with (
                self.subTest(status_code=status_code),
                patch("trae_agent.utils.llm_clients.retry_utils.time.sleep"),
            ):
                decorated, calls = counted_failer(StatusError(status_code), max_retries=2)
                with self.assertRaises(StatusError):
                    decorated()
                self.assertEqual(len(calls), 3)

    def test_a_server_side_error_is_still_retried(self):
        for status_code in (500, 502, 503, 504):
            with (
                self.subTest(status_code=status_code),
                patch("trae_agent.utils.llm_clients.retry_utils.time.sleep"),
            ):
                decorated, calls = counted_failer(StatusError(status_code), max_retries=3)
                with self.assertRaises(StatusError):
                    decorated()
                self.assertEqual(len(calls), 4)

    def test_an_error_without_a_status_code_keeps_being_retried(self):
        # A connection problem carries no status, and that path must not change.
        for error in (ConnectionError("no route"), RuntimeError("boom")):
            with (
                self.subTest(error=type(error).__name__),
                patch("trae_agent.utils.llm_clients.retry_utils.time.sleep"),
            ):
                decorated, calls = counted_failer(error, max_retries=1)
                with self.assertRaises(type(error)):
                    decorated()
                self.assertEqual(len(calls), 2)


class TestIsPermanentFailure(unittest.TestCase):
    def test_only_a_client_status_counts_as_permanent(self):
        cases = {
            StatusError(401): True,
            StatusError(404): True,
            StatusError(429): False,
            StatusError(408): False,
            StatusError(503): False,
            StatusError("401"): False,
            StatusError(None): False,
            ConnectionError("reset"): False,
        }
        for error, expected in cases.items():
            with self.subTest(error=error):
                self.assertEqual(is_permanent_failure(error), expected)


if __name__ == "__main__":
    unittest.main()
