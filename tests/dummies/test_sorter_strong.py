"""Thorough tests -- should kill most mutants."""
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))
from sorter import bubble_sort, find_max


def test_sort_empty():
    assert bubble_sort([]) == []

def test_sort_single():
    assert bubble_sort([1]) == [1]

def test_sort_sorted():
    assert bubble_sort([1, 2, 3]) == [1, 2, 3]

def test_sort_reverse():
    assert bubble_sort([3, 2, 1]) == [1, 2, 3]

def test_sort_duplicates():
    assert bubble_sort([2, 1, 2]) == [1, 2, 2]

def test_sort_negative():
    assert bubble_sort([-3, -1, -2]) == [-3, -2, -1]

def test_sort_does_not_mutate_original():
    original = [3, 1, 2]
    bubble_sort(original)
    assert original == [3, 1, 2]

def test_max_empty():
    assert find_max([]) is None

def test_max_single():
    assert find_max([5]) == 5

def test_max_negative():
    assert find_max([-3, -1, -2]) == -1

def test_max_all_same():
    assert find_max([4, 4, 4]) == 4

    