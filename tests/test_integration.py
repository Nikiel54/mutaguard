"""
End-to-end integration tests.

Runs MutaGuard as a full pipeline against the dummy projects.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path
import os

import pytest

from core.equivalent import check_equivalent
from core.mutator import MutatorRegistry
from core.operators.arithmetic import ArithmeticOperator
from core.operators.boundary import BoundaryOperator
from core.operators.constant import ConstantOperator
from core.operators.relational import RelationalOperator
from core.operators.statement import StatementOperator
from core.parallel import run_mutants_parallel
from core.parser import parse_source
from core.results import MutationReport
from core.runner import MutantStatus

DUMMIES = Path(__file__).parent / "dummies"


# --- Helpers -----------------------------------------------------------

def run_pipeline(
    source: Path,
    tests: Path,
    workers: int = 1,
) -> MutationReport:
    """Run the full MutaGuard pipeline and return the report."""
    tree, source_text = parse_source(source)

    operators = [
        ArithmeticOperator(), RelationalOperator(),
        StatementOperator(), ConstantOperator(), BoundaryOperator(),
    ]
    registry = MutatorRegistry(operators)
    mutants  = list(registry.generate_mutants(tree, str(source), source_text))

    results = run_mutants_parallel(
        mutants,
        [tests],
        project_root=DUMMIES,
        timeout=30.0,
        workers=workers,
    )

    equivalent_flags = {
        r.mutant.id: check_equivalent(r.mutant, tree)
        for r in results
        if r.status == MutantStatus.SURVIVED
        and check_equivalent(r.mutant, tree).is_equivalent
    }

    return MutationReport(
        source_file=source.name,
        results=results,
        equivalent_flags=equivalent_flags,
        elapsed_seconds=0.0,
    )


# ---Session fixtures that are computed once, so shared across tests --------------

@pytest.fixture(scope="session")
def sorter_weak_report():
    return run_pipeline(
        DUMMIES / "sorter.py",
        DUMMIES / "test_sorter_weak.py",
    )


@pytest.fixture(scope="session")
def sorter_strong_report():
    return run_pipeline(
        DUMMIES / "sorter.py",
        DUMMIES / "test_sorter_strong.py",
    )


@pytest.fixture(scope="session")
def calculator_report():
    return run_pipeline(
        DUMMIES / "calculator.py",
        DUMMIES / "test_calculator.py",
    )


# ------ Score comparisons -------------------------------------------------

class TestMutationScores:
    def test_strong_tests_outscore_weak_tests(
        self, sorter_weak_report, sorter_strong_report
    ):
        """Strong test suite must produce a meaningfully higher score."""
        weak_score   = sorter_weak_report.mutation_score
        strong_score = sorter_strong_report.mutation_score

        print(f"\n  Weak score:   {weak_score * 100:.1f}%")
        print(f"  Strong score: {strong_score * 100:.1f}%")

        assert strong_score > weak_score, (
            f"Strong tests ({strong_score:.1%}) should outscore "
            f"weak tests ({weak_score:.1%})"
        )

    def test_weak_tests_leave_survivors(self, sorter_weak_report):
        """Weak tests must leave at least some mutants alive."""
        assert sorter_weak_report.survived > 0, (
            "Weak tests killed everything — they are not actually weak"
        )

    def test_calculator_score_reasonable(self, calculator_report):
        """Strong calculator tests should achieve above 50% score."""
        assert calculator_report.mutation_score > 0.5, (
            f"Expected >50%, got {calculator_report.mutation_score:.1%}"
        )

    def test_total_equals_outcomes(self, calculator_report):
        r = calculator_report
        assert r.total == r.killed + r.survived + r.timeout + r.error + r.equivalent_count


# ----- HTML report testing ----------------------------------------------

class TestHtmlReport:
    def test_html_report_created(self, tmp_path, calculator_report):
        from reporting.html import generate_html_report
        from core.parser import parse_source

        source_text = (DUMMIES / "calculator.py").read_text()
        out = tmp_path / "report.html"
        generate_html_report(calculator_report, source_text, out)

        assert out.exists()
        assert out.stat().st_size > 0

    def test_html_contains_score(self, tmp_path, calculator_report):
        from reporting.html import generate_html_report

        source_text = (DUMMIES / "calculator.py").read_text()
        out = tmp_path / "report.html"
        generate_html_report(calculator_report, source_text, out)

        content = out.read_text(encoding="utf-8")
        assert "Mutation Score" in content
        assert calculator_report.source_file in content

    def test_html_contains_operator_breakdown(self, tmp_path, calculator_report):
        from reporting.html import generate_html_report

        source_text = (DUMMIES / "calculator.py").read_text()
        out = tmp_path / "report.html"
        generate_html_report(calculator_report, source_text, out)

        content = out.read_text(encoding="utf-8")
        assert "ArithmeticOperator" in content
        assert "Operator Breakdown" in content

    def test_html_is_valid_structure(self, tmp_path, calculator_report):
        from reporting.html import generate_html_report

        source_text = (DUMMIES / "calculator.py").read_text()
        out = tmp_path / "report.html"
        generate_html_report(calculator_report, source_text, out)

        content = out.read_text(encoding="utf-8")
        assert content.startswith("<!DOCTYPE html>")
        assert "</html>" in content


# ----- CLI ---------------------------------------------------------------

def _cli_env() -> dict:
        """Environment with PYTHONPATH set for subprocess CLI calls."""
        env = os.environ.copy()
        env["PYTHONPATH"] = str(Path(__file__).parent.parent)
        return env


class TestCLI:
    def test_cli_runs_successfully(self, tmp_path):
        """CLI must run end-to-end without crashing."""
        report_path = tmp_path / "report.html"
        result = subprocess.run(
            [
                sys.executable, "cli.py",
                str(DUMMIES / "calculator.py"),
                "--tests", str(DUMMIES / "test_calculator.py"),
                "--workers", "1",
                "--timeout", "30",
                "--report", str(report_path.resolve()),
                "--operators", "arithmetic,relational",
            ],
            capture_output=True,
            text=True,
            cwd=Path(__file__).parent.parent,  # mutaguard root
            env=_cli_env()
        )
        # Exit 0 (all killed) or 1 (some survived) are both acceptable
        assert result.returncode in (0, 1), (
            f"CLI crashed with code {result.returncode}\n"
            f"stderr: {result.stderr[:500]}"
        )

    def test_cli_creates_html_report(self, tmp_path):
        report_path = tmp_path / "report.html"
        subprocess.run(
            [
                sys.executable, "cli.py",
                str(DUMMIES / "calculator.py"),
                "--tests", str(DUMMIES / "test_calculator.py"),
                "--workers", "1",
                "--timeout", "30",
                "--report", str(report_path.resolve()),
                "--operators", "arithmetic",
            ],
            capture_output=True,
            text=True,
            cwd=Path(__file__).parent.parent,
            env=_cli_env(),
        )
        assert report_path.exists()

    def test_cli_missing_source_exits_1(self, tmp_path):
        result = subprocess.run(
            [
                sys.executable, "cli.py",
                "nonexistent.py",
                "--tests", str(DUMMIES / "test_calculator.py"),
            ],
            capture_output=True,
            text=True,
            cwd=Path(__file__).parent.parent,
            env=_cli_env(),
        )
        assert result.returncode == 1
        assert "error" in result.stderr.lower()

    def test_cli_invalid_operator_exits_1(self, tmp_path):
        result = subprocess.run(
            [
                sys.executable, "cli.py",
                str(DUMMIES / "calculator.py"),
                "--tests", str(DUMMIES / "test_calculator.py"),
                "--operators", "invalidoperator",
            ],
            capture_output=True,
            text=True,
            cwd=Path(__file__).parent.parent,
            env=_cli_env(),
        )
        assert result.returncode == 1

    def test_cli_verbose_flag(self, tmp_path):
        """--verbose should produce more output than default."""
        report_path = tmp_path / "report.html"

        default_run = subprocess.run(
            [
                sys.executable, "cli.py",
                str(DUMMIES / "calculator.py"),
                "--tests", str(DUMMIES / "test_calculator.py"),
                "--workers", "1", "--timeout", "30",
                "--report", str(report_path.resolve()),
                "--operators", "arithmetic",
            ],
            capture_output=True, text=True,
            cwd=Path(__file__).parent.parent,
            env=_cli_env(),
        )
        verbose_run = subprocess.run(
            [
                sys.executable, "cli.py",
                str(DUMMIES / "calculator.py"),
                "--tests", str(DUMMIES / "test_calculator.py"),
                "--workers", "1", "--timeout", "30",
                "--report", str(report_path),
                "--operators", "arithmetic",
                "--verbose",
            ],
            capture_output=True, text=True,
            cwd=Path(__file__).parent.parent,
            env=_cli_env(),
        )
        assert len(verbose_run.stderr) > len(default_run.stderr)


