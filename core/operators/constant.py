"""Constant value mutation operator.

Mutations on ast.Constant nodes:
  0           → 1
  1           → 0
  ""          → "fuzz"
  "non-empty" → ""
"""
from __future__ import annotations

import ast
import copy

from core.mutator import MutationOperator


class ConstantOperator(MutationOperator):
    '''
    Handles mutations in constant/literal values
    '''

    def can_mutate(self, node: ast.AST) -> bool:
        if not isinstance(node, ast.Constant):
            return False
        if isinstance(node.value, bool):
            return False
        if isinstance(node.value, int) and node.value in (0, 1):
            return True
        if isinstance(node.value, str):
            return True
        return False

    def mutate(self, node: ast.AST) -> list[ast.AST]:
        assert isinstance(node, ast.Constant)

        val = node.value

        if isinstance(val, int) and not isinstance(val, bool):
            new = copy.deepcopy(node)
            new.value = 1 if val == 0 else 0
            return [new]

        if isinstance(val, str):
            new = copy.deepcopy(node)
            new.value = "fuzz" if val == "" else ""
            return [new]

        return []


