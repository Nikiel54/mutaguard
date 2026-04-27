"""Sorting module with boundary edge cases -- MutaGuard dummy fixture."""


def bubble_sort(arr):
    """Sort a list ascending using bubble sort."""
    arr = arr.copy()
    n = len(arr)
    for i in range(n):
        for j in range(0, n - i - 1):
            if arr[j] > arr[j + 1]:
                arr[j], arr[j + 1] = arr[j + 1], arr[j]
    return arr


def find_max(arr):
    """Return the maximum value in arr, or None if empty."""
    if not arr:
        return None
    max_val = arr[0]
    for val in arr[1:]:
        if val > max_val:
            max_val = val
    return max_val

