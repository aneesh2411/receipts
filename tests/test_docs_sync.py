"""Displayed metrics must be generated from the eval artifacts, never hand-copied."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_docs_metrics_are_in_sync():
    proc = subprocess.run(
        [sys.executable, "scripts/sync_docs.py", "--check"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, (
        f"Displayed metrics have drifted from the eval artifacts: {proc.stdout.strip()}\n"
        "Run `python scripts/sync_docs.py` to regenerate them."
    )
