import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from subpoena.ingest.action_log import ActionLogError, load_action_log, parse_action_log
from subpoena.models import (
    AppointmentBooked,
    Cancelled,
    ClaimSource,
    ConfirmationSent,
    HandoffCreated,
    PatientRef,
    VerdictStatus,
)

_FIXTURES = Path(__file__).parent / "fixtures" / "action_log"


def test_maps_actions_and_preserves_provenance():
    caller = PatientRef(name="Maya Chen", phone="+15550101001")
    first, second = load_action_log(
        _FIXTURES / "multi_call.jsonl",
        agent_id="my-agent",
        agent_version="release-7",
        callers={"call-a": caller},
    )

    assert (first.call_id, second.call_id) == ("call-a", "call-b")
    assert first.agent_id == "my-agent"
    assert first.caller == caller
    assert first.provenance.platform == "action-log"
    assert first.provenance.agent_version == "release-7"
    assert first.started_at == datetime(2026, 1, 2, 9, tzinfo=UTC)
    assert first.ended_at == datetime(2026, 1, 2, 9, 1, tzinfo=UTC)
    assert second.started_at == second.ended_at == datetime(2026, 1, 2, 10, tzinfo=UTC)
    assert [claim.claim_id for claim in first.claims] == ["01", "02", "03"]
    assert [claim.turn_index for claim in first.claims] == [0, 1, 2]
    assert all(claim.source == ClaimSource.STRUCTURED for claim in first.claims + second.claims)

    booking, confirmation, handoff = first.claims
    (cancellation,) = second.claims
    assert isinstance(booking, AppointmentBooked)
    assert (booking.patient, booking.provider, booking.duration_min) == (caller, "Lee", 30)
    assert isinstance(confirmation, ConfirmationSent)
    assert confirmation.to == caller.phone
    assert confirmation.about_start == booking.start
    assert isinstance(handoff, HandoffCreated)
    assert (handoff.summary, handoff.priority) == ("Request accessibility assistance", "urgent")
    assert isinstance(cancellation, Cancelled)
    assert cancellation.patient.name == "Daniel Okafor"


def test_reordered_input_produces_identical_records():
    lines = (_FIXTURES / "multi_call.jsonl").read_text(encoding="utf-8").splitlines()
    expected = [call.model_dump_json() for call in parse_action_log(lines)]
    assert [call.model_dump_json() for call in parse_action_log(reversed(lines))] == expected


def test_existing_auditor_consumes_each_claim(clinic):
    calls = load_action_log(_FIXTURES / "multi_call.jsonl")
    for call in calls:
        report = clinic.audit(call)
        assert tuple(verdict.claim for verdict in report.verdicts) == call.claims
        assert all(verdict.status == VerdictStatus.NOT_FOUND for verdict in report.verdicts)


@pytest.mark.parametrize(
    ("file", "message"),
    [
        ("missing_timestamp", r"line 1, timestamp: Field required"),
        ("wrong_type", r"line 1, payload\.duration_min:"),
        ("duplicate_event_id", r"line 2, event_id: duplicate .*first seen on line 1"),
    ],
)
def test_rejects_invalid_fixtures(file, message):
    with pytest.raises(ActionLogError, match=message):
        load_action_log(_FIXTURES / f"{file}.jsonl")


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"kind": "transcript"}, r"kind: unknown event kind 'transcript'"),
        ({"kind": 7}, r"kind:"),
        ({"timestamp": "2026-01-02T09:00:00"}, r"timestamp:"),
        ({"timestamp": "1767344400"}, r"timestamp:"),
        ({"timestamp": 1767344400}, r"timestamp:"),
        ({"timestamp": "2026-01-02T09:00:00+00:90"}, r"timestamp:"),
        ({"kind": "booking", "payload": {}}, r"payload\.patient:.*payload\.start:"),
        ({"payload": []}, r"payload:"),
        ({"payload": {"patient": {"name": 1}}}, r"payload\.patient\.name:"),
        ({"payload": {"source": "transcript"}}, r"payload\.source:"),
        ({"payload": {"time": "later"}}, r"payload\.time:"),
        ({"event_id": " "}, r"event_id:"),
        ({"call_id": "contains spaces"}, r"call_id:"),
        ({"extra": True}, r"extra:"),
    ],
)
def test_rejects_invalid_fields(changes, message):
    valid_line = (_FIXTURES / "multi_call.jsonl").read_text(encoding="utf-8").splitlines()[1]
    event = json.loads(valid_line)
    with pytest.raises(ActionLogError, match=f"line 2, {message}"):
        parse_action_log([valid_line, json.dumps(event | changes)])


@pytest.mark.parametrize(
    ("line", "message"),
    [
        ("{", r"event: invalid JSON"),
        ("", r"event: invalid JSON"),
        ("[]", r"event:"),
        ('{"kind":"handoff","kind":"booking"}', r"kind: duplicate field"),
        ('{"payload":{"priority":NaN}}', r"event: invalid JSON constant"),
    ],
)
def test_rejects_invalid_json(line, message):
    with pytest.raises(ActionLogError, match=f"line 1, {message}"):
        parse_action_log([line])


def test_reports_invalid_utf8_on_the_physical_line(tmp_path):
    path = tmp_path / "log.jsonl"
    path.write_bytes((_FIXTURES / "multi_call.jsonl").read_bytes() + b"\xff\n")
    with pytest.raises(ActionLogError, match="line 5, event: invalid UTF-8"):
        load_action_log(path)


def test_empty_log():
    assert parse_action_log([]) == ()


def test_call_claim_limit_identifies_the_excess_line():
    event = {
        "call_id": "call-a",
        "timestamp": "2026-01-02T09:00:00Z",
        "kind": "handoff",
        "payload": {},
    }
    lines = [json.dumps(event | {"event_id": str(index)}) for index in range(201)]
    (call,) = parse_action_log(lines[:200])
    assert len(call.claims) == 200
    with pytest.raises(ActionLogError, match="line 201, call_id: exceeds 200 claims"):
        parse_action_log(lines)
