#!/usr/bin/env python3
"""Bake the live demo's API responses to static files for the GitHub Pages site.

docs/demo/ is the replay view with no server: the same golden scenarios, played
and audited exactly as POST /demo/scenarios/{id}/run does, written to JSON the
static page fetches. Regenerate after any auditor or scenario change:

    python scripts/export_demo.py
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from receipts.auditor import RuleBasedExtractor, Sealer
from receipts.auditor.render import render_markdown
from receipts.scenarios import BY_ID
from receipts.scenarios.world import audit_call, build_world, run_suspect

DEFAULT_OUT = Path(__file__).resolve().parent.parent / "docs" / "demo" / "data"

# Fixed key so the baked seals are deterministic from one export to the next.
SEALING_KEY = b"receipts-pages-demo"


def export(out: Path) -> list[str]:
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    sealer, extractor = Sealer(SEALING_KEY), RuleBasedExtractor()
    index = []
    for scenario in BY_ID.values():
        world = build_world(scenario)
        try:
            result = run_suspect(scenario, world)
            report = audit_call(scenario, world, result, extractor=extractor, sealer=sealer)
        finally:
            world.store.close()
        payload = json.dumps(report.model_dump(mode="json"), indent=1)
        (out / f"run-{scenario.id}.json").write_text(payload)
        (out / f"audit-{report.audit_id}.json").write_text(payload)
        (out / f"report-{report.audit_id}.md").write_text(render_markdown(report))
        index.append(
            {
                "id": scenario.id,
                "title": scenario.title,
                "story": scenario.story,
                "group": scenario.id.split("-", 1)[0],
                "faults": sorted(m.value for m in scenario.fault_modes),
                "known_gap": scenario.known_gap,
            }
        )
    (out / "scenarios.json").write_text(json.dumps(index, indent=1))
    return sorted(p.name for p in out.iterdir())


def main() -> None:
    files = export(DEFAULT_OUT)
    print(f"wrote {len(files)} files to {DEFAULT_OUT}")


if __name__ == "__main__":
    main()
