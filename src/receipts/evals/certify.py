"""Certification scorecards: a golden-set run pinned to the code it certifies.

A scorecard says "this configuration passes the golden set". Configurations
change silently - a prompt edit, a new fault mode, a dataset fix - so every
scorecard carries a fingerprint of the code that plays and grades the calls,
plus an expiry date. The moment either no longer matches, the scorecard is
STALE and must be re-earned. A standing scorecard would be a lie.

`receipts certify` writes a new scorecard; `receipts certify --check` reports
whether the latest one is still current (exit 1 when stale or missing), which
is the gate CI or a release checklist can enforce.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from receipts import __version__
from receipts.evals.run import by_fault, evaluate
from receipts.evals.score import EvalSummary
from receipts.scenarios import GOLDEN

SCHEMA_VERSION = 1
VALIDITY_DAYS = 90

# The code a scorecard certifies: whatever plays the calls, grades them, and
# defines the dataset. A change to any of these is a different agent.
FINGERPRINT_INPUTS = (
    "src/receipts/scenarios/golden.py",
    "src/receipts/scenarios/world.py",
    "src/receipts/suspect/agent.py",
    "src/receipts/suspect/narrator.py",
    "src/receipts/suspect/faults.py",
    "src/receipts/auditor/engine.py",
    "src/receipts/auditor/verdicts.py",
    "src/receipts/auditor/findings.py",
)

DEFAULT_DIR = Path(__file__).resolve().parents[3] / "evals" / "scorecards"


def repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def fingerprint(root: Path | None = None) -> str:
    """Content hash of the code and dataset being certified."""
    root = root or repo_root()
    h = hashlib.sha256()
    h.update(f"receipts/{__version__}".encode())
    for rel in FINGERPRINT_INPUTS:
        h.update(rel.encode())
        h.update((root / rel).read_bytes())
    return h.hexdigest()


@dataclass(frozen=True)
class Scorecard:
    certified_at: datetime
    expires_at: datetime
    fingerprint: str
    golden: EvalSummary
    faults: tuple[dict[str, Any], ...]

    def status(self, now: datetime, current_fingerprint: str) -> str:
        if self.fingerprint != current_fingerprint:
            return "STALE (configuration changed)"
        if now >= self.expires_at:
            return "STALE (expired)"
        return "CURRENT"

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": SCHEMA_VERSION,
            "certified_at": self.certified_at.isoformat(),
            "expires_at": self.expires_at.isoformat(),
            "fingerprint": self.fingerprint,
            "golden": self.golden.as_dict(),
            "by_fault_mode": list(self.faults),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Scorecard:
        # Fault rows and the summary are display data; the load path exists so
        # --check can read certified_at/expires_at/fingerprint without reruns.
        return cls(
            certified_at=datetime.fromisoformat(data["certified_at"]),
            expires_at=datetime.fromisoformat(data["expires_at"]),
            fingerprint=data["fingerprint"],
            golden=None,  # type: ignore[arg-type]  # not needed for --check
            faults=tuple(data.get("by_fault_mode", ())),
        )


def _diff(previous: dict[str, Any] | None, current: EvalSummary) -> dict[str, Any]:
    """What changed since the last scorecard: the part a reviewer reads first."""
    if previous is None:
        return {"previous": None}
    prev_fail = {f["scenario"] for f in previous["golden"]["failures"]}
    cur_fail = {f["scenario"] for f in current.as_dict()["failures"]}
    return {
        "previous": previous["certified_at"],
        "strict_accuracy": {
            "was": previous["golden"]["call_strict_accuracy"],
            "now": round(current.strict_accuracy, 4),
        },
        "newly_failing": sorted(cur_fail - prev_fail),
        "newly_passing": sorted(prev_fail - cur_fail),
    }


def certify(
    out_dir: Path | None = None, *, now: datetime | None = None, root: Path | None = None
) -> Scorecard:
    """Run the golden set and write the scorecard (JSON + Markdown)."""
    out_dir = out_dir or DEFAULT_DIR
    now = now or datetime.now(UTC)
    summary = evaluate(GOLDEN, label="Receipts")
    faults = tuple(
        {"fault": r.mode.value, "scenarios": r.scenarios, "fully_correct": r.caught}
        for r in by_fault(GOLDEN, summary)
    )
    card = Scorecard(
        certified_at=now,
        expires_at=now + timedelta(days=VALIDITY_DAYS),
        fingerprint=fingerprint(root),
        golden=summary,
        faults=faults,
    )
    out_dir.mkdir(parents=True, exist_ok=True)
    latest_path = out_dir / "latest.json"
    previous = json.loads(latest_path.read_text()) if latest_path.exists() else None
    payload = card.as_dict()
    payload["diff"] = _diff(previous, summary)
    stem = f"{now:%Y%m%d}-{card.fingerprint[:12]}"
    (out_dir / f"{stem}.json").write_text(json.dumps(payload, indent=2) + "\n")
    (out_dir / f"{stem}.md").write_text(render_markdown(card, payload["diff"]))
    (out_dir / "latest.json").write_text(json.dumps(payload, indent=2) + "\n")
    return card


def latest(out_dir: Path | None = None) -> Scorecard | None:
    out_dir = out_dir or DEFAULT_DIR
    path = out_dir / "latest.json"
    if not path.exists():
        return None
    return Scorecard.from_dict(json.loads(path.read_text()))


def check(
    out_dir: Path | None = None, *, now: datetime | None = None, root: Path | None = None
) -> tuple[str, Scorecard | None]:
    """Status of the latest scorecard against the code as it is now."""
    card = latest(out_dir)
    if card is None:
        return "MISSING (no scorecard has ever been written)", None
    now = now or datetime.now(UTC)
    return card.status(now, fingerprint(root)), card


def render_markdown(card: Scorecard, diff: dict[str, Any]) -> str:
    s = card.golden
    lines = [
        "# Certification scorecard",
        "",
        f"- Certified at: {card.certified_at.isoformat()}",
        f"- Expires at: {card.expires_at.isoformat()} ({VALIDITY_DAYS} days, or any change "
        "to the certified code)",
        f"- Fingerprint: `{card.fingerprint[:16]}...` "
        f"({len(FINGERPRINT_INPUTS)} source files + receipts/{__version__})",
        "",
        "| calls | claim F1 | status accuracy | finding F1 | call accuracy | strict |",
        "|---|---|---|---|---|---|",
    ]

    def pct(x: float | None) -> str:
        return "n/a" if x is None else f"{x:.1%}"

    lines.append(
        f"| {s.calls} | {pct(s.claims.f1)} | {pct(s.status_accuracy)} | "
        f"{pct(s.findings.f1)} | {pct(s.call_accuracy)} | {pct(s.strict_accuracy)} |"
    )
    lines += ["", "| fault mode | scenarios | fully correct |", "|---|---|---|"]
    for row in card.faults:
        lines.append(f"| {row['fault']} | {row['scenarios']} | {row['fully_correct']} |")
    if diff.get("previous"):
        lines += [
            "",
            "## Since the last scorecard",
            "",
            f"- Strict accuracy: {diff['strict_accuracy']['was']:.1%} -> "
            f"{diff['strict_accuracy']['now']:.1%}",
            f"- Newly failing: {', '.join(diff['newly_failing']) or 'none'}",
            f"- Newly passing: {', '.join(diff['newly_passing']) or 'none'}",
        ]
    lines.append("")
    return "\n".join(lines)
