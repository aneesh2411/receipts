"""Recovering claims from the transcript.

Structured claims are the agent's own account of itself. The transcript is what
the caller actually heard, and that is the promise that matters. Anything the
agent said it did, but did not log as a claim, is recovered here and audited
like any other claim.

This is the only place a language model may be used, and only to *read*. The
rule-based extractor is the default and needs no model.
"""

from __future__ import annotations

import json
import re
from collections.abc import Sequence
from datetime import datetime
from typing import Any, Literal, Protocol

from pydantic import AwareDatetime, BaseModel, ValidationError

from receipts.llm import LLMClient
from receipts.models import (
    AppointmentBooked,
    CallRecord,
    Cancelled,
    Claim,
    ClaimSource,
    ConfirmationSent,
    HandoffCreated,
    Rescheduled,
)
from receipts.util import ClinicConfig, find_times


class ClaimExtractor(Protocol):
    def extract(self, call: CallRecord, clinic: ClinicConfig) -> list[Claim]: ...


_SENTENCE = re.compile(r"(?<!Dr\.)(?<!Mr\.)(?<!Ms\.)(?<=[.!?])\s+")
_NEGATED = re.compile(
    r"\b(?:couldn't|could not|can't|cannot|unable|wasn't able|was not able|not able|"
    r"didn't|did not|unfortunately|sorry)\b",
    re.IGNORECASE,
)
_RESCHEDULED = re.compile(r"\b(?:moved|rescheduled)\b", re.IGNORECASE)
_CANCELLED = re.compile(r"\bcancel(?:l)?ed\b", re.IGNORECASE)
_BOOKED = re.compile(r"\b(?:booked|scheduled|got you down|reserved)\b", re.IGNORECASE)
_SENT = re.compile(r"\b(?:sent|texted|emailed)\b", re.IGNORECASE)
_CONFIRMATION = re.compile(r"\b(?:confirmation|text|email)\b", re.IGNORECASE)
_HANDOFF = re.compile(r"\b(?:ticket|flagged|escalated)\b", re.IGNORECASE)
_URGENT = re.compile(r"\b(?:urgent|right away|emergency)\b", re.IGNORECASE)
_PROVIDER = re.compile(r"\bDr\.\s+[A-Z][A-Za-z'-]+")


class RuleBasedExtractor:
    """Deterministic, offline. Reads explicit statements; misses vague ones by design."""

    def extract(self, call: CallRecord, clinic: ClinicConfig) -> list[Claim]:
        claims: list[Claim] = []
        for turn in call.transcript:
            if turn.speaker != "agent":
                continue
            last_time: datetime | None = None
            for sentence in _SENTENCE.split(turn.text):
                if _NEGATED.search(sentence):
                    continue
                times = find_times(sentence, ref=call.started_at, tz=clinic.zone)
                meta: dict[str, Any] = {
                    "claim_id": f"{call.call_id}-t{len(claims) + 1}",
                    "turn_index": turn.index,
                    "source": ClaimSource.TRANSCRIPT,
                    "utterance": sentence,
                }
                if _RESCHEDULED.search(sentence) and len(times) >= 2:
                    claims.append(
                        Rescheduled(
                            **meta, patient=call.caller, old_start=times[0], new_start=times[1]
                        )
                    )
                    last_time = times[1]
                elif _CANCELLED.search(sentence) and times:
                    claims.append(Cancelled(**meta, patient=call.caller, start=times[0]))
                elif _BOOKED.search(sentence) and times:
                    provider = _PROVIDER.search(sentence)
                    claims.append(
                        AppointmentBooked(
                            **meta,
                            patient=call.caller,
                            start=times[0],
                            provider=provider.group(0) if provider else None,
                        )
                    )
                    last_time = times[0]
                elif _SENT.search(sentence) and _CONFIRMATION.search(sentence):
                    email = "email" in sentence.lower()
                    if call.caller.phone or email:
                        claims.append(
                            ConfirmationSent(
                                **meta,
                                channel="email" if email else "sms",
                                to=call.caller.phone or call.caller.name,
                                about_start=last_time,
                            )
                        )
                elif _HANDOFF.search(sentence):
                    claims.append(
                        HandoffCreated(
                            **meta,
                            patient=call.caller,
                            summary=sentence,
                            priority="urgent" if _URGENT.search(sentence) else "normal",
                        )
                    )
        return claims


class _Extracted(BaseModel):
    """The only shape accepted back from a model. Anything else is discarded."""

    turn_index: int
    type: Literal[
        "AppointmentBooked", "Rescheduled", "Cancelled", "ConfirmationSent", "HandoffCreated"
    ]
    start: AwareDatetime | None = None
    old_start: AwareDatetime | None = None
    new_start: AwareDatetime | None = None
    provider: str | None = None
    channel: Literal["sms", "email"] = "sms"
    priority: Literal["low", "normal", "urgent"] = "normal"


