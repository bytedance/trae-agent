"""Fibonacci utilities.

Provides functions to compute the n-th Fibonacci number and to generate
the first n Fibonacci numbers. Also includes a small CLI for convenience.

Fibonacci definition used:
  fibonacci(0) == 0
  fibonacci(1) == 1
  fibonacci(n) == fibonacci(n-1) + fibonacci(n-2) for n >= 2
"""
from typing import Iterator, List
import argparse


def fibonacci(n: int) -> int:
    """Return the n-th Fibonacci number.

    Args:
        n: Non-negative integer index into the Fibonacci sequence.

    Returns:
        The n-th Fibonacci number where fibonacci(0) == 0 and fibonacci(1) == 1.

    Raises:
        TypeError: if n is not an integer.
        ValueError: if n is negative.
    """
    if not isinstance(n, int):
        raise TypeError("n must be an integer")
    if n < 0:
        raise ValueError("n must be non-negative")

    a, b = 0, 1
    for _ in range(n):
        a, b = b, a + b
    return a


def fib_sequence(count: int) -> List[int]:
    """Return a list with the first `count` Fibonacci numbers.

    Args:
        count: number of elements to generate. Must be >= 0.

    Returns:
        List of length `count` with the Fibonacci sequence starting at 0.

    Raises:
        TypeError: if count is not an integer.
        ValueError: if count is negative.
    """
    if not isinstance(count, int):
        raise TypeError("count must be an integer")
    if count < 0:
        raise ValueError("count must be non-negative")

    seq = []
    a, b = 0, 1
    for _ in range(count):
        seq.append(a)
        a, b = b, a + b
    return seq


def fib_generator(count: int) -> Iterator[int]:
    """Yield the first `count` Fibonacci numbers."""
    if not isinstance(count, int):
        raise TypeError("count must be an integer")
    if count < 0:
        raise ValueError("count must be non-negative")

    a, b = 0, 1
    for _ in range(count):
        yield a
        a, b = b, a + b


def main() -> int:
    parser = argparse.ArgumentParser(description="Compute Fibonacci numbers")
    parser.add_argument("n", type=int, help="Index of Fibonacci number or count when --list is used")
    parser.add_argument("--list", action="store_true", help="Print the first n Fibonacci numbers")
    args = parser.parse_args()

    if args.list:
        seq = fib_sequence(args.n)
        print(" ".join(str(x) for x in seq))
    else:
        print(fibonacci(args.n))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
