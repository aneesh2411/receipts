"""Review items and versioned receipts, independent of the audit report schema."""

from __future__ import annotations

import hashlib
import hmac
import json
from datetime import UTC, datetime
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, StrictInt, StringConstraints

from subpoena.auditor.seal import GENESIS, Authentication, Sealer
from subpoena.models import AuditReport, VerdictStatus

Hash = Annotated[str, StringConstraints(strict=True, pattern=r"^[a-f0-9]{64}$")]
KeyID = Annotated[str, StringConstraints(strict=True, pattern=r"^[a-f0-9]{12}$")]


def _printable(value: str) -> str:
    if not value.strip() or not value.isprintable():
        raise ValueError("must contain printable text on one line")
    return value


Actor = Annotated[
    str, StringConstraints(strict=True, min_length=1, max_length=128), AfterValidator(_printable)
]
Reason = Annotated[
    str, StringConstraints(strict=True, min_length=1, max_length=2000), AfterValidator(_printable)
]


class ReviewState(StrEnum):
    OPEN = "open"
    ACKNOWLEDGED = "acknowledged"
    RESOLVED = "resolved"
    DISPUTED = "disputed"


EDGES = {
    ReviewState.OPEN: {ReviewState.ACKNOWLEDGED},
    ReviewState.ACKNOWLEDGED: {ReviewState.RESOLVED, ReviewState.DISPUTED},
    ReviewState.RESOLVED: set(),
    ReviewState.DISPUTED: {ReviewState.OPEN},
}


class ReviewModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class TransitionRequest(ReviewModel):
    expected_head: Hash
    state: ReviewState
    actor: Actor
    reason: Reason


class ReviewItem(ReviewModel):
    item_id: Hash
    audit_id: str
    audit_chain_hash: Hash
    result_pointer: str
    state: ReviewState = ReviewState.OPEN
    head: Hash


class Transition(ReviewModel):
    version: Literal[1]
    sequence: StrictInt
    item_id: Hash
    previous_item_head: Hash
    previous_hash: Hash
    from_state: ReviewState
    to_state: ReviewState
    timestamp: str
    actor: Actor
    reason: Reason
    key_id: KeyID | None


class Receipt(Transition):
    hash: Hash
    signature: Hash | None


class ReviewError(Exception):
    """An error with a fixed, client-safe explanation."""

    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status


def _digest(domain: str, payload: dict) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(f"{domain}:{canonical}".encode("ascii")).hexdigest()


def audit_items(report: AuditReport) -> list[ReviewItem]:
    assert report.seal is not None
    items = []
    pointers = [f"/findings/{index}" for index in range(len(report.findings))]
    pointers.extend(
        f"/verdicts/{index}"
        for index, verdict in enumerate(report.verdicts)
        if verdict.status is not VerdictStatus.VERIFIED
    )
    for pointer in pointers:
        source = {
            "audit_id": report.audit_id,
            "audit_chain_hash": report.seal.chain_hash,
            "result_pointer": pointer,
        }
        item_id = _digest("subpoena.review.item.v1", source)
        items.append(ReviewItem(item_id=item_id, head=item_id, **source))
    return items


def _sign(key: bytes, digest: str) -> str:
    return hmac.new(key, f"subpoena.review.signature.v1:{digest}".encode(), "sha256").hexdigest()


def seal_transition(transition: Transition, key: bytes | None) -> Receipt:
    body = transition.model_dump(mode="json")
    digest = _digest("subpoena.review.transition.v1", body)
    return Receipt(**body, hash=digest, signature=_sign(key, digest) if key else None)


def replay(
    items: dict[str, ReviewItem],
    journal: list[Receipt],
    key: bytes | None,
    checkpoint: str | None = None,
) -> tuple[dict[str, ReviewItem], Authentication]:
    """Verify the journal and derive dispositions. A trusted checkpoint may be any prefix."""
    items = items.copy()
    expected_key_id = Sealer(key).key_id
    previous = GENESIS
    reached_checkpoint = checkpoint in (None, GENESIS)
    journal_key_id = journal[0].key_id if journal else None
    for sequence, receipt in enumerate(journal, start=1):
        item = items.get(receipt.item_id)
        body = receipt.model_dump(mode="json", exclude={"hash", "signature"})
        if (
            item is None
            or receipt.sequence != sequence
            or receipt.previous_hash != previous
            or receipt.previous_item_head != item.head
            or receipt.from_state != item.state
            or receipt.to_state not in EDGES[item.state]
            or receipt.hash != _digest("subpoena.review.transition.v1", body)
            or receipt.key_id != journal_key_id
            or (receipt.signature is None) != (receipt.key_id is None)
        ):
            raise ReviewError(500, "review journal integrity check failed")
        try:
            timestamp = datetime.fromisoformat(receipt.timestamp)
            if (
                timestamp.tzinfo != UTC
                or timestamp.isoformat(timespec="microseconds") != receipt.timestamp
            ):
                raise ValueError("expected canonical UTC timestamp")
        except ValueError as exc:
            raise ReviewError(500, "review journal timestamp is invalid") from exc
        if key and (
            receipt.key_id != expected_key_id
            or receipt.signature is None
            or not hmac.compare_digest(receipt.signature, _sign(key, receipt.hash))
        ):
            raise ReviewError(500, "review journal signature check failed")
        items[item.item_id] = item.model_copy(
            update={"state": receipt.to_state, "head": receipt.hash}
        )
        previous = receipt.hash
        reached_checkpoint |= checkpoint == previous
    if not reached_checkpoint:
        raise ReviewError(409, "review journal does not contain the supplied checkpoint")
    if journal_key_id is None:
        authentication = Authentication.UNSIGNED
    elif key:
        authentication = Authentication.AUTHENTICATED
    else:
        authentication = Authentication.UNVERIFIABLE
    return items, authentication
