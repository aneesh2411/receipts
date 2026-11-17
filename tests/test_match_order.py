"""Regression: a vague claim must not take the write a specific claim describes.

From docs/FAILURE_ANALYSIS.md section 4, item 7: matching was greedy in claim
order, so a vague claim could verify against a write and leave the specific
claim - the one that actually contradicts the record - judged NOT_FOUND
instead of MISMATCH.
"""

from __future__ import annotations

from dataclasses import replace

from receipts.models import VerdictStatus
from receipts.scenarios.world import PATEL, Scenario, at, build_world
from receipts.scenarios.world import audit_call, run_suspect
from receipts.suspect import Book

SLOT = at(1, 14, 30)


def _report():
    scenario = Scenario(
        "test-match-order",
        "One booking, two claims for it",
        "x",
        (Book(start=SLOT, provider=PATEL, duration_min=60, confirm=False),),
        (),
    )
    world = build_world(scenario)
    result = run_suspect(scenario, world)
    logged = result.call.claims[0]
    vague = logged.model_copy(update={"claim_id": "vague", "provider": None, "duration_min": None})
    specific = logged.model_copy(update={"claim_id": "specific", "duration_min": 30})
    # Vague first in the log, as a sloppy agent would write it.
    call = result.call.model_copy(update={"claims": (vague, specific)})
    return audit_call(scenario, world, replace(result, call=call))


def test_specific_claim_matches_first():
    report = _report()
    statuses = [v.status for v in report.verdicts]
    # The specific claim (30 min vs the 60 on record) is the real discrepancy:
    # MISMATCH. The vague claim has no write left to corroborate it: NOT_FOUND.
    # Greedy claim-order matching returned [VERIFIED, NOT_FOUND] here.
    assert statuses == [VerdictStatus.NOT_FOUND, VerdictStatus.MISMATCH]


def test_mismatch_mentions_the_duration():
    report = _report()
    mismatch = report.verdicts[1]
    assert mismatch.status == VerdictStatus.MISMATCH
    assert "duration" in mismatch.summary.lower() or any(
        "duration" in (c.detail or "").lower() for c in mismatch.checks
    )
