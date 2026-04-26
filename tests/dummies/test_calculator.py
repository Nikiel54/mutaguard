"""Strong test suite for calculator.py — should kill most mutants."""
import sys
import os
import pytest

sys.path.insert(0, os.path.dirname(__file__))
from calculator import add, subtract, divide, is_positive, clamp


def test_add():
    assert add(2, 3) == 5
    assert add(-1, 1) == 0
    assert add(0, 0) == 0
    assert add(-5, -3) == -8


def test_subtract():
    assert subtract(5, 3) == 2
    assert subtract(3, 5) == -2
    assert subtract(0, 0) == 0


def test_divide():
    assert divide(10, 2) == 5.0
    assert divide(9, 3) == 3.0
    with pytest.raises(ValueError):
        divide(1, 0)


def test_is_positive():
    assert is_positive(1) is True
    assert is_positive(100) is True
    assert is_positive(-1) is False
    assert is_positive(0) is False   # boundary


def test_clamp():
    assert clamp(5, 0, 10) == 5     # in range
    assert clamp(-1, 0, 10) == 0    # below low
    assert clamp(11, 0, 10) == 10   # above high
    assert clamp(0, 0, 10) == 0     # at low boundary
    assert clamp(10, 0, 10) == 10   # at high boundary
