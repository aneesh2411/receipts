"""Regression: reconcile pairs competing claims by assignment, not claim order.

Issue #39: same-type claims in one call share an evidence pool, and greedy
claim-order matching let the wrong claim consume a write - a rolled-back
booking "verified" against a duplicate's leftover, a phantom cancel took the
honest cancel's release, and two handoffs paired with each other's tickets.
"""

from __future__ import annotations

from subpoena.models import VerdictStatus
from subpoena.scenarios.world import (
    KIM,
    MAYA,
    PATEL,
    Scenario,
    SeedAppointment,
    at,
    audit_call,
    build_world,
    run_suspect,
)
from subpoena.suspect import Book, Cancel, FaultMode, Handoff

F = FaultMode
S1, S2 = at(2, 10), at(3, 11)


def _audit(steps, faults, seeds=()):
    scenario = Scenario(
        "test-reconcile-assignment",
        "Competing same-type claims in one call",
        "x",
        steps,
        (),
        faults=faults,
        seed=tuple(seeds),
    )
    world = build_world(scenario)
    return audit_call(scenario, world, run_suspect(scenario, world))


def test_rolled_back_claim_cannot_take_the_duplicates_leftover():
    report = _audit(
        (
            Book(start=S1, provider=PATEL, confirm=False),
            Book(start=S2, provider=KIM, confirm=False),
        ),
        {0: frozenset({F.ROLLBACK}), 1: frozenset({F.DUPLICATE_WRITE})},
    )
    verdicts = [v for v in report.verdicts if v.claim.type == "AppointmentBooked"]
    # The rolled-back booking was never written: NOT_FOUND. The duplicated
    # booking verifies once, and its leftover copy is an unclaimed write.
    # Greedy matching turned the first claim into MISMATCH and hid the leftover.
    assert [v.status for v in verdicts] == [VerdictStatus.NOT_FOUND, VerdictStatus.VERIFIED]
    assert "unclaimed_appointment_created" in {f.code for f in report.findings}


def test_phantom_cancel_cannot_take_the_wrong_target_cancels_release():
    # The agent claims to cancel S2 but actually cancels the other appointment
    # on the patient's list - S1, which an earlier step only claimed to cancel.
    # The release of S1 exactly matches the phantom's words; causally it belongs
    # to the second step.
    report = _audit(
        (Cancel(start=S1), Cancel(start=S2)),
        {0: frozenset({F.PHANTOM_CANCEL}), 1: frozenset({F.WRONG_APPOINTMENT_CANCELLED})},
        seeds=(
            SeedAppointment(MAYA, PATEL, S1),
            SeedAppointment(MAYA, KIM, S2),
        ),
    )
    verdicts = [v for v in report.verdicts if v.claim.type == "Cancelled"]
    # The phantom found nothing to cancel: NOT_FOUND. The second claim's words
    # (S2) contradict what was actually released (S1): MISMATCH. Greedy matching
    # VERIFIED the phantom against the release and left the real claim NOT_FOUND.
    assert [v.status for v in verdicts] == [VerdictStatus.NOT_FOUND, VerdictStatus.MISMATCH]


def test_competing_handoffs_pair_with_their_own_tickets():
    report = _audit(
        (
            Handoff("a billing question", priority="urgent"),
            Handoff("a knocked-out tooth", priority="urgent"),
        ),
        {0: frozenset({F.DOWNGRADED_HANDOFF})},
    )
    verdicts = [v for v in report.verdicts if v.claim.type == "HandoffCreated"]
    # The billing handoff was downgraded to a normal ticket: MISMATCH. The
    # dental emergency went out urgent: VERIFIED. Greedy matching paired each
    # claim with the other's ticket and flipped both verdicts.
    assert [v.status for v in verdicts] == [VerdictStatus.MISMATCH, VerdictStatus.VERIFIED]
