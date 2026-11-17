# Failure analysis

Numbers here come from `receipts eval` at the commit that added this file. Regenerate them
with:

```bash
receipts eval --report docs/EVAL_REPORT.md --json evals/results/latest.json
```

## 1. Results in one screen

Golden set: 52 hand-labelled calls, 86 claims, 7 findings beyond claims.

| Metric | Receipts | Naive lookup |
|---|---|---|
| Claim precision | 100% | 100% |
| Claim recall | 93.3% | 66.7% |
| Exact verdict | 97.7% | 79.1% |
| Finding recall | 100% | 0% |
| Call accuracy | 96.2% | 71.2% |
| Calls fully correct | 96.2% | 55.8% |

Claim-level confusion for Receipts: 28 true positives, 0 false positives, 2 false negatives,
56 true negatives.

Fuzzed set: 500 generated calls, 732 claims, 87 findings. No disagreements with ground
truth.

## 2. The two failures

Both are labelled `known_gap` in the dataset. They are counted in every metric above. A
test asserts they still fail, so that if one starts passing the label has to be removed.

### 2.1 `gap-vague-spoken-promise`: a false claim the auditor never sees

**What happens.** The agent tells the caller *"Dr. Patel will see you Tuesday then, same
time we discussed."* It logs no structured claim and writes nothing. The expected verdict is
`NOT_FOUND` on a booking claim. The auditor reports a clean call.

**Why.** With no structured claim, the only trace of the promise is the transcript. The
rule-based reader recovers a booking claim only from an explicit statement: a booking verb
and a parseable date and time in the same sentence. "Same time we discussed" has neither.

**Why it is not fixed with more rules.** The time is in an earlier caller turn. Resolving it
means tracking references across turns, which is the point at which regexes start producing
false claims. A false claim becomes a false accusation, and precision matters more than
recall for an auditor people have to trust.

**The intended fix.** `LLMClaimExtractor` exists for this. A unit test shows that when a
model returns the resolved booking, the auditor produces the correct `NOT_FOUND`. That test
uses a stand-in model. **It has not been run against a live model**, so there is no measured
recall for that path yet.

**Impact if left alone.** This is the most damaging miss: the patient believes they are
booked and nothing in the report says otherwise. Any deployment where agents speak freely
needs the model-backed reader, measured on real transcripts.

### 2.2 `gap-garbled-handoff`: a wrong ticket that verifies

**What happens.** The caller has a billing question. The agent files a ticket for the right
patient at the right priority, about parking validation. Expected `MISMATCH`; the auditor
says `VERIFIED`.

**Why.** Ticket summaries are free text and are deliberately not compared. Deciding whether
"billing question" and "parking validation" describe the same thing is a semantic judgment.
Doing it with string similarity is guesswork, and doing it with a model would put a model on
the verdict path, which the design rules out.

**A fix that keeps the rule.** Have the model-backed extractor produce a structured
`topic` for both the claim and the ticket at read time, then compare topics
deterministically. The model reads; it still does not judge.

**Impact if left alone.** Moderate. A human reads the ticket and usually notices. The report
does say, in the evidence line, that the summary was not compared.

## 3. Bugs the tests and evals caught during the build

These were real defects in the auditor or service, found before release. Listing them
because they show what kind of mistake this design is prone to.

### 3.1 An outage produced a false accusation

**Found by** a hand-written test for a CRM outage.

With the CRM unreachable, the auditor could not resolve who the patient was, so the booking
claim was correctly `UNVERIFIABLE`. But because that claim never consumed its write, the
appointment was left over and reported as an **unclaimed write**. A verified-honest call was
flagged because a dependency was down.

**Fix.** If a claim that might own a write could not be verified, the unclaimed-write check
for that system is skipped and the call is `INCONCLUSIVE`. Added to the golden set as
`edge-crm-outage`.

**Lesson.** The two directions of reconciliation are coupled. Anything that stops a claim
from being judged also makes "leftover writes" meaningless for that system.

### 3.2 Deleting the first ledger entry went undetected

**Found by** a test that removes an audit from the ledger and expects verification to fail.

`/ledger/verify` checked each report's link to the previous one, but did not check that the
first report linked to genesis. Removing the oldest audit left a chain that verified.

**Fix.** Verification starts from the genesis hash.

## 4. Open findings from independent review (not yet fixed)

After the build, a separate reviewer was asked to construct calls that make the auditor
return a wrong verdict. It reproduced the following by running code. **None are fixed in
this commit.** The golden set and the fuzzer do not contain these shapes, which is why the
headline numbers did not catch them. Until they are fixed, treat a `VERIFIED` as "no
discrepancy found in the shapes the dataset covers", not as proof.

False `VERIFIED`:

1. **Duplicate claim ids.** Two claims sharing one `claim_id` both verify against a single
   write. Call records do not yet enforce unique ids.
