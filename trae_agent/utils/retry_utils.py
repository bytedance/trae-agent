# Copyright (c) 2025 ByteDance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

import random
import time
from functools import wraps
from typing import Any, Callable, TypeVar

T = TypeVar("T")


def retry_with(
    func: Callable[..., T],
    service_name: str = "OpenAI",
    max_retries: int = 3,
    provider_name: str = "unknown",
) -> Callable[..., T]:
    """
    Decorator that adds retry logic with randomized backoff.

    Args:
        func: The function to decorate
        provider_name: The name of the service being called
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
                last_exception = e

                if attempt == max_retries:
                    # Last attempt, re-raise the exception
                    raise

                sleep_time = random.randint(3, 30)
                this_error_message = str(e)
                print(
                    f"{provider_name.capitalize()} API call failed: {this_error_message} will sleep for {sleep_time} seconds and will retry."
                )
                # Randomly sleep for 3-30 seconds
                time.sleep(sleep_time)

        # This should never be reached, but just in case
        raise last_exception or Exception("Retry failed for unknown reason")

    return wrapper
