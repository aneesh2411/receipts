"""Seeded, offline properties of write attribution and the audit window."""

from __future__ import annotations

import random
from datetime import timedelta

import pytest

from subpoena.evals.fuzz import PROVIDERS, _slot
from subpoena.models import AppointmentBooked, VerdictStatus
from subpoena.scenarios.world import MAYA, PATEL, ROSTER, at

SEED = 112
CASE_COUNT = 64
GRACE = timedelta(seconds=30)


@pytest.mark.parametrize("case_seed", random.Random(SEED).sample(range(10_000), CASE_COUNT))
@pytest.mark.parametrize("placement", ["foreign", "before", "after"])
def test_excluded_booking_write(clinic, case_seed, placement):
    rng = random.Random(case_seed)
    patient = rng.choice(ROSTER)
    provider = rng.choice(PROVIDERS)
    slot = _slot(rng, set())
    claim = AppointmentBooked(
        claim_id="booking", turn_index=0, patient=patient, provider=provider, start=slot
    )
    call = clinic.call([claim], caller=patient, minutes=rng.randint(1, 5))
    writer_id = f"{call.agent_id}-other" if placement == "foreign" else call.agent_id
    actor = rng.choice((writer_id, f"{writer_id}:{call.call_id}"))
    window_end = call.ended_at + GRACE
    offset = timedelta(seconds=rng.randint(1, 20))
    if placement == "before":
        written_at = call.started_at - offset
    elif placement == "after":
        written_at = window_end + offset
    else:
        written_at = call.started_at + timedelta(
            seconds=rng.randrange(int((call.ended_at - call.started_at).total_seconds()))
        )
    appointment = clinic.as_actor(actor, written_at).calendar.create_appointment(
        patient_id=clinic.patient(patient).id, provider=provider, start=slot
    )
    case = (case_seed, placement, actor, written_at, call.started_at, window_end)

    verdicts = clinic.audit(call, grace=GRACE).verdicts
    assert [verdict.claim for verdict in verdicts] == [claim], case
    if placement == "foreign":
        # The verdict can cite the appointment as a current-state observation.
        # A citation to the write itself carries journal provenance.
        for verdict in verdicts:
            for receipt in verdict.evidence:
                if receipt.ref == appointment.id:
                    assert receipt.note.endswith("(current state)"), (case, receipt)
    assert all(verdict.status is not VerdictStatus.VERIFIED for verdict in verdicts), case
    assert clinic.audit(call, grace=GRACE).verdicts == verdicts, case

    # The same write can verify the claim when its agent and time are eligible.
    control = call.model_copy(
        update={
            "agent_id": writer_id,
            "started_at": written_at,
            "ended_at": written_at + (call.ended_at - call.started_at),
        }
    )
    (positive,) = clinic.audit(control, grace=GRACE).verdicts
    assert positive.status is VerdictStatus.VERIFIED, case
    assert any(receipt.ref == appointment.id for receipt in positive.evidence), case


def test_write_in_same_second_as_window_end_can_verify(clinic):
    slot = at(1, 14, 30)
    claim = AppointmentBooked(
        claim_id="booking", turn_index=0, patient=MAYA, provider=PATEL, start=slot
    )
    call = clinic.call([claim], caller=MAYA)
    window_end = call.ended_at + GRACE
    # The audit window includes the entire final second at its documented
    # one-second resolution. See issue #116 for the future microsecond option.
    written_at = window_end + timedelta(microseconds=1)
    appointment = clinic.as_actor(call.agent_id, written_at).calendar.create_appointment(
        patient_id=clinic.patient(MAYA).id, provider=PATEL, start=slot
    )

    (verdict,) = clinic.audit(call, grace=GRACE).verdicts
    assert verdict.claim == claim
    assert verdict.status is VerdictStatus.VERIFIED
    assert any(receipt.ref == appointment.id for receipt in verdict.evidence)
