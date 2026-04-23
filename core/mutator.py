"""Core mutation abstractions for MutaGuard.

Three things live here:

  Mutant          - immutable record of one specific code change.
  MutationOperator - abstract base; each operator category subclasses this.
  MutatorRegistry  - walks the AST, asks every operator "can you mutate this
                     node?", and lazily yields Mutant objects.

Design decisions:
  - Mutants are LAZY: `generate_source()` unparsed on demand so we never hold
    thousands of full source strings in memory at once.
  - The registry skips docstrings (detected via parent map + is_docstring()).
  - Each mutant gets a stable, sortable ID like "ArithmeticOperator_0042".
"""
from __future__ import annotations

import ast
import copy
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Iterator

from core.parser import build_parent_map, is_docstring


# ---------------------------------------------------------------------------
# Mutant dataclass
# ---------------------------------------------------------------------------

@dataclass
class Mutant:
    """One specific mutation of the source file."""
    id: str               # e.g. "ArithmeticOperator_0001"
    operator: str         # class name of the operator that produced this
    original_node: str    # ast.unparse() of the original node  (display)
    mutated_node: str     # ast.unparse() of the replacement    (display)
    source_file: str      # absolute path of the file being mutated
    line_number: int      # line in the *original* source
    column: int           # column offset in the original source

    # Private: held for lazy source generation – not shown in repr
    _mutated_tree: ast.Module = field(repr=False, default=None)

    def generate_source(self) -> str:
        """Unparse the mutated AST into a full source string on demand."""
        return ast.unparse(self._mutated_tree)


# ---------------------------------------------------------------------------
# Operator base class
# ---------------------------------------------------------------------------

class MutationOperator(ABC):
    """Abstract base for all mutation operators."""

    @property
    def name(self) -> str:
        return self.__class__.__name__

    @abstractmethod
    def can_mutate(self, node: ast.AST) -> bool:
        """Return True if this operator applies to *node*."""

    @abstractmethod
    def mutate(self, node: ast.AST) -> list[ast.AST]:
        """Return a list of replacement nodes (fresh copies, not in-place edits)."""


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

class MutatorRegistry:
    """Collects operators and generates all Mutants for a given AST."""

    def __init__(self, operators: list[MutationOperator]) -> None:
        self.operators = operators

    def generate_mutants(
        self,
        tree: ast.Module,
        source_file: str,
        source_text: str,
    ) -> Iterator[Mutant]:
        """Yield every Mutant that any registered operator can produce.

        Traversal order is deterministic (ast.walk is depth-first).
        Docstrings are always skipped.
        """
        parent_map = build_parent_map(tree)
        counters: dict[str, int] = {}

        for node in ast.walk(tree):
            parent = parent_map.get(id(node))

            for operator in self.operators:
                if not operator.can_mutate(node):
                    continue
                if is_docstring(node, parent):
                    continue

                for replacement in operator.mutate(node):
                    op_name = operator.name
                    counters[op_name] = counters.get(op_name, 0) + 1
                    mutant_id = f"{op_name}_{counters[op_name]:04d}"

                    mutated_tree = _replace_node(tree, node, replacement)

                    try:
                        original_src = ast.unparse(node)
                        mutated_src = ast.unparse(replacement)
                    except Exception:
                        original_src = "<unparse-error>"
                        mutated_src = "<unparse-error>"

                    yield Mutant(
                        id=mutant_id,
                        operator=op_name,
                        original_node=original_src,
                        mutated_node=mutated_src,
                        source_file=source_file,
                        line_number=getattr(node, "lineno", 0),
                        column=getattr(node, "col_offset", 0),
                        _mutated_tree=mutated_tree,
                    )


# ---------------------------------------------------------------------------
# Internal helper
# ---------------------------------------------------------------------------

def _replace_node(tree: ast.Module, target: ast.AST, replacement: ast.AST) -> ast.Module:
    """Return a deep-copied tree with exactly *target* replaced by *replacement*.

    Matching is by object identity on the *original* tree; after deepcopy we
    re-walk to find the structurally equivalent position.

    Strategy: deepcopy the tree first, then use a NodeTransformer that matches
    on (lineno, col_offset, type) to find the copy of our target node and swap
    it out. Using identity (id()) on the copy won't work since deepcopy changes
    addresses — we use a positional fingerprint instead.
    """
    target_lineno = getattr(target, "lineno", None)
    target_col = getattr(target, "col_offset", None)
    target_type = type(target)
    # We may have multiple nodes with the same position/type (e.g. chained ops).
    # Use a one-shot flag so only the first match is replaced.
    replaced = [False]

    class _Replacer(ast.NodeTransformer):
        def generic_visit(self, node: ast.AST) -> ast.AST:
            if (
                not replaced[0]
                and type(node) is target_type
                and getattr(node, "lineno", None) == target_lineno
                and getattr(node, "col_offset", None) == target_col
            ):
                replaced[0] = True
                new = copy.deepcopy(replacement)
                if target_lineno is not None:
                    ast.copy_location(new, node)
                ast.fix_missing_locations(new)
                return new
            return super().generic_visit(node)

    tree_copy = copy.deepcopy(tree)
    _Replacer().visit(tree_copy)
    ast.fix_missing_locations(tree_copy)
    return tree_copy
