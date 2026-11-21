"""Coverage gaps are first-class output: named systems, affected claims, and
UNVERIFIABLE stays its own state, never a forced pass or fail."""

from __future__ import annotations

from datetime import timedelta

from subpoena.auditor.render import render_markdown
from subpoena.models import HandoffCreated, VerdictStatus
from subpoena.scenarios.world import CALL_START, ROSTER
from subpoena.sor.base import Coverage, with_coverage, with_outage
from subpoena.suspect import AGENT_ID

CALLER = ROSTER[0]
CREATED = CALL_START + timedelta(seconds=5)
AUDITED = CALL_START + timedelta(minutes=3)


def _handoff_call(clinic):
    agent = clinic.as_actor(f"{AGENT_ID}:call-test", CREATED)
    agent.tickets.create_ticket(
        patient_id=clinic.patient(CALLER).id, summary="call back about billing", priority="urgent"
    )
    return clinic.call(
        claims=[HandoffCreated(claim_id="c1", turn_index=0, patient=CALLER, priority="urgent")]
    )


def test_clean_audit_has_no_gaps(clinic) -> None:
    report = clinic.audit(_handoff_call(clinic))
    assert report.coverage_gaps == ()
    assert "## Coverage gaps" not in render_markdown(report)


def test_an_unreadable_system_is_listed_with_its_claims(clinic) -> None:
    sor = clinic.as_actor("auditor", AUDITED)
    report = clinic.audit(_handoff_call(clinic), reader=with_outage(sor, "tickets"))
    (gap,) = report.coverage_gaps
    assert gap.source == "tickets"
    assert gap.kind == "unavailable"
    assert gap.claim_ids == ("c1",)
    assert report.verdicts[0].status is VerdictStatus.UNVERIFIABLE
    md = render_markdown(report)
    assert "## Coverage gaps" in md
    assert "`tickets` (unavailable)" in md
    assert "`c1`" in md


def test_a_partial_history_is_listed_as_incomplete(clinic) -> None:
    sor = clinic.as_actor("auditor", AUDITED)
    reader = with_coverage(sor, "tickets", Coverage(complete=False, detail="cursor expired"))
    report = clinic.audit(_handoff_call(clinic), reader=reader)
    (gap,) = report.coverage_gaps
    assert gap.kind == "incomplete"
    assert gap.detail == "cursor expired"
    assert gap.claim_ids == ("c1",)
    # Downgraded, never forced either way.
    assert report.verdicts[0].status is VerdictStatus.UNVERIFIABLE


def test_a_gap_with_no_dependent_claims_says_so(clinic) -> None:
    sor = clinic.as_actor("auditor", AUDITED)
    reader = with_coverage(sor, "messages", Coverage(complete=False, detail="stale cache"))
    report = clinic.audit(_handoff_call(clinic), reader=reader)
    (gap,) = report.coverage_gaps
    assert gap.source == "messages"
    assert gap.claim_ids == ()
    assert "No claims depended on it." in render_markdown(report)
