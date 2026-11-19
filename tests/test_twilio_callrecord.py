import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from subpoena.auditor import Auditor
from subpoena.cli import main
from subpoena.ingest.twilio import load_call_record
from subpoena.models import CallRecord, ClaimSource, VerdictStatus
from subpoena.sor import SqliteStore

_FIXTURES = Path(__file__).parent / "fixtures" / "twilio"
_INPUTS = (
    _FIXTURES / "completed-status.json",
    _FIXTURES / "completed-transcription.json",
    _FIXTURES / "completed-call-resource.json",
)
_CLAIMS = _FIXTURES / "structured-claims.json"
_OPERATOR = {"agent_id": "test-agent", "agent_version": "v3", "caller_name": "Test Caller"}
_CLI_INPUTS = ["ingest-twilio", *map(str, _INPUTS)]
_CLI_FLAGS = ["--agent-id", "test-agent", "--agent-version", "v3", "--caller-name", "Test Caller"]


def test_maps_provider_window_and_operator_metadata():
    record = load_call_record(*_INPUTS, **_OPERATOR)
    assert record.call_id == "CA00000000000000000000000000000001"
    assert record.agent_id == "test-agent"
    assert record.caller.model_dump() == {"name": "Test Caller", "phone": "+12025550101"}
    assert record.started_at == datetime(2026, 11, 19, 18, 0, tzinfo=UTC)
    assert record.ended_at == datetime(2026, 11, 19, 18, 0, 19, tzinfo=UTC)
    assert record.transcript == ()
    assert record.raw_transcript == "Please call me back tomorrow."
    assert record.claims == ()
    provenance = record.provenance
    assert provenance is not None
    assert provenance.platform == "twilio"
    assert provenance.agent_version == "v3"
    assert provenance.from_address == "+12025550101"
    assert provenance.to_address == "+12025550102"
    assert provenance.completion_callback_at == datetime(2026, 11, 19, 18, 0, 20, tzinfo=UTC)


@pytest.mark.parametrize("with_claims", [False, True])
def test_existing_auditor_consumes_cli_json(capsys, with_claims):
    optional_args = ["--claims", str(_CLAIMS)] if with_claims else []
    assert main([*_CLI_INPUTS, *_CLI_FLAGS, *optional_args]) == 0
    captured = capsys.readouterr()
    assert captured.err == ""
    call = CallRecord.model_validate_json(captured.out)
    now = call.started_at + timedelta(seconds=5)
    store = SqliteStore()
    try:
        agent = store.session(f"{call.agent_id}:{call.call_id}", lambda: now)
        if with_claims:
            agent.messages.send(recipient="+12025550102", channel="sms", body="Confirmed")
        report = Auditor(agent, clock=lambda: call.ended_at).audit(call, audit_id="twilio-test")
    finally:
        store.close()
    assert report.call == call
    assert report.call.transcript == ()
    assert any("0 recovered from the transcript" in event.message for event in report.trail)
    if with_claims:
        (verdict,) = report.verdicts
        assert verdict.status == VerdictStatus.VERIFIED
        assert verdict.claim.source == ClaimSource.STRUCTURED
        assert verdict.claim.claim_id == "tool-1"
        assert verdict.claim.turn_index == 4
    else:
        assert report.stats.claims == 0
        assert report.verdicts == ()


