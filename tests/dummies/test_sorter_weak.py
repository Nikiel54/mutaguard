"""Intentionally weak tests -- many mutants should survive."""
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))
from sorter import bubble_sort, find_max


def test_sort_basic():
    assert bubble_sort([3, 1, 2]) == [1, 2, 3]


def test_max_basic():
    assert find_max([1, 2, 3]) == 3

    