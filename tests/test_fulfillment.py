"""Handoff fulfillment: acknowledged is not fulfilled, and missing evidence
never upgrades the state of a promise."""

from __future__ import annotations

from datetime import timedelta

from subpoena.auditor import fulfillment
from subpoena.auditor.render import render_markdown
from subpoena.models import FulfillmentState, HandoffCreated
from subpoena.scenarios.world import CALL_START, ROSTER
from subpoena.sor.base import Coverage, with_coverage, with_outage
from subpoena.suspect import AGENT_ID

CREATED = CALL_START + timedelta(seconds=5)
AUDITED = CALL_START + timedelta(minutes=3)
CALLER = ROSTER[0]


def _ticket(clinic):
    agent = clinic.as_actor(f"{AGENT_ID}:call-test", CREATED)
    return agent.tickets.create_ticket(
        patient_id=clinic.patient(CALLER).id, summary="call back about billing", priority="urgent"
    )


def test_created_ticket_is_recorded_and_pending(clinic) -> None:
    ticket = _ticket(clinic)
    feed = clinic.as_actor("auditor", AUDITED).tickets
    result = fulfillment.assess(ticket, f"{AGENT_ID}:call-test", feed, AUDITED)
    assert result.state is FulfillmentState.RECORDED
    assert result.pending


def test_staff_close_completes_the_promise(clinic) -> None:
    ticket = _ticket(clinic)
    clinic.as_actor("staff:nurse", CREATED + timedelta(minutes=1)).tickets.update_ticket(
        ticket.id, status="closed"
    )
    feed = clinic.as_actor("auditor", AUDITED).tickets
    result = fulfillment.assess(ticket, f"{AGENT_ID}:call-test", feed, AUDITED)
    assert result.state is FulfillmentState.COMPLETED
    assert not result.pending
    assert any("Closed by staff:nurse" in e.note for e in result.evidence)


def test_staff_touch_acknowledges_but_does_not_fulfill(clinic) -> None:
    ticket = _ticket(clinic)
    clinic.as_actor("staff:nurse", CREATED + timedelta(minutes=1)).tickets.update_ticket(
        ticket.id, assignee="nurse-amy"
    )
    feed = clinic.as_actor("auditor", AUDITED).tickets
    result = fulfillment.assess(ticket, f"{AGENT_ID}:call-test", feed, AUDITED)
    assert result.state is FulfillmentState.ACKNOWLEDGED
    assert result.pending


def test_agent_own_later_writes_do_not_acknowledge(clinic) -> None:
    ticket = _ticket(clinic)
    # The same agent identity, on a later call, sets an assignee: that names an
    # owner but is not a human picking the ticket up.
    clinic.as_actor(f"{AGENT_ID}:call-other", CREATED + timedelta(minutes=1)).tickets.update_ticket(
        ticket.id, assignee="nurse-amy"
    )
    feed = clinic.as_actor("auditor", AUDITED).tickets
    result = fulfillment.assess(ticket, f"{AGENT_ID}:call-test", feed, AUDITED)
    assert result.state is FulfillmentState.ASSIGNED
    assert result.pending


def test_unreadable_queue_is_inconclusive(clinic) -> None:
    ticket = _ticket(clinic)
    sor = clinic.as_actor("auditor", AUDITED)
    feed = with_outage(sor, "tickets").tickets
    result = fulfillment.assess(ticket, f"{AGENT_ID}:call-test", feed, AUDITED)
    assert result.state is FulfillmentState.INCONCLUSIVE
    assert not result.pending


def test_incomplete_history_leaves_an_open_promise_inconclusive(clinic) -> None:
    ticket = _ticket(clinic)
    sor = clinic.as_actor("auditor", AUDITED)
    partial = with_coverage(
        sor, "tickets", Coverage(complete=False, detail="cursor expired")
    ).tickets
    result = fulfillment.assess(ticket, f"{AGENT_ID}:call-test", partial, AUDITED)
    assert result.state is FulfillmentState.INCONCLUSIVE
    assert "recorded" in result.summary


def test_incomplete_history_cannot_hide_an_observed_close(clinic) -> None:
    # A gap can hide a row but cannot fabricate one: an observed close still
    # completes the promise.
    ticket = _ticket(clinic)
    clinic.as_actor("staff:nurse", CREATED + timedelta(minutes=1)).tickets.update_ticket(
        ticket.id, status="closed"
    )
    sor = clinic.as_actor("auditor", AUDITED)
    partial = with_coverage(
        sor, "tickets", Coverage(complete=False, detail="cursor expired")
    ).tickets
    result = fulfillment.assess(ticket, f"{AGENT_ID}:call-test", partial, AUDITED)
    assert result.state is FulfillmentState.COMPLETED


def test_audit_report_carries_fulfillment(clinic) -> None:
    _ticket(clinic)
    call = clinic.call(
        claims=[HandoffCreated(claim_id="c1", turn_index=0, patient=CALLER, priority="urgent")]
    )
    report = clinic.audit(call)
    assert len(report.fulfillments) == 1
    result = report.fulfillments[0]
    assert result.state is FulfillmentState.RECORDED
    assert result.pending
    md = render_markdown(report)
    assert "## Handoff fulfillment" in md
    assert "RECORDED (promise pending)" in md


def test_fulfillment_does_not_change_the_outcome(clinic) -> None:
    ticket = _ticket(clinic)
    clinic.as_actor("staff:nurse", CREATED + timedelta(minutes=1)).tickets.update_ticket(
        ticket.id, status="closed"
    )
    call = clinic.call(
        claims=[HandoffCreated(claim_id="c1", turn_index=0, patient=CALLER, priority="urgent")]
    )
    report = clinic.audit(call)
    assert report.outcome.value == "CLEAN"
    assert report.fulfillments[0].state is FulfillmentState.COMPLETED
    assert ticket.id == report.fulfillments[0].ticket_id
