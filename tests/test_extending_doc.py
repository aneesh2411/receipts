"""Keep the contributor guide's walkthroughs executable."""

import re
from datetime import timedelta
from pathlib import Path

import pytest

from subpoena.models import VerdictStatus
from subpoena.scenarios import BY_ID, Scenario
from subpoena.sor.base import SystemOfRecordReader

ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "docs" / "EXTENDING.md"
TEXT = DOC.read_text(encoding="utf-8")
LINKS = re.findall(r"\[[^\]\n]+\]\(([^)\n]+)\)", TEXT)
PYTHON = re.findall(r"^```python\n(.*?)^```$", TEXT, re.MULTILINE | re.DOTALL)


@pytest.mark.parametrize("target", LINKS)
def test_local_links_point_to_files(target):
    assert (DOC.parent / target).is_file(), target


def test_reader_walkthrough(monkeypatch):
    reader_example, _ = PYTHON
    monkeypatch.chdir(ROOT)
    namespace = {}
    exec(compile(reader_example, str(DOC), "exec"), namespace)

    reader = namespace["reader"]
    ticket = namespace["ticket"]
    creation = namespace["creation"]
    assert isinstance(reader, SystemOfRecordReader)
    assert reader.tickets is namespace["tickets"]
    assert reader.tickets.list_tickets(patient_id=ticket.patient_id) == [ticket]
    assert reader.tickets.list_tickets(patient_id="unknown") == []
    assert reader.tickets.changes(creation.at, creation.at) == [creation]
    later = creation.at + timedelta(seconds=1)
    assert reader.tickets.changes(later, later) == []
    (verdict,) = namespace["report"].verdicts
    assert verdict.status is VerdictStatus.VERIFIED


def test_golden_walkthrough(monkeypatch):
    _, scenario_example = PYTHON
    monkeypatch.chdir(ROOT)
    namespace = {}
    exec(compile(scenario_example, str(DOC), "exec"), namespace)

    scenario = namespace["scenario"]
    assert isinstance(scenario, Scenario)
    assert scenario.id not in BY_ID
    assert scenario.expected_claims == tuple(
        (kind, status) for kind, status, _ in scenario.expected_claims_v2
    )
    assert namespace["positional"].problems == ()
    assert namespace["identity"].problems == ()
