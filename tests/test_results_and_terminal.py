"""Integration tests for results aggregation and terminal reporting.

Tests the full pipeline:
  parser → mutator → runner → equivalent detection → results → terminal output

Uses calculator.py as the subject so we have a known, predictable baseline.
"""
from __future__ import annotations

import io
from pathlib import Path
from unittest.mock import patch

import pytest

from core.equivalent import check_equivalent
from core.mutator import MutatorRegistry
from core.operators.arithmetic import ArithmeticOperator
from core.operators.boolean import BooleanOperator
from core.operators.boundary import BoundaryOperator
from core.operators.constant import ConstantOperator
from core.operators.relational import RelationalOperator
from core.operators.statement import StatementOperator
from core.parallel import run_mutants_parallel
from core.parser import build_parent_map, parse_source
from core.results import MutationReport, OperatorStats
from core.runner import MutantResult, MutantStatus
from reporting.terminal import print_summary, _pct, _truncate


DUMMIES = Path(__file__).parent / "dummies"


# run the full pipeline once, reuse across all tests

@pytest.fixture(scope="session")
def full_report() -> MutationReport:
    """Run all operators against calculator.py and return the report."""
    source_path = DUMMIES / "calculator.py"
    test_paths  = [DUMMIES / "test_calculator.py"]

    tree, source = parse_source(source_path)
    parent_map   = build_parent_map(tree)

    operators = [
        ArithmeticOperator(), RelationalOperator(), BooleanOperator(),
        StatementOperator(),  ConstantOperator(),   BoundaryOperator(),
    ]
    registry = MutatorRegistry(operators)
    mutants  = list(registry.generate_mutants(tree, str(source_path), source))

    results = run_mutants_parallel(
        mutants,
        test_paths,
        project_root=DUMMIES,
        timeout=30.0,
        workers=1,
    )

    equivalent_flags = {
        r.mutant.id: check_equivalent(r.mutant, tree)
        for r in results
        if r.status == MutantStatus.SURVIVED
        and check_equivalent(r.mutant, tree).is_equivalent
    }

    return MutationReport(
        source_file=source_path.name,
        results=results,
        equivalent_flags=equivalent_flags,
        elapsed_seconds=1.0,
    )


# MutationReport — counts and score

class TestMutationReport:
    def test_total_equals_sum_of_outcomes(self, full_report):
        r = full_report
        assert r.total == r.killed + r.survived + r.timeout + r.error + r.equivalent_count

    def test_mutation_score_between_0_and_1(self, full_report):
        assert 0.0 <= full_report.mutation_score <= 1.0

    def test_strong_tests_produce_high_score(self, full_report):
        """test_calculator.py is a strong suite — score should be above 50%."""
        assert full_report.mutation_score > 0.5, (
            f"Expected score > 50%, got {full_report.mutation_score * 100:.1f}%"
        )

    def test_score_formula_excludes_equivalent(self, full_report):
        """Score denominator must exclude equivalent and errored mutants."""
        r = full_report
        denominator = r.total - r.equivalent_count - r.error
        if denominator > 0:
            expected = r.killed / denominator
            assert abs(r.mutation_score - expected) < 1e-9

    def test_surviving_mutants_are_not_equivalent(self, full_report):
        for result in full_report.surviving_mutants:
            assert result.mutant.id not in full_report.equivalent_flags

    def test_equivalent_results_pairs_correct(self, full_report):
        for result, eq_info in full_report.equivalent_results:
            assert result.mutant.id in full_report.equivalent_flags
            assert eq_info.is_equivalent

    def test_operator_stats_total_matches_results(self, full_report):
        op_stats = full_report.operator_stats()
        stats_total = sum(s.total for s in op_stats.values())
        assert stats_total == full_report.total


## OperatorStats

class TestOperatorStats:
    def test_all_operators_present(self, full_report):
        """Only operators that produced at least one mutant appear in stats."""
        op_stats = full_report.operator_stats()
        # BooleanOperator produces no mutants for calculator.py
        # (no and/or/not/True/False in the source) so it won't appear
        expected = {
            "ArithmeticOperator", "RelationalOperator",
            "StatementOperator", "ConstantOperator", "BoundaryOperator",
        }
        assert expected.issubset(set(op_stats.keys())), (
            f"Missing operators: {expected - set(op_stats.keys())}"
        )

    def test_operator_score_between_0_and_1(self, full_report):
        for name, s in full_report.operator_stats().items():
            if s.score is not None:
                assert 0.0 <= s.score <= 1.0, f"{name} score out of range"

    def test_operator_stats_sorted_alphabetically(self, full_report):
        keys = list(full_report.operator_stats().keys())
        assert keys == sorted(keys)


# Terminal reporter output

class TestTerminalReporter:
    def _capture_summary(self, report: MutationReport) -> str:
        """Capture stdout from print_summary into a string."""
        buf = io.StringIO()
        with patch("sys.stdout", buf):
            print_summary(report)
        return buf.getvalue()

    def test_summary_contains_source_file(self, full_report):
        output = self._capture_summary(full_report)
        assert full_report.source_file in output

    def test_summary_contains_mutation_score(self, full_report):
        output = self._capture_summary(full_report)
        assert "Mutation Score" in output
        score_str = f"{full_report.mutation_score * 100:.1f}%"
        assert score_str in output

    def test_summary_contains_all_count_labels(self, full_report):
        output = self._capture_summary(full_report)
        for label in ("Killed", "Survived", "Timeout", "Equivalent", "Total"):
            assert label in output, f"Missing label: {label}"

    def test_summary_contains_operator_breakdown(self, full_report):
        output = self._capture_summary(full_report)
        assert "ArithmeticOperator" in output
        assert "RelationalOperator" in output

    def test_summary_shows_surviving_mutants(self, full_report):
        output = self._capture_summary(full_report)
        if full_report.surviving_mutants:
            assert "Surviving Mutants" in output
        else:
            assert "All mutants killed" in output

    def test_summary_elapsed_time_present(self, full_report):
        output = self._capture_summary(full_report)
        assert "Elapsed" in output

    def test_no_surviving_mutants_shows_celebration(self):
        """If no mutants survive, show the celebration message."""
        # Build a report with all mutants killed
        from core.mutator import Mutant
        import ast

        class _FM(Mutant):
            def generate_source(self): return ""

        fake_mutant = _FM(
            id="fake_001", operator="ArithmeticOperator",
            original_node="a + b", mutated_node="a - b",
            source_file="fake.py", line_number=1, column=0,
            _mutated_tree=ast.parse("x = 1"),
        )
        fake_result = MutantResult(
            mutant=fake_mutant,
            status=MutantStatus.KILLED,
            duration=0.1,
        )
        report = MutationReport(
            source_file="fake.py",
            results=[fake_result],
            equivalent_flags={},
            elapsed_seconds=0.1,
        )
        buf = io.StringIO()
        with patch("sys.stdout", buf):
            print_summary(report)
        assert "All mutants killed" in buf.getvalue()



## Helper tests

class TestHelpers:
    def test_pct_zero_denominator(self):
        assert _pct(0, 0) == "  0.0%"

    def test_pct_full(self):
        assert _pct(10, 10) == "100.0%"

    def test_pct_half(self):
        assert _pct(5, 10) == " 50.0%"

    def test_truncate_short_string(self):
        assert _truncate("hello", 10) == "hello"

    def test_truncate_exact_length(self):
        assert _truncate("hello", 5) == "hello"

    def test_truncate_long_string(self):
        result = _truncate("hello world", 8)
        assert len(result) == 8
        assert result.endswith("…")


