"""Command line: demo, eval, serve, verify."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from subpoena.auditor import Sealer
from subpoena.auditor.render import claim_headline, stamp
from subpoena.evals import run_all
from subpoena.evals.run import render_markdown as render_eval
from subpoena.models import AuditReport, Outcome, Severity, Verdict, VerdictStatus
from subpoena.scenarios import BY_ID, GOLDEN, HERO, run_scenario

_STATUS_STYLE = {
    VerdictStatus.VERIFIED: "bold green",
    VerdictStatus.MISMATCH: "bold yellow",
    VerdictStatus.NOT_FOUND: "bold red",
    VerdictStatus.UNVERIFIABLE: "bold magenta",
}
_SEVERITY_STYLE = {
    Severity.INFO: "dim",
    Severity.LOW: "cyan",
    Severity.MEDIUM: "yellow",
    Severity.HIGH: "red",
    Severity.CRITICAL: "bold white on red",
}
_OUTCOME_STYLE = {
    Outcome.CLEAN: "bold green",
    Outcome.DISCREPANCIES: "bold red",
    Outcome.INCONCLUSIVE: "bold magenta",
}


def _signing_key() -> bytes | None:
    key = os.environ.get("SUBPOENA_SIGNING_KEY")
    return key.encode() if key else None


# ----------------------------------- demo ---------------------------------- #


def _verdict_panel(n: int, v: Verdict) -> Panel:
    body = Table.grid(padding=(0, 1))
    body.add_row(Text(v.summary))
    if v.diffs:
        table = Table(show_header=True, header_style="bold", box=None, pad_edge=False)
        table.add_column("field")
        table.add_column("agent claimed")
        table.add_column("system of record")
        table.add_column("")
        for d in v.diffs:
            mark = Text("match", style="green") if d.match else Text("DIFFERS", style="bold red")
            style = None if d.match else "red"
            table.add_row(d.field, d.claimed, Text(d.actual, style=style or ""), mark)
        body.add_row(table)
    for e in v.evidence:
        body.add_row(Text(f"evidence  {e.source}:{e.ref}  {e.note}", style="dim"))
    if v.remediation:
        body.add_row(Text(f"fix  {v.remediation}", style="italic"))
    title = Text.assemble(
        (f" {n}. {claim_headline(v.claim)}  ", "bold"),
        (f" {stamp(v.status)} ", _STATUS_STYLE[v.status] + " reverse"),
        ("  "),
        (f" {v.severity.value} ", _SEVERITY_STYLE[v.severity]),
    )
    return Panel(body, title=title, title_align="left", border_style=_STATUS_STYLE[v.status])


def play(report: AuditReport, console: Console, *, title: str, story: str, delay: float) -> None:
    def pause(scale: float = 1.0) -> None:
        if delay:
            time.sleep(delay * scale)

    console.print()
    console.print(Panel(Text(story), title=f"SUBPOENA  |  {title}", border_style="cyan"))
    console.rule("[bold]1. THE CALL[/]  what the caller heard")
    by_turn: dict[int, list[Verdict]] = {}
    for v in report.verdicts:
        by_turn.setdefault(v.claim.turn_index, []).append(v)
    for turn in report.call.transcript:
        who = Text(f"{turn.speaker:>7}  ", style="bold blue" if turn.speaker == "agent" else "bold")
        console.print(who + Text(turn.text))
        for v in by_turn.get(turn.index, []):
            console.print(Text(f"           claim: {claim_headline(v.claim)}", style="cyan"))
        pause()

    console.rule("[bold]2. THE AUDIT[/]  what the system of record shows")
    for event in report.trail:
        if event.stage == "evidence":
            console.print(Text(f"  {event.message}", style="dim"))
    pause(2)
    for n, v in enumerate(report.verdicts, start=1):
        console.print(_verdict_panel(n, v))
        pause(2)
    if not report.verdicts:
        console.print("  The agent made no claims.")

    console.rule("[bold]3. BEYOND THE CLAIMS[/]  writes nobody mentioned, rules broken")
    if not report.findings:
        console.print("  Nothing. Every write the agent made is covered by a claim.")
    for f in report.findings:
        console.print(
            Panel(
                Text(f.summary + (f"\nfix  {f.remediation}" if f.remediation else "")),
                title=Text.assemble(
                    (f" {f.kind.value}  {f.code} ", "bold"),
                    (f" {f.severity.value} ", _SEVERITY_STYLE[f.severity]),
                ),
                title_align="left",
                border_style="red",
            )
        )
        pause(2)

    s = report.stats
    trust = "n/a" if s.trust_score is None else f"{s.trust_score:.0%}"
    seal = report.seal.chain_hash[:16] if report.seal else "unsealed"
    console.rule("[bold]VERDICT[/]")
    console.print(
        Text.assemble(
            ("  Outcome: ", "bold"),
            (report.outcome.value, _OUTCOME_STYLE[report.outcome]),
            (
                f"   claims {s.claims}: {s.verified} verified, {s.mismatch} mismatch, "
                f"{s.not_found} not found, {s.unverifiable} unverifiable"
                f"   findings {s.findings}   trust {trust}"
            ),
        )
    )
    console.print(Text(f"  Sealed: sha256 chain {seal}...", style="dim"))
    console.print()


def cmd_demo(args: argparse.Namespace, console: Console) -> int:
    if args.list:
        table = Table("id", "title", "faults", title="Scenarios")
        for s in GOLDEN:
            table.add_row(s.id, s.title, ", ".join(sorted(m.value for m in s.fault_modes)) or "-")
        console.print(table)
        return 0
    scenario = BY_ID.get(args.scenario)
    if scenario is None:
        console.print(f"[red]Unknown scenario '{args.scenario}'. Try: subpoena demo --list[/]")
        return 2
    run = run_scenario(scenario, sealer=Sealer(_signing_key()))
    play(
        run.report,
        console,
        title=scenario.title,
        story=scenario.story,
        delay=0 if args.fast else 0.6,
    )
    if args.json:
        Path(args.json).write_text(run.report.model_dump_json(indent=2))
        console.print(f"Report written to {args.json}")
    return 0


# ----------------------------------- eval ---------------------------------- #


def cmd_eval(args: argparse.Namespace, console: Console) -> int:
    result = run_all(fuzz_n=args.fuzz, fuzz_seed=args.seed)
    table = Table(title="Eval: claim-level detection and call-level accuracy")
    for col in ("auditor", "calls", "claim P", "claim R", "exact status", "finding R",
                "call acc", "call strict"):  # fmt: skip
        table.add_column(col)

    def pct(x: float | None) -> str:
        return f"{x:.1%}" if x is not None else "n/a"

    for s in (result.golden, result.baseline, result.fuzz):
        table.add_row(
            s.label, str(s.calls), pct(s.claims.precision), pct(s.claims.recall),
            pct(s.status_accuracy), pct(s.findings.recall), pct(s.call_accuracy),
            pct(s.strict_accuracy),
        )  # fmt: skip
    console.print(table)

    known = {s.id for s in GOLDEN if s.known_gap}
    unexpected = [r for r in result.golden.failures if r.scenario_id not in known]
    fixed = [sid for sid in known if sid not in {r.scenario_id for r in result.golden.failures}]
    for run in result.golden.failures:
        tag = "known gap" if run.scenario_id in known else "UNEXPECTED"
        console.print(
            f"  [{'yellow' if tag == 'known gap' else 'red'}]{tag}[/] "
            f"{run.scenario_id}: {'; '.join(run.problems)}"
        )
    for run in result.fuzz.failures[:20]:
        console.print(f"  [red]FUZZ[/] {run.scenario_id}: {'; '.join(run.problems)}")
    for sid in fixed:
        console.print(f"  [green]known gap now passes[/] {sid}: remove its known_gap label")

    if args.json:
        Path(args.json).parent.mkdir(parents=True, exist_ok=True)
        Path(args.json).write_text(json.dumps(result.as_dict(), indent=2) + "\n")
    if args.report:
        Path(args.report).parent.mkdir(parents=True, exist_ok=True)
        Path(args.report).write_text(render_eval(result))
    ok = not unexpected and not result.fuzz.failures
    console.print("[green]PASS[/]" if ok else "[red]FAIL: unexpected eval failures[/]")
    return 0 if ok else 1


# ------------------------------ serve / verify ----------------------------- #


LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}


def unsafe_bind_reason(host: str, api_key: str | None) -> str | None:
    """Why serving this way would expose an unauthenticated API, or None if safe."""
    if host in LOOPBACK_HOSTS or api_key:
        return None
    return (
        f"binding to {host} exposes the API to the network but SUBPOENA_API_KEY is "
        "not set, so every endpoint - including writes - would be open. Set "
        "SUBPOENA_API_KEY or serve on 127.0.0.1."
    )


def cmd_certify(args: argparse.Namespace, console: Console) -> int:
    from subpoena.evals import certify as cert

    if args.check:
        status, card = cert.check()
        color = "green" if status == "CURRENT" else "red"
        console.print(f"[{color}]{status}[/]")
        if card is not None:
            console.print(
                f"  latest: certified {card.certified_at:%Y-%m-%d}, "
                f"expires {card.expires_at:%Y-%m-%d}, fingerprint {card.fingerprint[:16]}..."
            )
        return 0 if status == "CURRENT" else 1
    card = cert.certify()
    console.print(
        f"[green]CERTIFIED[/] strict accuracy {card.golden.strict_accuracy:.1%} "
        f"over {card.golden.calls} golden calls"
    )
    console.print(
        f"  scorecard written to {cert.DEFAULT_DIR} "
        f"(fingerprint {card.fingerprint[:16]}..., valid {cert.VALIDITY_DAYS} days)"
    )
    return 0


def cmd_serve(args: argparse.Namespace, console: Console) -> int:  # pragma: no cover
    import uvicorn

    from subpoena.api import create_app

    if reason := unsafe_bind_reason(args.host, os.environ.get("SUBPOENA_API_KEY") or None):
        console.print(f"[red]Refusing to serve.[/red] {reason}")
        return 2
    console.print(f"Replay view: http://{args.host}:{args.port}/   API docs: /docs")
    uvicorn.run(create_app(), host=args.host, port=args.port, log_level="info")
    return 0


def cmd_verify(args: argparse.Namespace, console: Console) -> int:
    try:
        report = AuditReport.model_validate_json(Path(args.file).read_text())
    except (OSError, ValueError) as exc:
        console.print(f"[red]Cannot read report: {exc}[/]")
        return 2
    check = Sealer(_signing_key()).verify(report)
    console.print(
        f"[{'green' if check.ok else 'red'}]{'VALID' if check.ok else 'INVALID'}[/] "
        f"{report.audit_id}: {check.reason}"
    )
    return 0 if check.ok else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="subpoena", description="Every claim needs a receipt.")
    sub = parser.add_subparsers(dest="command", required=True)

    demo = sub.add_parser("demo", help="watch the suspect take a call and the auditor check it")
    demo.add_argument("--scenario", default=HERO)
    demo.add_argument("--fast", action="store_true", help="no pauses")
    demo.add_argument("--list", action="store_true", help="list scenarios")
    demo.add_argument("--json", help="also write the sealed report to this file")
    demo.set_defaults(func=cmd_demo)

    ev = sub.add_parser("eval", help="score the auditor on the golden set and fuzzed calls")
    ev.add_argument("--fuzz", type=int, default=500, help="number of fuzzed calls")
    ev.add_argument("--seed", type=int, default=7)
    ev.add_argument("--json", help="write metrics as JSON")
    ev.add_argument("--report", help="write the Markdown eval report")
    ev.set_defaults(func=cmd_eval)

    cert = sub.add_parser(
        "certify", help="write a golden-set scorecard pinned to the current configuration"
    )
    cert.add_argument(
        "--check",
        action="store_true",
        help="exit 1 if the latest scorecard is stale or missing",
    )
    cert.set_defaults(func=cmd_certify)

    serve = sub.add_parser("serve", help="run the API and replay view")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)
    serve.set_defaults(func=cmd_serve)

    verify = sub.add_parser("verify", help="check a saved report's seal")
    verify.add_argument("file")
    verify.set_defaults(func=cmd_verify)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args, Console())


if __name__ == "__main__":
    sys.exit(main())
