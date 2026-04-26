"""Tests for equivalent mutant detection (false positive mitigations).

Verifies:
  - Known equivalent mutants are correctly flagged
  - Each heuristic works independently
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

from core.equivalent import (
    check_equivalent,
    EquivalenceReason,
    EquivalenceResult,
)
from core.mutator import Mutant

DUMMIES_PATH = "dummies"
DUMMIES = Path(__file__).parent / DUMMIES_PATH


def make_mutant(
    original_node: str,
    mutated_node: str,
    operator: str = "ArithmeticOperator",
    line: int = 1,
    source_file: str = "<test>",
) -> Mutant:
    """Build a minimal Mutant for equivalence testing."""
    class _FakeMutant(Mutant):
        def generate_source(self) -> str:
            return mutated_node

    return _FakeMutant(
        id="equiv_test",
        operator=operator,
        original_node=original_node,
        mutated_node=mutated_node,
        source_file=source_file,
        line_number=line,
        column=0,
        _mutated_tree=ast.parse(mutated_node),
    )


def parse(src: str) -> ast.Module:
    return ast.parse(src)


# Constant folding/indempotent rules
class TestConstantFold:
    def test_add_zero_to_sub_zero_is_equivalent(self):
        mutant = make_mutant("x + 0", "x - 0")
        result = check_equivalent(mutant, parse("x = x + 0"))
        assert result.is_equivalent
        assert result.reason == EquivalenceReason.CONSTANT_FOLD

    def test_sub_zero_to_add_zero_is_equivalent(self):
        mutant = make_mutant("x - 0", "x + 0")
        result = check_equivalent(mutant, parse("x = x - 0"))
        assert result.is_equivalent

    def test_mult_one_to_div_one_is_equivalent(self):
        mutant = make_mutant("x * 1", "x / 1")
        result = check_equivalent(mutant, parse("x = x * 1"))
        assert result.is_equivalent
        assert result.reason == EquivalenceReason.CONSTANT_FOLD

    def test_div_one_to_mult_one_is_equivalent(self):
        mutant = make_mutant("x / 1", "x * 1")
        result = check_equivalent(mutant, parse("x = x / 1"))
        assert result.is_equivalent

    def test_add_one_not_equivalent(self):
        """x + 1 → x - 1 changes the result — not equivalent."""
        mutant = make_mutant("x + 1", "x - 1")
        result = check_equivalent(mutant, parse("x = x + 1"))
        assert not result.is_equivalent

    def test_mult_zero_not_equivalent(self):
        """x * 0 → x + 0 changes the result — not equivalent."""
        mutant = make_mutant("x * 0", "x + 0")
        result = check_equivalent(mutant, parse("x = x * 0"))
        assert not result.is_equivalent

    def test_explanation_is_populated(self):
        mutant = make_mutant("x + 0", "x - 0")
        result = check_equivalent(mutant, parse("x = 1"))
        assert result.explanation


# Dead code checks
class TestDeadCode:
    def test_mutation_in_if_false_is_equivalent(self):
        src = """
if False:
    x = 1 + 1
"""
        mutant = make_mutant("1 + 1", "1 - 1", line=3)
        result = check_equivalent(mutant, parse(src))
        assert result.is_equivalent
        assert result.reason == EquivalenceReason.DEAD_CODE

    def test_mutation_in_while_false_is_equivalent(self):
        src = """
while False:
    x = x + 1
"""
        mutant = make_mutant("x + 1", "x - 1", line=3)
        result = check_equivalent(mutant, parse(src))
        assert result.is_equivalent

    def test_mutation_outside_dead_code_not_equivalent(self):
        src = """
x = 1 + 1
if False:
    y = 2 + 2
"""
        mutant = make_mutant("1 + 1", "1 - 1", line=2)
        result = check_equivalent(mutant, parse(src))
        assert not result.is_equivalent

    def test_if_true_body_not_flagged(self):
        """if True body IS reachable — must not be flagged."""
        src = """
if True:
    x = 1 + 1
"""
        mutant = make_mutant("1 + 1", "1 - 1", line=3)
        result = check_equivalent(mutant, parse(src))
        assert not result.is_equivalent

    def test_dynamic_condition_not_flagged(self):
        """Non-constant conditions cannot be statically determined."""
        src = """
if some_flag:
    x = 1 + 1
"""
        mutant = make_mutant("1 + 1", "1 - 1", line=3)
        result = check_equivalent(mutant, parse(src))
        assert not result.is_equivalent


# No return use 
class TestNoopReturn:
    def test_return_flagged_when_value_never_used(self):
        src = """
def log(msg):
    print(msg)
    return msg

log("hello")
log("world")
"""
        mutant = make_mutant(
            "return msg", "return None",
            operator="StatementOperator",
            line=4,
        )
        result = check_equivalent(mutant, parse(src))
        assert result.is_equivalent
        assert result.reason == EquivalenceReason.NO_RETURN_USE

    def test_return_not_flagged_when_value_used(self):
        src = """
def compute(x):
    return x + 1

result = compute(5)
"""
        mutant = make_mutant(
            "return x + 1", "return None",
            operator="StatementOperator",
            line=3,
        )
        result = check_equivalent(mutant, parse(src))
        assert not result.is_equivalent

    def test_non_statement_operator_not_checked(self):
        """No-op return only applies to StatementOperator mutations."""
        src = """
def add(a, b):
    return a + b

add(1, 2)
"""
        mutant = make_mutant(
            "a + b", "a - b",
            operator="ArithmeticOperator",
            line=3,
        )
        result = check_equivalent(mutant, parse(src))
        assert not result.is_equivalent


# Conservative bias, doesnt flag unless you are sure
class TestConservativeBias:
    def test_ambiguous_mutation_not_flagged(self):
        """A mutation with no clear equivalence pattern must not be flagged."""
        mutant = make_mutant("a + b", "a - b")
        result = check_equivalent(mutant, parse("x = a + b"))
        assert not result.is_equivalent

    def test_relational_mutation_not_flagged(self):
        mutant = make_mutant("x > 0", "x >= 0")
        result = check_equivalent(mutant, parse("y = x > 0"))
        assert not result.is_equivalent

    def test_result_has_no_reason_when_not_equivalent(self):
        mutant = make_mutant("a + b", "a - b")
        result = check_equivalent(mutant, parse("x = a + b"))
        assert result.reason is None
        assert result.explanation == ""

    def test_boolean_mutation_not_flagged(self):
        mutant = make_mutant("True", "False")
        result = check_equivalent(mutant, parse("x = True"))
        assert not result.is_equivalent


