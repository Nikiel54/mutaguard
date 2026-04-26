"""Tests for the subprocess runner.

Basically:
  - KILLED outcome: a real mutation caught by a strong test
  - SURVIVED outcome: a mutation not covered by a weak test
  - TIMEOUT outcome: infinite loop is killed within deadline
  - ERROR outcome: mutant with invalid syntax is rejected cleanly
  - Isolation: a mutant calling os._exit() cannot crash MutaGuard
  - Original source is never modified
"""
from __future__ import annotations

import ast
import textwrap
import time
from pathlib import Path

import pytest

from core.mutator import Mutant
from core.runner import MutantResult, MutantStatus, run_mutant

FIXTURES = Path(__file__).parent / "fixtures"


# ---------------------------------------------------------------------------
# Helper: build a Mutant from raw source text without going through registry
# ---------------------------------------------------------------------------

def make_mutant(source_file: Path, mutated_source: str) -> Mutant:
    """Construct a Mutant whose generate_source() returns *mutated_source*."""

    # Subclass to override generate_source cleanly
    class _DirectMutant(Mutant):
        def generate_source(self) -> str:
            return mutated_source

    tree = ast.parse(mutated_source)
    return _DirectMutant(
        id="test_mutant",
        operator="TestOperator",
        original_node="original",
        mutated_node="mutated",
        source_file=str(source_file),
        line_number=1,
        column=0,
        _mutated_tree=tree,
    )


# ---------------------------------------------------------------------------
# KILLED
# ---------------------------------------------------------------------------

class TestKilledOutcome:
    def test_arithmetic_mutation_killed(self):
        """Changing add(a,b): a+b → a-b must be caught by test_calculator."""
        mutated = textwrap.dedent("""\
            def add(a, b):
                return a - b

            def subtract(a, b):
                return a - b

            def divide(a, b):
                if b == 0:
                    raise ValueError("Cannot divide by zero")
                return a / b

            def is_positive(n):
                return n > 0

            def clamp(value, low, high):
                if value < low:
                    return low
                if value > high:
                    return high
                return value
        """)
        mutant = make_mutant(FIXTURES / "calculator.py", mutated)
        result = run_mutant(mutant, [FIXTURES / "test_calculator.py"], FIXTURES, timeout=30.0)
        assert result.status == MutantStatus.KILLED

    def test_relational_mutation_killed(self):
        """Changing is_positive: n>0 → n>=0 must be caught (test checks n==0)."""
        mutated = textwrap.dedent("""\
            def add(a, b):
                return a + b

            def subtract(a, b):
                return a - b

            def divide(a, b):
                if b == 0:
                    raise ValueError("Cannot divide by zero")
                return a / b

            def is_positive(n):
                return n >= 0

            def clamp(value, low, high):
                if value < low:
                    return low
                if value > high:
                    return high
                return value
        """)
        mutant = make_mutant(FIXTURES / "calculator.py", mutated)
        result = run_mutant(mutant, [FIXTURES / "test_calculator.py"], FIXTURES, timeout=30.0)
        assert result.status == MutantStatus.KILLED

    def test_result_has_duration(self):
        """Every result must record how long the run took."""
        mutated = FIXTURES / "calculator.py"
        source = mutated.read_text()
        mutant = make_mutant(mutated, source.replace("a + b", "a - b"))
        result = run_mutant(mutant, [FIXTURES / "test_calculator.py"], FIXTURES, timeout=30.0)
        assert result.duration > 0


# ---------------------------------------------------------------------------
# SURVIVED
# ---------------------------------------------------------------------------

class TestSurvivedOutcome:
    def test_mutation_not_covered_survives(self, tmp_path):
        """A mutation that the test never exercises must survive."""
        src = tmp_path / "mymod.py"
        src.write_text(textwrap.dedent("""\
            def double(x):
                return x * 2

            def triple(x):
                return x * 3
        """))

        # Weak test: only checks double(), never calls triple()
        test = tmp_path / "test_mymod.py"
        test.write_text(textwrap.dedent("""\
            import sys, os
            sys.path.insert(0, os.path.dirname(__file__))
            from mymod import double

            def test_double():
                assert double(4) == 8
        """))

        # Mutate triple() — weak test will never notice
        mutated_src = textwrap.dedent("""\
            def double(x):
                return x * 2

            def triple(x):
                return x * 9
        """)
        mutant = make_mutant(src, mutated_src)
        result = run_mutant(mutant, [test], tmp_path, timeout=30.0)
        assert result.status == MutantStatus.SURVIVED

    def test_survived_result_has_empty_ish_output(self, tmp_path):
        """A passing test run produces minimal output."""
        src = tmp_path / "mod.py"
        src.write_text("def f(): return 1\n")
        test = tmp_path / "test_mod.py"
        test.write_text(textwrap.dedent("""\
            import sys, os
            sys.path.insert(0, os.path.dirname(__file__))
            from mod import f
            def test_f(): assert f() == 1
        """))
        mutant = make_mutant(src, "def f(): return 1\n")
        result = run_mutant(mutant, [test], tmp_path, timeout=30.0)
        assert result.status == MutantStatus.SURVIVED


