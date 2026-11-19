"""Repair queue: grouping, ranking and the no-invented-numbers rule."""

from __future__ import annotations

from subpoena.api.repair_queue import build_repair_queue
from subpoena.scenarios import BY_ID, run_scenario


def _reports(*ids: str):
    return [run_scenario(BY_ID[i]).report for i in ids]


def test_clean_calls_produce_no_groups() -> None:
    queue = build_repair_queue(_reports("clean-book", "clean-cancel"))
    assert queue == {"audits_scanned": 2, "groups": []}


def test_recurring_shape_is_counted_across_audits() -> None:
    queue = build_repair_queue(
        _reports("fault-phantom-booking", "fault-phantom-booking", "clean-book")
    )
    top = queue["groups"][0]
    assert top["shape"] == "AppointmentBooked:NOT_FOUND"
    assert top["occurrences"] == 2
    assert top["calls_affected"] == 1  # both audits are of the same call id
    assert queue["audits_scanned"] == 3
    assert top["evidence"] and top["evidence"][0]["result_pointer"].startswith("/verdicts/")


def test_ranking_puts_severity_before_frequency() -> None:
    queue = build_repair_queue(_reports("fault-double-book", "fault-phantom-booking"))
    ranks = ["INFO", "LOW", "MEDIUM", "HIGH", "CRITICAL"]
    sev = [ranks.index(g["worst_severity"]) for g in queue["groups"]]
    assert sev == sorted(sev, reverse=True)


def test_output_carries_no_money_or_time_estimates() -> None:
    queue = build_repair_queue(_reports("fault-phantom-booking"))
    text = str(queue).lower()
    assert "revenue" not in text and "$" not in text and "saved" not in text
    for g in queue["groups"]:
        assert set(g) == {
            "shape", "origin", "occurrences", "calls_affected",
            "worst_severity", "remediable", "remediation", "evidence",
        }  # fmt: skip


def test_is_deterministic() -> None:
    def view(queue):
        return [(g["shape"], g["occurrences"], g["worst_severity"]) for g in queue["groups"]]

    a = build_repair_queue(_reports("fault-phantom-booking", "fault-wrong-time"))
    b = build_repair_queue(_reports("fault-wrong-time", "fault-phantom-booking"))
    assert view(a) == view(b)
