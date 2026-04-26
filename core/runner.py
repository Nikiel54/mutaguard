"""Subprocess-isolated test runner so it doesn't crash main process.

Features:
  1. Creates a fresh temporary directory
  2. Copies the entire project into it
  3. Writes the mutated source over the original file
  4. Runs pytest in a subprocess against the temp copy
  5. Returns a MutantResult with status KILLED / SURVIVED / TIMEOUT / ERROR
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from enum import Enum, auto
from pathlib import Path

from core.mutator import Mutant


class MutantStatus(Enum):
    KILLED   = auto()   # tests failed — mutation was detected
    SURVIVED = auto()   # tests passed — mutation slipped through
    TIMEOUT  = auto()   # subprocess exceeded time limit
    ERROR    = auto()   # mutant source could not compile or run


@dataclass
class MutantResult:
    """The outcome of running the test suite against one mutant."""
    mutant: Mutant
    status: MutantStatus
    duration: float   # for tracking clocked seconds
    output: str = "" # pytest stdout


def run_mutant(
    mutant: Mutant,
    test_paths: list[Path],
    project_root: Path,
    timeout: float = 10.0,
) -> MutantResult:
    """
    Run the test suite against mutant in a fully isolated subprocess.

    Only the mutated file is written to a temp directory. All other project
    files are accessed directly from project_root via PYTHONPATH.
    """
    start = time.monotonic()

    # Verify the mutant compiles before touching the filesystem
    try:
        mutated_source = mutant.generate_source()
        compile(mutated_source, mutant.source_file, "exec")
    except SyntaxError as exc:
        return MutantResult(
            mutant=mutant,
            status=MutantStatus.ERROR,
            duration=time.monotonic() - start,
            output=f"Mutant produced invalid syntax: {exc}",
        )

    with tempfile.TemporaryDirectory(prefix="mutaguard_") as tmp_str:
        tmp_dir = Path(tmp_str)

        # Write only the mutated file — everything else loads from project_root
        _setup_tmp_dir(mutated_source, Path(mutant.source_file), test_paths, project_root, tmp_dir)

        remapped_tests = _remap_test_paths(test_paths, project_root, tmp_dir)

        remapped_tests = _remap_test_paths(test_paths, project_root, tmp_dir)

        status, output = _run_pytest(
            test_paths=remapped_tests,
            cwd=tmp_dir,
            timeout=timeout,
            tmp_dir=tmp_dir,
            project_root=project_root,
        )

    return MutantResult(
        mutant=mutant,
        status=status,
        duration=time.monotonic() - start,
        output=output,
    )



## Internal helpers


def _run_pytest(
    test_paths: list[Path],
    cwd: Path,
    timeout: float,
    tmp_dir: Path,
    project_root: Path,
) -> tuple[MutantStatus, str]:
    """
    Invoke pytest in a subprocess and return (status, output) for the isolated mutant.

    Works across Windows and UNIX/Linux platforms.
    """
    cmd = [
        sys.executable, "-m", "pytest",
        *[str(p) for p in test_paths],
        "--tb=no",
        "-q",
        "--no-header",
        "-x",
    ]

    env = _clean_env(tmp_dir, project_root)

    popen_kwargs: dict = dict(
        cwd=str(cwd),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env,
    )
    if sys.platform == "win32":
        popen_kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        popen_kwargs["start_new_session"] = True

    try:
        with subprocess.Popen(cmd, **popen_kwargs) as proc:
            try:
                stdout, stderr = proc.communicate(timeout=timeout)
                output = (stdout + stderr)[:2000]

                # if non-0 exit code, pytest failed so the bug survived for some reason
                status = MutantStatus.SURVIVED if proc.returncode == 0 else MutantStatus.KILLED
                return status, output

            except subprocess.TimeoutExpired:
                _kill_process_tree(proc)
                proc.wait()
                return MutantStatus.TIMEOUT, f"Timed out after {timeout}s"

    except Exception as exc:
        return MutantStatus.ERROR, f"Subproccess failed creation -" + str(exc)


def _setup_tmp_dir(
    mutated_source: str,
    source_file: Path,
    test_paths: list[Path],
    project_root: Path,
    tmp_dir: Path,
) -> None:
    """
    Write the mutated source and test files into tmp_dir.

    Copy test files where the mutated file lives.

    Everything else (imports, dependencies) resolves via PYTHONPATH pointing
    at project_root, so no further copying is needed.
    """
    try:
        rel_path = source_file.relative_to(project_root)
    except ValueError:
        rel_path = Path(source_file.name)

    dest = tmp_dir / rel_path
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(mutated_source, encoding="utf-8")

    for tp in test_paths:
        tp = tp.resolve()
        if tp.is_file():
            _copy_test_file(tp, project_root, tmp_dir)
        elif tp.is_dir():
            for test_file in tp.rglob("*.py"):
                _copy_test_file(test_file, project_root, tmp_dir)


def _copy_test_file(test_file: Path, project_root: Path, tmp_dir: Path) -> None:
    """Copy a single test file into tmp_dir preserving its relative path."""
    try:
        rel = test_file.relative_to(project_root)
    except ValueError:
        rel = Path(test_file.name)
    dest = tmp_dir / rel
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(test_file, dest)


def _kill_process_tree(proc: subprocess.Popen) -> None:
    """Kill proccess, proc, and all its children. Cross-platform compatible."""
    if sys.platform == "win32":
        subprocess.run(
            ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
            capture_output=True,
        )
    else:
        try:
            os.killpg(os.getpgid(proc.pid), 9)
        except (ProcessLookupError, PermissionError, OSError):
            pass


def _clean_env(tmp_dir: Path, project_root: Path) -> dict[str, str]:
    """
    Return a clean environment for the subprocess.
    """
    env = os.environ.copy()
    env["PYTHONPATH"] = str(tmp_dir) + os.pathsep + str(project_root)

    for key in ("COV_CORE_SOURCE", "COVERAGE_PROCESS_START", "COVERAGE_FILE"):
        env.pop(key, None)

    return env


def _remap_test_paths(
    test_paths: list[Path],
    project_root: Path,
    tmp_dir: Path,
) -> list[Path]:
    """Translate test paths from the real project into tmp_dir."""
    remapped: list[Path] = []
    for tp in test_paths:
        tp = tp.resolve()
        try:
            rel = tp.relative_to(project_root)
            remapped.append(tmp_dir / rel)
        except ValueError:
            remapped.append(tmp_dir / tp.name)
    return remapped