class LLMClaimExtractor:
    """Model-backed reader for phrasing the rules cannot resolve.

    The model's output is parsed and validated; on any failure the rule-based
    extractor's answer is used instead. The model never sees the system of
    record and never produces a verdict.
    """

    _SYSTEM = (
        "You read phone-call transcripts from an AI receptionist. List every action the AGENT "
        "tells the caller it has COMPLETED (booked, rescheduled, cancelled, sent a confirmation, "
        "created a handoff ticket). Ignore offers, questions and things it says it could not do. "
        'Reply with a JSON array only. Each item: {"turn_index": int, "type": '
        '"AppointmentBooked|Rescheduled|Cancelled|ConfirmationSent|HandoffCreated", '
        '"start"|"old_start"|"new_start": ISO-8601 with UTC offset or null, '
        '"provider": string or null, "channel": "sms|email", '
        '"priority": "low|normal|urgent"}.'
    )

    def __init__(self, llm: LLMClient, fallback: ClaimExtractor | None = None) -> None:
        self._llm = llm
        self._fallback = fallback or RuleBasedExtractor()

    def extract(self, call: CallRecord, clinic: ClinicConfig) -> list[Claim]:
        try:
            reply = self._llm.complete(system=self._SYSTEM, prompt=self._prompt(call, clinic))
            raw = json.loads(reply[reply.index("[") : reply.rindex("]") + 1])
            items = [_Extracted.model_validate(item) for item in raw]
            return [
                claim
                for n, item in enumerate(items, start=1)
                if (claim := self._to_claim(call, item, n)) is not None
            ]
        except (ValueError, ValidationError, TypeError, RuntimeError, OSError):
            return self._fallback.extract(call, clinic)

    @staticmethod
    def _prompt(call: CallRecord, clinic: ClinicConfig) -> str:
        lines = "\n".join(f"[{t.index}] {t.speaker.upper()}: {t.text}" for t in call.transcript)
        local = call.started_at.astimezone(clinic.zone)
        return f"The call took place on {local:%A, %B %d, %Y} ({clinic.tz}).\n\n{lines}"

    @staticmethod
    def _to_claim(call: CallRecord, item: _Extracted, n: int) -> Claim | None:
        turns = {t.index: t for t in call.transcript}
        if item.turn_index not in turns or turns[item.turn_index].speaker != "agent":
            return None  # a claim must point at something the agent actually said
        meta: dict[str, Any] = {
            "claim_id": f"{call.call_id}-t{n}",
            "turn_index": item.turn_index,
            "source": ClaimSource.TRANSCRIPT,
            "utterance": turns[item.turn_index].text,
        }
        if item.type == "AppointmentBooked" and item.start:
            return AppointmentBooked(
                **meta, patient=call.caller, start=item.start, provider=item.provider
            )
        if item.type == "Rescheduled" and item.old_start and item.new_start:
            return Rescheduled(
                **meta, patient=call.caller, old_start=item.old_start, new_start=item.new_start
            )
        if item.type == "Cancelled" and item.start:
            return Cancelled(**meta, patient=call.caller, start=item.start)
        if item.type == "ConfirmationSent" and call.caller.phone:
            return ConfirmationSent(
                **meta, channel=item.channel, to=call.caller.phone, about_start=item.start
            )
        if item.type == "HandoffCreated":
            return HandoffCreated(
                **meta, patient=call.caller, summary=meta["utterance"], priority=item.priority
            )
        return None


# ----------------------- merging spoken and structured --------------------- #


def _same_promise(spoken: Claim, logged: Claim) -> bool:
    """Do a spoken claim and a structured claim describe the same commitment?"""
    if isinstance(spoken, AppointmentBooked) and isinstance(logged, AppointmentBooked):
        return spoken.start == logged.start
    if isinstance(spoken, Rescheduled) and isinstance(logged, Rescheduled):
        return spoken.new_start == logged.new_start
    if isinstance(spoken, Cancelled) and isinstance(logged, Cancelled):
        return spoken.start == logged.start
    return spoken.type == logged.type  # confirmations / handoffs: one per logged claim


def merge_claims(structured: Sequence[Claim], spoken: Sequence[Claim]) -> tuple[Claim, ...]:
    """Structured claims, plus every spoken claim that no structured claim corroborates.

    A spoken claim is corroborated by a structured claim made in the same turn
    that describes the same commitment. Each structured claim corroborates at
    most one spoken claim.
    """
    used: set[str] = set()
    extra: list[Claim] = []
    for claim in spoken:
        partner = next(
            (
                s
                for s in structured
                if s.claim_id not in used
                and s.turn_index == claim.turn_index
                and _same_promise(claim, s)
            ),
            None,
        )
        if partner is None:
            extra.append(claim)
        else:
            used.add(partner.claim_id)
    merged = [*structured, *extra]
    order = {c.claim_id: i for i, c in enumerate(merged)}
    return tuple(
        sorted(
            merged,
            key=lambda c: (c.turn_index, c.source is ClaimSource.TRANSCRIPT, order[c.claim_id]),
        )
    )
