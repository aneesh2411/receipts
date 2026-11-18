"""Regression: spoken claims that disagree with the log, and recaps.

From docs/FAILURE_ANALYSIS.md section 4, items 4 and 6: a spoken provider that
differed from the logged one was merged away (false VERIFIED), and a later-turn
recap was read as a second claim with no write behind it (false NOT_FOUND).
"""

from __future__ import annotations

import pytest

from subpoena.auditor.extractor import RuleBasedExtractor, merge_claims
from subpoena.models import (
    AppointmentBooked,
    Claim,
    ClaimSource,
    ConfirmationSent,
    HandoffCreated,
    Rescheduled,
)
from subpoena.scenarios.world import CALL_START, CLINIC, MAYA, at


def _booked(claim_id: str, turn: int, provider: str, **kw) -> AppointmentBooked:
    return AppointmentBooked(
        claim_id=claim_id,
        turn_index=turn,
        patient=MAYA,
        start=at(1, 14, 30),
        provider=provider,
        **kw,
    )


def test_spoken_provider_disagreement_is_not_merged_away() -> None:
    logged = _booked("c1", 0, "Dr. Patel")
    spoken = _booked("t1", 0, "Dr. Kim", source=ClaimSource.TRANSCRIPT)
    merged = merge_claims([logged], [spoken])
    assert len(merged) == 2


def test_same_promise_still_merges() -> None:
    logged = _booked("c1", 0, "Dr. Patel")
    spoken = _booked("t1", 0, "Dr. Patel", source=ClaimSource.TRANSCRIPT)
    merged = merge_claims([logged], [spoken])
    assert merged == (logged,)


def test_recap_in_a_later_turn_corroborates_the_logged_claim() -> None:
    logged = _booked("c1", 0, "Dr. Patel")
    recap = _booked("t9", 9, "Dr. Patel", source=ClaimSource.TRANSCRIPT)
    merged = merge_claims([logged], [recap])
    assert merged == (logged,)


def test_repeated_spoken_claims_dedupe() -> None:
    first = _booked("t1", 1, "Dr. Patel", source=ClaimSource.TRANSCRIPT)
    recap = _booked("t9", 9, "Dr. Patel", source=ClaimSource.TRANSCRIPT)
    merged = merge_claims([], [first, recap])
    assert merged == (first,)


def test_extractor_reads_a_recap_line() -> None:
    clinic_call = type(
        "Call",
        (),
        {
            "transcript": (),
            "caller": MAYA,
            "started_at": CALL_START,
            "call_id": "c",
        },
    )()
    # covered end to end by the edge-recap golden scenario; here just the regex path
    from subpoena.models import Turn

    clinic_call.transcript = (
        Turn(
            index=0,
            speaker="agent",
            text="To recap, you're booked with Dr. Patel on Tuesday, March 3 at 2:30 PM.",
            at=CALL_START,
        ),
    )
    claims = RuleBasedExtractor().extract(clinic_call, CLINIC)
    assert len(claims) == 1 and claims[0].provider == "Dr. Patel"


@pytest.mark.parametrize(
    ("claim", "changes"),
    [
        pytest.param(
            ConfirmationSent(claim_id="c", turn_index=1, to="maya@example.com", channel="email"),
            {"channel": "sms"},
            id="confirmation-channel",
        ),
        pytest.param(
            ConfirmationSent(claim_id="c", turn_index=1, to="+15550101001"),
            {"to": "+15550101002"},
            id="confirmation-recipient",
        ),
        pytest.param(
            ConfirmationSent(
                claim_id="c", turn_index=1, to="+15550101001", about_start=at(1, 14, 30)
            ),
            {"about_start": at(2, 14, 30)},
            id="confirmation-appointment",
        ),
        pytest.param(
            Rescheduled(
                claim_id="c",
                turn_index=1,
                patient=MAYA,
                old_start=at(1, 14, 30),
                new_start=at(3, 14, 30),
                provider="Dr. Patel",
            ),
            {"old_start": at(2, 14, 30)},
            id="reschedule-old-time",
        ),
        pytest.param(
            HandoffCreated(claim_id="c", turn_index=1, summary="billing", priority="normal"),
            {"priority": "urgent"},
            id="handoff-priority",
        ),
        pytest.param(
            HandoffCreated(claim_id="c", turn_index=1, summary="billing", priority="normal"),
            {"summary": "tooth pain"},
            id="handoff-topic",
        ),
    ],
)
def test_material_disagreement_survives_merging(claim: Claim, changes: dict) -> None:
    spoken = claim.model_copy(update={"claim_id": "t", "source": ClaimSource.TRANSCRIPT, **changes})
    assert merge_claims([claim], [spoken]) == (claim, spoken)


