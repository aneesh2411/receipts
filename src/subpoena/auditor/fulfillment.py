"""Handoff fulfillment: a created ticket is a recorded promise, not a kept one.

The handoff auditor proves a ticket exists. This module asks what happened
next, using only the ticket queue's journal: was it assigned, did someone
other than the creating agent acknowledge it, and was it actually closed.
Each state is backed by a journal row; no model is involved.

Missing downstream evidence never upgrades the state. When the feed's history
for the window is incomplete, an open promise is INCONCLUSIVE rather than
pending: a later update may simply be unobserved. A closing row is proof on
its own, because a gap can hide a row but cannot fabricate one.

The REST ticket adapter carries creation evidence only, so fulfillment beyond
``recorded`` is inconclusive there until it exposes lifecycle reads.
"""

from __future__ import annotations

from datetime import datetime

from subpoena.models import Change, Evidence, Fulfillment, FulfillmentState, Ticket
from subpoena.sor.base import COMPLETE, AdapterUnavailable, ChangeFeed, Coverage


def _evidence(row: Change, note: str) -> Evidence:
    return Evidence(
        source="tickets", ref=row.entity_id, note=f"{note} (journal #{row.seq})", record=row.after
    )


def _is_staff_touch(row: Change, creator: str) -> bool:
    """A touch by someone other than the creating agent.

    The agent's own later writes (same identity, any call) do not acknowledge
    its own ticket; the queue's staff must write under their own actors.
    """
    agent = creator.split(":", 1)[0]
    return row.actor != creator and row.actor != agent and not row.actor.startswith(agent + ":")


def assess(ticket: Ticket, creator: str, feed: ChangeFeed, now: datetime) -> Fulfillment:
    """Walk the ticket's journal from creation to ``now`` and grade the promise."""
    try:
        rows = [c for c in feed.changes(ticket.created_at, now) if c.entity_id == ticket.id]
    except AdapterUnavailable as exc:
        return Fulfillment(
            ticket_id=ticket.id,
            state=FulfillmentState.INCONCLUSIVE,
            pending=False,
            summary=f"The ticket queue could not be read ({exc}). Whether the callback "
            "happened is unknown, and we will not guess.",
        )

    closed = next(
        (c for c in rows if c.after is not None and c.after.get("status") == "closed"), None
    )
    assigned = next((c for c in rows if c.after is not None and c.after.get("assignee")), None)
    acknowledged = next((c for c in rows if c.op == "update" and _is_staff_touch(c, creator)), None)

    state = FulfillmentState.RECORDED
    evidence: list[Evidence] = []
    if rows:
        first = rows[0]
        evidence.append(_evidence(first, "Ticket created during the call"))
    if assigned is not None:
        state = FulfillmentState.ASSIGNED
        evidence.append(_evidence(assigned, f"Assigned to {assigned.after['assignee']}"))
    if acknowledged is not None:
        state = FulfillmentState.ACKNOWLEDGED
        evidence.append(
            _evidence(acknowledged, f"Touched by {acknowledged.actor}, not the creating agent")
        )
    if closed is not None:
        state = FulfillmentState.COMPLETED
        evidence.append(_evidence(closed, f"Closed by {closed.actor}"))

    if state is FulfillmentState.COMPLETED:
        return Fulfillment(
            ticket_id=ticket.id,
            state=state,
            pending=False,
            summary=f"The callback promise was fulfilled: {closed.actor} closed the ticket.",
            evidence=tuple(evidence),
        )

    cov_fn = getattr(feed, "coverage", None)
    try:
        cov = cov_fn(ticket.created_at, now) if callable(cov_fn) else COMPLETE
    except AdapterUnavailable as exc:
        cov = Coverage(complete=False, detail=str(exc))
    if not cov.complete:
        return Fulfillment(
            ticket_id=ticket.id,
            state=FulfillmentState.INCONCLUSIVE,
            pending=False,
            summary=f"The ticket journal is incomplete for the window since creation "
            f"({cov.detail or 'no detail'}); a later update may be unobserved. Highest "
            f"evidenced state: {state.value}.",
            evidence=tuple(evidence),
        )

    notes = {
        FulfillmentState.RECORDED: "The ticket was created and nothing further happened. "
        "Nobody is known to be calling back.",
        FulfillmentState.ASSIGNED: "The ticket has an assignee but no sign anyone picked "
        "it up. The callback is still pending.",
        FulfillmentState.ACKNOWLEDGED: "Someone picked the ticket up, but it is still "
        "open. Acknowledged is not fulfilled.",
    }
    return Fulfillment(
        ticket_id=ticket.id,
        state=state,
        pending=True,
        summary=notes[state],
        evidence=tuple(evidence),
    )
