# Swarm experiments and known-answer evaluation

Use this repository as a test subject: declare the expected result, select ready
work with the planner, run real agents, return verified receipts to the ledger,
review the candidate, and repeat only when a new failure or hypothesis warrants it.
Keep experiment candidates isolated until they pass the same acceptance checks.
Replacing a topology is allowed; improving a score on a convenient example is not
enough to promote it.

## Reproduce the known-answer benchmark

From the repository or source ZIP root, run (the plugin ZIP contains the answer
fixtures for reading, but does not include the benchmark scripts):

```text
python tools/benchmark_swarm.py
python tools/benchmark_swarm.py --planner .agents/skills/run-diverse-luna-research/scripts/plan_swarm.py
```

The command emits JSON and exits nonzero on an oracle mismatch. CI runs it on
Windows, macOS and Linux. The independent expectations live in
[swarm_benchmark.json](../tools/fixtures/swarm_benchmark.json); the runner does not
derive them from planner output. Case descriptions, expected selected IDs, required
blocker reasons and error codes are reviewable before execution. Scoring requires
the exact set of blocked attempts and reason codes, and reports missing and
unexpected blocks separately. Repeated blocked attempt IDs fail, including
identical repeats; reasons from every occurrence remain visible in diagnostics.
This prevents a later report from hiding an earlier contradiction. Fixture UUIDs,
timestamps, receipt locators and artifact digests are synthetic labels.

The first 15 cases cover independent work, capacity, candidate review, rolling
handoff, rejected inputs, overlapping writers, future completion, deadlines, root
integration and explicit model selection. A mismatch is a finding, not permission
to rewrite the answer key. Fix an invalid fixture only with a recorded explanation
that preserves its intended question. Add independent challenge cases after an
implementation is frozen; once used for repair, they are regression cases, not an
unseen test set.

Three planning policies see identical snapshots: the planner, a wave-barrier
ablation that suppresses starts while any other work remains active, and a negative
control that starts all planned work. Report exact selection, missed ready tasks,
unexpected starts, blocker reasons and invalid-input handling separately. The
barrier ablation deliberately reuses the planner's safety checks to isolate the
effect of waiting; it is not an independently implemented scheduler.

The communication trial replays the same labelled events through broadcast,
dependency-addressed delivery, and dependency delivery with current-epoch and
duplicate filtering. The oracle lists the required event/recipient pairs. Count
deliveries and require exact agreement: fewer messages that lose required evidence
are a failure. This is a simulation of routing rules, not a deployed message bus;
its digest strings do not authenticate actual artifacts or establish sender trust.

### Compare run and consumer-contract scope

Run `python tools/benchmark_communication.py`. Its separate
[14-case fixture](../tools/fixtures/communication_benchmark.json) fixes required
deliveries before comparing the existing epoch/digest policy, a run-only filter,
and a run plus consumer-contract filter. Each policy sees the same event stream.
The last policy checks run identity, current sender epoch and each recipient's
required contract before recording a duplicate. Its duplicate key also includes
the recipient and contract: identical bytes can legitimately serve different
contracts without one delivery hiding another.

The fixture includes wrong-run and wrong-contract messages arriving before valid
messages with the same digest, missing scope, old epochs in both arrival orders,
fan-out, no consumers and distinct payloads. The policies match 7, 10 and 14 cases,
respectively. Run-only filtering still makes four wrong deliveries and misses two
required ones. The full scope check recovers seven baseline failures, with no lost
baseline successes or extra/missing deliveries on these injected cases. Message
counts are 16, 14 and 12; these are simulated deliveries, not measured token or
latency savings. The CLI exits 1 for an answer/comparison mismatch and 2 for an
invalid fixture; duplicate event IDs or incomplete consumer contracts are invalid.

