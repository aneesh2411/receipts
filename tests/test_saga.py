"""The digest's three-call callback incident, played against one clinic:

call 1 promises a billing callback and files a ticket; nobody acts. Call 2
repeats the promise and files a duplicate ticket. Call 3 promises again, files
nothing (caught as a phantom), and staff finally close both tickets; the same
caller's separate prescription request stays out of the incident.
"""

from __future__ import annotations

from subpoena.models import IncidentStatus, VerdictStatus
from subpoena.scenarios.world import (
    CALL_START,
    MAYA,
    Followup,
    SagaCall,
    Scenario,
    at,
    run_saga,
)
from subpoena.suspect import FaultMode, Handoff


def _call_scenario(
    id: str,
    summary: str,
    *,
    faults=None,
    followups=(),
    audit_delay_min=1,
    extra_steps=(),
) -> Scenario:
    steps = (Handoff(reason=summary, priority="urgent"), *extra_steps)
    expected = [("HandoffCreated", VerdictStatus.VERIFIED)] * (1 + len(extra_steps))
    if faults:
        expected[0] = ("HandoffCreated", VerdictStatus.NOT_FOUND)
    return Scenario(
        id=id,
        title=id,
        story="saga test call",
        steps=steps,
        expected_claims=tuple(expected),
        caller=MAYA,
        faults=faults or {},
        followups=followups,
        audit_delay_min=audit_delay_min,
    )


def _digest_saga():
    call1 = _call_scenario("saga-callback-1", "call back about billing")
    call2 = _call_scenario("saga-callback-2", "call back about billing")
    call3 = _call_scenario(
        "saga-callback-3",
        "call back about billing",
        faults={0: frozenset({FaultMode.PHANTOM_HANDOFF})},
        followups=(Followup(minutes_after=30, close=True, all_open_for_caller=True),),
        audit_delay_min=90,
        extra_steps=(Handoff(reason="call back about a prescription refill"),),
    )
    return run_saga(
        [
            SagaCall(call1, CALL_START),
            SagaCall(call2, at(1, 9, 5)),
            SagaCall(call3, at(2, 9, 5)),
        ]
    )


def test_three_calls_group_into_one_incident() -> None:
    saga = _digest_saga()
    assert len(saga.incidents) == 1
    incident = saga.incidents[0]
    assert incident.repeated_promises == 3
    assert len(incident.calls) == 3
    assert saga.reviews == ()


def test_the_duplicate_ticket_is_flagged() -> None:
    saga = _digest_saga()
    incident = saga.incidents[0]
    assert len(incident.duplicate_writes) == 1
    dup = incident.duplicate_writes[0]
    assert dup.source == "tickets"
    assert dup.audit_id == "aud-saga-callback-2"


def test_completion_is_seen_as_of_the_sagas_end() -> None:
    saga = _digest_saga()
    assert saga.incidents[0].handoff_status is IncidentStatus.FULFILLED


def test_the_phantom_third_promise_is_caught() -> None:
    saga = _digest_saga()
    report3 = saga.runs[2].report
    phantom = next(v for v in report3.verdicts if v.claim.priority == "urgent")
    assert phantom.status is VerdictStatus.NOT_FOUND


def test_the_separate_request_stays_out() -> None:
    saga = _digest_saga()
    incident = saga.incidents[0]
    claim_ids = {cid for call in incident.calls for cid in call.claim_ids}
    refill_claims = {
        v.claim.claim_id for v in saga.runs[2].report.verdicts if "prescription" in v.claim.summary
    }
    assert refill_claims and not (refill_claims & claim_ids)


def test_sagas_are_deterministic() -> None:
    first = _digest_saga()
    second = _digest_saga()
    assert first == second
