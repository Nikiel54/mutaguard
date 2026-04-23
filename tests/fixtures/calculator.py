"""Simple arithmetic module — MutaGuard test fixture."""


def add(a, b):
    return a + b


def subtract(a, b):
    return a - b


def divide(a, b):
    if b == 0:
        raise ValueError("Cannot divide by zero")
    return a / b


def is_positive(n):
    return n > 0


def clamp(value, low, high):
    if value < low:
        return low
    if value > high:
        return high
    return value
