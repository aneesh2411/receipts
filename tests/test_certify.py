"""Certification scorecards: fingerprinting, staleness, diffs."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from shutil import copytree

import pytest

from subpoena.evals import certify as cert

NOW = datetime(2026, 11, 18, 12, 0, tzinfo=UTC)


@pytest.fixture
def root(tmp_path):
    repo = tmp_path / "repo"
    source = cert.repo_root()
    copytree(source / "src" / "subpoena", repo / "src" / "subpoena")
    (repo / "pyproject.toml").write_bytes((source / "pyproject.toml").read_bytes())
    return repo


@pytest.mark.parametrize(
    "relative_path",
    ["src/subpoena/auditor/extractor.py", "src/subpoena/scenarios/golden.py", "pyproject.toml"],
)
def test_fingerprint_changes_when_input_content_changes(root, relative_path):
    base = cert.fingerprint(root)
    target = root / relative_path
    target.write_bytes(target.read_bytes() + b"\n# fingerprint input changed\n")
    assert cert.fingerprint(root) != base


def test_fingerprint_tracks_source_addition_rename_and_removal(root):
    base = cert.fingerprint(root)
    assert cert.fingerprint(root) == base
    new_source = root / "src" / "subpoena" / "auditor" / "new_module.py"
    new_source.write_bytes(b"VALUE = 1\n")
    added = cert.fingerprint(root)
    assert added != base

    renamed = new_source.with_name("renamed_module.py")
    new_source.rename(renamed)
    assert cert.fingerprint(root) not in {base, added}
    renamed.unlink()
    assert cert.fingerprint(root) == base


def test_fingerprint_ignores_generated_files(root):
    base = cert.fingerprint(root)
    for relative_path in (
        "src/subpoena/auditor/__pycache__/extractor.pyc",
        "src/subpoena/auditor/__pycache__/generated.py",
        "src/subpoena/build/lib/generated.py",
        "src/subpoena/auditor/generated.json",
        "evals/results/generated.json",
    ):
        target = root / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"generated")
    assert cert.fingerprint(root) == base


def test_certify_writes_json_markdown_and_latest(tmp_path):
    out = tmp_path / "scorecards"
    card = cert.certify(out, now=NOW)
    files = {p.name for p in out.iterdir()}
    assert f"20261118-{card.fingerprint[:12]}.json" in files
    assert f"20261118-{card.fingerprint[:12]}.md" in files
    assert "latest.json" in files
    assert card.status(NOW, card.fingerprint) == "CURRENT"


def test_scorecard_goes_stale_when_the_code_changes(tmp_path, root):
    out = tmp_path / "scorecards"
    cert.certify(out, now=NOW, root=root)
    (root / "src" / "subpoena" / "auditor" / "extractor.py").write_bytes(b"# changed\n")
    status, _ = cert.check(out, now=NOW, root=root)
    assert status == "STALE (configuration changed)"


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
