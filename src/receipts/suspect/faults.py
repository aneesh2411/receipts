"""Fault modes: the ways the suspect can say one thing and do another."""

from __future__ import annotations

import random
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Protocol


class FaultMode(StrEnum):
    # -- the six from the brief ------------------------------------------- #
    PHANTOM_BOOKING = "phantom_booking"  # claims a booking it never wrote
    WRONG_TIME = "wrong_time"  # writes a different time than it claims
    UNCLAIMED_WRITE = "unclaimed_write"  # writes something it never mentions
    PHANTOM_CONFIRMATION = "phantom_confirmation"  # claims a message it never sent
    PHANTOM_HANDOFF = "phantom_handoff"  # claims a ticket it never created
    DOUBLE_BOOK = "double_book"  # books into an occupied slot
    # -- booking, extended ------------------------------------------------- #
    WRONG_PATIENT = "wrong_patient"  # books under someone else's record
    DUPLICATE_WRITE = "duplicate_write"  # retry bug: writes the booking twice
    ROLLBACK = "rollback"  # writes the booking, then removes it
    OFF_HOURS_BOOKING = "off_hours_booking"  # books while the clinic is closed
    SILENT_CRM_EDIT = "silent_crm_edit"  # overwrites the patient's phone on file
    SPOKEN_ONLY = "spoken_only"  # tells the caller "booked"; logs and writes nothing
    MISSPOKEN_TIME = "misspoken_time"  # system is right, the caller was told another time
    # -- confirmations ----------------------------------------------------- #
    WRONG_RECIPIENT = "wrong_recipient"  # confirmation goes to a stranger's number
    STALE_CONFIRMATION = "stale_confirmation"  # confirmation states the wrong time
    # -- reschedule / cancel ----------------------------------------------- #
    PHANTOM_RESCHEDULE = "phantom_reschedule"  # claims a move it never made
    ZOMBIE_RESCHEDULE = "zombie_reschedule"  # creates the new slot, leaves the old one
    LOST_RESCHEDULE = "lost_reschedule"  # cancels the old slot, never creates the new one
    PHANTOM_CANCEL = "phantom_cancel"  # claims a cancellation it never made
    WRONG_APPOINTMENT_CANCELLED = "wrong_appointment_cancelled"  # cancels a different visit
    # -- handoffs ---------------------------------------------------------- #
    DOWNGRADED_HANDOFF = "downgraded_handoff"  # says urgent, files low priority
    GARBLED_HANDOFF = "garbled_handoff"  # files a ticket about the wrong thing


REQUIRED_FAULTS: frozenset[FaultMode] = frozenset(
    {
        FaultMode.PHANTOM_BOOKING,
        FaultMode.WRONG_TIME,
        FaultMode.UNCLAIMED_WRITE,
        FaultMode.PHANTOM_CONFIRMATION,
        FaultMode.PHANTOM_HANDOFF,
        FaultMode.DOUBLE_BOOK,
    }
)

_F = FaultMode
BOOK_FAULTS = frozenset(
    {
        _F.PHANTOM_BOOKING, _F.WRONG_TIME, _F.UNCLAIMED_WRITE, _F.PHANTOM_CONFIRMATION,
        _F.DOUBLE_BOOK, _F.WRONG_PATIENT, _F.DUPLICATE_WRITE, _F.ROLLBACK,
        _F.OFF_HOURS_BOOKING, _F.SILENT_CRM_EDIT, _F.SPOKEN_ONLY, _F.MISSPOKEN_TIME,
        _F.WRONG_RECIPIENT, _F.STALE_CONFIRMATION,
    }
)  # fmt: skip
RESCHEDULE_FAULTS = frozenset(
    {_F.PHANTOM_RESCHEDULE, _F.ZOMBIE_RESCHEDULE, _F.LOST_RESCHEDULE, _F.WRONG_TIME, _F.DOUBLE_BOOK}
)
CANCEL_FAULTS = frozenset({_F.PHANTOM_CANCEL, _F.WRONG_APPOINTMENT_CANCELLED})
HANDOFF_FAULTS = frozenset({_F.PHANTOM_HANDOFF, _F.DOWNGRADED_HANDOFF, _F.GARBLED_HANDOFF})


class FaultPlan(Protocol):
    def modes(self, step_index: int, applicable: frozenset[FaultMode]) -> frozenset[FaultMode]:
        """Which fault modes are active for this step."""
        ...


@dataclass(frozen=True)
class NoFaults:
    def modes(self, step_index: int, applicable: frozenset[FaultMode]) -> frozenset[FaultMode]:
        return frozenset()


@dataclass(frozen=True)
class ForcedFaults:
    """Deterministic plan: exactly these faults on exactly these steps."""

    by_step: Mapping[int, frozenset[FaultMode]]

    def modes(self, step_index: int, applicable: frozenset[FaultMode]) -> frozenset[FaultMode]:
        wanted = frozenset(self.by_step.get(step_index, frozenset()))
        invalid = wanted - applicable
        if invalid:
            names = sorted(m.value for m in invalid)
            raise ValueError(f"fault(s) {names} do not apply to step {step_index}")
        return wanted


@dataclass
class RandomFaults:
    """Tunable plan: each applicable fault fires with its own probability (seeded)."""

    rates: Mapping[FaultMode, float]
    seed: int = 0
    _rng: random.Random = field(init=False, repr=False)

    def __post_init__(self) -> None:
        bad = {m: r for m, r in self.rates.items() if not 0.0 <= r <= 1.0}
        if bad:
            raise ValueError(f"fault rates must be within [0, 1]: {bad}")
        self._rng = random.Random(self.seed)

    def modes(self, step_index: int, applicable: frozenset[FaultMode]) -> frozenset[FaultMode]:
        for mode in sorted(applicable):  # sorted: draw order must not depend on set hashing
            if self._rng.random() < self.rates.get(mode, 0.0):
                return frozenset({mode})  # at most one fault per step keeps truth unambiguous
        return frozenset()