# ---------------------------------------------------------------------------
# TIMEOUT
# ---------------------------------------------------------------------------

class TestTimeoutOutcome:
    def test_infinite_loop_times_out(self, tmp_path):
        """A mutant with while True must be killed within timeout + small buffer."""
        src = tmp_path / "worker.py"
        src.write_text("def work(): return 42\n")

        test = tmp_path / "test_worker.py"
        test.write_text(textwrap.dedent("""\
            import sys, os
            sys.path.insert(0, os.path.dirname(__file__))
            from worker import work
            def test_work(): work()
        """))

        mutated = "def work():\n    while True: pass\n"
        mutant = make_mutant(src, mutated)

        timeout = 3.0
        t0 = time.monotonic()
        result = run_mutant(mutant, [test], tmp_path, timeout=timeout)
        elapsed = time.monotonic() - t0

        assert result.status == MutantStatus.TIMEOUT
        # Must not hang — should return within timeout + 3s buffer
        assert elapsed < timeout + 3.0, f"Runner took too long: {elapsed:.1f}s"

    def test_timeout_message_in_output(self, tmp_path):
        src = tmp_path / "s.py"
        src.write_text("def f(): pass\n")
        test = tmp_path / "test_s.py"
        test.write_text(textwrap.dedent("""\
            import sys, os
            sys.path.insert(0, os.path.dirname(__file__))
            from s import f
            def test_f(): f()
        """))
        mutant = make_mutant(src, "def f():\n    while True: pass\n")
        result = run_mutant(mutant, [test], tmp_path, timeout=2.0)
        assert "Timed out" in result.output


# ---------------------------------------------------------------------------
# ERROR
# ---------------------------------------------------------------------------

class TestErrorOutcome:
    def test_invalid_syntax_returns_error(self, tmp_path):
        """A mutant that produces unparseable Python must return ERROR cleanly."""
        src = tmp_path / "src.py"
        src.write_text("x = 1\n")
        test = tmp_path / "test_src.py"
        test.write_text("def test_x(): assert True\n")

        class _BrokenMutant(Mutant):
            def generate_source(self) -> str:
                return "def (:\n"  # deliberately invalid

        mutant = _BrokenMutant(
            id="broken", operator="Test",
            original_node="x", mutated_node="(",
            source_file=str(src), line_number=1, column=0,
            _mutated_tree=ast.parse("x = 1"),
        )
        result = run_mutant(mutant, [test], tmp_path, timeout=10.0)
        assert result.status == MutantStatus.ERROR
        assert "syntax" in result.output.lower()


# ---------------------------------------------------------------------------
# Isolation
# ---------------------------------------------------------------------------

class TestIsolation:
    def test_os_exit_does_not_crash_mutaguard(self, tmp_path):
        """A mutant calling os._exit(1) must not kill the MutaGuard process."""
        src = tmp_path / "bomb.py"
        src.write_text("def safe(): return 42\n")

        test = tmp_path / "test_bomb.py"
        test.write_text(textwrap.dedent("""\
            import sys, os
            sys.path.insert(0, os.path.dirname(__file__))
            from bomb import safe
            def test_safe(): safe()
        """))

        mutated = "import os\ndef safe():\n    os._exit(1)\n"
        mutant = make_mutant(src, mutated)

        # If isolation fails this test will itself crash — proving the bug
        result = run_mutant(mutant, [test], tmp_path, timeout=15.0)
        assert result.status in (MutantStatus.KILLED, MutantStatus.ERROR)

    def test_original_file_not_modified(self, tmp_path):
        """The original source file must be byte-for-byte identical after a run."""
        src = tmp_path / "orig.py"
        original_content = "def f(): return 1\n"
        src.write_text(original_content)

        test = tmp_path / "test_orig.py"
        test.write_text(textwrap.dedent("""\
            import sys, os
            sys.path.insert(0, os.path.dirname(__file__))
            from orig import f
            def test_f(): assert f() == 1
        """))

        mutant = make_mutant(src, "def f(): return 99\n")
        run_mutant(mutant, [test], tmp_path, timeout=15.0)

        assert src.read_text() == original_content, "Original file was modified!"

    def test_temp_directory_cleaned_up(self, tmp_path):
        """No temp directories should be left behind after a run."""
        import tempfile
        tmp_root = Path(tempfile.gettempdir())
        before = set(tmp_root.glob("mutaguard_*"))

        src = tmp_path / "m.py"
        src.write_text("def f(): return 1\n")
        test = tmp_path / "test_m.py"
        test.write_text(textwrap.dedent("""\
            import sys, os
            sys.path.insert(0, os.path.dirname(__file__))
            from m import f
            def test_f(): assert f() == 1
        """))
        mutant = make_mutant(src, "def f(): return 2\n")
        run_mutant(mutant, [test], tmp_path, timeout=15.0)

        after = set(tmp_root.glob("mutaguard_*"))
        leaked = after - before
        assert not leaked, f"Temp dirs leaked: {leaked}"
