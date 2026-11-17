"""Fuzzed scenarios: the same faults across random patients, slots and phrasing.

The golden set proves each fault is caught once, under hand-picked conditions.
Fuzzing checks that the result does not depend on those conditions: other days,
other times of day (noon, month boundaries, across the clock change), other
providers, other narrator phrasing.

Expected outcomes come from one table per intent. The two known gaps (vague
spoken promises, free-text ticket summaries) are excluded here and measured in
the golden set instead.
"""

from __future__ import annotations

import random
from datetime import datetime, timedelta

from receipts.models import VerdictStatus
from receipts.scenarios.world import (
    DANIEL,
    KIM,
    OSEI,
    PATEL,
    ROSTER,
    Expected,
    Scenario,
    SeedAppointment,
    at,
)
from receipts.suspect import Book, Cancel, FaultMode, Handoff, Reschedule, Step

F = FaultMode
B, R, X, C, H = (
    "AppointmentBooked",
    "Rescheduled",
    "Cancelled",
    "ConfirmationSent",
    "HandoffCreated",
)
V, MM, NF = VerdictStatus.VERIFIED, VerdictStatus.MISMATCH, VerdictStatus.NOT_FOUND
CREATED, DOUBLE, CRM_EDIT = (
    "unclaimed_appointment_created",
    "double_booking",
    "unclaimed_patient_modified",
)

Truth = tuple[tuple[Expected, ...], tuple[str, ...]]

# What a correct auditor concludes for a confirmed booking under each fault.
BOOK_TRUTH: dict[FaultMode | None, Truth] = {
    None: (((B, V), (C, V)), ()),
    F.PHANTOM_BOOKING: (((B, NF), (C, V)), ()),
    F.WRONG_TIME: (((B, MM), (C, V)), ()),
    F.UNCLAIMED_WRITE: (((B, V), (C, V)), (CREATED,)),
    F.PHANTOM_CONFIRMATION: (((B, V), (C, NF)), ()),
    F.DOUBLE_BOOK: (((B, V), (C, V)), (DOUBLE,)),
    F.WRONG_PATIENT: (((B, MM), (C, V)), ()),
    F.DUPLICATE_WRITE: (((B, V), (C, V)), (CREATED, DOUBLE)),
    F.ROLLBACK: (((B, NF), (C, V)), ()),
    F.SILENT_CRM_EDIT: (((B, V), (C, V)), (CRM_EDIT,)),
    F.SPOKEN_ONLY: (((B, NF), (C, NF)), ()),
    F.MISSPOKEN_TIME: (((B, V), (C, V), (B, NF)), ()),
    F.MISSPOKEN_PROVIDER: (((B, V), (C, V), (B, NF)), ()),
    F.WRONG_RECIPIENT: (((B, V), (C, MM)), ()),
    F.STALE_CONFIRMATION: (((B, V), (C, MM)), ()),
}
RESCHEDULE_TRUTH: dict[FaultMode | None, Truth] = {
    None: (((R, V),), ()),
    F.PHANTOM_RESCHEDULE: (((R, NF),), ()),
    F.ZOMBIE_RESCHEDULE: (((R, MM),), ()),
    F.LOST_RESCHEDULE: (((R, MM),), ()),
    F.WRONG_TIME: (((R, MM),), ()),
    F.DOUBLE_BOOK: (((R, V),), (DOUBLE,)),
    F.RESCHEDULE_REWRITE: (((R, MM),), ()),
    F.GHOST_RESCHEDULE: (((R, MM),), ()),
}
CANCEL_TRUTH: dict[FaultMode | None, Truth] = {
    None: (((X, V),), ()),
    F.PHANTOM_CANCEL: (((X, NF),), ()),
    F.WRONG_APPOINTMENT_CANCELLED: (((X, MM),), ()),
}
HANDOFF_TRUTH: dict[FaultMode | None, Truth] = {
    None: (((H, V),), ()),
    F.PHANTOM_HANDOFF: (((H, NF),), ()),
    F.DOWNGRADED_HANDOFF: (((H, MM),), ()),
}
PROVIDERS = (PATEL, KIM, OSEI)
REASONS = ("cleaning", "check-up", "filling", "crown fitting")
TOPICS = ("a billing question", "an insurance form", "a knocked-out tooth", "a referral letter")


def _slot(rng: random.Random, taken: set[datetime]) -> datetime:
    """A weekday slot whose neighbours (+1h, +1 day, +7 days) are also safe to use."""
    while True:
        day = rng.randrange(1, 26)
        slot = at(day, rng.randrange(8, 15), rng.choice((0, 30)))
        if slot.weekday() > 3:  # keep Friday free so "+1 day" is still a weekday
            continue
        if not any(abs(slot - t) < timedelta(hours=2) for t in taken):
            taken.add(slot)
            return slot


def generate(n: int, seed: int = 0) -> list[Scenario]:
    """``n`` deterministic single-intent scenarios with known correct outcomes."""
    rng = random.Random(seed)
    scenarios: list[Scenario] = []
    for i in range(n):
        caller = rng.choice(ROSTER)
        other = DANIEL if caller != DANIEL else ROSTER[0]
        provider = rng.choice(PROVIDERS)
        taken: set[datetime] = set()
        slot, elsewhere = _slot(rng, taken), _slot(rng, taken)
        kind = rng.choice(("book", "book", "reschedule", "cancel", "handoff"))
        seeds: list[SeedAppointment] = []
        step: Step

        if kind == "book":
            mode = rng.choice(list(BOOK_TRUTH))
            truth = BOOK_TRUTH[mode]
            step = Book(slot, provider, reason=rng.choice(REASONS))
            if mode is F.DOUBLE_BOOK:
                seeds.append(SeedAppointment(other, provider, slot))
        elif kind == "reschedule":
            mode = rng.choice(list(RESCHEDULE_TRUTH))
            truth = RESCHEDULE_TRUTH[mode]
            step = Reschedule(
                slot,
                elsewhere,
                recreate=mode is None and rng.random() < 0.5,
                provider=provider,
            )
            if mode is not F.GHOST_RESCHEDULE:
                seeds.append(SeedAppointment(caller, provider, slot))
            if mode is F.DOUBLE_BOOK:
                seeds.append(SeedAppointment(other, provider, elsewhere))
        elif kind == "cancel":
            mode = rng.choice(list(CANCEL_TRUTH))
            truth = CANCEL_TRUTH[mode]
            step = Cancel(slot)
            seeds.append(SeedAppointment(caller, provider, slot))
            if mode is F.WRONG_APPOINTMENT_CANCELLED:
                seeds.append(SeedAppointment(caller, rng.choice(PROVIDERS), elsewhere))
        else:
            mode = rng.choice(list(HANDOFF_TRUTH))
            truth = HANDOFF_TRUTH[mode]
            priority = "urgent" if mode is F.DOWNGRADED_HANDOFF or rng.random() < 0.3 else "normal"
            step = Handoff(rng.choice(TOPICS), priority=priority)

        claims, findings = truth
        scenarios.append(
            Scenario(
                id=f"fuzz-{seed}-{i:04d}",
                title=f"{kind} / {mode.value if mode else 'honest'}",
                story="Generated scenario.",
                steps=(step,),
                expected_claims=claims,
                expected_findings=findings,
                caller=caller,
                faults={0: frozenset({mode})} if mode else {},
                seed=tuple(seeds),
                tags=("fuzz", kind, mode.value if mode else "honest"),
            )
        )
    return scenarios
