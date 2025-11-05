import pytest
from tools import fibonacci


def test_fibonacci_basic():
    # first few Fibonacci numbers
    expected = [0, 1, 1, 2, 3, 5, 8, 13, 21, 34]
    for i, val in enumerate(expected):
        assert fibonacci.fibonacci(i) == val


def test_fib_sequence():
    assert fibonacci.fib_sequence(0) == []
    assert fibonacci.fib_sequence(1) == [0]
    assert fibonacci.fib_sequence(5) == [0, 1, 1, 2, 3]


def test_fib_generator():
    assert list(fibonacci.fib_generator(0)) == []
    assert list(fibonacci.fib_generator(6)) == [0, 1, 1, 2, 3, 5]


def test_invalid_args():
    with pytest.raises(TypeError):
        fibonacci.fibonacci(3.5)
    with pytest.raises(ValueError):
        fibonacci.fibonacci(-1)
    with pytest.raises(TypeError):
        fibonacci.fib_sequence('3')
    with pytest.raises(ValueError):
        fibonacci.fib_sequence(-2)
