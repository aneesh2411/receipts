# Roadmap

Where Receipts is, what comes next, and the plan for the product surfaces: a web console
and a mobile app.

## Where it stands (v0.1)

Working today:

- Simulated receptionist with 22 fault modes.
- SQLite system of record with a trigger-written, append-only change journal.
- Auditor: claim verdicts with evidence, unclaimed writes, policy checks, sealed reports.
- 52 golden scenarios, 500-call fuzzing, naive baseline, ablations.
- FastAPI service, CLI demo, single-page replay view.
- 228 tests, 99% line coverage, lint clean.

Not done:

- No real adapters (Google Calendar is a documented stub).
- The live-model transcript reader has not been run against a real model.
- An independent code review found open correctness issues. They are listed in
  [FAILURE_ANALYSIS.md](FAILURE_ANALYSIS.md) section 4 and are the first item below.

## Now: make the verdicts trustworthy (v0.2)

Nothing else matters until a `VERIFIED` can be relied on.

1. **Fix the open review findings.** Six ways to get a false `VERIFIED` or a false
   accusation, each with a reproduction. Add a regression test and a golden scenario for
   each.
2. **Score findings by code, not by kind.** Today a wrong unclaimed write can still count
   as a correct one.
3. **Report undefined precision as n/a**, not 100%.
4. **Harden the API**: refuse to bind a public address without an API key, return 409 when
   an inline call conflicts with a stored one, lock the store swap in the demo stage
   endpoint.

Done when: the review's reproductions all fail to reproduce, and the eval still passes.

## Next: touch reality (v0.3)

1. **One real adapter**: Google Calendar reader with a snapshot cache for before-images.
   Re-run the golden set through it.
2. **Live-model transcript reader, measured.** Real, messy transcripts. Precision tracked
   separately from recall. A model that invents claims is worse than one that misses them.
3. **Overlapping calls.** Decide and test attribution when one agent identity handles two
   calls at once.
4. **Ingest from voice platforms.** Webhook receivers that turn a platform's end-of-call
   payload into a `CallRecord`.
5. **Fuzz multi-intent and multi-fault calls.**

## Later: make it a product (v0.4+)

1. **Remediation queue.** Each discrepancy becomes a task with an owner and a one-step fix.
2. **Agent scorecards over time.** Honesty rate per agent version, per claim type. Catch a
   regression the day a prompt changes.
3. **Alerting.** Critical findings to the on-call human within a minute.
4. **Multi-tenant auth, roles, retention policy** for transcripts and patient data.
5. **More claim types**: payments taken, prescriptions refilled, records updated.
6. **Structured topics for handoffs**, to compare ticket content without a model on the
   verdict path.

## Web console plan

**Who it is for.** The clinic operations lead, and the engineer who owns the voice agent.
One wants to know which patients need a call back. The other wants to know what broke.

**Principle.** The console is a triage tool, not a dashboard. It opens on work to do.

Screens:

1. **Inbox.** Calls with discrepancies, worst first. Each row: caller, what went wrong in
   one line, severity, age. Clean calls are hidden by default.
2. **Call.** The replay view that exists today, plus a fix panel: "create the booking",
   "send the confirmation", "mark called back". Evidence stays side by side with the claim.
3. **Agent.** Honesty rate over time, by claim type and by agent version. Top failure
   modes. Links back into the inbox, filtered.
4. **Ledger.** Every sealed report, chain status, export for compliance.
5. **Connections.** Which systems of record are connected, last successful read, and
   which are currently unreadable.

Build order:

1. Inbox and call screen on top of the existing API (`/audits`, `/audit/{id}/report`).
2. Fix actions, which need write adapters and an approval step.
3. Agent trends, which need audits stored over time.
4. Ledger export and connections.

Stack: keep the server-rendered-data, small-client approach. React with TypeScript once
there is more than one screen with shared state; the API is already JSON with a stable
envelope. No model calls from the browser.

Not in the console: editing verdicts. A verdict is evidence. A human can add a note or
resolve a task, and that is recorded next to the verdict, not over it.

## Mobile app plan

**Who it is for.** The person on call for the clinic: the practice manager, evenings and
weekends. They are not at a desk and they need to act on one thing quickly.

**Why a separate app, and why second.** The console is where patterns are understood. The
phone is where a single critical finding gets fixed before the patient is affected. It only
becomes useful once alerting and remediation exist, so it follows the console.

Core flow, one screen each:

1. **Alert.** Push notification: "Maya Chen was told she is booked Tue 2:30 PM. No
   appointment exists." Critical and high severity only.
2. **Evidence.** What the agent said, what the record shows, one table. Same content as the
   console's call screen, cut down to the failing claim.
3. **Act.** Up to three buttons, chosen by the finding: call the patient, apply the
   suggested fix, hand to a colleague. Applying a fix asks for confirmation and shows what
   will be written.
4. **Done.** The action is recorded against the audit, and the finding is re-checked
   against the system of record. The task closes only when the re-check passes.

Also: a short list of open findings, and a quiet-hours setting.

Deliberately left out: scorecards, ledger browsing, scenario replay, settings beyond
notifications. Those belong on the console.

Technical choices:

- **React Native with Expo.** One codebase, shared types with the console, fast to ship.
  Nothing here needs native performance.
- **No patient data at rest on the device.** Fetch on open, keep in memory, clear on
  background. Notifications carry a finding id and severity; names appear only after the
  app is unlocked.
- **Biometric unlock**, short session lifetime, per-user API tokens.
- **Offline**: show the last alert list as stale, queue nothing. A fix applied from stale
  evidence is exactly the failure this product exists to catch.

What the backend needs first:

1. User accounts and device registration.
2. A notifications service keyed on severity.
3. Remediation endpoints with an approval record.
4. A re-audit endpoint for a single claim.

Milestones:

1. Read-only: alerts, evidence, open list.
2. Call-the-patient and hand-off actions.
3. Apply-fix actions with confirmation and re-check.

## Recommendation

Do v0.2 first, then the web console inbox and call screen, then the first real adapter.
Start the mobile app only after remediation exists on the console: an alert with no way to
act on it trains people to ignore alerts.
