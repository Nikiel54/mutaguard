"""
Parallel mutant execution using multiprocessing.

Worker function is a top-level module function (not a lambda or nested
function) so it can be pickled and sent to worker processes on Windows,
which uses 'spawn' rather than 'fork'.
"""
from __future__ import annotations

import multiprocessing
import os
from pathlib import Path
from typing import Callable

from core.mutator import Mutant
from core.runner import MutantResult, run_mutant


# ---------------------------------------------------------------------------
# Top-level worker — must be at module level to be picklable on Windows
# ---------------------------------------------------------------------------

def _worker(args: tuple) -> MutantResult:
    """Unpack args and run a single mutant. Called inside worker processes."""
    mutant, test_paths, project_root, timeout = args
    return run_mutant(mutant, test_paths, project_root, timeout)


def default_worker_count() -> int:
    """
    Sensible default: half of CPU count, capped at 4 for now.
    """
    MAX_CORES = 4
    cpu = os.cpu_count() or 2
    return max(1, min(cpu // 2, MAX_CORES))


def run_mutants_parallel(
    mutants: list[Mutant],
    test_paths: list[Path],
    project_root: Path,
    timeout: float = 10.0,
    workers: int = default_worker_count(),
    # progress_callback called in main process after each result to print to terminal
    progress_callback: Callable[[MutantResult, int, int], None] | None = None,
) -> list[MutantResult]:
    """
    Run all mutants and return results sorted by mutant ID.

    Results are always sorted by mutant ID regardless of worker count,
    guaranteeing identical output whether run with 1 or 8 workers.
    """
    total = len(mutants)
    if total == 0:
        return []

    workers = max(1, min(workers, total)) # can be modified here based on cpu limitations

    args = [
        (m, test_paths, project_root, timeout)
        for m in mutants
    ]

    results: list[MutantResult] = []

    if workers == 1:
        # Skip multiprocessing overhead entirely for single-worker runs
        for i, arg in enumerate(args, 1):
            result = _worker(arg)
            results.append(result)
            if progress_callback:
                progress_callback(result, i, total)
    else:
        # spawn context for both Windows/Unix
        ctx = multiprocessing.get_context("spawn")
        with ctx.Pool(processes=workers) as pool:
            done = 0
            for result in pool.imap_unordered(_worker, args, chunksize=1):
                done += 1
                results.append(result)
                if progress_callback:
                    progress_callback(result, done, total)

    results.sort(key=lambda r: r.mutant.id)
    return results


