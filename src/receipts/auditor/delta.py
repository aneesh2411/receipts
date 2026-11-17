"""Turn a raw change feed into the net effect of a call.

A call's journal may touch the same record several times (create, then move,
then delete). What matters for the caller is the *net* change between the state
before the call and the state after it.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from receipts.models import Change, Entity, Evidence

SOURCE: dict[Entity, str] = {
    Entity.APPOINTMENT: "calendar",
    Entity.PATIENT: "crm",
    Entity.MESSAGE: "messages",
    Entity.TICKET: "tickets",
}


class ChangeKind(StrEnum):
    CREATED = "created"
    UPDATED = "updated"
    DELETED = "deleted"
    TRANSIENT = "transient"  # no net effect: created-then-deleted, or changed back


@dataclass(frozen=True)
class NetChange:
    entity: Entity
    entity_id: str
    kind: ChangeKind
    before: dict[str, Any] | None
    after: dict[str, Any] | None
    changes: tuple[Change, ...]

    @property
    def key(self) -> tuple[Entity, str]:
        return (self.entity, self.entity_id)

    @property
    def snapshot(self) -> dict[str, Any] | None:
        """The most informative image of the record, even for a transient change."""
        if self.after is not None:
            return self.after
        if self.before is not None:
            return self.before
        return next((c.after for c in self.changes if c.after is not None), None)

    def evidence(self, note: str) -> Evidence:
        seqs = ", ".join(f"#{c.seq}" for c in self.changes)
        return Evidence(
            source=SOURCE[self.entity],
            ref=self.entity_id,
            note=f"{note} (journal {seqs}; net: {self.kind.value})",
            record=self.snapshot,
        )


def collapse(changes: Sequence[Change]) -> list[NetChange]:
    """Group journal rows by record and reduce each group to its net change."""
    grouped: dict[tuple[Entity, str], list[Change]] = {}
    for change in sorted(changes, key=lambda c: c.seq):
        grouped.setdefault((change.entity, change.entity_id), []).append(change)

    net: list[NetChange] = []
    for (entity, entity_id), rows in grouped.items():
        before, after = rows[0].before, rows[-1].after
        if before is None and after is None:
            kind = ChangeKind.TRANSIENT
        elif before is None:
            kind = ChangeKind.CREATED
        elif after is None:
            kind = ChangeKind.DELETED
        elif before == after:
            kind = ChangeKind.TRANSIENT
        else:
            kind = ChangeKind.UPDATED
        net.append(NetChange(entity, entity_id, kind, before, after, tuple(rows)))
    return net
