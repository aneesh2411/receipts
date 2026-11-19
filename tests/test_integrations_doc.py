"""Keep the integration guide's links and runnable examples tied to the repo."""

import re
import shlex
import sys
from pathlib import Path
from runpy import run_path

import pytest

from subpoena.cli import main

ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "docs" / "INTEGRATIONS.md"
TEXT = DOC.read_text(encoding="utf-8")
LINKS = re.findall(r"\[[^\]\n]+\]\(([^)\n]+)\)", TEXT)
PYTHON = re.findall(r"^```python\n(.*?)^```$", TEXT, re.MULTILINE | re.DOTALL)
COMMANDS = re.findall(r"^```bash\n(.*?)^```$", TEXT, re.MULTILINE | re.DOTALL)


def test_all_integration_paths_have_examples():
    assert len(PYTHON) == 4
    assert len(COMMANDS) == 2


@pytest.mark.parametrize("target", LINKS)
def test_local_links_point_to_files(target):
    assert (DOC.parent / target).is_file(), target


@pytest.mark.parametrize("example", PYTHON)
def test_python_examples_import_and_run(example, monkeypatch):
    monkeypatch.chdir(ROOT)
    exec(compile(example, str(DOC), "exec"), {})


@pytest.mark.parametrize("example", COMMANDS)
def test_cli_examples_parse_and_run(example, monkeypatch, capsys):
    monkeypatch.chdir(ROOT)
    argv = shlex.split(example.replace("\\\n", "").strip())
    if argv[0] == "subpoena":
        assert main(argv[1:]) == 0
    else:
        assert argv[:2] == ["python", "scripts/verify_seal.py"]
        monkeypatch.setattr(sys, "argv", argv[1:])
        with pytest.raises(SystemExit) as result:
            run_path(argv[1], run_name="__main__")
        assert result.value.code == 0
        assert "VERDICT PASS" in capsys.readouterr().out
