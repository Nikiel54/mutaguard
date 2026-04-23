"""AST parsing and source mapping for MutaGuard.

Responsibilities:
  - Parse a Python source file into an ast.Module (or raise clearly).
  - Build a parent-node map so operators can ask "what contains this node?"
    (needed to detect docstrings, which are the first Expr in a body).
  - Expose `is_docstring()` so operators can skip them.
  - Provide `unparse()` as a single import point for ast.unparse.
"""
from __future__ import annotations

import ast
from pathlib import Path


def parse_source(source_path: Path) -> tuple[ast.Module, str]:
    """Parse *source_path* and return (ast_tree, raw_source_text).

    Raises:
        FileNotFoundError: path does not exist.
        SyntaxError: source cannot be parsed (message includes line number).
    """
    source_text = source_path.read_text(encoding="utf-8")
    try:
        tree = ast.parse(source_text, filename=str(source_path))
    except SyntaxError as exc:
        raise SyntaxError(
            f"Cannot parse {source_path}: {exc.msg} at line {exc.lineno}"
        ) from exc
    return tree, source_text


def build_parent_map(tree: ast.Module) -> dict[int, ast.AST]:
    """Return {id(child): parent_node} for every node in *tree*.

    Used by the mutator registry to check whether a Constant is a docstring.
    """
    parents: dict[int, ast.AST] = {}
    for parent in ast.walk(tree):
        for child in ast.iter_child_nodes(parent):
            parents[id(child)] = parent
    return parents


def is_docstring(node: ast.AST, parent: ast.AST | None) -> bool:
    """Return True when *node* is the docstring of a function, class, or module.

    A docstring is a `Constant(str)` that is the *value* of the first `Expr`
    statement in a function/class/module body.
    """
    if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
        return False
    if parent is None:
        return False
    if not isinstance(parent, (ast.FunctionDef, ast.AsyncFunctionDef,
                               ast.ClassDef, ast.Module)):
        return False
    body = parent.body
    if body and isinstance(body[0], ast.Expr) and body[0].value is node:
        return True
    return False


def unparse(node: ast.AST) -> str:
    """Convert an AST node back to a source string (Python 3.9+)."""
    return ast.unparse(node)
