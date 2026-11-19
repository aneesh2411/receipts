"""Eval runner: golden dataset, fuzzed scenarios and the naive baseline."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal

from subpoena.auditor import ClaimExtractor
from subpoena.evals.fuzz import generate
from subpoena.evals.score import EvalSummary, RunScore, score_run, score_run_v2
from subpoena.scenarios import GOLDEN, Scenario, run_scenario
from subpoena.suspect import FaultMode


def evaluate(
    scenarios: Sequence[Scenario],
    *,
    label: str,
    auditor: Literal["subpoena", "naive"] = "receipts",
    extractor: ClaimExtractor | None = None,
    options: Mapping[str, Any] | None = None,
) -> EvalSummary:
    runs: list[RunScore] = []
    for scenario in scenarios:
        report = run_scenario(
            scenario, auditor=auditor, extractor=extractor, options=options
        ).report
        runs.append(
            score_run(scenario.id, scenario.expected_claims, scenario.expected_findings, report)
        )
    return EvalSummary.of(label, runs)


def evaluate_v2(
    scenarios: Sequence[Scenario], *, extractor: ClaimExtractor | None = None
) -> EvalSummary | None:
    """Score the scenarios that carry reviewed identity labels, semantically.

    Returns None when nothing is labelled, so the report can say so instead of
    printing an empty second verdict.
    """
    labelled = [s for s in scenarios if s.expected_claims_v2]
    if not labelled:
        return None
    runs: list[RunScore] = []
    for scenario in labelled:
        report = run_scenario(scenario, extractor=extractor).report
        runs.append(
            score_run_v2(
                scenario.id, scenario.expected_claims_v2, scenario.expected_findings, report
            )
        )
    return EvalSummary.of("Subpoena (v2 semantic pairing)", runs)


@dataclass(frozen=True)
class FaultRow:
    mode: FaultMode
    scenarios: int
    caught: int  # scenarios with this fault where every verdict and finding was right


def by_fault(scenarios: Sequence[Scenario], summary: EvalSummary) -> list[FaultRow]:
    correct = {r.scenario_id: r.strict_correct for r in summary.runs}
    rows = []
    for mode in FaultMode:
        hits = [s for s in scenarios if mode in s.fault_modes]
        rows.append(FaultRow(mode, len(hits), sum(correct[s.id] for s in hits)))
    return rows


@dataclass(frozen=True)
class EvalResult:
    golden: EvalSummary
    baseline: EvalSummary
    fuzz: EvalSummary
    faults: tuple[FaultRow, ...]
    fuzz_seed: int
    ablations: tuple[EvalSummary, ...] = ()
    golden_v2: EvalSummary | None = None
    fuzz_v2: EvalSummary | None = None

    def as_dict(self) -> dict[str, object]:
        return {
            "golden": self.golden.as_dict(),
            "golden_v2_semantic": self.golden_v2.as_dict() if self.golden_v2 else None,
            "baseline_naive_existence_check": self.baseline.as_dict(),
            "ablations": [a.as_dict() for a in self.ablations],
            "fuzz": {**self.fuzz.as_dict(), "seed": self.fuzz_seed},
            "fuzz_v2_semantic": (
                {**self.fuzz_v2.as_dict(), "seed": self.fuzz_seed} if self.fuzz_v2 else None
            ),
            "by_fault_mode": [
                {"fault": r.mode.value, "scenarios": r.scenarios, "fully_correct": r.caught}
                for r in self.faults
            ],
        }


# Each ablation switches off one capability. If the numbers do not drop, that capability
# is not being exercised by the dataset, and the dataset needs more scenarios.
ABLATIONS: dict[str, dict[str, Any]] = {
    "Subpoena without the transcript reader": {"use_transcript": False},
    "Subpoena without policy checks": {"policies": ()},
}


def run_all(
    *, fuzz_n: int = 500, fuzz_seed: int = 7, extractor: ClaimExtractor | None = None
) -> EvalResult:
    golden = evaluate(GOLDEN, label="Subpoena", extractor=extractor)
    baseline = evaluate(GOLDEN, label="Naive existence check", auditor="naive")
    fuzz_scenarios = generate(fuzz_n, fuzz_seed)
    fuzz = evaluate(fuzz_scenarios, label=f"Subpoena on {fuzz_n} fuzzed calls")
    ablations = tuple(
        evaluate(GOLDEN, label=label, options=options) for label, options in ABLATIONS.items()
    )
    return EvalResult(
        golden,
        baseline,
        fuzz,
        tuple(by_fault(GOLDEN, golden)),
        fuzz_seed,
        ablations,
        golden_v2=evaluate_v2(GOLDEN, extractor=extractor),
        fuzz_v2=evaluate_v2(fuzz_scenarios, extractor=extractor),
    )


# ------------------------------- reporting --------------------------------- #


def _pct(x: float | None) -> str:
    if x is None:
        return "n/a"
    return f"{x:.1%}"


def _row(s: EvalSummary) -> str:
    c, f = s.claims, s.findings
    return (
        f"| {s.label} | {s.calls} | {_pct(c.precision)} | {_pct(c.recall)} | {_pct(c.f1)} | "
        f"{_pct(s.status_accuracy)} | {_pct(f.precision)} | {_pct(f.recall)} | "
        f"{_pct(s.call_accuracy)} | {_pct(s.strict_accuracy)} |"
    )


def render_markdown(result: EvalResult) -> str:
    g = result.golden
    known = {s.id: s.known_gap for s in GOLDEN if s.known_gap}
    lines = [
        "# Eval report",
        "",
        "Generated by `subpoena eval`. Deterministic: the same code produces the same numbers.",
        "",
        "## Headline",
        "",
        "| Auditor | Calls | Claim precision | Claim recall | Claim F1 | Exact status | "
        "Finding precision | Finding recall | Call accuracy | Call strict |",
        "|---|---|---|---|---|---|---|---|---|---|",
        _row(g),
        _row(result.fuzz),
        _row(result.baseline),
        *[_row(a) for a in result.ablations],
        "",
    ]
    if result.golden_v2 is not None:
        lines += [
            "## Semantic pairing (v2)",
            "",
            "The headline pairs expected and predicted claims positionally. The v2 scorer",
            "pairs them by reviewed identity labels (which appointment, message or ticket",
            "the expectation is about), one-to-one, so a right verdict on the wrong target",
            "cannot read as correct. v2 is reported beside v1 until it earns the headline;",
            "historical scorecards remain valid as positional-v1 cards.",
            "",
            "| Auditor | Calls | Claim precision | Claim recall | Claim F1 | Exact status | "
            "Finding precision | Finding recall | Call accuracy | Call strict |",
            "|---|---|---|---|---|---|---|---|---|---|",
            _row(result.golden_v2),
            *([_row(result.fuzz_v2)] if result.fuzz_v2 is not None else []),
            "",
        ]
    lines += [
        "- **Claim precision / recall**: flagging false claims (any status other than VERIFIED).",
        "- **Exact status**: the precise verdict (VERIFIED / MISMATCH / NOT_FOUND / UNVERIFIABLE).",
        "- **Finding precision / recall**: unclaimed writes and policy violations.",
        "- **Call accuracy**: did the auditor correctly decide the call needs attention.",
        "- **Call strict**: every verdict and every finding in the call exactly right.",
        "",
        f"Confusion (golden, claim level): TP {g.claims.tp}, FP {g.claims.fp}, "
        f"FN {g.claims.fn}, TN {g.claims.tn}. "
        f"Findings: TP {g.findings.tp}, FP {g.findings.fp}, FN {g.findings.fn}.",
        "",
        "## Coverage by fault mode (golden)",
        "",
        "| Fault mode | Scenarios | Fully correct |",
        "|---|---|---|",
    ]
    lines += [f"| `{r.mode.value}` | {r.scenarios} | {r.caught} |" for r in result.faults]
    lines += ["", "## Failures (golden)", ""]
    if not g.failures:
        lines.append("None.")
    for run in g.failures:
        tag = "known gap" if run.scenario_id in known else "**UNEXPECTED**"
        lines.append(f"- `{run.scenario_id}` ({tag}): {'; '.join(run.problems)}")
        if run.scenario_id in known:
            lines.append(f"  - Why: {known[run.scenario_id]}")
    if result.golden_v2 is not None:
        lines += ["", "## Failures (golden, v2 semantic pairing)", ""]
        if not result.golden_v2.failures:
            lines.append("None.")
        for run in result.golden_v2.failures:
            tag = "known gap" if run.scenario_id in known else "**UNEXPECTED**"
            lines.append(f"- `{run.scenario_id}` ({tag}): {'; '.join(run.problems)}")
    lines += ["", f"## Failures (fuzz, seed {result.fuzz_seed})", ""]
    if not result.fuzz.failures:
        lines.append("None.")
    lines += [f"- `{r.scenario_id}`: {'; '.join(r.problems)}" for r in result.fuzz.failures[:50]]
    lines += ["", "## What the naive baseline gets wrong (golden)", ""]
    lines += [
        f"- `{r.scenario_id}`: {'; '.join(r.problems)}" for r in result.baseline.failures
    ] or ["Nothing."]
    return "\n".join(lines) + "\n"
