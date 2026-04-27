"""Tests for all six mutation operators (Step 1).

Each operator is tested for:
  - can_mutate() correctly identifies applicable nodes
  - mutate() produces the expected replacements
  - every mutant is valid Python (compile() succeeds)
  - docstrings are never mutated (registry-level check)
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

from core.operators.arithmetic import ArithmeticOperator
from core.operators.boundary import BoundaryOperator
from core.operators.boolean import BooleanOperator
from core.operators.constant import ConstantOperator
from core.operators.relational import RelationalOperator
from core.operators.statement import StatementOperator
from core.mutator import MutatorRegistry
from core.parser import parse_source

DUMMIES = Path(__file__).parent / "dummies"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def expr(src: str) -> ast.AST:
    """Parse a single expression."""
    return ast.parse(src, mode="eval").body


def stmt(src: str) -> ast.AST:
    """Parse the first statement of *src*."""
    return ast.parse(src).body[0]


def is_valid_python(node: ast.AST) -> bool:
    """Return True if *node* can be compiled as a statement or expression.

    return/break/continue are only legal inside a function/loop body, so we
    wrap them in a minimal function definition before compiling.
    """
    try:
        if isinstance(node, (ast.Return, ast.Break, ast.Continue, ast.Pass)):
            # Wrap in a function so return/break/continue are syntactically valid
            wrapper = ast.parse("def _f():\n    pass")
            wrapper.body[0].body = [node]  # type: ignore[attr-defined]
            mod = wrapper
        elif isinstance(node, ast.stmt):
            mod = ast.Module(body=[node], type_ignores=[])
        else:
            mod = ast.Module(body=[ast.Expr(value=node)], type_ignores=[])
        ast.fix_missing_locations(mod)
        compile(mod, "<test>", "exec")
        return True
    except Exception:
        return False


def all_ops_for(src: str, operator) -> list[ast.AST]:
    """Return every mutant node the operator produces by walking *src*."""
    tree = ast.parse(src, mode="eval") if not src.strip().startswith("def") else ast.parse(src)
    results = []
    for node in ast.walk(tree):
        if operator.can_mutate(node):
            results.extend(operator.mutate(node))
    return results


# ---------------------------------------------------------------------------
# ArithmeticOperator
# ---------------------------------------------------------------------------

class TestArithmeticOperator:
    op = ArithmeticOperator()

    def test_add_becomes_sub(self):
        node = expr("a + b")
        assert self.op.can_mutate(node)
        mutants = self.op.mutate(node)
        assert len(mutants) == 1
        assert isinstance(mutants[0].op, ast.Sub)

    def test_sub_becomes_add(self):
        node = expr("a - b")
        mutants = self.op.mutate(node)
        assert any(isinstance(m.op, ast.Add) for m in mutants)

    def test_mult_becomes_div(self):
        node = expr("a * b")
        mutants = self.op.mutate(node)
        assert any(isinstance(m.op, ast.Div) for m in mutants)

    def test_div_becomes_mult(self):
        node = expr("a / b")
        mutants = self.op.mutate(node)
        assert any(isinstance(m.op, ast.Mult) for m in mutants)

    def test_floordiv_becomes_mult(self):
        node = expr("a // b")
        mutants = self.op.mutate(node)
        assert any(isinstance(m.op, ast.Mult) for m in mutants)

    def test_pow_becomes_mult(self):
        node = expr("a ** b")
        mutants = self.op.mutate(node)
        assert any(isinstance(m.op, ast.Mult) for m in mutants)

    def test_mod_becomes_add(self):
        node = expr("a % b")
        mutants = self.op.mutate(node)
        assert any(isinstance(m.op, ast.Add) for m in mutants)

    def test_not_applicable_to_compare(self):
        assert not self.op.can_mutate(expr("a > b"))

    def test_all_mutants_valid_python(self):
        for mutant in all_ops_for("a + b - c * d // e ** f % g", self.op):
            assert is_valid_python(mutant), f"Invalid: {ast.unparse(mutant)}"

    def test_expected_mutant_count(self):
        # a + b - c * d  →  3 BinOps, each producing 1 mutant = 3 total
        mutants = all_ops_for("a + b - c * d", self.op)
        assert len(mutants) == 3


# ---------------------------------------------------------------------------
# RelationalOperator
# ---------------------------------------------------------------------------

class TestRelationalOperator:
    op = RelationalOperator()

    def test_gt_becomes_gte_and_lt(self):
        node = expr("a > b")
        mutants = self.op.mutate(node)
        types = {type(m.ops[0]) for m in mutants}
        assert ast.GtE in types
        assert ast.Lt in types

    def test_gte_becomes_gt_and_lte(self):
        node = expr("a >= b")
        mutants = self.op.mutate(node)
        types = {type(m.ops[0]) for m in mutants}
        assert ast.Gt in types
        assert ast.LtE in types

    def test_lt_becomes_lte_and_gt(self):
        node = expr("a < b")
        mutants = self.op.mutate(node)
        types = {type(m.ops[0]) for m in mutants}
        assert ast.LtE in types
        assert ast.Gt in types

    def test_eq_becomes_noteq(self):
        node = expr("a == b")
        mutants = self.op.mutate(node)
        assert all(isinstance(m.ops[0], ast.NotEq) for m in mutants)

    def test_noteq_becomes_eq(self):
        node = expr("a != b")
        mutants = self.op.mutate(node)
        assert all(isinstance(m.ops[0], ast.Eq) for m in mutants)

    def test_not_applicable_to_binop(self):
        assert not self.op.can_mutate(expr("a + b"))

    def test_all_mutants_valid_python(self):
        for mutant in all_ops_for("x >= 0", self.op):
            assert is_valid_python(mutant), f"Invalid: {ast.unparse(mutant)}"


# ---------------------------------------------------------------------------
# BooleanOperator
# ---------------------------------------------------------------------------

class TestBooleanOperator:
    op = BooleanOperator()

    def test_and_becomes_or(self):
        node = expr("a and b")
        mutants = self.op.mutate(node)
        assert len(mutants) == 1
        assert isinstance(mutants[0].op, ast.Or)

    def test_or_becomes_and(self):
        node = expr("a or b")
        mutants = self.op.mutate(node)
        assert isinstance(mutants[0].op, ast.And)

    def test_true_becomes_false(self):
        node = expr("True")
        mutants = self.op.mutate(node)
        assert len(mutants) == 1
        assert mutants[0].value is False

    def test_false_becomes_true(self):
        node = expr("False")
        assert self.op.mutate(node)[0].value is True

    def test_not_x_becomes_x(self):
        node = expr("not x")
        mutants = self.op.mutate(node)
        assert len(mutants) == 1
        assert isinstance(mutants[0], ast.Name)
        assert mutants[0].id == "x"

    def test_all_valid_python(self):
        for src in ["a and b", "a or b", "not x", "True", "False"]:
            for m in all_ops_for(src, self.op):
                assert is_valid_python(m)


# ---------------------------------------------------------------------------
# StatementOperator
# ---------------------------------------------------------------------------

class TestStatementOperator:
    op = StatementOperator()

    def test_return_value_nullified(self):
        node = stmt("return x + 1")
        assert self.op.can_mutate(node)
        mutants = self.op.mutate(node)
        assert len(mutants) == 1
        assert isinstance(mutants[0], ast.Return)
        assert isinstance(mutants[0].value, ast.Constant)
        assert mutants[0].value.value is None

    def test_bare_return_not_mutated(self):
        # `return` with no value → value is None already, should not be mutated
        node = stmt("return")
        assert not self.op.can_mutate(node)

    def test_break_becomes_pass(self):
        node = stmt("break")
        mutants = self.op.mutate(node)
        assert isinstance(mutants[0], ast.Pass)

    def test_continue_becomes_pass(self):
        node = stmt("continue")
        mutants = self.op.mutate(node)
        assert isinstance(mutants[0], ast.Pass)

    def test_all_valid_python(self):
        for m in self.op.mutate(stmt("return 42")):
            assert is_valid_python(m)
        assert is_valid_python(self.op.mutate(stmt("break"))[0])
        assert is_valid_python(self.op.mutate(stmt("continue"))[0])


# ---------------------------------------------------------------------------
# ConstantOperator
# ---------------------------------------------------------------------------

class TestConstantOperator:
    op = ConstantOperator()

    def test_zero_becomes_one(self):
        node = expr("0")
        assert self.op.can_mutate(node)
        assert self.op.mutate(node)[0].value == 1

    def test_one_becomes_zero(self):
        node = expr("1")
        assert self.op.mutate(node)[0].value == 0

    def test_empty_string_becomes_fuzz(self):
        node = expr('""')
        assert self.op.mutate(node)[0].value == "fuzz"

    def test_nonempty_string_becomes_empty(self):
        node = expr('"hello"')
        assert self.op.mutate(node)[0].value == ""

    def test_bool_not_mutated(self):
        assert not self.op.can_mutate(expr("True"))
        assert not self.op.can_mutate(expr("False"))

    def test_arbitrary_int_not_mutated(self):
        # Only 0 and 1 are in scope; 42 is not
        assert not self.op.can_mutate(expr("42"))

    def test_docstring_skipped_by_registry(self):
        """The registry must not mutate docstrings even if ConstantOperator would."""
        src = '''
def greet(name):
    """Say hello."""
    return "hello " + name
'''
        tree = ast.parse(src)
        registry = MutatorRegistry([ConstantOperator()])
        mutants = list(registry.generate_mutants(tree, "<test>", src))
        docstring_mutations = [m for m in mutants if m.original_node == '"Say hello."']
        assert not docstring_mutations, "Docstring was mutated — it should be skipped"


# ---------------------------------------------------------------------------
# BoundaryOperator
# ---------------------------------------------------------------------------

class TestBoundaryOperator:
    op = BoundaryOperator()

    def test_lt_generates_plus1_and_minus1(self):
        node = expr("x < 5")
        assert self.op.can_mutate(node)
        mutants = self.op.mutate(node)
        vals = {m.comparators[0].value for m in mutants}
        assert vals == {6, 4}

    def test_gt_generates_variants(self):
        node = expr("x > 10")
        vals = {m.comparators[0].value for m in self.op.mutate(node)}
        assert vals == {11, 9}

    def test_lte_generates_variants(self):
        node = expr("x <= 3")
        vals = {m.comparators[0].value for m in self.op.mutate(node)}
        assert vals == {4, 2}

    def test_gte_generates_variants(self):
        node = expr("x >= 0")
        vals = {m.comparators[0].value for m in self.op.mutate(node)}
        assert vals == {1, -1}

    def test_string_comparator_not_mutated(self):
        assert not self.op.can_mutate(expr('x < "hello"'))

    def test_eq_not_in_scope(self):
        # == is handled by RelationalOperator, not BoundaryOperator
        assert not self.op.can_mutate(expr("x == 5"))

    def test_all_valid_python(self):
        for mutant in all_ops_for("n >= 0", self.op):
            assert is_valid_python(mutant)


# ---------------------------------------------------------------------------
# MutatorRegistry integration
# ---------------------------------------------------------------------------

class TestMutatorRegistry:
    def test_generates_mutants_for_calculator(self):
        """Registry should produce a reasonable number of mutants for calculator.py."""
        from core.operators.arithmetic import ArithmeticOperator
        from core.operators.relational import RelationalOperator
        from core.operators.constant import ConstantOperator

        tree, source = parse_source(DUMMIES / "calculator.py")
        registry = MutatorRegistry([ArithmeticOperator(), RelationalOperator(), ConstantOperator()])
        mutants = list(registry.generate_mutants(tree, "calculator.py", source))

        assert len(mutants) > 5, f"Expected >5 mutants, got {len(mutants)}"

    def test_mutant_ids_are_unique(self):
        tree, source = parse_source(DUMMIES / "calculator.py")
        registry = MutatorRegistry([
            ArithmeticOperator(), RelationalOperator(), BooleanOperator(),
            StatementOperator(), ConstantOperator(), BoundaryOperator(),
        ])
        mutants = list(registry.generate_mutants(tree, "calculator.py", source))
        ids = [m.id for m in mutants]
        assert len(ids) == len(set(ids)), "Duplicate mutant IDs found"

    def test_every_mutant_has_line_number(self):
        tree, source = parse_source(DUMMIES / "calculator.py")
        registry = MutatorRegistry([ArithmeticOperator(), RelationalOperator()])
        for m in registry.generate_mutants(tree, "calculator.py", source):
            assert m.line_number > 0, f"Mutant {m.id} has no line number"

    def test_every_mutant_generates_valid_source(self):
        """generate_source() must produce compilable Python for every mutant."""
        tree, source = parse_source(DUMMIES / "calculator.py")
        registry = MutatorRegistry([
            ArithmeticOperator(), RelationalOperator(), BooleanOperator(),
            StatementOperator(), ConstantOperator(), BoundaryOperator(),
        ])
        for m in registry.generate_mutants(tree, "calculator.py", source):
            src = m.generate_source()
            try:
                compile(src, m.source_file, "exec")
            except SyntaxError as exc:
                pytest.fail(
                    f"Mutant {m.id} produced invalid Python:\n{src}\nError: {exc}"
                )


