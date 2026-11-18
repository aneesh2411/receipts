"""Coverage-aware verdicts: incomplete history is UNVERIFIABLE, never a clean pass.

A change feed does not always observe the whole call window: cursors expire,
retrieval is partial, caches go stale, a create/delete pair can straddle the
observed interval. From a partial history neither presence nor absence is
proof, so verdicts degrade to UNVERIFIABLE with a current-state observation.
"""

from __future__ import annotations

from datetime import timedelta

import pytest

from subpoena.auditor import Auditor
from subpoena.models import (
    AppointmentBooked,
    Outcome,
    VerdictStatus,
)
from subpoena.scenarios.world import CLINIC, MAYA, PATEL, at
from subpoena.sor import Coverage, with_coverage, with_outage

V, NF, UV = VerdictStatus.VERIFIED, VerdictStatus.NOT_FOUND, VerdictStatus.UNVERIFIABLE
SLOT = at(1, 14, 30)


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


def _book(clinic):
    return clinic.agent.calendar.create_appointment(
        patient_id=clinic.patient(MAYA).id, provider=PATEL, start=SLOT
    )


def _reader(clinic, name: str, cov: Coverage, drop=None):
    return with_coverage(clinic.as_actor("auditor"), name, cov, drop=drop)


def _coverage(verdict):
    return next(c for c in verdict.checks if c.name.value == "coverage")


@pytest.mark.parametrize(
    "detail",
    [
        "sync cursor expired before the window was fully replayed",
        "served from a snapshot cache 40 minutes old",
    ],
)
def test_partial_history_turns_a_matched_write_unverifiable(clinic, detail):
    _book(clinic)
    report = clinic.audit(
        clinic.call([_booked()]), reader=_reader(clinic, "calendar", Coverage(False, detail))
    )
    (verdict,) = report.verdicts
    assert verdict.status is UV
    assert _coverage(verdict).passed is False
    assert detail in _coverage(verdict).detail
    assert report.outcome is Outcome.INCONCLUSIVE
    # The same call against a fully observed window verifies.
    assert clinic.audit(clinic.call([_booked()])).verdicts[0].status is V


def test_partial_retrieval_cannot_support_not_found(clinic):
    appt = _book(clinic)
    reader = _reader(
        clinic,
        "calendar",
        Coverage(False, "page 2 of the window was never retrieved"),
        drop=lambda c: c.entity_id == appt.id,
    )
    (verdict,) = clinic.audit(clinic.call([_booked()]), reader=reader).verdicts
    # The write is missing from the feed, but absence from a partial feed is not
    # evidence: no unsupported NOT_FOUND. The current-state observation stays.
    assert verdict.status is UV
    assert "Absence cannot be proven" in verdict.summary
    assert any("current state" in (e.note or "") for e in verdict.evidence)


def test_a_delete_the_feed_missed_cannot_support_a_clean_pass(clinic):
    appt = _book(clinic)
    clinic.agent.calendar.delete_appointment(appt.id)
    reader = _reader(
        clinic,
        "calendar",
        Coverage(False, "the delete fell outside the observed interval"),
        drop=lambda c: c.op == "delete",
    )
    (verdict,) = clinic.audit(clinic.call([_booked()]), reader=reader).verdicts
    # The feed shows only the insert, so the net effect looks CREATED. A clean
    # pass here would certify a booking that no longer exists.
    assert verdict.status is UV
    assert "could change the net effect" in verdict.summary


def test_incomplete_history_suppresses_unclaimed_write_findings(clinic):
    clinic.agent.messages.send(recipient=MAYA.phone, channel="sms", body="unclaimed")
    reader = _reader(clinic, "messages", Coverage(False, "partial retrieval"))
    report = clinic.audit(clinic.call([]), reader=reader)
    assert report.findings == ()
    assert any("unclaimed-write check skipped" in e.message for e in report.trail)
    assert report.outcome is Outcome.INCONCLUSIVE


def test_reaudit_after_recovery_preserves_the_original_sealed_report(clinic):
    _book(clinic)
    call = clinic.call([_booked()])
    audited_at = call.ended_at + timedelta(minutes=1)
    down = with_outage(clinic.as_actor("auditor"), "calendar")
    first = Auditor(down, clinic=CLINIC, clock=lambda: audited_at).audit(call)
    assert first.outcome is Outcome.INCONCLUSIVE
    assert first.verdicts[0].status is UV

    reader = clinic.as_actor("auditor")
    second = Auditor(reader, clinic=CLINIC, clock=lambda: audited_at + timedelta(hours=1)).audit(
        call, prev_hash=first.seal.chain_hash
    )
    # Later evidence permits a new audit; the original report stands untouched.
    assert second.verdicts[0].status is V
    assert second.seal.prev_hash == first.seal.chain_hash
    assert first.outcome is Outcome.INCONCLUSIVE
    assert first.seal.chain_hash != second.seal.chain_hash


def test_complete_coverage_is_recorded_on_judged_verdicts(clinic):
    _book(clinic)
    (verdict,) = clinic.audit(clinic.call([_booked()])).verdicts
    check = _coverage(verdict)
    assert check.passed is True and "fully observed" in check.detail