2. **Reschedule that also rewrites the record.** An in-place move that also reassigns the
   patient, provider or duration verifies, because only the times are compared.
3. **Reschedule of an appointment that never existed.** "Moved from A to B" verifies when
   nothing was ever booked at A and a fresh appointment was created at B.
4. **Spoken detail that differs from the log.** The caller is told one provider, the log
   says another. The spoken claim is merged away because only the time is compared.
5. **Two patients with the same name.** With no usable phone number, a booking for the
   other person of that name verifies.

False accusation:

6. **Recaps.** "To recap, you're booked for Tuesday" in a later turn is read as a second
   booking claim with no write behind it, and reported `NOT_FOUND`.

Weaker than they should be:

7. **Claim order affects attribution.** Matching is greedy in claim order, so an earlier
   claim can take a write that belongs to a later, more specific one.
8. **Findings are scored by kind only.** A wrong unclaimed write can be counted as a
   correct one. Undefined precision is reported as 100%.
9. **API**: no authentication unless a key is set, an inline call that conflicts with a
   stored one is not rejected, and the demo stage endpoint swaps the store without a lock.

No SQL injection, cross-site scripting or error-detail leaks were found.

**Lesson.** Every one of items 1 to 6 is a case the author did not think to write a
scenario for. Hand-written labels and a fuzzer built by the same person share that
person's blind spots. An adversarial pass by someone else found more in a few minutes
than 552 self-authored cases did. That pass should be a standing part of the eval.

Fixing these is the first item in [ROADMAP.md](ROADMAP.md).

## 5. What the baseline and ablations show

The naive baseline looks up current state and asks whether something matching the claim
exists. It fails 23 of 52 calls. The pattern:

- **It reports the wrong verdict for partial failures.** Wrong time, wrong patient and wrong
  recipient all come back `NOT_FOUND`: it can see that the claimed record is absent, not
  that a different one was written in its place. The operator is told "nothing happened"
  when something wrong happened.
- **It is fooled when something matching exists for another reason.** A pre-existing
  appointment, a zombie reschedule and a confirmation with the wrong time in it all
  "verify".
- **It is blind to everything not claimed.** Finding recall is 0%: no unclaimed writes, no
  policy violations, no spoken-only promises.

Ablations switch off one capability of the real auditor:

| Variant | Claim recall | Finding recall | Calls fully correct |
|---|---|---|---|
| Full | 93.3% | 100% | 96.2% |
| No transcript reader | 80.0% | 100% | 90.4% |
| No policy checks | 93.3% | 42.9% | 88.5% |

Each ablation costs what it should and nothing else. That is evidence the dataset exercises
those capabilities and that the scorer can tell a worse auditor from a better one. A CLI
test also breaks the auditor on purpose and checks that `receipts eval` exits non-zero.

## 6. What these numbers do not show

Read this section before quoting the table.

**The suspect is simulated.** Its speech comes from a small set of seeded templates, and the
rule-based reader was written by the same person with those templates in view. 100% on
explicit phrasing here says the reader handles these templates, not that it handles real
call transcripts. Speech-to-text errors, interruptions, corrections ("sorry, I meant
Thursday") and agents that paraphrase are not represented. The one vague phrasing in the set
is a miss.

**100% on fuzzing is narrower than it sounds.** Fuzzing varies patient, provider, day, time
of day, phrasing variant and fault mode, one intent per call. It shows the verdicts do not
depend on hand-picked dates and slots (it crosses the daylight-saving change and month
boundaries). It does not explore multi-intent calls, combinations of faults, or the two
known gaps, which are excluded from generation. Its expected outcomes come from a table
written by the same author as the auditor.

**Precision is measured on 56 true claims and 16 clean calls.** Zero false accusations in
that sample is encouraging and not a guarantee. One false positive was found and fixed
during the build (3.1) and another is open (section 4, item 6).

**The dataset is one clinic, one agent, non-overlapping calls.** Attribution by identity
and time window is untested against two calls in progress at once under the same agent
identity. The architecture document describes what would go wrong.

**The reference store is ideal evidence.** A trigger-written journal with before-images and
actors is the best case. Google Calendar gives you update times and no before-images. The
adapter contract says what has to be reconstructed; nothing here measures how well that
works.

## 7. What I would do next, in order

1. Fix the open review findings in section 4, each with a regression test and a golden
   scenario.
2. Measure the model-backed reader on real, messy transcripts, with precision tracked
   separately from recall.
3. Add overlapping-call scenarios and decide attribution rules for them.
4. Build one real adapter (Google Calendar) and re-run the golden set through it.
5. Add multi-fault and multi-intent generation to the fuzzer.
6. Structured topics for handoffs, to close gap 2.2 without a model on the verdict path.