def test_later_reschedule_with_different_old_time_is_not_a_recap() -> None:
    logged = Rescheduled(
        claim_id="c",
        turn_index=1,
        patient=MAYA,
        old_start=at(1, 14, 30),
        new_start=at(3, 14, 30),
        provider="Dr. Patel",
    )
    later = logged.model_copy(
        update={
            "claim_id": "t",
            "source": ClaimSource.TRANSCRIPT,
            "turn_index": 3,
            "old_start": at(2, 14, 30),
        }
    )
    assert merge_claims([logged], [later]) == (logged, later)


def test_confirmation_duplicates_pair_one_to_one_before_later_recap() -> None:
    logged = ConfirmationSent(claim_id="c", turn_index=1, to="+15550101001")
    first = logged.model_copy(update={"claim_id": "t1", "source": ClaimSource.TRANSCRIPT})
    second = first.model_copy(update={"claim_id": "t2"})
    recap = first.model_copy(update={"claim_id": "t3", "turn_index": 4})
    assert merge_claims([logged], [first, second, recap]) == (logged, second)
    second_log = logged.model_copy(update={"claim_id": "c2"})
    assert merge_claims([logged, second_log], [first, second, recap]) == (logged, second_log)


def test_confirmation_without_spoken_time_pairs_with_logged_appointment() -> None:
    logged = ConfirmationSent(
        claim_id="c", turn_index=1, to="+15550101001", about_start=at(1, 14, 30)
    )
    spoken = logged.model_copy(
        update={"claim_id": "t", "source": ClaimSource.TRANSCRIPT, "about_start": None}
    )
    assert merge_claims([logged], [spoken]) == (logged,)
    unspecified_log = logged.model_copy(update={"about_start": None})
    specific_spoken = spoken.model_copy(update={"about_start": logged.about_start})
    assert merge_claims([unspecified_log], [specific_spoken]) == (unspecified_log, specific_spoken)


def test_handoff_topic_matches_the_built_in_spoken_wording() -> None:
    logged = HandoffCreated(
        claim_id="c",
        turn_index=1,
        patient=MAYA,
        summary="Caller needs help with billing",
        priority="normal",
    )
    spoken = logged.model_copy(
        update={
            "claim_id": "t",
            "source": ClaimSource.TRANSCRIPT,
            "summary": "I've created a ticket for the front desk about billing.",
        }
    )
    assert merge_claims([logged], [spoken]) == (logged,)
    repeated = spoken.model_copy(update={"claim_id": "t2"})
    assert merge_claims([logged], [spoken, repeated]) == (logged, repeated)


def test_spoken_reschedule_recap_preserves_a_different_provider() -> None:
    first = Rescheduled(
        claim_id="t1",
        turn_index=1,
        source=ClaimSource.TRANSCRIPT,
        patient=MAYA,
        old_start=at(1, 14, 30),
        new_start=at(3, 14, 30),
        provider="Dr. Patel",
    )
    different = first.model_copy(update={"claim_id": "t2", "turn_index": 2, "provider": "Dr. Kim"})
    recap = first.model_copy(update={"claim_id": "t3", "turn_index": 3})
    assert merge_claims([], [first, different, recap]) == (first, different)
