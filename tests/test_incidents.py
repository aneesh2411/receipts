"""Cross-call incident grouping: strong identity plus request matching, with an
ambiguous-match review path and no merges on a phone number alone."""

from __future__ import annotations

from datetime import timedelta

from subpoena.auditor.incidents import group_incidents
from subpoena.models import (
    CallRecord,
    HandoffCreated,
    IncidentStatus,
    PatientRef,
)
from subpoena.scenarios.world import CALL_START, ROSTER
from subpoena.suspect import AGENT_ID

CALLER = ROSTER[0]
DAY = timedelta(days=1)


def _handoff_report(clinic, call_id, when, summary, caller=CALLER, close=False):
    agent = clinic.as_actor(f"{AGENT_ID}:{call_id}", when + timedelta(seconds=5))
    ticket = agent.tickets.create_ticket(
        patient_id=clinic.patient(CALLER).id, summary=summary, priority="urgent"
    )
    if close:
        clinic.as_actor("staff:nurse", when + timedelta(seconds=90)).tickets.update_ticket(
            ticket.id, status="closed"
        )
    claim = HandoffCreated(
        claim_id="c1", turn_index=0, patient=caller, summary=summary, priority="urgent"
    )
    call = CallRecord(
        call_id=call_id,
        agent_id=AGENT_ID,
        caller=caller,
        started_at=when,
        ended_at=when + timedelta(minutes=2),
        transcript=(),
        claims=(claim,),
    )
    report = clinic.audit(call)
    return report.model_copy(update={"audit_id": f"aud-{call_id}"}), ticket


def test_same_request_across_calls_groups_into_one_incident(clinic) -> None:
    first, _ = _handoff_report(clinic, "call-1", CALL_START, "call back about billing")
    second, _ = _handoff_report(clinic, "call-2", CALL_START + DAY, "call back about billing")
    incidents, reviews = group_incidents([first, second])
    assert len(incidents) == 1
    incident = incidents[0]
    assert incident.repeated_promises == 2
    assert [c.call_id for c in incident.calls] == ["call-1", "call-2"]
    assert incident.request == "a callback about billing"
    assert reviews == ()


def test_duplicate_tickets_are_flagged(clinic) -> None:
    first, ticket1 = _handoff_report(clinic, "call-1", CALL_START, "call back about billing")
    second, ticket2 = _handoff_report(clinic, "call-2", CALL_START + DAY, "call back about billing")
    incidents, _ = group_incidents([first, second])
    duplicates = incidents[0].duplicate_writes
    assert len(duplicates) == 1
    assert duplicates[0].ref == ticket2.id
    assert ticket1.id in duplicates[0].note


def test_a_different_request_from_the_same_caller_stays_separate(clinic) -> None:
    first, _ = _handoff_report(clinic, "call-1", CALL_START, "call back about billing")
    second, _ = _handoff_report(clinic, "call-2", CALL_START + DAY, "call back about billing")
    third, _ = _handoff_report(
        clinic, "call-3", CALL_START + 2 * DAY, "call back about a prescription refill"
    )
    incidents, reviews = group_incidents([first, second, third])
    assert len(incidents) == 1
    assert "call-3" not in [c.call_id for c in incidents[0].calls]
    assert reviews == ()


def test_same_phone_different_names_goes_to_review(clinic) -> None:
    first, _ = _handoff_report(clinic, "call-1", CALL_START, "call back about billing")
    other = PatientRef(name="Robin Banks", phone=CALLER.phone)
    second, _ = _handoff_report(
        clinic, "call-2", CALL_START + DAY, "call back about billing", caller=other
    )
    incidents, reviews = group_incidents([first, second])
    assert incidents == ()
    assert [r.reason for r in reviews] == ["same-phone-different-names"]
    assert set(reviews[0].audits) == {first.audit_id, second.audit_id}


def test_same_name_without_a_phone_goes_to_review(clinic) -> None:
    first, _ = _handoff_report(clinic, "call-1", CALL_START, "call back about billing")
    unverified = PatientRef(name=CALLER.name)
    second, _ = _handoff_report(
        clinic, "call-2", CALL_START + DAY, "call back about billing", caller=unverified
    )
    incidents, reviews = group_incidents([first, second])
    assert incidents == ()
    assert [r.reason for r in reviews] == ["same-name-no-phone"]


def test_ambiguous_handoff_topic_goes_to_review(clinic) -> None:
    first, _ = _handoff_report(clinic, "call-1", CALL_START, "call back about billing")
    second, _ = _handoff_report(
        clinic, "call-2", CALL_START + DAY, "call back about a billing dispute"
    )
    incidents, reviews = group_incidents([first, second])
    assert incidents == ()
    assert [r.reason for r in reviews] == ["ambiguous-handoff-topic"]


def test_incident_is_pending_until_every_linked_handoff_completes(clinic) -> None:
    first, _ = _handoff_report(clinic, "call-1", CALL_START, "call back about billing")
    second, _ = _handoff_report(
        clinic, "call-2", CALL_START + DAY, "call back about billing", close=True
    )
    incidents, _ = group_incidents([first, second])
    assert incidents[0].handoff_status is IncidentStatus.PENDING


def test_incident_is_fulfilled_when_every_linked_handoff_completes(clinic) -> None:
    first, _ = _handoff_report(clinic, "call-1", CALL_START, "call back about billing", close=True)
    second, _ = _handoff_report(
        clinic, "call-2", CALL_START + DAY, "call back about billing", close=True
    )
    incidents, _ = group_incidents([first, second])
    assert incidents[0].handoff_status is IncidentStatus.FULFILLED


def test_grouping_is_deterministic_regardless_of_input_order(clinic) -> None:
    first, _ = _handoff_report(clinic, "call-1", CALL_START, "call back about billing")
    second, _ = _handoff_report(clinic, "call-2", CALL_START + DAY, "call back about billing")
    forward = group_incidents([first, second])
    backward = group_incidents([second, first])
    assert forward == backward


def test_a_single_call_is_not_an_incident(clinic) -> None:
    only, _ = _handoff_report(clinic, "call-1", CALL_START, "call back about billing")
    incidents, reviews = group_incidents([only])
    assert incidents == ()
    assert reviews == ()
