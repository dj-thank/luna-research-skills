# Swarm coordination

Use this reference when several workstreams can progress independently but must
exchange results or take turns using a shared resource. The root owns the ledger,
dispatch decisions and integration. This is a procedure for the existing native
tools and v2 ledger, not an automatic scheduler or distributed lock service.

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
| B: UI | `src/ui` | accepted API revision from A | after A is verified, even if D is still running |
| V: verifier | read-only | root-integrated A/B/D candidate | after integration and its required checks |

After A returns, root verifies A and supplies its exact revision to B's isolated
checkout before dispatching B. D may continue because its ownership and inputs
are independent. When B and D return, root integrates, freezes the candidate and
starts V. Four attempts are used; two credits remain unspent, not automatically
assigned to extra agents.

If A times out while its writer is still active, B and A's replacement stay
blocked; D can continue. Once release is verified, one counted retry can supply
B's input. If the budget is exhausted, root completes mandatory remaining work
and reports which independent verification was not obtained.

## Measure coordination rather than agent count

At the acceptance boundary, record outcome checks, elapsed time, attempts,
ownership collisions, blocked-input time, stale results rejected and rework.
Compare only matched tasks and evidence gates. More messages, more agents or a
passing synthetic ledger do not demonstrate faster delivery, lower cost or better
answers. Keep runtime observations separate from tests of this protocol.
