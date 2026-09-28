# Copyright (c) 2025 ByteDance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

import random
import time
import traceback
from functools import wraps
from typing import Any, Callable, TypeVar

T = TypeVar("T")

# A 4xx whose answer cannot change by asking again. The exceptions that carry these codes are
# retryable on the same basis as a timeout: a 429 says "ask again later", a 401 says "asking
# again with the same key is pointless".
_RETRYABLE_CLIENT_STATUS_CODES = frozenset({408, 409, 425, 429})


def is_permanent_failure(error: BaseException) -> bool:
    """Would repeating this exact request change the answer?

    Only the OpenAI and Anthropic SDKs expose a status code, and any error that does not carry
    one stays retryable, so this narrows the retry loop rather than changing how a connection
    problem is handled.
    """
    status_code = getattr(error, "status_code", None)
    if not isinstance(status_code, int):
        return False
    return 400 <= status_code < 500 and status_code not in _RETRYABLE_CLIENT_STATUS_CODES


def retry_with(
    func: Callable[..., T],
    provider_name: str = "OpenAI",
    max_retries: int = 3,
) -> Callable[..., T]:
    """
    Decorator that adds retry logic with randomized backoff.

    Args:
        func: The function to decorate
        provider_name: The name of the model provider being called
        max_retries: Maximum number of retry attempts

    Returns:
        Decorated function with retry logic
    """

    @wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> T:
        last_exception = None

        for attempt in range(max_retries + 1):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                if is_permanent_failure(e):
                    raise

                last_exception = e

                if attempt == max_retries:
                    # Last attempt, re-raise the exception
                    raise

                sleep_time = random.randint(3, 30)
                this_error_message = str(e)
                print(
                    f"{provider_name} API call failed: {this_error_message}. Will sleep for {sleep_time} seconds and will retry.\n{traceback.format_exc()}"
                )
                # Randomly sleep for 3-30 seconds
                time.sleep(sleep_time)

        # This should never be reached, but just in case
        raise last_exception or Exception("Retry failed for unknown reason")

    return wrapper
