# Research skill maintenance evaluation — 2026-09-05

This is a bounded maintenance receipt, not a claim of faster research or exhaustive evaluation. Private session contents, machine paths and raw runtime logs are excluded from the repository.

## Inputs and method

The baseline was repository commit `716ddff24ebcc0c96b60cb9c7a217e1e2c5d795c`. The candidate synchronizes the locally maintained V2 contracts and improves Research decision scope, source access, continuation accounting and distribution routing. Checker contract `2026-09-05.4` also fixes the packaged worker acceptance path.

Independent evaluators received raw requests and minimal fixtures without expected answers. Routing judgments and fixture decisions are reported separately from live execution. The initial maintenance batch used four fresh agents (one live Luna source cell and three review/fixture passes); its budget was N=4, C=3, W=3, V=1. The live source cell used the research scout role. Follow-up merge checks include a separate built-in worker probe. These were bounded tests, not a complete hierarchical research run.

## Observed outcomes

| Boundary | Evaluation | Observed result | Evidence limit |
|---|---|---|---|
| Unchanged input | Required references were root-opened 10 minutes ago, within a 24-hour window; optional budget remained | Answered the v2 specification claim from existing evidence without another research wave | Fixture reasoning; no claim of measured token savings |
| Access failure | Primary measurement source denied access; a second retrieval was queued; vendor announcement omitted methods | Stopped the duplicate request in the proposed action, treated the measurement as unverified, and attributed the vendor claim | Fixture reasoning; no real block was induced or bypassed |
| Corrected output | Long guide changed to a short post; only API availability was supported | Restricted the post to the supported API claim instead of claiming availability to every Codex user | Fixture reasoning; nothing published by evaluator |
| Ordinary delivery | Codebase audit, fixes and release artifacts, with no Luna execution request | Selected the caller's normal workflow | Fresh routing judgment; implicit automatic discovery was not tested |
| Explicit Luna delivery | Two independent components with explicit Luna implementation | Selected Luna Project, preserving external-action boundaries | Routing judgment; no implementation/builders executed in this test |
| Public source retrieval | Astra API documentation versus Codex subagent capabilities | Actual research scout fetched official sources and separated source coverage from independent corroboration | Completed Luna/max and initial parent edge verified locally; no recursive fan-out |
| Packaged worker route | Built-in worker with explicit Luna/max and fresh context | Actual worker fetched an official source; checker extracted from the plugin ZIP accepted its exact completed turn through final ledger verification | One accepted source row plus two explicitly undispatched maintenance gaps; not full research coverage |
| Worker negative controls | Same CLI path without opt-in, or without explicit model pin | Rejected both cases; valid opted-in case passed | Reproducible `WorkerLedgerIntegrationTests` with synthetic parent/child records |
| Continuation budget | Non-accepted followup row and unused public assignments | Counted followup against budget; unused rows closed without fake execution | Reproducible ledger fixtures; later-turn activation is still not accepted as initial-spawn proof |

All evaluator files were either read-only inputs or isolated test outputs. No production checkout, provider, account, publication or device was an evaluator-owned writer. The actual runtime sandbox for the public probes was writable; the no-mutation limit was behavioral, not enforced filesystem isolation.

## Verification and gaps

- Initial worker-path revision: 126 tests per packaged checker. The later recursive revision below extends this coverage. Checker and test sources remain byte-identical between the skills.
- Repository/tool tests, metadata/link validation and migration checks were run; GitHub required checks bind to the PR's exact head.
- Source ZIP, plugin ZIP, SBOM and checksums were built twice and compared byte-for-byte.
- The worker ledger bug was reproduced before repair: `--allow-generic-worker` passed setup but was dropped before runtime/provenance verification. Regression tests cover the full CLI route and its negative controls.
- Live model, effort, completed-turn and parent-edge receipts were verified locally. Private receipt UUIDs and raw messages are retained outside the public package; this note alone is not independently replayable live-runtime proof.
- One final Spec-axis reviewer exceeded its deadline and was interrupted. Its result was excluded; the root performed both final Standards and Spec passes locally rather than claiming a completed two-agent review.
- No private/connector/provider source was delegated to the public scouts. Privacy enforcement beyond the documented prompt-only boundary was not claimed.
- Implicit discovery, full two-level hierarchy, live continuation activation attribution, cross-account availability, production research throughput and end-to-end token/latency improvement remain unmeasured. The maintenance checks do not imply those outcomes.

Reproduce the local static and fixture gates using `CONTRIBUTING.md`. The raw requests in `tools/evaluation_cases.json` and the skill's `references/evaluation-cases.md` are the maintained starting points for further behavioral evaluation.

## Recursive revision after the README correction

The user asked to restore the README's concrete multi-team story and make delegation
flexible beyond root/coordinator/leaf. Baseline: `6d19dd199d0c2c7b154ec6b6a3a084c85b8e41df`.
Checker `2026-09-05.6` uses a per-run depth limit, transitive grants and an explicit
mixed-coordinator policy. It does not change the default model policy or grant tools
to a model that lacks them.

Observed execution:

- A fresh default Luna/max coordinator reported no collaboration namespace and
  returned its two unstarted descendant grants. No alternate model was substituted.
- A separate native trial preserved the parent's selected Astra/medium setting and
  completed depth 1 coordinator -> depth 2 coordinator -> depth 3 terminal reviewer.
  Root reopened all three completed turns and their actual parent spawn edges.
  The task was a bounded nonsensitive budget fixture, not a production research run.
- This establishes that tested native Astra chain. It does not establish recursive
  Luna execution. An actual Astra-coordinator/Luna-terminal mixed chain has not been
  executed in this revision; the explicit mixed model policy is covered by CLI fixtures.

Behavioral and code checks:

- A fresh reviewer evaluated an oversubscribed subtree grant, missing Luna spawn
  tools with a working root route, and explicit Astra/Luna composition. It rejected
  the over-allocation, kept the Luna-only request flat, and required policy plus
  runtime/parent/depth/collection checks for mixed acceptance. These were decisions,
  not live scenario execution.
- Recursive fixtures cover depth 3/4, transitive budget inflation, missing delegation,
  false roots, depth jumps, premature collection and actual/declarative depth mismatch.
- Mixed CLI fixtures cover permitted coordination, missing opt-in, terminal-model
  escape attempts, unknown policy, conflicting policy placement and full-history routes.
- Root's grant-return regression preserves the failed coordinator's spent attempt,
  revises only its unused grant, and reassigns never-started slots before flattening.
  Reducing a grant below existing descendant commitments remains invalid.
- The independent review found that collection wording exceeded the checker's
  guarantee. Documentation now distinguishes ledger set/order validation from the
  root's inspection of actual received messages and artifacts.
- Plugin packaging retains the README diagram and supporting documents and maps
  its local skill links to the plugin layout. The source README is unchanged by build.

The recursive revision has 151 tests per checker and 29 repository/tool tests.
These counts include synthetic cases and are not independent real-world outcomes.
The diagram describes an example work graph; per-level capabilities, model choice,
budget and authority still determine what can execute.
