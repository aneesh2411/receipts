"""Human-readable audit report (Markdown)."""

from __future__ import annotations

from subpoena.models import AuditReport, Claim, Finding, Verdict, VerdictStatus

_STAMP = {
    VerdictStatus.VERIFIED: "RECEIPT FOUND",
    VerdictStatus.MISMATCH: "RECEIPT DOES NOT MATCH",
    VerdictStatus.NOT_FOUND: "NO RECEIPT",
    VerdictStatus.UNVERIFIABLE: "COULD NOT CHECK",
}


def stamp(status: VerdictStatus) -> str:
    return _STAMP[status]


def claim_headline(claim: Claim) -> str:
    said = "said to caller, never logged" if claim.source.value == "transcript" else "logged claim"
    return f"{claim.type} ({said})"


def _cell(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ")


def _verdict_md(n: int, v: Verdict) -> list[str]:
    lines = [
        f"### {n}. {claim_headline(v.claim)}: {stamp(v.status)}",
        "",
        f"- **Status:** `{v.status.value}` | **Severity:** `{v.severity.value}`",
        f"- **Finding:** {v.summary}",
    ]
    if v.claim.utterance:
        lines.append(
            f'- **What the caller heard (turn {v.claim.turn_index}):** "{v.claim.utterance}"'
        )
    if v.remediation:
        lines.append(f"- **Fix:** {v.remediation}")
    if v.diffs:
        lines += ["", "| Field | Agent claimed | System of record | Match |", "|---|---|---|---|"]
        lines += [
            f"| {_cell(d.field)} | {_cell(d.claimed)} | {_cell(d.actual)} | "
            f"{'yes' if d.match else '**NO**'} |"
            for d in v.diffs
        ]
    lines += ["", "Checks:"]
    marks = {True: "pass", False: "FAIL", None: "n/a"}
    lines += [f"- `{c.name.value}`: {marks[c.passed]}. {c.detail}" for c in v.checks]
    if v.evidence:
        lines += ["", "Evidence:"]
        lines += [f"- `{e.source}` `{e.ref}`: {e.note}" for e in v.evidence]
    return [*lines, ""]


def _finding_md(n: int, f: Finding) -> list[str]:
    lines = [
        f"### F{n}. {f.kind.value}: `{f.code}`",
        "",
        f"- **Severity:** `{f.severity.value}`",
        f"- **Finding:** {f.summary}",
    ]
    if f.remediation:
        lines.append(f"- **Fix:** {f.remediation}")
    lines += [f"- Evidence `{e.source}` `{e.ref}`: {e.note}" for e in f.evidence]
    return [*lines, ""]


def render_markdown(report: AuditReport) -> str:
    s, call = report.stats, report.call
    trust = "n/a" if s.trust_score is None else f"{s.trust_score:.0%}"
    lines = [
        f"# Audit report `{report.audit_id}`",
        "",
        f"**Outcome: {report.outcome.value}**",
        "",
        f"- Call: `{call.call_id}` | Agent: `{call.agent_id}` | Caller: {call.caller.name}",
        f"- Window: {call.started_at.isoformat()} to {call.ended_at.isoformat()}",
        f"- Claims: {s.claims} | verified {s.verified}, mismatch {s.mismatch}, "
        f"not found {s.not_found}, unverifiable {s.unverifiable}",
        f"- Findings beyond claims: {s.findings} | Claim trust score: {trust} | "
        f"Highest severity: `{s.max_severity.value}`",
        f"- Audited by `{report.auditor}` at {report.created_at.isoformat()}",
    ]
    if call.provenance is not None:
        prov = call.provenance
        parts = [f"agent `{prov.agent_version}`"]
        if prov.model:
            parts.append(f"model `{prov.model}`")
        if prov.prompt_version:
            parts.append(f"prompt `{prov.prompt_version}`")
        parts.append(f"human handoffs: {len(prov.human_handoffs)}")
        lines.append("- Provenance (platform-supplied, unverified): " + " | ".join(parts))
    lines += [
        "",
        "## Claims",
        "",
    ]
    if not report.verdicts:
        lines += ["The agent made no claims in this call.", ""]
    for n, verdict in enumerate(report.verdicts, start=1):
        lines += _verdict_md(n, verdict)
    lines += ["## Findings beyond claims", ""]
    if not report.findings:
        lines += ["None. Every write the agent made is accounted for by a claim.", ""]
    for n, finding in enumerate(report.findings, start=1):
        lines += _finding_md(n, finding)
    lines += ["## Audit trail", ""]
    lines += [f"{e.seq}. `{e.stage}` {e.message}" for e in report.trail]
    if report.seal:
        signed = f"signed (key `{report.seal.key_id}`)" if report.seal.signature else "unsigned"
        lines += [
            "",
            "## Seal",
            "",
            f"- content `{report.seal.content_hash}`",
            f"- chain `{report.seal.chain_hash}` (prev `{report.seal.prev_hash[:16]}...`)",
            f"- {signed}",
        ]
    return "\n".join(lines) + "\n"
