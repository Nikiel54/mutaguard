"""Arithmetic mutation operator.

Mutations applied to Binary Operator nodes 
are toggled to logical negation equivalent operator.
"""
from __future__ import annotations

import ast
import copy

from core.mutator import MutationOperator


_MUTATIONS: dict[type, list[type]] = {
    ast.Add:      [ast.Sub],
    ast.Sub:      [ast.Add],
    ast.Mult:     [ast.Div],
    ast.Div:      [ast.Mult],
    ast.FloorDiv: [ast.Mult],
    ast.Pow:      [ast.Mult],
    ast.Mod:      [ast.Add],
}


class ArithmeticOperator(MutationOperator):
    '''
    Handles Arithmetic logical mutations
    '''
    def can_mutate(self, node: ast.AST) -> bool:
        return isinstance(node, ast.BinOp) and type(node.op) in _MUTATIONS

    def mutate(self, node: ast.AST) -> list[ast.AST]:
        assert isinstance(node, ast.BinOp)
        results: list[ast.AST] = []

        for replacement_type in _MUTATIONS[type(node.op)]:
            new_node = copy.deepcopy(node)
            new_node.op = replacement_type()
            results.append(new_node)
        return results
