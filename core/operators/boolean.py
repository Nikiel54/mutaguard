"""Boolean mutation operator.

Three distinct mutations:
  1. BoolOp:    and → or,  or → and
  2. Constant:  True → False,  False → True
  3. UnaryOp:   not x  →  x
"""
from __future__ import annotations

import ast
import copy

from core.mutator import MutationOperator


class BooleanOperator(MutationOperator):
    '''
    Handles boolean logical mutations
    '''
    def can_mutate(self, node: ast.AST) -> bool:
        if isinstance(node, ast.BoolOp):
            return isinstance(node.op, (ast.And, ast.Or))
        if isinstance(node, ast.Constant) and isinstance(node.value, bool):
            return True
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
            return True
        return False

    def mutate(self, node: ast.AST) -> list[ast.AST]:
        if isinstance(node, ast.BoolOp):
            new = copy.deepcopy(node)
            new.op = ast.Or() if isinstance(node.op, ast.And) else ast.And()
            return [new]

        if isinstance(node, ast.Constant) and isinstance(node.value, bool):
            new = copy.deepcopy(node)
            new.value = not node.value
            return [new]

        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
            return [copy.deepcopy(node.operand)] # returns past the 'not' operator

        return []
