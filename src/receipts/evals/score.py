"""Scoring an auditor against labelled scenarios.

Three levels, because they answer different questions:

* **Claim level**: of the claims the auditor flagged, how many were really false
  (precision), and of the false claims, how many did it flag (recall)? "Flagged"
  means any status other than VERIFIED.
* **Finding level**: the same, for discrepancies that are not tied to a claim
  (unclaimed writes, policy violations).
* **Call level**: did the auditor correctly decide whether the call needs a
  human to look at it? And, strictly, did it get every verdict and finding right?
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass, field

from receipts.models import AuditReport, Outcome, VerdictStatus

Expected = tuple[str, VerdictStatus]


@dataclass(frozen=True)
class Counts:
    tp: int = 0
    fp: int = 0
    fn: int = 0
    tn: int = 0

    def __add__(self, other: Counts) -> Counts:
        return Counts(
            self.tp + other.tp, self.fp + other.fp, self.fn + other.fn, self.tn + other.tn
        )

    @property
    def precision(self) -> float | None:
        """None when undefined (nothing predicted): 100% would be a lie."""
        return self.tp / (self.tp + self.fp) if self.tp + self.fp else None

    @property
    def recall(self) -> float | None:
        """None when undefined (nothing to find)."""
        return self.tp / (self.tp + self.fn) if self.tp + self.fn else None

    @property
    def f1(self) -> float | None:
        p, r = self.precision, self.recall
        if p is None or r is None:
            return None
        return 2 * p * r / (p + r) if p + r else 0.0


@dataclass(frozen=True)
class RunScore:
    scenario_id: str
    claims: Counts
    findings: Counts
    status_correct: int
    status_total: int
    expected_dirty: bool
    predicted_dirty: bool
    problems: tuple[str, ...] = ()

    @property
    def call_correct(self) -> bool:
        return self.expected_dirty == self.predicted_dirty

    @property
    def strict_correct(self) -> bool:
        return not self.problems


def _flagged(status: VerdictStatus) -> bool:
    return status is not VerdictStatus.VERIFIED


def _score_claims(
    expected: Sequence[Expected], predicted: Sequence[Expected]
) -> tuple[Counts, int, int, list[str]]:
    """Align claims by type and order, then compare statuses.

    A false claim the auditor never saw counts as a miss. A claim the auditor
    invented and flagged counts as a false alarm.
    """
    counts, correct, total, problems = Counts(), 0, 0, []
    for claim_type in sorted({t for t, _ in (*expected, *predicted)}):
        want = [s for t, s in expected if t == claim_type]
        got = [s for t, s in predicted if t == claim_type]
        for i in range(max(len(want), len(got))):
            w = want[i] if i < len(want) else None
            g = got[i] if i < len(got) else None
            if w is not None:
                total += 1
            if w is not None and g is not None:
                correct += w is g
                counts += Counts(
                    tp=_flagged(w) and _flagged(g),
                    fp=not _flagged(w) and _flagged(g),
                    fn=_flagged(w) and not _flagged(g),
                    tn=not _flagged(w) and not _flagged(g),
                )
                if w is not g:
                    problems.append(f"{claim_type}[{i}]: expected {w.value}, got {g.value}")
            elif w is not None:
                counts += Counts(fn=1) if _flagged(w) else Counts()
                problems.append(f"{claim_type}[{i}]: expected {w.value}, auditor saw no claim")
            elif g is not None:
                counts += Counts(fp=1) if _flagged(g) else Counts()
                problems.append(f"{claim_type}[{i}]: unexpected claim judged {g.value}")
    return counts, correct, total, problems


def _score_findings(expected: Sequence[str], predicted: Sequence[str]) -> tuple[Counts, list[str]]:
    """Match findings by code: a wrong unclaimed write is not a correct one."""
    want, got = Counter(expected), Counter(predicted)
    counts, problems = Counts(), []
    for code in sorted(set(want) | set(got)):
        tp = min(want[code], got[code])
        counts += Counts(tp=tp, fp=got[code] - tp, fn=want[code] - tp)
        if want[code] != got[code]:
            problems.append(f"{code}: expected {want[code]}, got {got[code]}")
    return counts, problems


def score_run(
    scenario_id: str,
    expected_claims: Sequence[Expected],
    expected_findings: Sequence[str],
    report: AuditReport,
) -> RunScore:
    predicted = [(v.claim.type, v.status) for v in report.verdicts]
    claims, correct, total, claim_problems = _score_claims(expected_claims, predicted)
    findings, finding_problems = _score_findings(
        expected_findings, [f.code for f in report.findings]
    )
    expected_dirty = bool(expected_findings) or any(_flagged(s) for _, s in expected_claims)
    return RunScore(
        scenario_id=scenario_id,
        claims=claims,
        findings=findings,
        status_correct=correct,
        status_total=total,
        expected_dirty=expected_dirty,
        predicted_dirty=report.outcome is not Outcome.CLEAN,
        problems=(*claim_problems, *finding_problems),
    )


@dataclass(frozen=True)
class EvalSummary:
    label: str
    runs: tuple[RunScore, ...]
    claims: Counts = field(default_factory=Counts)
    findings: Counts = field(default_factory=Counts)

    @classmethod
    def of(cls, label: str, runs: Sequence[RunScore]) -> EvalSummary:
        claims, findings = Counts(), Counts()
        for run in runs:
            claims, findings = claims + run.claims, findings + run.findings
        return cls(label=label, runs=tuple(runs), claims=claims, findings=findings)

    @property
    def calls(self) -> int:
        return len(self.runs)

    @property
    def call_accuracy(self) -> float:
        return sum(r.call_correct for r in self.runs) / self.calls if self.calls else 1.0

    @property
    def strict_accuracy(self) -> float:
        return sum(r.strict_correct for r in self.runs) / self.calls if self.calls else 1.0

    @property
    def status_accuracy(self) -> float:
        total = sum(r.status_total for r in self.runs)
        return sum(r.status_correct for r in self.runs) / total if total else 1.0

    @property
    def failures(self) -> tuple[RunScore, ...]:
        return tuple(r for r in self.runs if not r.strict_correct)

    def as_dict(self) -> dict[str, object]:
        def counts(c: Counts) -> dict[str, float | None]:
            def rnd(x: float | None) -> float | None:
                return round(x, 4) if x is not None else None

            return {
                "tp": c.tp, "fp": c.fp, "fn": c.fn, "tn": c.tn,
                "precision": rnd(c.precision),
                "recall": rnd(c.recall),
                "f1": rnd(c.f1),
            }  # fmt: skip

        return {
            "label": self.label,
            "calls": self.calls,
            "claim_level": counts(self.claims),
            "claim_status_accuracy": round(self.status_accuracy, 4),
            "finding_level": counts(self.findings),
            "call_accuracy": round(self.call_accuracy, 4),
            "call_strict_accuracy": round(self.strict_accuracy, 4),
            "failures": [
                {"scenario": r.scenario_id, "problems": list(r.problems)} for r in self.failures
            ],
        }
