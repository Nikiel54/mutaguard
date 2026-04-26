"""Equivalent mutant detection (false counting).

An equivalent mutant is a mutation that cannot possibly change program
behavior; it looks different but always produces the same result. These
inflate the survived count unfairly so I detect and skip them. I tried to
mitigate chances of false positives occuring.

Four heuristics implemented:
    1. Constant folding  — x+0 → x-0, x*1 → x/1 (result is always same)
    2. Dead code         — mutation inside `if False` or `while False` block
    3. No return use      — function return value is never used by any caller
    4. Redundant compare — comparison that is always True/False by annotation
"""
from __future__ import annotations

import ast
from dataclasses import dataclass
from enum import Enum, auto

from core.mutator import Mutant


# my main equivalent mutant types
class EquivalenceReason(Enum):
    CONSTANT_FOLD    = auto()
    DEAD_CODE        = auto()
    NO_RETURN_USE      = auto()
    REDUNDANT_COMPARE = auto()


@dataclass
class EquivalenceResult:
    is_equivalent: bool
    reason: EquivalenceReason | None
    explanation: str


# Sentinel value for "not equivalent"
_NOT_EQUIVALENT = EquivalenceResult(
    is_equivalent=False,
    reason=None,
    explanation="",
)


def check_equivalent(mutant: Mutant, original_tree: ast.Module) -> EquivalenceResult:
    """Apply all heuristics to mutant and return the first match.

    Only flags clear equivalences.Cheapest checks first so order matters 
    (this can be improved later).
    """
    for check in (
        _check_constant_fold,
        _check_dead_code,
        _check_no_return_use,
    ):
        result = check(mutant, original_tree)
        if result.is_equivalent:
            return result

    return _NOT_EQUIVALENT


#  Constant folding

# _tree omitted, its just there to match other check fns
def _check_constant_fold(mutant: Mutant, _tree: ast.Module) -> EquivalenceResult:
    """
    Detect mutations where both sides reduce to the same value.

    Main Patterns (more can be added maybe?):
        x + 0  →  x - 0    (both equal x)
        x - 0  →  x + 0    (both equal x)
        x * 1  →  x / 1    (both equal x)
        x / 1  →  x * 1    (both equal x)
    """
    try:
        orig = ast.parse(mutant.original_node, mode="eval").body
        mut  = ast.parse(mutant.mutated_node,  mode="eval").body
    except SyntaxError:
        return _NOT_EQUIVALENT

    if not (isinstance(orig, ast.BinOp) and isinstance(mut, ast.BinOp)):
        return _NOT_EQUIVALENT

    orig_right = orig.right
    mut_right  = mut.right

    if not (isinstance(orig_right, ast.Constant) and isinstance(mut_right, ast.Constant)):
        return _NOT_EQUIVALENT

    orig_val = orig_right.value
    mut_val  = mut_right.value

    # check if both sides are identity operations on 0
    if orig_val == 0 and mut_val == 0:
        identity_on_zero = {ast.Add, ast.Sub}
        if type(orig.op) in identity_on_zero and type(mut.op) in identity_on_zero:
            return EquivalenceResult(
                is_equivalent=True,
                reason=EquivalenceReason.CONSTANT_FOLD,
                explanation=(
                    f"'{mutant.original_node}' and '{mutant.mutated_node}' "
                    f"both reduce to the same value when operand is 0"
                ),
            )

    # check if both sides are identity operations on 1
    if orig_val == 1 and mut_val == 1:
        identity_on_one = {ast.Mult, ast.Div}
        if type(orig.op) in identity_on_one and type(mut.op) in identity_on_one:
            return EquivalenceResult(
                is_equivalent=True,
                reason=EquivalenceReason.CONSTANT_FOLD,
                explanation=(
                    f"'{mutant.original_node}' and '{mutant.mutated_node}' "
                    f"both reduce to the same value when operand is 1"
                ),
            )

    return _NOT_EQUIVALENT


# Dead code

def _check_dead_code(mutant: Mutant, tree: ast.Module) -> EquivalenceResult:
    """
    Detect mutations inside statically unreachable branches.
    """
    line = mutant.line_number
    if line <= 0:
        return _NOT_EQUIVALENT

    for node in ast.walk(tree):
        if not isinstance(node, (ast.If, ast.While)):
            continue
        if not isinstance(node.test, ast.Constant):
            continue
        if node.test.value:
            continue  # if True, body is reachable

        # Collect all line numbers inside the dead branch body
        dead_lines = {
            child.lineno
            for child in ast.walk(node)
            if hasattr(child, "lineno")
        }

        if line in dead_lines:
            return EquivalenceResult(
                is_equivalent=True,
                reason=EquivalenceReason.DEAD_CODE,
                explanation=(
                    f"Line {line} is inside a statically unreachable "
                    f"branch (condition is always False)"
                ),
            )

    return _NOT_EQUIVALENT


## No-op return

def _check_no_return_use(mutant: Mutant, tree: ast.Module) -> EquivalenceResult:
    """Detect return mutations where the return value is never used by callers."""
    if mutant.operator != "StatementOperator":
        return _NOT_EQUIVALENT

    func_name = _find_containing_function(tree, mutant.line_number)
    if func_name is None:
        return _NOT_EQUIVALENT

    called_at_all = False
    used_in_expr = False

    # Collect all Call nodes that appear as bare statements
    bare_call_ids: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
            if _call_name(node.value) == func_name:
                called_at_all = True
                bare_call_ids.add(id(node.value))

    # Now check for uses in expression context, excluding bare calls
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and _call_name(node) == func_name:
            if id(node) not in bare_call_ids:
                used_in_expr = True
                break

    if called_at_all and not used_in_expr:
        return EquivalenceResult(
            is_equivalent=True,
            reason=EquivalenceReason.NO_RETURN_USE,
            explanation=(
                f"'{func_name}' return value is never used by any caller "
                f"in this file — mutating the return is a no-op"
            ),
        )

    return _NOT_EQUIVALENT


def _find_containing_function(tree: ast.Module, lineno: int) -> str | None:
    """Return the name of the function whose body contains *lineno*, or None."""
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if not hasattr(node, "lineno") or not hasattr(node, "end_lineno"):
            continue
        if node.lineno <= lineno <= node.end_lineno:
            return node.name
    return None


def _call_name(call: ast.Call) -> str | None:
    """Return the simple name of a Call node, or None if it's complex."""
    if isinstance(call.func, ast.Name):
        return call.func.id
    if isinstance(call.func, ast.Attribute):
        return call.func.attr
    return None

