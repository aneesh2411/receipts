import json
import re
import shlex
import subprocess
import sys
from html import unescape
from pathlib import Path
from urllib.parse import urlsplit

from subpoena.auditor.seal import Sealer

ROOT = Path(__file__).resolve().parents[1]
DEMO = ROOT / "docs" / "demo"
PAGE = (DEMO / "verify.html").read_text(encoding="utf-8")


def code_block(block_id):
    match = re.search(rf'<pre id="{block_id}"[^>]*><code>(.*?)</code></pre>', PAGE, re.S)
    assert match, f"Missing code block {block_id}"
    return unescape(match[1])


def test_audit_download_and_key_id():
    audit_names = set(re.findall(r"\baudit-[\w-]+\.json\b", PAGE))
    assert audit_names
    key_id = re.search(r'<code id="demo-key-id">([^<]+)</code>', PAGE)
    assert key_id

    curl, flags, url = shlex.split(code_block("download"))
    assert (curl, flags) == ("curl", "-fsSLO")
    download = urlsplit(url)
    assert download.scheme == "https"
    assert download.netloc == "aneesh2411.github.io"
    audit_name = Path(download.path).name
    assert download.path == f"/subpoena/demo/data/{audit_name}"
    assert f'href="data/{audit_name}"' in PAGE

    command = shlex.split(code_block("verify-original").splitlines()[0])
    assert command[2] == audit_name
    assert Sealer(command[-1].encode()).key_id == key_id[1]

    for name in audit_names:
        report = json.loads((DEMO / "data" / name).read_text(encoding="utf-8"))
        assert report["seal"]["key_id"] == key_id[1]


def test_walkthrough_commands_and_output(tmp_path):
    def run_python(command):
        python, *args = shlex.split(command)
        assert python == "python"
        if args[0] == "scripts/verify_seal.py":
            args[0] = str(ROOT / args[0])
        return subprocess.run(
            [sys.executable, *args], cwd=tmp_path, capture_output=True, text=True, check=False
        )

    audit_name = Path(urlsplit(shlex.split(code_block("download"))[-1]).path).name
    (tmp_path / audit_name).write_bytes((DEMO / "data" / audit_name).read_bytes())

    for sample, expected_exit in [("original", 0), ("tampered", 1)]:
        if sample == "tampered":
            edit = run_python(code_block("edit-copy"))
            assert edit.returncode == 0, edit.stderr

        command, exit_command = code_block(f"verify-{sample}").splitlines()
        assert shlex.split(command)[1] == "scripts/verify_seal.py"
        assert exit_command == 'echo "Exit code: $?"'
        result = run_python(command)
        assert result.returncode == expected_exit, result.stdout + result.stderr
        assert f"{result.stdout}Exit code: {result.returncode}" == code_block(f"{sample}-output")
