"""
Result aggregation and statistics.

Takes a list of MutantResults and equivalent flags, and computes
counts, score, operator breakdown, surviving mutants list for reporting.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from core.equivalent import EquivalenceResult
from core.runner import MutantResult, MutantStatus


@dataclass
class OperatorStats:
    """Per-operator breakdown of mutant outcomes."""
    name: str
    total: int = 0
    killed: int = 0
    survived: int = 0
    timeout: int = 0
    equivalent: int = 0
    error: int = 0

    @property
    def score(self) -> float | None:
        """Operator-level mutation score, or None if no testable mutants."""
        denominator = self.total - self.equivalent - self.error
        if denominator <= 0:
            return None
        return self.killed / denominator


@dataclass
class MutationReport:
    """Aggregated results from a full mutation testing run."""
    source_file: str
    results: list[MutantResult]
    equivalent_flags: dict[str, EquivalenceResult] = field(default_factory=dict)
    elapsed_seconds: float = 0.0

    #### Counts #####
    @property
    def total(self) -> int:
        return len(self.results)

    @property
    def killed(self) -> int:
        return sum(
            1 for r in self.results
            if r.status == MutantStatus.KILLED
            and r.mutant.id not in self.equivalent_flags
        )

    @property
    def survived(self) -> int:
        return sum(
            1 for r in self.results
            if r.status == MutantStatus.SURVIVED
            and r.mutant.id not in self.equivalent_flags
        )

    @property
    def timeout(self) -> int:
        return sum(
            1 for r in self.results
            if r.status == MutantStatus.TIMEOUT
            and r.mutant.id not in self.equivalent_flags
        )

    @property
    def error(self) -> int:
        return sum(
            1 for r in self.results
            if r.status == MutantStatus.ERROR
            and r.mutant.id not in self.equivalent_flags
        )

    @property
    def equivalent_count(self) -> int:
        return len(self.equivalent_flags)


    #### Scores #####
    @property
    def mutation_score(self) -> float:
        """killed / (total - equivalent - error)

        Equivalent and errored mutants are excluded from the denominator
        since they cannot meaningfully be killed or survived.
        """
        denominator = self.total - self.equivalent_count - self.error
        if denominator <= 0:
            return 0.0
        return self.killed / denominator


    @property
    def surviving_mutants(self) -> list[MutantResult]:
        """Results where the mutant survived and is not equivalent."""
        return [
            r for r in self.results
            if r.status == MutantStatus.SURVIVED
            and r.mutant.id not in self.equivalent_flags
        ]

    @property
    def equivalent_results(self) -> list[tuple[MutantResult, EquivalenceResult]]:
        """Pairs of (result, equivalence_info) for all equivalent mutants."""
        pairs = []
        for r in self.results:
            if r.mutant.id in self.equivalent_flags:
                pairs.append((r, self.equivalent_flags[r.mutant.id]))
        return pairs

    def operator_stats(self) -> dict[str, OperatorStats]:
        """Per-operator breakdown, sorted by operator name."""
        stats: dict[str, OperatorStats] = {}

        for result in self.results:
            op = result.mutant.operator
            if op not in stats:
                stats[op] = OperatorStats(name=op)
            s = stats[op]
            s.total += 1

            mid = result.mutant.id
            if mid in self.equivalent_flags:
                s.equivalent += 1
                continue

            match result.status:
                case MutantStatus.KILLED:
                    s.killed += 1
                case MutantStatus.SURVIVED:
                    s.survived += 1
                case MutantStatus.TIMEOUT:
                    s.timeout += 1
                case MutantStatus.ERROR:
                    s.error += 1

        return dict(sorted(stats.items()))
    

