"""Tamper-evident sealing of audit reports.

An audit trail is only worth something if it cannot be quietly edited later.
Every report carries:

* ``content_hash``: SHA-256 of its canonical JSON,
* ``prev_hash`` / ``chain_hash``: a hash chain linking it to the previous report
  in the ledger, so removing or reordering reports is detectable,
* ``signature``: an HMAC over the chain hash when a signing key is configured.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import dataclass

from receipts.models import AuditReport, Seal

GENESIS = "0" * 64


def canonical_bytes(report: AuditReport) -> bytes:
    payload = report.model_dump(mode="json", exclude={"seal"})
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


@dataclass(frozen=True)
class SealCheck:
    ok: bool
    reason: str


class Sealer:
    def __init__(self, key: bytes | None = None) -> None:
        self._key = key or None

    @property
    def key_id(self) -> str | None:
        return _sha256(self._key)[:12] if self._key else None

    def _sign(self, chain_hash: str) -> str | None:
        if not self._key:
            return None
        return hmac.new(self._key, chain_hash.encode(), hashlib.sha256).hexdigest()

    def seal(self, report: AuditReport, prev_hash: str = GENESIS) -> AuditReport:
        content_hash = _sha256(canonical_bytes(report))
        chain_hash = _sha256(f"{prev_hash}:{content_hash}".encode())
        seal = Seal(
            content_hash=content_hash,
            prev_hash=prev_hash,
            chain_hash=chain_hash,
            signature=self._sign(chain_hash),
            key_id=self.key_id,
        )
        return report.model_copy(update={"seal": seal})

    def verify(self, report: AuditReport, expected_prev: str | None = None) -> SealCheck:
        seal = report.seal
        if seal is None:
            return SealCheck(False, "report is not sealed")
        if _sha256(canonical_bytes(report)) != seal.content_hash:
            return SealCheck(False, "content does not match its hash: the report was altered")
        if _sha256(f"{seal.prev_hash}:{seal.content_hash}".encode()) != seal.chain_hash:
            return SealCheck(False, "chain hash is inconsistent")
        if expected_prev is not None and seal.prev_hash != expected_prev:
            return SealCheck(False, "report is not linked to the expected previous report")
        if self._key:
            expected = self._sign(seal.chain_hash) or ""
            if seal.signature is None or not hmac.compare_digest(expected, seal.signature):
                return SealCheck(False, "signature is missing or invalid")
            return SealCheck(True, "content, chain and signature verified")
        if seal.signature is not None:
            return SealCheck(True, "content and chain verified (signature not checked: no key)")
        return SealCheck(True, "content and chain verified (unsigned)")
