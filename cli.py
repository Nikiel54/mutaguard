"""MutaGuard CLI entry point.

Usage:
    mutaguard source.py --tests tests/test_source.py
    mutaguard source.py --tests tests/ --workers 4 --timeout 15 --report out.html
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="mutaguard",
        description="Mutation testing engine for Python.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument(
        "source",
        type=Path,
        help="Python source file to mutate",
    )
    p.add_argument(
        "--tests",
        type=Path,
        required=True,
        nargs="+",
        metavar="PATH",
        help="Test file(s) or directory to run with pytest",
    )
    p.add_argument(
        "--workers",
        type=int,
        default=None,
        metavar="N",
        help="Number of parallel workers (default: auto)",
    )
    p.add_argument(
        "--timeout",
        type=float,
        default=10.0,
        metavar="SECONDS",
        help="Per-mutant timeout in seconds (default: 10)",
    )
    p.add_argument(
        "--report",
        type=Path,
        default=Path("mutaguard_report.html"),
        metavar="FILE",
        help="Output path for HTML report (default: mutaguard_report.html)",
    )
    p.add_argument(
        "--operators",
        type=str,
        default=None,
        metavar="LIST",
        help=(
            "Comma-separated operator categories to use. "
            "Options: arithmetic, relational, boolean, statement, constant, boundary. "
            "Default: all"
        ),
    )
    p.add_argument(
        "--verbose",
        action="store_true",
        help="Print each mutant result as it completes",
    )
    p.add_argument(
        "--exclude-lines",
        type=str,
        default=None,
        metavar="LINES",
        help="Comma-separated line numbers to skip (e.g. 12,34,56)",
    )
    return p


def resolve_operators(operator_arg: str | None) -> list:
    """Return operator instances based on --operators flag."""
    from core.operators.arithmetic import ArithmeticOperator
    from core.operators.relational import RelationalOperator
    from core.operators.boolean    import BooleanOperator
    from core.operators.statement  import StatementOperator
    from core.operators.constant   import ConstantOperator
    from core.operators.boundary   import BoundaryOperator

    all_operators = {
        "arithmetic": ArithmeticOperator,
        "relational": RelationalOperator,
        "boolean":    BooleanOperator,
        "statement":  StatementOperator,
        "constant":   ConstantOperator,
        "boundary":   BoundaryOperator,
    }

    if operator_arg is None:
        return [cls() for cls in all_operators.values()]

    selected = []
    for name in operator_arg.split(","):
        name = name.strip().lower()
        if name not in all_operators:
            print(
                f"[error] Unknown operator: {name!r}. "
                f"Valid options: {', '.join(all_operators)}",
                file=sys.stderr,
            )
            sys.exit(1)
        selected.append(all_operators[name]())
    return selected


def main(argv: list[str] | None = None) -> int:
    # Force utf-8 stdout/stderr so unicode characters don't crash on Windows
    if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
        sys.stdout.reconfigure(encoding="utf-8")
    if sys.stderr.encoding and sys.stderr.encoding.lower() != "utf-8":
        sys.stderr.reconfigure(encoding="utf-8")
    
    parser = build_parser()
    args   = parser.parse_args(argv)

    source_path: Path      = args.source.resolve()
    test_paths:  list[Path] = [p.resolve() for p in args.tests]
    report_path: Path      = args.report
    timeout:     float     = args.timeout
    verbose:     bool      = args.verbose

    # Validate inputs
    if not source_path.exists():
        print(f"[error] Source file not found: {source_path}", file=sys.stderr)
        return 1
    for tp in test_paths:
        if not tp.exists():
            print(f"[error] Test path not found: {tp}", file=sys.stderr)
            return 1

    # Parse source
    from core.parser import parse_source, build_parent_map
    try:
        tree, source_text = parse_source(source_path)
    except SyntaxError as exc:
        print(f"[error] {exc}", file=sys.stderr)
        return 1

    parent_map = build_parent_map(tree)

    # Excluded lines
    excluded_lines: set[int] = set()
    if args.exclude_lines:
        for part in args.exclude_lines.split(","):
            try:
                excluded_lines.add(int(part.strip()))
            except ValueError:
                print(f"[warn] Ignoring invalid line number: {part!r}", file=sys.stderr)

    # Generate mutants
    from core.mutator import MutatorRegistry
    operators = resolve_operators(args.operators)
    registry  = MutatorRegistry(operators)

    print(f"[mutaguard] Parsing {source_path.name} ...", file=sys.stderr)
    mutants = list(registry.generate_mutants(tree, str(source_path), source_text))

    if excluded_lines:
        before  = len(mutants)
        mutants = [m for m in mutants if m.line_number not in excluded_lines]
        print(
            f"[mutaguard] Excluded {before - len(mutants)} mutants "
            f"on lines: {sorted(excluded_lines)}",
            file=sys.stderr,
        )

    print(
        f"[mutaguard] Generated {len(mutants)} mutants "
        f"across {len(operators)} operator(s)",
        file=sys.stderr,
    )

    if not mutants:
        print("[mutaguard] No mutants generated. Check operator selection.", file=sys.stderr)
        return 0

    # Workers
    from core.parallel import default_worker_count
    workers = args.workers if args.workers is not None else default_worker_count()
    workers = max(1, workers)

    print(
        f"[mutaguard] Running {len(mutants)} mutants | "
        f"workers={workers} | timeout={timeout}s ...",
        file=sys.stderr,
    )

    # Run mutants
    from core.parallel import run_mutants_parallel
    from core.runner   import MutantStatus
    from reporting.terminal import print_progress

    killed_count   = 0
    survived_count = 0
    timeout_count  = 0

    def on_progress(result, done, total):
        nonlocal killed_count, survived_count, timeout_count
        if result.status == MutantStatus.KILLED:
            killed_count += 1
        elif result.status == MutantStatus.SURVIVED:
            survived_count += 1
        elif result.status == MutantStatus.TIMEOUT:
            timeout_count += 1

        if verbose:
            icon = {"KILLED": "x", "SURVIVED": "~", "TIMEOUT": "T", "ERROR": "!"}.get(
                result.status.name, "?"
            )
            print(
                f"  {icon} [{done:>4}/{total}] {result.mutant.id}  "
                f"{result.mutant.original_node!r} -> {result.mutant.mutated_node!r} "
                f"(line {result.mutant.line_number})",
                file=sys.stderr,
            )
        else:
            print(
                f"\r  [{done:>5}/{total}] "
                f"killed={killed_count} survived={survived_count} "
                f"timeout={timeout_count}   ",
                end="",
                file=sys.stderr,
                flush=True,
            )
            if done == total:
                print(file=sys.stderr)

    start_time = time.monotonic()
    results    = run_mutants_parallel(
        mutants=mutants,
        test_paths=test_paths,
        project_root=source_path.parent,
        timeout=timeout,
        workers=workers,
        progress_callback=on_progress,
    )
    elapsed = time.monotonic() - start_time

    # Equivalent detection
    from core.equivalent import check_equivalent
    equivalent_flags = {}
    for result in results:
        if result.status == MutantStatus.SURVIVED:
            eq = check_equivalent(result.mutant, tree)
            if eq.is_equivalent:
                equivalent_flags[result.mutant.id] = eq

    # Build report
    from core.results import MutationReport
    report = MutationReport(
        source_file=source_path.name,
        results=results,
        equivalent_flags=equivalent_flags,
        elapsed_seconds=elapsed,
    )

    # Terminal output
    from reporting.terminal import print_summary
    print_summary(report)

    # HTML report
    from reporting.html import generate_html_report
    generate_html_report(report, source_text, report_path)
    print(f"[mutaguard] HTML report -> {report_path}", file=sys.stderr)

    # Exit 1 if any mutants survived (can be useful for CI)
    return 0 if report.survived == 0 else 1


if __name__ == "__main__":
    sys.exit(main())


