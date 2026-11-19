#!/usr/bin/env python3
"""Export the recorded golden eval results as JUnit XML."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from xml.etree import ElementTree as ET

from subpoena.scenarios import GOLDEN

DEFAULT_RESULTS = Path(__file__).resolve().parents[1] / "evals" / "results" / "latest.json"


def to_junit(results: object) -> bytes:
    if not isinstance(results, dict) or not isinstance(results.get("golden"), dict):
        raise ValueError("expected a golden results object")
    golden = results["golden"]
    scenario_ids = tuple(scenario.id for scenario in GOLDEN)
    calls = golden.get("calls")
    if type(calls) is not int or calls != len(scenario_ids):
        raise ValueError(f"golden.calls must match the {len(scenario_ids)} golden scenarios")

    failures = golden.get("failures")
    if not isinstance(failures, list):
        raise ValueError("golden.failures must be a list")
    problems_by_scenario: dict[str, list[str]] = {}
    for failure in failures:
        if not isinstance(failure, dict):
            raise ValueError("each golden failure must be an object")
        scenario_id = failure.get("scenario")
        if not isinstance(scenario_id, str) or scenario_id not in scenario_ids:
            raise ValueError(f"unknown golden failure scenario: {scenario_id!r}")
        if scenario_id in problems_by_scenario:
            raise ValueError(f"duplicate golden failure for {scenario_id!r}")
        problems = failure.get("problems")
        if (
            not isinstance(problems, list)
            or not problems
            or any(not isinstance(problem, str) or not problem.strip() for problem in problems)
        ):
            raise ValueError(f"expected a list of problem messages for {scenario_id!r}")
        problems_by_scenario[scenario_id] = problems

    suite = ET.Element(
        "testsuite",
        name="golden",
        tests=str(calls),
        failures=str(len(problems_by_scenario)),
        errors="0",
        skipped="0",
    )
    properties = ET.SubElement(suite, "properties")
    for key in ("call_strict_accuracy", "call_accuracy"):
        if key == "call_accuracy" and key not in golden:
            continue
        accuracy = golden.get(key)
        if type(accuracy) not in (int, float) or not 0 <= accuracy <= 1:
            raise ValueError(f"golden.{key} must be a number between 0 and 1")
        ET.SubElement(properties, "property", name=key, value=str(accuracy))

    for scenario_id in scenario_ids:
        case = ET.SubElement(suite, "testcase", classname="golden", name=scenario_id)
        if scenario_id in problems_by_scenario:
            message = "\n".join(problems_by_scenario[scenario_id])
            ET.SubElement(case, "failure", message=message).text = message

    ET.indent(suite)
    output = ET.tostring(suite, encoding="utf-8", xml_declaration=True) + b"\n"
    # ElementTree escapes markup but can serialize characters forbidden in XML 1.0.
    try:
        ET.fromstring(output)
    except ET.ParseError as exc:
        raise ValueError(f"results contain text that XML 1.0 cannot represent: {exc}") from exc
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("results_json", nargs="?", type=Path, default=DEFAULT_RESULTS)
    parser.add_argument("-o", type=Path, help="write JUnit XML to this file")
    args = parser.parse_args()

    try:
        data = args.results_json.read_bytes()
    except OSError as exc:
        parser.exit(1, f"Unable to read eval results {args.results_json}: {exc}\n")

    try:
        output = to_junit(json.loads(data))
    except (ValueError, RecursionError) as exc:
        parser.exit(1, f"Invalid eval results {args.results_json}: {exc}\n")

    try:
        if args.o is None:
            sys.stdout.buffer.write(output)
        else:
            args.o.write_bytes(output)
    except OSError as exc:
        parser.exit(1, f"Unable to write JUnit XML: {exc}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