This experiment is motivated by Xue et al.,
[AECP](https://arxiv.org/html/2610.06481v1), sections 3.2, D.4 and E, read on
2026-11-02: interface revisions require affected consumers to revisit their
contracts. Run identity is an additional assumption in this experiment. This
snapshot comparison does not implement AECP's harness, static interface checks or
consumer acknowledgements, and it does not inherit the paper's performance claims.
Scope labels are trusted fixture inputs, not signatures or proof of actual bytes.
No native transport, dispatch, acceptance, or installed skill policy changes.

### Compare bounded delivery recovery

Run `python tools/benchmark_delivery.py` against its separate
[18-case fixture](../tools/fixtures/delivery_benchmark.json). This extends the
experiment beyond static routing; it does not replace or deploy a message bus.
All three policies see the same loss/corruption schedule and have a ceiling of
two transmissions. The send-once control uses one; ACK retry stops only after a
matching acknowledgement or exhaustion. The third policy also stores a receiver
receipt and its local effect row in one SQLite transaction. A duplicate returns
the recorded acknowledgement without applying another local effect.

The frozen cases cover lost data and ACKs, mismatched identities, corrupted bytes,
rollback between receipt and effect, and reopening a connection after commit but
before confirmation. ACK identity binds run, sender, epoch, consumer contract,
recipient, delivery ID and digest. The receiver compares bytes with the trusted
fixture digest before writing. A third scheduled success beyond the two-attempt
ceiling remains unused. Database rows are read back to count actual local effects.

| Policy | Correct cases | Transmissions | Local effect rows | Confirmed cases |
|---|---:|---:|---:|---:|
| Send once | 3/18 | 18 | 10 | 1 |
| Retry missing ACKs | 9/18 | 35 | 26 | 16 |
| Retry with transactional receiver deduplication | 18/18 | 35 | 17 | 16 |

The final policy recovers 15 send-once failures without losing a send-once success.
Plain retry repeats effects when an ACK is lost. When every ACK is lost, the local
effect exists but the sender still reports `unconfirmed`. No ACK is not proof that
the operation did not happen. An expected negative control is retained in JSON;
the CLI exits 1 on a comparison mismatch and 2 on malformed input.

The identity/retry/uncertainty distinction follows Birrell and Nelson,
[Implementing Remote Procedure Calls](https://www.cl.cam.ac.uk/teaching/0708/DigiCommI/birrell1984rpc.pdf),
sections 3.1–3.2 (1984), read on 2026-11-02. The bounded retry policy and SQLite
model are this experiment's choices; the paper's performance is not transferred.
Connections are closed/reopened, not processes killed or devices powered off.
The effect is a local database row inside the receipt transaction. These tests do
not establish concurrent-writer behavior, authenticated transport or exactly-once
file writes, external tool calls, payments, or other out-of-transaction effects.

For a real handoff, preserve the delivery identity across bounded retries, bind
the acknowledgement to the expected artifact/consumer, and reconcile an uncertain
result from receiver evidence before repeating a side effect. Receiver deduplication
requires an appropriate durable transaction or idempotent operation; a sender's
in-memory `seen` set is insufficient. A message retry does not create a new native
spawn/followup allowance, reset the task budget, release a writer, or prove artifact
acceptance. Root still applies the ordinary receipt and artifact gates.

## Research hypotheses, including counterevidence

The following primary papers were opened on 2026-11-02. Version-pinned snapshots
make the reasoning reproducible; this is a focused comparison, not an exhaustive
survey of the newest publications. Each row is a different author/research family.

| Evidence | Candidate experiment | What it does not establish |
| --- | --- | --- |
| Li et al., [Sparse Communication Topology](https://arxiv.org/html/2406.11776v1), sections 3 and 5, 2024-06-17: sparse debate graphs retained or improved performance on studied tasks with less input cost. | Compare broadcast with dependency-addressed updates on the same events and faults. | A direct performance claim for this repository, root-relay workflows or Codex tools. |
| Cemri et al., [Why Do Multi-Agent LLM Systems Fail?](https://arxiv.org/html/2503.13657v1), sections 4.1–4.3, 2025-03-17: failures include specification, inter-agent coordination and verification/termination. | Inject stale artifacts, missing handoffs, duplicate messages and false completion; check each invariant separately. | Adding a verifier alone fixes upstream design failures; v1 counts are not later-version statistics. |
| Choi et al., [Debate or Vote](https://arxiv.org/html/2508.17536v1), sections 3 and 6, 2025-08-24: independent voting explains much of the measured benefit in their experiments. | Preserve independent answers, then permit one counterexample-based critique. Compare against no discussion at equal budgets. | Universal superiority of voting, or that extra conversation necessarily improves tool-using agents. |
| Hu et al., [Automated Design of Agentic Systems](https://arxiv.org/html/2408.08435v1), sections 3–4 and appendix G, 2024-08-15: code-based agent search uses evaluation and an archive of candidates. | Try a finite set of routing/review policies, archive all outcomes and evaluate the selected candidate once on withheld cases. | This deterministic benchmark implements Meta Agent Search or establishes general reasoning gains. |

## Native communication and repair trial

Use an existing reviewer turn, not an extra coordinator. Give it an immutable
artifact and an intentionally stale candidate receipt in a disposable directory.
Record the expected artifact digest/epoch before dispatch without presenting the
candidate's claimed digest as authoritative. The reviewer first records its own
assessment, then sends a bounded issue to the root:

```json
{"issue_id":"X1","artifact":"candidate.json","observed_epoch":1,"requested_action":"provide current epoch and artifact digest"}
```

Root replies with the current revision, epoch, digest and evidence locator. Reviewer
reopens the bytes, checks the reply, writes only its owned repaired receipt and
returns a verdict. Final verifier checks the artifact, repaired receipt and actual
request/reply records. A send call alone is not acknowledgement; a task name is
not a completed-turn or parent-edge receipt. A stale or incorrect reply must fail,
and an absent reply leaves the trial blocked. Keep raw native logs private.

For ordinary collaboration, send dependency-relevant deltas containing issue ID,
revision/digest, epoch, evidence and requested action. Preserve root visibility for
acceptance and writer reassignment. Deduplicate repeated results, reject superseded
epochs and require the receiver to verify actual bytes. Retain the initial independent
assessment before exposing another agent's conclusion. This protocol permits a
short repair exchange without making debate or consensus an acceptance criterion.

### Bind the handoff to the artifact being consumed

Keep the expected identity in the root's accepted ledger or integration record,
separate from the sender's claim. A matching sender-provided digest and file can
both describe the wrong result. Conversely, an old passing receipt can refer to a
file that has since changed or disappeared.

1. Root selects the accepted run, producer/attempt, epoch, consumer contract and
   artifact revision or digest from reopened evidence. A consumer does not create
   this expected identity from the arriving message.
2. After checking actual writer release, use the frozen candidate or a private
   snapshot. Reopen its bytes and compare their digest with both the recorded
   expectation and the handoff. A missing file, different bytes or different scope
   leaves the dependency unsatisfied.
3. Preserve the checked snapshot through consumption and integration. For code,
   bind test/CI receipts to the tested commit or tree and compare it with the tree
   being integrated. A hash check followed by an uncontrolled write is insufficient.
4. Revalidate changed contracts, epochs and artifacts. Matching bytes do not prove
   functional correctness, successful tests, authorization or the sender's model;
   those still require their own acceptance and runtime evidence.

This distinction is also discussed in Ghosh's
[PCM v1](https://arxiv.org/html/2610.39109v1), section 13.1, read on 2026-11-02:
evidence of a past event does not by itself establish the file's current state.
The handoff procedure above uses root-reviewed records; it does not implement
PCM's signing service, transparency log, authority grants or security guarantees.

For a bounded critique comparison, freeze the independent proposals, one critic
proposal and correctness labels before running any policy. Include a correct
minority, a wrong critic, no correct proposal and contradictory duplicate reports
in both arrival orders. Compare no discussion with unconditional and checked
critique. Judge final answers using the frozen labels, not the same scorer that
accepts proposals: otherwise a scorer defect can certify its own false positives.
Report false acceptance, abstention, missed valid alternatives and repair
regressions separately, along with deliveries and oracle checks actually used.
Equal ceilings do not imply equal work, and access to a known-answer oracle does
not model open-ended reasoning.

## Promotion and reporting

### Reproduce the bounded review comparison

Run `python tools/benchmark_review.py`. Its separate
[frozen fixture](../tools/fixtures/review_benchmark.json) contains independent
correctness labels, expected choices and expected evaluation counts. All three
policies receive the same three initial proposals and one critic proposal, with a
ceiling of two deterministic oracle calls. The tool reports the calls actually
used; a cache hit is not another oracle call. Missing a valid answer and returning
an invalid answer are separate failures. Three-way ties are outside this fixture
and are rejected explicitly.

The policies check the majority plus the critic, the majority plus the minority,
or the majority plus the critic with exact evaluation reuse. The last policy
retains critic priority and checks another independent candidate only if duplicate
work left a call available. The budget includes failed evaluations; exhaustion
returns an unchecked result, not a passing verdict. Reuse applies only within one
serial policy/case evaluation to the deterministic scorer and includes the full
proposal, full answer key, validator source revision and epoch. No external cached
receipt or agent-provided digest is accepted. Changed content or context requires
a new evaluation. This is an offline simulator, not a native scheduling change or
a cache for LLM judgments.

On the 12 injected cases, critic checking returns 7 correct answers, minority
checking 8, and critic checking with reuse 9. Minority checking still loses two
baseline successes, so its higher aggregate score does not pass the case gate.
Reuse recovers two missed answers with zero baseline regressions in these cases;
it uses 22 oracle calls versus 24 for the baseline. Both receive 48 proposals.
Its three abstentions include a case where a distinct invalid critic consumes the
remaining call and prevents inspection of a correct minority. These are curated
fault cases, not an estimated accuracy rate or a speed/cost measurement.

The CLI fails when outcomes, labels or call counts disagree with the fixture.
`passes_case_gate` is only a local case comparison, never permission to deploy.
The regression tests cover changed oracle/proposal/revision/epoch, cached rejection,
exhaustion, failed evaluations and deliberately wrong fixtures. The earlier failed
minority policy remains in the comparison. As discussed in the paper's
[oracle experiment](https://arxiv.org/html/2508.17536v1#S5), known-answer access is a
different setting from open-ended debate. Reuse also requires deterministic,
side-effect-free evaluation; see the [Python caching documentation](https://docs.python.org/3/library/functools.html#functools.lru_cache).

### Adoption requirements

Archive baseline, candidate revision, hypothesis, frozen fixture digest, per-case
outputs, rejected candidates, repair reason and fresh verification. Native traces
stay outside the public repository; publish a redacted outcome summary with its
limits. Count all starts and followups against the existing objective budget.

Adopt a change only when no required invariant regresses, all known-answer cases
pass, fresh challenges pass, and a real task reaches the required acceptance gate.
For a proposed performance improvement, additionally compare matched real tasks
over repeated trials and include all research, retry and verification costs. This
benchmark does **not** measure LLM reasoning quality, real latency, token savings
or monetary savings. A reproducible local simulation and one native repair exchange
are useful evidence, but neither proves a universally better swarm architecture.
