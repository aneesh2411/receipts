#!/usr/bin/env python3
"""Bake the correction-binding walkthrough for GitHub Pages.

Regenerate with `python scripts/export_corrections_demo.py`.
"""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

from subpoena.auditor import RuleBasedExtractor, Sealer
from subpoena.models import AppointmentBooked
from subpoena.scenarios.world import CLINIC, PATEL, Scenario, at, run_scenario
from subpoena.suspect import Book, Correct, FaultMode

DEFAULT_OUT = Path(__file__).resolve().parents[1] / "docs" / "demo" / "data-corrections"
SEALING_KEY = b"subpoena-pages-demo"


def export(out: Path = DEFAULT_OUT) -> None:
    """Run both branches of the same call and save their sealed audits."""
    honored = Scenario(
        id="pages-correction-honored",
        title="Correction honored",
        story="The agent updates the calendar to Tuesday.",
        steps=(Book(at(2, 14, 30), PATEL, confirm=False), Correct(at(1, 14, 30))),
        expected_claims=(),
    )
    stale = replace(
        honored,
        id="pages-correction-stale-write",
        title="Stale write",
        story="The agent confirms Tuesday and leaves Wednesday booked.",
        faults={1: frozenset({FaultMode.STALE_CORRECTION})},
    )
    extractor = RuleBasedExtractor()
    sealer = Sealer(SEALING_KEY)
    cases = []
    for scenario in (honored, stale):
        run = run_scenario(scenario, extractor=extractor, sealer=sealer)
        report = run.report
        (acknowledgment,) = (
            claim
            for claim in extractor.extract(run.result.call, CLINIC)
            if isinstance(claim, AppointmentBooked) and claim.corrects_prior
        )
        cases.append(
            {
                "title": scenario.title,
                "story": scenario.story,
                "acknowledgment": acknowledgment.model_dump(mode="json"),
                "audit": report.model_dump(mode="json"),
            }
        )
    out.mkdir(parents=True, exist_ok=True)
    (out / "cases.json").write_text(
        json.dumps(cases, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    export()
