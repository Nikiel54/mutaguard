"""Relational / comparison mutation operator.

Mutations applied to ast.Compare nodes:
    >   →  >=, <
    >=  →  >,  <=
    <   →  <=, >
    <=  →  <,  >=
    ==  →  !=
    !=  →  ==
"""
from __future__ import annotations

import ast
import copy

from core.mutator import MutationOperator

_MUTATIONS: dict[type, list[type]] = {
    ast.Gt:    [ast.GtE, ast.Lt],
    ast.GtE:   [ast.Gt,  ast.LtE],
    ast.Lt:    [ast.LtE, ast.Gt],
    ast.LtE:   [ast.Lt,  ast.GtE],
    ast.Eq:    [ast.NotEq],
    ast.NotEq: [ast.Eq],
}


class RelationalOperator(MutationOperator):
    '''
    Handles mutation in logical comparison operators
    '''
    def can_mutate(self, node: ast.AST) -> bool:
        return (
            isinstance(node, ast.Compare)
            and any(type(op) in _MUTATIONS for op in node.ops)
        )

    def mutate(self, node: ast.AST) -> list[ast.AST]:
        assert isinstance(node, ast.Compare)
        results: list[ast.AST] = []
        
        for idx, op in enumerate(node.ops):
            if type(op) not in _MUTATIONS:
                continue
            for replacement_type in _MUTATIONS[type(op)]:
                new_node = copy.deepcopy(node)
                new_node.ops[idx] = replacement_type()
                results.append(new_node)
        return results
