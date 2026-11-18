"""Seal verification reports integrity and authentication as separate states."""

from __future__ import annotations

from subpoena.auditor import GENESIS, Authentication, Integrity, Sealer, render_markdown
from subpoena.models import AuditReport, Outcome
from subpoena.scenarios import BY_ID, HERO, run_scenario

KEY = b"test-signing-key"
OTHER = b"another-key"


def _hero(sealer: Sealer | None = None) -> AuditReport:
    return run_scenario(BY_ID[HERO], sealer=sealer).report


def test_unsigned_report_lenient_and_strict():
    report = _hero()
    check = Sealer().verify(report)
    assert check.ok
    assert check.integrity is Integrity.INTACT
    assert check.authentication is Authentication.UNSIGNED
    strict = Sealer().verify(report, strict=True)
    assert not strict.ok and strict.authentication is Authentication.UNSIGNED


def test_signed_report_without_a_key_is_unverifiable():
    report = _hero(Sealer(KEY))
    check = Sealer().verify(report)
    assert check.ok  # lenient: intact, and there is no key to check against
    assert check.integrity is Integrity.INTACT
    assert check.authentication is Authentication.UNVERIFIABLE
    strict = Sealer().verify(report, strict=True)
    assert not strict.ok and strict.authentication is Authentication.UNVERIFIABLE


def test_signed_report_with_the_right_key_is_authenticated():
    report = _hero(Sealer(KEY))
    check = Sealer(KEY).verify(report)
    assert check.ok and check.authentication is Authentication.AUTHENTICATED
    assert Sealer(KEY).verify(report, strict=True).ok


def test_wrong_key_and_missing_signature_are_invalid():
    signed = _hero(Sealer(KEY))
    wrong = Sealer(OTHER).verify(signed)
    assert not wrong.ok
    assert wrong.integrity is Integrity.INTACT
    assert wrong.authentication is Authentication.INVALID
    missing = Sealer(KEY).verify(_hero())  # unsigned report, key expected
    assert not missing.ok and missing.authentication is Authentication.INVALID
    assert not Sealer(KEY).verify(_hero(), strict=True).ok


def test_altered_content_and_broken_links_are_altered():
    report = _hero(Sealer(KEY))
    tampered = report.model_copy(update={"outcome": Outcome.CLEAN})
    check = Sealer(KEY).verify(tampered)
    assert not check.ok and check.integrity is Integrity.ALTERED
    linked = _hero(Sealer(KEY))
    broken = Sealer(KEY).verify(linked, expected_prev="f" * 64)
    assert not broken.ok and broken.integrity is Integrity.ALTERED
    assert broken.authentication is Authentication.AUTHENTICATED  # seal itself is genuine


def test_unsealed_report_reports_unsealed():
    report = _hero().model_copy(update={"seal": None})
    check = Sealer(KEY).verify(report)
    assert not check.ok
    assert check.integrity is Integrity.UNSEALED
    assert check.authentication is Authentication.UNSIGNED


def test_genesis_link_still_required_on_the_first_report():
    report = _hero(Sealer(KEY))
    assert report.seal is not None and report.seal.prev_hash == GENESIS
    assert Sealer(KEY).verify(report, expected_prev=GENESIS, strict=True).ok


def test_markdown_renders_the_seal_state():
    signed = render_markdown(_hero(Sealer(KEY)))
    assert "signed (key `" in signed
    unsigned = render_markdown(_hero())
    assert "unsigned (tamper-evident, not authenticated)" in unsigned
    unsealed = render_markdown(_hero().model_copy(update={"seal": None}))
    assert "unsealed" in unsealed
