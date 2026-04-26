"""Tests for parallel execution (Step 3)."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

from core.mutator import MutatorRegistry
from core.operators.arithmetic import ArithmeticOperator
from core.operators.relational import RelationalOperator
from core.parallel import run_mutants_parallel, default_worker_count
from core.parser import parse_source, build_parent_map
from core.runner import MutantStatus

DUMMIES = Path(__file__).parent / "dummies"


def get_mutants():
    operators = [ArithmeticOperator(), RelationalOperator()]
    tree, source = parse_source(DUMMIES / "calculator.py")
    registry = MutatorRegistry(operators)
    return list(registry.generate_mutants(
        tree, str(DUMMIES / "calculator.py"), source
    ))


@pytest.fixture(scope="session")
def mutants():
    return get_mutants()


@pytest.fixture(scope="session")
def results_single_worker(mutants):
    """Run full suite once with 1 worker — reused by all tests that need it."""
    return run_mutants_parallel(
        mutants,
        [DUMMIES / "test_calculator.py"],
        DUMMIES,
        timeout=30.0,
        workers=1,
    )


@pytest.fixture(scope="session")
def results_multi_worker(mutants):
    """Run full suite once with 2 workers — reused by all tests that need it."""
    return run_mutants_parallel(
        mutants,
        [DUMMIES / "test_calculator.py"],
        DUMMIES,
        timeout=30.0,
        workers=2,
    )


class TestDeterminism:
    def test_same_score_single_vs_multi_worker(self, results_single_worker, results_multi_worker):
        map_1 = {r.mutant.id: r.status for r in results_single_worker}
        map_2 = {r.mutant.id: r.status for r in results_multi_worker}

        assert len(map_1) == len(map_2)

        mismatches = []
        for mid in map_1:
            s1, s2 = map_1[mid], map_2[mid]
            both_detected = (
                s1 in (MutantStatus.KILLED, MutantStatus.TIMEOUT)
                and s2 in (MutantStatus.KILLED, MutantStatus.TIMEOUT)
            )
            if s1 != s2 and not both_detected:
                mismatches.append((mid, s1, s2))

        assert not mismatches, (
            "Status mismatches between 1 and 2 workers:\n"
            + "\n".join(f"  {m[0]}: {m[1].name} vs {m[2].name}" for m in mismatches)
        )

    def test_same_killed_set(self, results_single_worker, results_multi_worker):
        killed_1 = {r.mutant.id for r in results_single_worker if r.status == MutantStatus.KILLED}
        killed_2 = {r.mutant.id for r in results_multi_worker if r.status == MutantStatus.KILLED}

        assert killed_1 == killed_2, (
            f"Only in workers=1: {killed_1 - killed_2}\n"
            f"Only in workers=2: {killed_2 - killed_1}"
        )


class TestCompleteness:
    def test_no_dropped_mutants(self, mutants, results_multi_worker):
        result_ids = {r.mutant.id for r in results_multi_worker}
        mutant_ids = {m.id for m in mutants}
        assert result_ids == mutant_ids, (
            f"Missing: {mutant_ids - result_ids}"
        )

    def test_no_duplicate_results(self, results_multi_worker):
        ids = [r.mutant.id for r in results_multi_worker]
        assert len(ids) == len(set(ids))


class TestOrdering:
    def test_single_worker_sorted(self, results_single_worker):
        ids = [r.mutant.id for r in results_single_worker]
        assert ids == sorted(ids)

    def test_multi_worker_sorted(self, results_multi_worker):
        ids = [r.mutant.id for r in results_multi_worker]
        assert ids == sorted(ids)


class TestProgressCallback:
    def test_callback_called_once_per_mutant(self, mutants):
        calls: list = []
        run_mutants_parallel(
            mutants[:3],  # use only 3 mutants — fast, still proves the contract
            [DUMMIES / "test_calculator.py"],
            DUMMIES,
            timeout=30.0,
            workers=1,
            progress_callback=lambda r, done, total: calls.append(done),
        )
        assert len(calls) == 3

    def test_callback_done_count_increases(self, mutants):
        done_counts: list[int] = []
        run_mutants_parallel(
            mutants[:3],
            [DUMMIES / "test_calculator.py"],
            DUMMIES,
            timeout=30.0,
            workers=1,
            progress_callback=lambda r, done, total: done_counts.append(done),
        )
        assert done_counts == [1, 2, 3]

    def test_callback_total_is_consistent(self, mutants):
        totals: list[int] = []
        run_mutants_parallel(
            mutants[:3],
            [DUMMIES / "test_calculator.py"],
            DUMMIES,
            timeout=30.0,
            workers=1,
            progress_callback=lambda r, done, total: totals.append(total),
        )
        assert all(t == 3 for t in totals)


class TestDefaultWorkerCount:
    def test_returns_at_least_one(self):
        assert default_worker_count() >= 1

    def test_capped_at_four(self):
        assert default_worker_count() <= 4

