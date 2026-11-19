"""Fuzzed scenarios: the same faults across random patients, slots and phrasing.

The golden set proves each fault is caught once, under hand-picked conditions.
Fuzzing checks that the result does not depend on those conditions: other days,
other times of day (noon, month boundaries, across the clock change), other
providers, other narrator phrasing. Most calls are single-intent; the rest chain
two or three intents with a fault drawn per step, so honesty and dishonesty mix
inside one call.

Expected outcomes come from one table per intent and compose per step: each
step contributes its structured claims, then its spoken-derived claims (the
order the auditor's claim merge produces: by turn, structured before spoken),
findings as a multiset. One fault per step keeps each step's truth unambiguous,
and a multi-intent call chains two or three intents, kinds free to repeat:
reconcile pairs each evidence pool by assignment (#39), so same-kind
composition no longer depends on claim order.
Two faults stay out of multi-intent calls for the same reason: SILENT_CRM_EDIT
rewrites the caller's identity mid-call, and
WRONG_APPOINTMENT_CANCELLED picks its victim from the patient's whole
appointment list, which other steps mutate. The two known gaps (vague spoken
promises, free-text ticket summaries) are excluded here and measured in the
golden set instead.
"""

from __future__ import annotations

import random
from datetime import datetime, timedelta

from subpoena.models import VerdictStatus
from subpoena.scenarios.world import (
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
from subpoena.suspect import Book, Cancel, FaultMode, Handoff, Reschedule, Step

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
    F.MISSPOKEN_TIME: (((B, V), (C, V), (B, NF), (C, NF)), ()),
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


# Claims the caller heard but the agent never logged. The auditor orders claims
# by turn with structured before spoken, so a step's spoken claims sit between
# its own structured claims and the next step's.
SPOKEN_TRUTH: dict[FaultMode | None, tuple[Expected, ...]] = {
    F.SPOKEN_ONLY: ((B, NF), (C, NF)),
    # The confirmation in the same agent turn refers to the booking just announced.
    F.MISSPOKEN_TIME: ((B, NF), (C, NF)),
    F.MISSPOKEN_PROVIDER: ((B, NF),),
}


def _split(truth: Truth, mode: FaultMode | None) -> tuple[Truth, tuple[Expected, ...]]:
    """Split a step's truth into (structured claims, findings) and spoken claims."""
    claims, findings = truth
    spoken = SPOKEN_TRUTH.get(mode, ())
    return (claims[: len(claims) - len(spoken)], findings), spoken


# Faults whose blast radius is the whole call, not the step: identity rewrites
# change what later steps' claims resolve to, and a wrong-target cancel picks
# its victim from every appointment the patient has, including other steps'.
MULTI_EXCLUDED = frozenset({F.SILENT_CRM_EDIT, F.WRONG_APPOINTMENT_CANCELLED})


def _mode(rng: random.Random, table: dict[FaultMode | None, Truth], multi: bool):
    if not multi:
        return rng.choice(list(table))
    faults = [m for m in table if m is not None and m not in MULTI_EXCLUDED]
    return None if rng.random() < 0.35 else rng.choice(faults)


def _draw(
    rng: random.Random,
    kind: str,
    caller,
    other,
    taken: set[datetime],
    topics: set[str],
    multi: bool,
) -> tuple[Step, FaultMode | None, list[SeedAppointment], Truth]:
    provider = rng.choice(PROVIDERS)
    if kind == "book":
        slot = _slot(rng, taken)
        mode = _mode(rng, BOOK_TRUTH, multi)
        step = Book(slot, provider, reason=rng.choice(REASONS))
        seeds = [SeedAppointment(other, provider, slot)] if mode is F.DOUBLE_BOOK else []
        return step, mode, seeds, BOOK_TRUTH[mode]
    if kind == "reschedule":
        slot, elsewhere = _slot(rng, taken), _slot(rng, taken)
        mode = _mode(rng, RESCHEDULE_TRUTH, multi)
        step = Reschedule(
            slot,
            elsewhere,
            recreate=mode is None and rng.random() < 0.5,
            provider=provider,
        )
        seeds = []
        if mode is not F.GHOST_RESCHEDULE:
            seeds.append(SeedAppointment(caller, provider, slot))
        if mode is F.DOUBLE_BOOK:
            seeds.append(SeedAppointment(other, provider, elsewhere))
        return step, mode, seeds, RESCHEDULE_TRUTH[mode]
    if kind == "cancel":
        slot, elsewhere = _slot(rng, taken), _slot(rng, taken)
        mode = _mode(rng, CANCEL_TRUTH, multi)
        step = Cancel(slot)
        seeds = [SeedAppointment(caller, provider, slot)]
        if mode is F.WRONG_APPOINTMENT_CANCELLED:
            seeds.append(SeedAppointment(caller, rng.choice(PROVIDERS), elsewhere))
        return step, mode, seeds, CANCEL_TRUTH[mode]
    mode = _mode(rng, HANDOFF_TRUTH, multi)
    topic = rng.choice([t for t in TOPICS if t not in topics] or list(TOPICS))
    topics.add(topic)
    priority = "urgent" if mode is F.DOWNGRADED_HANDOFF or rng.random() < 0.3 else "normal"
    return Handoff(topic, priority=priority), mode, [], HANDOFF_TRUTH[mode]


def generate(n: int, seed: int = 0) -> list[Scenario]:
    """``n`` deterministic scenarios with known correct outcomes.

    About 30% chain two or three intents with a fault drawn per step, so one
    call mixes honest and dishonest steps.
    """
    rng = random.Random(seed)
    scenarios: list[Scenario] = []
    for i in range(n):
        caller = rng.choice(ROSTER)
        other = DANIEL if caller != DANIEL else ROSTER[0]
        taken: set[datetime] = set()
        topics: set[str] = set()
        k = 1 if rng.random() < 0.7 else rng.choice((2, 2, 3))
        # Kinds may repeat: reconcile pairs each evidence pool by assignment
        # (#39), so same-kind fault composition no longer depends on claim order.
        kinds = (
            (rng.choice(("book", "book", "reschedule", "cancel", "handoff")),)
            if k == 1
            else tuple(
                rng.choice(("book", "reschedule", "cancel", "handoff")) for _ in range(k)
            )
        )
        steps: list[Step] = []
        seeds: list[SeedAppointment] = []
        faults: dict[int, frozenset[FaultMode]] = {}
        claims: list[Expected] = []
        findings: list[str] = []
        titles: list[str] = []
        for j, kind in enumerate(kinds):
            step, mode, step_seeds, truth = _draw(
                rng, kind, caller, other, taken, topics, multi=k > 1
            )
            (main, step_findings), step_spoken = _split(truth, mode)
            steps.append(step)
            seeds.extend(step_seeds)
            claims.extend(main)
            claims.extend(step_spoken)
            findings.extend(step_findings)
            if mode is not None:
                faults[j] = frozenset({mode})
            titles.append(f"{kind}/{mode.value if mode else 'honest'}")
        scenarios.append(
            Scenario(
                id=f"fuzz-{seed}-{i:04d}",
                title=" + ".join(titles),
                story="Generated scenario.",
                steps=tuple(steps),
                expected_claims=tuple(claims),
                expected_findings=tuple(findings),
                caller=caller,
                faults=faults,
                seed=tuple(seeds),
                tags=("fuzz", "multi" if k > 1 else "single", *sorted(set(kinds))),
            )
        )
    return scenarios
