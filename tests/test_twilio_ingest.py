import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from subpoena.cli import main
from subpoena.ingest.twilio import TwilioCallbacks, load_callbacks, parse_callbacks

_FIXTURES = Path(__file__).parent / "fixtures" / "twilio"
_STATUS = _FIXTURES / "completed-status.json"
_TRANSCRIPTION = _FIXTURES / "completed-transcription.json"


def test_normalizes_documented_callback_parameters():
    assert load_callbacks(_STATUS, _TRANSCRIPTION) == TwilioCallbacks(
        call_id="CA00000000000000000000000000000001",
        from_address="+12025550101",
        to_address="+12025550102",
        completion_callback_at=datetime(2026, 11, 19, 18, 0, 20, tzinfo=UTC),
        transcription_text="Please call me back tomorrow.",
    )


@pytest.mark.parametrize(
    ("source", "field", "value", "message"),
    [
        ("transcription", "CallSid", "CA" + "2" * 32, r"must match status\.CallSid"),
        ("status", "CallSid", "not-a-sid", "32 hexadecimal digits"),
        ("status", "CallStatus", "no-answer", r"status\.CallStatus must be completed"),
        ("transcription", "TranscriptionStatus", "failed", "TranscriptionStatus must be completed"),
        (
            "transcription",
            "TranscriptionText",
            "  ",
            "TranscriptionText must be a non-empty string",
        ),
        ("status", "To", None, r"status\.To must be a non-empty string"),
        ("status", "Timestamp", None, r"status\.Timestamp must be a non-empty string"),
        ("status", "Timestamp", "tomorrow", r"status\.Timestamp must be an RFC 2822 timestamp"),
        ("status", "Timestamp", "Thu, 19 Nov 2026 18:00:20", "explicit UTC offset"),
    ],
)
def test_rejects_malformed_or_partial_callbacks(source, field, value, message):
    payloads = {
        "status": json.loads(_STATUS.read_text()),
        "transcription": json.loads(_TRANSCRIPTION.read_text()),
    }
    if value is None:
        del payloads[source][field]
    else:
        payloads[source][field] = value

    with pytest.raises(ValueError, match=message):
        parse_callbacks(payloads["status"], payloads["transcription"])


def test_cli_validates_two_local_exports(capsys):
    assert main(["validate-twilio", str(_STATUS), str(_TRANSCRIPTION)]) == 0
    assert "passed offline validation" in capsys.readouterr().out


@pytest.mark.parametrize(
    ("contents", "message"),
    [("{", "has invalid JSON at line 1"), ("[]", "must contain a JSON object")],
)
def test_cli_rejects_invalid_exports(tmp_path, capsys, contents, message):
    invalid = tmp_path / "transcription.json"
    invalid.write_text(contents)
    assert main(["validate-twilio", str(_STATUS), str(invalid)]) == 2
    captured = capsys.readouterr()
    assert not captured.out
    assert f"transcription file {message}" in captured.err