@pytest.mark.parametrize(
    ("index", "field", "value", "message"),
    [
        (1, "CallSid", "CA" + "2" * 32, "transcription.CallSid must match"),
        (1, "From", "+12025550103", "transcription.From must match"),
        (1, "To", "+12025550103", "transcription.To must match"),
        (1, "To", None, "transcription.To must be a non-empty string"),
        (2, "sid", "CA" + "2" * 32, "call resource.sid must match"),
        (2, "sid", None, "call resource.sid must be a non-empty string"),
        (2, "status", "in-progress", "call resource.status must be completed"),
        (2, "from", "+12025550103", "call resource.from must match"),
        (2, "to", "+12025550103", "call resource.to must match"),
        (2, "start_time", None, "call resource.start_time must be a non-empty string"),
        (2, "end_time", None, "call resource.end_time must be a non-empty string"),
        (2, "end_time", 123, "call resource.end_time must be a non-empty string"),
        (2, "start_time", "2026-11-19T18:00:00Z", "call resource.start_time must be an RFC 2822"),
        (
            2,
            "end_time",
            "Thu, 19 Nov 2026 17:59:59 +0000",
            "end_time must not be before start_time",
        ),
        (2, "end_time", "Thu, 19 Nov 2026 18:00:21 +0000", "status.Timestamp must not be before"),
    ],
)
def test_rejects_incomplete_or_inconsistent_source(tmp_path, index, field, value, message):
    inputs = list(_INPUTS)
    payload = json.loads(inputs[index].read_text())
    if value is None:
        del payload[field]
    else:
        payload[field] = value
    inputs[index] = tmp_path / "input.json"
    inputs[index].write_text(json.dumps(payload))
    with pytest.raises(ValueError, match=message):
        load_call_record(*inputs, **_OPERATOR)


@pytest.mark.parametrize(("contents", "message"), [
    ("{", "call resource file has invalid JSON"),
    ("[]", "call resource file must contain a JSON object"),
])
def test_rejects_malformed_resource_json(tmp_path, contents, message):
    path = tmp_path / "resource.json"
    path.write_text(contents)
    with pytest.raises(ValueError, match=message):
        load_call_record(*_INPUTS[:2], path, **_OPERATOR)


def test_missing_resource_file_is_an_error(tmp_path):
    with pytest.raises(ValueError, match="cannot read call resource file"):
        load_call_record(*_INPUTS[:2], tmp_path / "absent.json", **_OPERATOR)


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ("malformed", "claims file has invalid JSON"),
        ("wrong_call", "claims.call_id must match"),
        ("wrong_type", "union_tag_invalid|does not match"),
        ("wrong_source", "source must be structured"),
        ("missing_index", "turn_index: Field required"),
        ("duplicate", "duplicate claim_id"),
    ],
)
def test_rejects_invalid_claims(tmp_path, change, message):
    payload = json.loads(_CLAIMS.read_text())
    claim = payload["claims"][0]
    if change == "wrong_call":
        payload["call_id"] = "CA" + "2" * 32
    elif change == "wrong_type":
        claim["type"] = "Unknown"
    elif change == "wrong_source":
        claim["source"] = "transcript"
    elif change == "missing_index":
        del claim["turn_index"]
    elif change == "duplicate":
        payload["claims"].append(claim)
    path = tmp_path / "claims.json"
    path.write_text("{" if change == "malformed" else json.dumps(payload))
    with pytest.raises(ValueError, match=message):
        load_call_record(*_INPUTS, **_OPERATOR, claims_path=path)


@pytest.mark.parametrize("flag", ["--agent-id", "--agent-version", "--caller-name"])
def test_cli_requires_operator_flags(capsys, flag):
    flags = _CLI_FLAGS.copy()
    index = flags.index(flag)
    del flags[index:index + 2]
    with pytest.raises(SystemExit, match="2"):
        main([*_CLI_INPUTS, *flags])
    assert flag in capsys.readouterr().err


def test_cli_rejects_blank_metadata_without_writing(capsys, tmp_path):
    output = tmp_path / "record.json"
    output.write_text("previous")
    assert main([*_CLI_INPUTS, *_CLI_FLAGS, "--agent-version", " ", "--out", str(output)]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "--agent-version must be a non-empty string" in captured.err
    assert output.read_text() == "previous"


def test_cli_writes_json_to_file_only(capsys, tmp_path):
    output = tmp_path / "record.json"
    assert main([*_CLI_INPUTS, *_CLI_FLAGS, "--out", str(output)]) == 0
    assert capsys.readouterr().out == ""
    assert CallRecord.model_validate_json(output.read_bytes()) == load_call_record(
        *_INPUTS, **_OPERATOR
    )
