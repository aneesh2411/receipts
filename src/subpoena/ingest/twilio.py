"""Validate saved Twilio Voice inputs and build an offline audit record."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from email.utils import parsedate_to_datetime
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from subpoena.models import CallRecord, Claim, ClaimSource, PatientRef, Provenance

_CALL_SID = re.compile(r"CA[0-9a-fA-F]{32}")


@dataclass(frozen=True)
class TwilioCallbacks:
    """Locally supplied callback data. Field validation does not authenticate it."""

    call_id: str
    from_address: str
    to_address: str
    completion_callback_at: datetime
    transcription_text: str


def _required_text(payload: Mapping[str, object], source: str, field: str) -> str:
    value = payload.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{source}.{field} must be a non-empty string")
    return value


def _call_id(payload: Mapping[str, object], source: str) -> str:
    call_id = _required_text(payload, source, "CallSid")
    if not _CALL_SID.fullmatch(call_id):
        raise ValueError(f"{source}.CallSid must be CA followed by 32 hexadecimal digits")
    return call_id


def parse_callbacks(
    status: Mapping[str, object], transcription: Mapping[str, object]
) -> TwilioCallbacks:
    """Normalize a completed call-progress callback and a <Record> transcription callback."""
    call_id = _call_id(status, "status")
    if _call_id(transcription, "transcription") != call_id:
        raise ValueError("transcription.CallSid must match status.CallSid")
    if _required_text(status, "status", "CallStatus") != "completed":
        raise ValueError("status.CallStatus must be completed")
    if _required_text(transcription, "transcription", "TranscriptionStatus") != "completed":
        raise ValueError("transcription.TranscriptionStatus must be completed")

    callback_at = _timestamp(status, "status", "Timestamp")
    return TwilioCallbacks(
        call_id=call_id,
        from_address=_required_text(status, "status", "From"),
        to_address=_required_text(status, "status", "To"),
        completion_callback_at=callback_at,
        transcription_text=_required_text(transcription, "transcription", "TranscriptionText"),
    )


def _timestamp(payload: Mapping[str, object], source: str, field: str) -> datetime:
    timestamp = _required_text(payload, source, field)
    error = f"{source}.{field} must be an RFC 2822 timestamp with an explicit UTC offset"
    try:
        parsed = parsedate_to_datetime(timestamp)
    except (ValueError, OverflowError):
        raise ValueError(error) from None
    if parsed.utcoffset() != timedelta(0):
        raise ValueError(error)
    return parsed.astimezone(UTC)


def _read_object(path: Path, source: str, description: str) -> dict[str, object]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"{source} file has invalid JSON at line {exc.lineno}") from None
    except (OSError, UnicodeError) as exc:
        raise ValueError(f"cannot read {source} file as UTF-8: {exc}") from None
    if not isinstance(payload, dict):
        raise ValueError(f"{source} file must contain a JSON object of {description}")
    return payload


def _read_callback(path: Path, source: str) -> dict[str, object]:
    return _read_object(path, source, "callback parameters")


def load_callbacks(status_path: Path, transcription_path: Path) -> TwilioCallbacks:
    """Read JSON exports of form parameters, one object per callback."""
    return parse_callbacks(
        _read_callback(status_path, "status"),
        _read_callback(transcription_path, "transcription"),
    )


class _ClaimsExport(BaseModel):
    """Subpoena's per-call structured claims export from a deployment tool log."""

    model_config = ConfigDict(extra="forbid")

    call_id: str
    claims: tuple[Claim, ...] = Field(max_length=200)


def _describe_validation(exc: ValidationError) -> str:
    return "; ".join(
        f"{'.'.join(map(str, error['loc'])) or 'record'}: {error['msg']}"
        for error in exc.errors(include_input=False)
    )


def _load_claims(path: Path, call_id: str) -> tuple[Claim, ...]:
    payload = _read_object(path, "claims", "deployment tool-log claims")
    try:
        export = _ClaimsExport.model_validate(payload)
    except ValidationError as exc:
        raise ValueError(f"claims file: {_describe_validation(exc)}") from None
    if export.call_id != call_id:
        raise ValueError("claims.call_id must match status.CallSid")
    for index, claim in enumerate(export.claims):
        if claim.source != ClaimSource.STRUCTURED:
            raise ValueError(f"claims.{index}.source must be structured for a tool-log claim")
    return export.claims


def load_call_record(
    status_path: Path,
    transcription_path: Path,
    resource_path: Path,
    *,
    agent_id: str,
    agent_version: str,
    caller_name: str,
    claims_path: Path | None = None,
) -> CallRecord:
    """Map offline exports for one call leg into an auditable CallRecord."""
    status = _read_callback(status_path, "status")
    transcription = _read_callback(transcription_path, "transcription")
    callbacks = parse_callbacks(status, transcription)
    resource = _read_object(resource_path, "call resource", "Twilio REST Call fields")

    if _required_text(resource, "call resource", "sid") != callbacks.call_id:
        raise ValueError("call resource.sid must match status.CallSid")
    if _required_text(resource, "call resource", "status") != "completed":
        raise ValueError("call resource.status must be completed")
    for field in ("From", "To"):
        if _required_text(transcription, "transcription", field) != status[field]:
            raise ValueError(f"transcription.{field} must match status.{field}")
        key = field.lower()
        if _required_text(resource, "call resource", key) != status[field]:
            raise ValueError(f"call resource.{key} must match status.{field}")

    started_at = _timestamp(resource, "call resource", "start_time")
    ended_at = _timestamp(resource, "call resource", "end_time")
    if ended_at < started_at:
        raise ValueError("call resource.end_time must not be before start_time")
    if callbacks.completion_callback_at < ended_at:
        raise ValueError("status.Timestamp must not be before call resource.end_time")

    operator = {"agent-id": agent_id, "agent-version": agent_version, "caller-name": caller_name}
    for flag, value in operator.items():
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"--{flag} must be a non-empty string")

    claims = _load_claims(claims_path, callbacks.call_id) if claims_path is not None else ()
    try:
        return CallRecord(
            call_id=callbacks.call_id,
            agent_id=agent_id,
            caller=PatientRef(name=caller_name, phone=callbacks.from_address),
            started_at=started_at,
            ended_at=ended_at,
            raw_transcript=callbacks.transcription_text,
            claims=claims,
            provenance=Provenance(
                agent_version=agent_version,
                platform="twilio",
                from_address=callbacks.from_address,
                to_address=callbacks.to_address,
                completion_callback_at=callbacks.completion_callback_at,
            ),
        )
    except ValidationError as exc:
        raise ValueError(f"invalid CallRecord: {_describe_validation(exc)}") from None
