"""Statement-level mutation operator.

Three mutations:
  1. Return(value=X)  →  Return(value=None)
  2. Break            →  Pass                 
  3. Continue         →  Pass              

Never deletes control flow keywords like return, as that just is a syntax error and crashes.
"""
from __future__ import annotations

import ast
import copy

from core.mutator import MutationOperator


class StatementOperator(MutationOperator):
    '''
    Handles logical mutations on control flow statements
    '''
    def can_mutate(self, node: ast.AST) -> bool:
        if isinstance(node, ast.Return) and node.value is not None:
            return True
        if isinstance(node, (ast.Break, ast.Continue)):
            return True
        return False

    def mutate(self, node: ast.AST) -> list[ast.AST]:
        if isinstance(node, ast.Return):
            new = copy.deepcopy(node)
            new.value = ast.Constant(value=None)
            return [new]

        if isinstance(node, ast.Break):
            return [ast.Pass()]

        if isinstance(node, ast.Continue):
            return [ast.Pass()]

        return []
