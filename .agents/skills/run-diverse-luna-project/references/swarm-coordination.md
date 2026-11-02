# Swarm coordination

Use this reference when several workstreams can progress independently but must
exchange results or take turns using a shared resource. The root owns the ledger,
dispatch decisions and integration. This is a procedure for the existing native
tools and v2 ledger, not an automatic scheduler or distributed lock service.

## Inspect the next batch

For a **flat project v2 ledger**, use the optional advisory planner before the
existing dispatch preflight. Obtain the current open-child count from the native
agent inventory and pass it explicitly:

```text
python <skill-dir>/scripts/plan_swarm.py --ledger-json work/project-ledger.json --open-children 1
```

It reads the ledger once, validates those same bytes with the packaged checker,
and emits JSON without modifying the ledger or starting agents. Unsupported
research/v1/hierarchical ledgers and malformed inputs fail with exit 2 and no
selected attempts. A valid plan exits 0 even if all work is blocked. The planner
is included in both standalone packages, but its scope remains project v2.

| Output | Use |
|---|---|
| `selected_attempt_ids` | One deterministic candidate batch in ledger order, bounded by available C/W/N and the unfulfilled final-verifier reserve |
| `blocked` | Unselected planned attempts, reason codes and causal attempt IDs; distinguish dependency, ownership, time, capacity and integration waits |
| `dependency_replacement_hints` | Recorded accepted retries of a blocked dependency, with root-review and ledger-order requirements; execution still uses the original dependency IDs |
| `active_attempt_ids`, `active_alerts` | Active work and expired deadline/TTL alerts; expiry does not release a writer or a slot |
| `integration_pending_attempt_ids` | Accepted writer candidates awaiting root integration |
| `capacity`, `next_wave` | Ledger-derived spend, remaining reserve and conservative available slots; use the larger of recorded and observed active counts |
| `required_checks` | Checks root must still perform before dispatch; `advisory_only` is always true |

Refresh the ledger and live inventory when a result arrives, then rerun the
planner. Selected candidates do not establish runtime identity, current input
bytes, authority, actual writer release or trace-backed attempt spend. Complete
those checks and the original `check_dispatch_budget.py` preflight before any
spawn. Do not reuse a plan after its inputs or live ownership change.

The default clock is current UTC. `--now <timezone-aware ISO timestamp>` supports
reproducible simulations; a historical override is not a live deadline check.
Dispatched rows with a recorded finish after that snapshot still occupy capacity,
with an alert; a future finish cannot release a slot early.
The planner does not rewrite wave assignments, wait, retry or repair invalid
ledgers. Root records any approved plan change before executing its suggestion.

If a consumer still names a failed or rejected attempt after a retry succeeds,
the original dependency remains blocked. Planner 1.2 lists completed, accepted
retry descendants in `dependency_replacement_hints`, including multi-step retry
lineage. The recorded finish must be at or before the snapshot. Pending, failed,
future-finished and unrelated attempts sharing only a dedup key are not candidates.
An invalid ledger produces no hints.

Root reopens each candidate's artifact and acceptance evidence, checks the
consumer's actual input requirements, then explicitly updates the dependency if
appropriate. Different acceptance criteria can require new review even within the
same retry chain. `requires_root_review` remains true for every hint. Multiple
recorded accepted candidates remain visible; the planner does not choose a winner
from their epoch or list order. Legacy rows may lack epoch protection.

When `requires_ledger_reordering` is true, the retry occurs after the consumer in
ledger order. Referenced dependencies must be earlier, so changing the ID alone
would produce an invalid ledger. Root must preserve dependency ordering when
editing the plan, revalidate it, and rerun the planner and dispatch preflight.
Hints grant no authority to rewrite a ledger or start work; all existing blockers,
capacity limits and required checks still apply.

## Execute one live selection

