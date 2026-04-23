"""Boundary condition mutation operator.

For comparisons of the form  `x OP n`  where n is a numeric constant and
OP is one of <, <=, >, >=, generate two mutants:
    x OP (n + 1)
    x OP (n - 1)

Aims to catch one off bugs
"""
from __future__ import annotations

import ast
import copy

from core.mutator import MutationOperator

_BOUNDARY_OPS = (ast.Lt, ast.LtE, ast.Gt, ast.GtE)


def _is_numeric(node: ast.AST) -> bool:
    return (
        isinstance(node, ast.Constant)
        and isinstance(node.value, (int, float))
        and not isinstance(node.value, bool)
    )


class BoundaryOperator(MutationOperator):
    '''
    Handles boundary operators and its mutations
    '''
    def can_mutate(self, node: ast.AST) -> bool:
        if not isinstance(node, ast.Compare):
            return False
        if not any(isinstance(op, _BOUNDARY_OPS) for op in node.ops):
            return False
        return any(_is_numeric(c) for c in node.comparators)

    def mutate(self, node: ast.AST) -> list[ast.AST]:
        assert isinstance(node, ast.Compare)
        results: list[ast.AST] = []

        for idx, (op, comparator) in enumerate(zip(node.ops, node.comparators)):
            if not isinstance(op, _BOUNDARY_OPS):
                continue
            if not _is_numeric(comparator):
                continue
            val = comparator.value
            for delta in (+1, -1):
                new_node = copy.deepcopy(node)
                new_comparator = ast.Constant(value=val + delta)
                ast.copy_location(new_comparator, comparator)
                new_node.comparators[idx] = new_comparator
                results.append(new_node)

        return results
