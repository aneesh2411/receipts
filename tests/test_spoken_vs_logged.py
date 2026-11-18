"""Regression: spoken claims that disagree with the log, and recaps.

From docs/FAILURE_ANALYSIS.md section 4, items 4 and 6: a spoken provider that
differed from the logged one was merged away (false VERIFIED), and a later-turn
recap was read as a second claim with no write behind it (false NOT_FOUND).
"""

from __future__ import annotations

from subpoena.auditor.extractor import RuleBasedExtractor, merge_claims
from subpoena.models import AppointmentBooked, ClaimSource
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
