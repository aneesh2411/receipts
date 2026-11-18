"""Certification scorecards: fingerprinting, staleness, diffs."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from subpoena.evals import certify as cert

NOW = datetime(2026, 11, 18, 12, 0, tzinfo=UTC)


def _root_with_inputs(tmp_path):
    root = tmp_path / "repo"
    for rel in cert.FINGERPRINT_INPUTS:
        src = cert.repo_root() / rel
        dst = root / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(src.read_bytes())
    return root


def test_fingerprint_covers_every_input_file(tmp_path):
    root = _root_with_inputs(tmp_path)
    base = cert.fingerprint(root)
    target = root / cert.FINGERPRINT_INPUTS[0]
    target.write_bytes(target.read_bytes() + b"\n# a quiet config change\n")
    assert cert.fingerprint(root) != base


def test_certify_writes_json_markdown_and_latest(tmp_path):
    out = tmp_path / "scorecards"
    card = cert.certify(out, now=NOW)
    files = {p.name for p in out.iterdir()}
    assert f"20261118-{card.fingerprint[:12]}.json" in files
    assert f"20261118-{card.fingerprint[:12]}.md" in files
    assert "latest.json" in files
    assert card.status(NOW, card.fingerprint) == "CURRENT"


def test_scorecard_goes_stale_when_the_code_changes(tmp_path):
    out = tmp_path / "scorecards"
    card = cert.certify(out, now=NOW)
    assert card.status(NOW, "0" * 64).startswith("STALE (configuration changed)")


def test_scorecard_expires(tmp_path):
    out = tmp_path / "scorecards"
    card = cert.certify(out, now=NOW)
    after = NOW + timedelta(days=cert.VALIDITY_DAYS)
    assert card.status(after, card.fingerprint).startswith("STALE (expired)")


def test_check_missing_then_current(tmp_path):
    out = tmp_path / "scorecards"
    status, card = cert.check(out, now=NOW)
    assert status.startswith("MISSING") and card is None
    cert.certify(out, now=NOW)
    status, card = cert.check(out, now=NOW)
    assert status == "CURRENT" and card is not None


def test_second_run_diffs_against_the_first(tmp_path):
    import json

    out = tmp_path / "scorecards"
    first = cert.certify(out, now=NOW)
    second = cert.certify(out, now=NOW + timedelta(days=1))
    assert second.fingerprint == first.fingerprint  # nothing changed
    payload = json.loads((out / "latest.json").read_text())
    diff = payload["diff"]
    assert diff["previous"] == first.certified_at.isoformat()
    assert diff["strict_accuracy"]["was"] == diff["strict_accuracy"]["now"]
    assert diff["newly_failing"] == [] and diff["newly_passing"] == []
