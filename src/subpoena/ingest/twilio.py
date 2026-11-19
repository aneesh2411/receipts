"""Read two saved Twilio Voice callback parameter maps for the same call."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from email.utils import parsedate_to_datetime
from pathlib import Path

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

    timestamp = _required_text(status, "status", "Timestamp")
    timestamp_error = "status.Timestamp must be an RFC 2822 timestamp with an explicit UTC offset"
    try:
        callback_at = parsedate_to_datetime(timestamp)
    except (ValueError, OverflowError):
        raise ValueError(timestamp_error) from None
    if callback_at.utcoffset() != timedelta(0):
        raise ValueError(timestamp_error)

    return TwilioCallbacks(
        call_id=call_id,
        from_address=_required_text(status, "status", "From"),
        to_address=_required_text(status, "status", "To"),
        completion_callback_at=callback_at.astimezone(UTC),
        transcription_text=_required_text(transcription, "transcription", "TranscriptionText"),
    )


def _read_callback(path: Path, source: str) -> dict[str, object]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"{source} file has invalid JSON at line {exc.lineno}") from None
    except (OSError, UnicodeError) as exc:
        raise ValueError(f"cannot read {source} file as UTF-8: {exc}") from None
    if not isinstance(payload, dict):
        raise ValueError(f"{source} file must contain a JSON object of callback parameters")
    return payload


def load_callbacks(status_path: Path, transcription_path: Path) -> TwilioCallbacks:
    """Read JSON exports of form parameters, one object per callback."""
    return parse_callbacks(
        _read_callback(status_path, "status"),
        _read_callback(transcription_path, "transcription"),
    )