Keep the planner JSON with the exact ledger/input revision and observed inventory
used to produce it. Root chooses only a currently selected attempt, runs the
objective's trace-backed dispatch-budget preflight, then makes the native
`spawn_agent` call. A plan is advisory; it never authorizes a spawn by itself.
Record the actual call ID, returned child thread ID, parent edge and exact
completed runtime turn from runtime evidence. A task label, requested model or
hand-written receipt cannot substitute for these observations.

Use one explicit specialist profile throughout a run. Public default remains
`gpt-6-luna`/`low`; the opt-in `--specialist-model gpt-6.1-sol` selects
`gpt-6.1-sol`/`low` for profile-aware planner and checker invocations. Retain that
selection when checking receipts; do not relabel a mismatching runtime turn.
The dispatch-budget preflight still checks actual trace spend, independent of
this profile selection. Logical ledger `kind`/`role` values such as `builder`,
`reviewer` and `verifier` describe duties. `agent_role` records the actual native
role (`worker`, `default`, or an explicitly supported custom role), never an
invented mapping from those duties. Confirm the currently supported fresh-context
spawn schema before dispatch.

The live sequence is: planner snapshot -> native candidate selection -> trace
preflight -> real spawn and runtime provenance -> `completed/pending` candidate
-> accepted review -> root acceptance and integration -> final verifier of the
frozen integrated revision. Root performs the actual ledger acceptance and
integration writes. The final verifier has no authority to invent missing
receipts, accept its own inputs or perform root integration. Root closes only
after checking the verifier's exact criterion results and receipts. A writable
runtime with prompt-only limits remains `prompt_only`, including for a logical
read-only reviewer; the assignment does not create a filesystem sandbox.

## Pass candidates through review without a cycle

In v2, `completed/pending` means the child finished and returned a candidate, but
root has not accepted it. An ordinary reviewer may inspect such a completed
candidate. A dependent builder and the final verifier still require accepted
inputs. Failed or rejected dependencies need an explicit root diagnostic decision.

Record the reviewer's completed-turn receipt and result, then accept or reject
the candidate. This satisfies the existing requirement that an accepted builder
has a subsequent accepted reviewer/verifier dependency. Do not label a candidate
rejected merely to represent a review wait. `completed/pending` cannot be marked
integrated or left unresolved at complete closure; it supplies no accepted-result
evidence. v1's state rules are unchanged.

## Release ready work as results arrive

A wave is a numbered dispatch batch, not a barrier that every child must cross.
Collect each completed result, verify its receipt and candidate, and release only
the dependent work whose inputs are now usable. An unrelated slow child need not
delay that work. Before each new batch, refresh the live-child count and run the
same objective's trace preflight; increment the wave number. Never split one
batch into invented wave numbers to exceed W. N, C and the verifier reserve remain
global across all overlapping waves.

For a builder or final verifier, readiness requires all of the following:

- Required dependencies completed and were accepted; their exact commit or
  artifact digest and evidence locator are available in the assignment packet.
- The input bytes still match that revision. When an input changes, assess the
  affected descendants and invalidate their stale checks before accepting them.
- Write ownership is disjoint from active work, or the previous owner has
  observably released the shared resource. A separate worktree isolates candidate
  edits; it does not make shared devices, browsers or provider sessions independent.
- The assignment can finish within its deadline and fits N/C/W/V.
- A final verifier receives the root-integrated, frozen candidate and criterion
  IDs, without the builder's conclusions. Builder completion alone is insufficient.

A failed or rejected dependency is terminal but does not supply a usable build
input. Root records a replacement input, revised scope or blocker. A diagnostic
reviewer may inspect a failed attempt deliberately; label that purpose and do not
promote the failed artifact to accepted input. The checker validates recorded
ordering; root must verify actual input usability and revisions.

## One writer per shared resource

Assign ownership in a common namespace. Use repository-relative paths for files
and a consistent resource identifier for a device, browser session or provider
writer. Directory ownership includes its descendants. Do not use alternate path
spellings to make two assignments appear independent. The checker uses lexical
path comparison, not filesystem identity: root still checks symlinks, worktrees,
mounts and aliases to the same resource.

