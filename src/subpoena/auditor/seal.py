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
from enum import StrEnum

from subpoena.models import AuditReport, Seal

GENESIS = "0" * 64


class Integrity(StrEnum):
    """Is the report the one that was sealed?"""

    UNSEALED = "unsealed"
    INTACT = "intact"
    ALTERED = "altered"  # content, chain, or ledger link no longer matches


class Authentication(StrEnum):
    """Is the seal proven to come from the key holder?"""

    UNSIGNED = "unsigned"  # no signature on the seal
    AUTHENTICATED = "authenticated"  # signature checked against the configured key
    UNVERIFIABLE = "unverifiable"  # signed, but no key configured to check against
    INVALID = "invalid"  # a key is configured and the signature is missing or wrong


def canonical_bytes(report: AuditReport) -> bytes:
    payload = report.model_dump(mode="json", exclude={"seal"})
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


@dataclass(frozen=True)
class SealCheck:
    ok: bool
    reason: str
    integrity: Integrity
    authentication: Authentication


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

    def verify(
        self,
        report: AuditReport,
        expected_prev: str | None = None,
        *,
        strict: bool = False,
    ) -> SealCheck:
        """Check integrity (is this the sealed report?) and authentication (is it
        from the key holder?) separately. Lenient mode keeps the historical bar:
        intact content, and a valid signature only when a key is configured.
        Strict mode requires an authenticated signature, so unsigned or
        unverifiable reports fail even when intact.
        """
        seal = report.seal
        if seal is None:
            return SealCheck(False, "report is not sealed", Integrity.UNSEALED,
                             Authentication.UNSIGNED)  # fmt: skip
        altered = None
        if _sha256(canonical_bytes(report)) != seal.content_hash:
            altered = "content does not match its hash: the report was altered"
        elif _sha256(f"{seal.prev_hash}:{seal.content_hash}".encode()) != seal.chain_hash:
            altered = "chain hash is inconsistent"
        elif expected_prev is not None and seal.prev_hash != expected_prev:
            altered = "report is not linked to the expected previous report"

        if self._key:
            expected = self._sign(seal.chain_hash) or ""
            if seal.signature is None:
                authentication, signed = Authentication.INVALID, "signature is missing"
            elif not hmac.compare_digest(expected, seal.signature):
                authentication, signed = Authentication.INVALID, "signature is invalid"
            else:
                authentication, signed = Authentication.AUTHENTICATED, "signature verified"
        elif seal.signature is not None:
            authentication = Authentication.UNVERIFIABLE
            signed = "signature present but not checked: no key configured"
        else:
            authentication, signed = Authentication.UNSIGNED, "unsigned"

        if altered is not None:
            return SealCheck(False, altered, Integrity.ALTERED, authentication)
        if authentication is Authentication.INVALID:
            return SealCheck(False, signed, Integrity.INTACT, authentication)
        if strict and authentication is not Authentication.AUTHENTICATED:
            return SealCheck(
                False,
                f"strict mode requires an authenticated seal ({signed})",
                Integrity.INTACT,
                authentication,
            )
        return SealCheck(True, f"content and chain verified ({signed})", Integrity.INTACT,
                         authentication)  # fmt: skip
