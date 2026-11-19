"""Exercise the JUnit exporter against the committed eval results."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest

from subpoena.scenarios import GOLDEN

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "evals" / "results" / "latest.json"


def run_export(*args: Path | str) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        [sys.executable, "scripts/export_evals_junit.py", *args],
        cwd=ROOT,
        capture_output=True,
        check=False,
    )


def test_default_export():
    result = run_export()
    assert result.returncode == 0, result.stderr
    assert result.stderr == b""

    golden = json.loads(RESULTS.read_bytes())["golden"]
    suite = ET.fromstring(result.stdout)
    assert suite.tag == "testsuite"
    cases = suite.findall("testcase")
    assert int(suite.attrib["tests"]) == len(cases) == len(GOLDEN) == golden["calls"]
    assert [case.attrib["name"] for case in cases] == [scenario.id for scenario in GOLDEN]

    failures = {
        case.attrib["name"]: case.find("failure")
        for case in cases
        if case.find("failure") is not None
    }
    assert {"gap-vague-spoken-promise", "gap-garbled-handoff"} <= failures.keys()
    assert int(suite.attrib["failures"]) == len(failures) == len(golden["failures"])
    for failure in golden["failures"]:
        element = failures[failure["scenario"]]
        assert element.text == "\n".join(failure["problems"])

    properties = {
        prop.attrib["name"]: prop.attrib["value"] for prop in suite.findall("./properties/property")
    }
    for key in ("call_strict_accuracy", "call_accuracy"):
        assert properties[key] == str(golden[key])

    rerun = run_export()
    assert rerun.returncode == 0, rerun.stderr
    assert rerun.stdout == result.stdout


def test_explicit_paths_and_xml_escaping(tmp_path):
    results = json.loads(RESULTS.read_bytes())
    scenario = results["golden"]["failures"][0]
    scenario["problems"] = ['Expected <book> & "confirm"', "Received > instead"]
    source = tmp_path / "results.json"
    source.write_text(json.dumps(results), encoding="utf-8")
    output = tmp_path / "results.xml"

    result = run_export(source, "-o", output)

    assert result.returncode == 0, result.stderr
    assert result.stdout == b""
    suite = ET.parse(output).getroot()
    failure = suite.find(f"./testcase[@name='{scenario['scenario']}']/failure")
    assert failure is not None
    assert failure.text == failure.attrib["message"] == "\n".join(scenario["problems"])


@pytest.mark.parametrize("contents", [None, b"{ broken", b'{"golden": {}}'])
def test_invalid_input(tmp_path, contents):
    source = tmp_path / "invalid.json"
    if contents is not None:
        source.write_bytes(contents)

    result = run_export(source)

    assert result.returncode != 0
    assert result.stdout == b""
    assert b"eval results" in result.stderr
    assert b"invalid.json" in result.stderr