For each shared resource, keep its ID, current attempt ID, epoch and observed
release/disposition evidence together in the root's existing integration record
(linked by `root_integration_receipt` when available). These are operational notes,
not new required v2 fields or a claim that the runtime enforces a lease.

On timeout, cancellation or reassignment:

1. Keep the previous attempt and its consumed credit; record its terminal status,
   timestamp and reason. A timeout or interrupt acknowledgement is not rollback.
2. Inspect the exact owner, process and candidate. Confirm the writer stopped or
   isolate it so it cannot affect the replacement's resource. Preserve partial
   work for assessment. If release is unverified, keep that resource blocked while
   unrelated ready work proceeds.
3. Create a new attempt with `retry_of`, the same logical `dedup_key`, a greater
   `epoch`, and a bounded new hypothesis. Dispatch only after the recorded prior
   attempt ends and actual resource release is verified. Planned retry reservations
   do not authorize execution. Continue counting against the original N.
4. Exclude late output from the old attempt. Check the current attempt and epoch
   before accepting output or integrating it; never let a late result overwrite
   the accepted successor. Recheck any downstream result built from replaced input.

These are root decisions. The ledger cannot prove that an external process stopped
or that a browser lease is released, and no helper here kills a process.

## Example: keep an independent branch moving

Illustrative plan, not a measured runtime result: N=6, C=2, W=2, V=1. Each writer
uses its own checkout and disjoint files. Root keeps integration as a separate
operation rather than inventing another child attempt.

| Attempt | Ownership | Required input | When to dispatch |
|---|---|---|---|
| A: API | `src/api` | pinned baseline | first batch, with D |
| D: guide | `docs/guide.md` | pinned public interface | first batch, with A |
| R: API reviewer | read-only | completed candidate from A | after A finishes, even while its acceptance is pending and D is running |
| B: UI | `src/ui` | accepted API revision from A | after R and root accept A, even if D is still running |
| S: UI/guide reviewer | read-only | completed candidates from B and D | after both candidates finish |
| V: verifier | read-only | root-integrated A/B/D candidate | after integration and its required checks |

After A returns, R reviews its fixed candidate. Root checks the receipts and
accepts A before supplying its exact revision to B's isolated checkout. D may
continue because its ownership and inputs are independent. S reviews B and D;
root accepts and integrates their candidates, freezes the result and starts V.
This builder/reviewer example uses all six attempts. Reviews count toward N;
they are not free callbacks or implicit permission to exceed the budget.

If A times out while its writer is still active, B and A's replacement stay
blocked; D can continue. Once release is verified, root may replan unused
assignments within the same N or complete the repair itself. There is no spare
retry credit in this six-attempt example. If the budget is exhausted, root
completes mandatory remaining work and reports any missing independent check.

## Measure coordination rather than agent count

At the acceptance boundary, record outcome checks, elapsed time, attempts,
ownership collisions, blocked-input time, stale results rejected and rework.
Compare only matched tasks and evidence gates. More messages, more agents or a
passing synthetic ledger do not demonstrate faster delivery, lower cost or better
answers. Keep runtime observations separate from tests of this protocol.

## Define the benchmark before observing results

Before each benchmark run, freeze its input ledger, clock and observed open-child
count, then record the expected selected IDs and blocked IDs with reason codes.
Compare the planner output against that declared answer; report unexpected
selection, missing blocks and unexpected blocks separately. Include cases for a
completed/pending candidate becoming reviewable, dependent builder acceptance
waits, final-verifier integration waits, and a receipt whose runtime model
mismatches the explicitly selected profile. A profile mismatch must fail receipt
acceptance, even when structural planning succeeds.

Hand-labelled known-answer fixtures test the intended contract. They are not live
observations and must not be described as measured runtime success. For a live
run, retain the actual planner snapshots, trace preflights, native call/turn
provenance, candidate revisions, review decisions, root integration receipt and
final criterion results separately. Report the observed selected/blocked set at
each transition against the predeclared expectation. Missing runtime evidence
remains unverified even if every fixture passes.
