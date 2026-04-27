"""
Terminal reporter for MutaGuard tool.

Prints a human-readable summary to stdout after a mutation run.
"""
from __future__ import annotations

import sys

from core.results import MutationReport
from core.runner import MutantResult, MutantStatus

_WIDTH = 52


def _pct(n: int, d: int) -> str:
    """Format n/d as a percentage string"""
    if d == 0:
        return "  0.0%"
    return f"{100 * n / d:5.1f}%"


def print_progress(result: MutantResult, done: int, total: int) -> None:
    """Prints a single-line progress update to stderr (flushes stderr)"""
    icon = {
        MutantStatus.KILLED:   "x",
        MutantStatus.SURVIVED: ".",
        MutantStatus.TIMEOUT:  "T",
        MutantStatus.ERROR:    "!",
    }.get(result.status, "?")

    print(
        f"\r  [{done:>5}/{total}] {icon} {result.mutant.id:<30}",
        end="",
        file=sys.stderr,
        flush=True,
    )
    if done == total:
        print(file=sys.stderr)


def print_summary(report: MutationReport) -> None:
    """Print the full mutation testing summary to stdout."""
    score     = report.mutation_score * 100
    total     = report.total

    print()
    print(f"  MutaGuard Report — {report.source_file}")
    print("  " + "═" * _WIDTH)
    print(f"  Total mutants generated: {total:>6,}")
    print(f"    Killed:                {report.killed:>6,}  ({_pct(report.killed,   total)})")
    print(f"    Survived:              {report.survived:>6,}  ({_pct(report.survived, total)})")
    print(f"    Timeout:               {report.timeout:>6,}  ({_pct(report.timeout,  total)})")
    print(f"    Error:                 {report.error:>6,}  ({_pct(report.error,    total)})")
    print(f"    Equivalent (skipped):  {report.equivalent_count:>6,}  ({_pct(report.equivalent_count, total)})")
    print("  " + "═" * _WIDTH)
    print(f"  Mutation Score: {score:.1f}%  (killed / non-equivalent)")
    print(f"  Elapsed:        {report.elapsed_seconds:.1f}s")
    print()

    _print_operator_breakdown(report)
    _print_surviving_mutants(report)
    _print_equivalent_mutants(report)


def _print_operator_breakdown(report: MutationReport) -> None:
    op_stats = report.operator_stats()
    if not op_stats:
        return

    col = 28
    print(f"  {'Operator':<{col}} {'Total':>6} {'Killed':>7} {'Survived':>9} {'Equiv':>6} {'Score':>7}")
    print("  " + "-" * _WIDTH)

    for name, s in op_stats.items():
        score_str = f"{s.score * 100:.0f}%" if s.score is not None else "N/A"
        print(
            f"  {name:<{col}} {s.total:>6} {s.killed:>7} "
            f"{s.survived:>9} {s.equivalent:>6} {score_str:>7}"
        )
    print()


def _print_surviving_mutants(report: MutationReport) -> None:
    survivors = report.surviving_mutants
    if not survivors:
        print("  All mutants killed. Tests look strong.")
        print()
        return

    limit = 10
    print(f"  Surviving Mutants ({len(survivors)} total"
          + (f", showing first {limit}" if len(survivors) > limit else "")
          + "):")

    for r in survivors[:limit]:
        m = r.mutant
        orig  = _truncate(m.original_node, 18)
        mut   = _truncate(m.mutated_node,  18)
        print(f"    Line {m.line_number:>4}:  {orig:<18}  →  {mut:<18}  [{m.operator}]")

    if len(survivors) > limit:
        print(f"    ... and {len(survivors) - limit} more.")
    print()


def _print_equivalent_mutants(report: MutationReport) -> None:
    pairs = report.equivalent_results
    if not pairs:
        return

    print(f"  Equivalent Mutants Detected ({len(pairs)}):")
    for result, eq in pairs:
        m = result.mutant
        print(f"    Line {m.line_number:>4}:  {_truncate(m.original_node, 20):<20}  "
              f"[{eq.reason.name if eq.reason else 'UNKNOWN'}]  {eq.explanation}")
    print()


def _truncate(s: str, max_len: int) -> str:
    """Truncate a string with ellipsis if it exceeds max_len."""
    if len(s) <= max_len:
        return s
    return s[:max_len - 1] + "…"


