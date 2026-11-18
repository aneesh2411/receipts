"""Concurrent calls under one shared agent identity: correlation is not attribution.

A journal row says who the connection claimed to be. When two calls run at once
under the same agent identity, a shared-identity row plus an overlapping time
window cannot establish which call caused the mutation - and a call id stamped
by the agent is a hint, not independent evidence. Only a platform-stamped
``agent:call-id`` session attributes a write to one call directly.
"""

from __future__ import annotations

from subpoena.models import (
    AppointmentBooked,
    CallRecord,
    Claim,
    Outcome,
    Severity,
    VerdictStatus,
)
from subpoena.scenarios.world import DANIEL, KIM, MAYA, PATEL, at
from subpoena.suspect import AGENT_ID

V, NF, UV = VerdictStatus.VERIFIED, VerdictStatus.NOT_FOUND, VerdictStatus.UNVERIFIABLE

SLOT = at(1, 14, 30)
SLOT2 = at(2, 10, 0)


def _booked(**kw):
    return AppointmentBooked(
        **{
            "claim_id": "c1",
            "turn_index": 0,
            "patient": MAYA,
            "provider": PATEL,
            "start": SLOT,
            **kw,
        }
    )


def _stamped(clinic, call_id: str):
    """A platform session whose writes carry the call's own stamp."""
    return clinic.as_actor(f"{AGENT_ID}:{call_id}")


def _call(clinic, call_id: str, claims: list[Claim]) -> CallRecord:
    return clinic.call(claims).model_copy(update={"call_id": call_id})


def _book_maya(sor, clinic):
    return sor.calendar.create_appointment(
        patient_id=clinic.patient(MAYA).id, provider=PATEL, start=SLOT
    )


def _attribution(verdict):
    return next(c for c in verdict.checks if c.name.value == "attribution")


def test_shared_identity_without_concurrency_still_verifies(clinic):
    _book_maya(clinic.agent, clinic)  # a legacy integration stamps only the agent
    (verdict,) = clinic.audit(clinic.call([_booked()])).verdicts
    assert verdict.status is V
    check = _attribution(verdict)
    assert check.passed is True and "shared agent identity" in check.detail


def test_shared_identity_under_concurrency_cannot_verify(clinic):
    _book_maya(clinic.agent, clinic)
    # Another call under the same identity was in progress in the same window.
    _stamped(clinic, "call-a").tickets.create_ticket(patient_id=None, summary="unrelated")
    report = clinic.audit(_call(clinic, "call-b", [_booked()]))
    (verdict,) = report.verdicts
    assert verdict.status is UV
    assert verdict.severity is Severity.HIGH
    assert "cannot be proven" in verdict.summary
    assert _attribution(verdict).passed is False
    assert report.outcome is Outcome.INCONCLUSIVE


def test_one_mutation_cannot_independently_verify_two_calls(clinic):
    appt = _book_maya(_stamped(clinic, "call-a"), clinic)
    claim = _booked()  # same patient, same slot, claimed on both calls
    a = clinic.audit(_call(clinic, "call-a", [claim]))
    b = clinic.audit(_call(clinic, "call-b", [claim]))
    assert a.verdicts[0].status is V
    assert a.verdicts[0].evidence[0].ref == appt.id
    # The same write is foreign to call B: it cannot corroborate B's claim.
    assert b.verdicts[0].status is NF
    assert b.findings == ()  # and it is not an unclaimed write of B's either


def test_a_stamp_for_another_call_is_not_attribution(clinic):
    _book_maya(_stamped(clinic, "call-ghost"), clinic)
    report = clinic.audit(_call(clinic, "call-test", [_booked()]))
    assert report.verdicts[0].status is NF
    assert report.findings == ()
    assert any("stamped to other call" in e.message for e in report.trail)


def test_replayed_batch_cannot_resurrect_a_cancelled_write(clinic):
    session = _stamped(clinic, "call-a")
    appt = _book_maya(session, clinic)
    session.calendar.delete_appointment(appt.id)
    # A redelivered batch replays the insert row with a fresh sequence number.
    conn = clinic.store._conn
    conn.execute(
        "INSERT INTO change_log(entity, entity_id, op, before, after, actor, at) "
        "SELECT entity, entity_id, op, before, after, actor, at FROM change_log "
        "WHERE entity = 'appointment' AND op = 'insert'"
    )
    report = clinic.audit(_call(clinic, "call-a", [_booked()]))
    (verdict,) = report.verdicts
    # Net effect of the call: written, then removed. The replay must not count twice.
    assert verdict.status is NF and "removed" in verdict.summary
    assert any("replay" in e.message for e in report.trail)


def test_audit_order_does_not_change_verdicts(clinic):
    _book_maya(_stamped(clinic, "call-a"), clinic)
    _stamped(clinic, "call-b").calendar.create_appointment(
        patient_id=clinic.patient(DANIEL).id, provider=KIM, start=SLOT2
    )
    claim_b = AppointmentBooked(
        claim_id="c1", turn_index=0, patient=DANIEL, provider=KIM, start=SLOT2
    )
    call_a = _call(clinic, "call-a", [_booked()])
    call_b = _call(clinic, "call-b", [claim_b])
    forward = (
        clinic.audit(call_a).verdicts[0].status,
        clinic.audit(call_b).verdicts[0].status,
    )
    reverse = (
        clinic.audit(call_b).verdicts[0].status,
        clinic.audit(call_a).verdicts[0].status,
    )
    # Each write carries its own call's stamp, so concurrency changes nothing and
    # processing order cannot leak one call's evidence into the other's report.
    assert forward == (V, V)
    assert reverse == (V, V)
