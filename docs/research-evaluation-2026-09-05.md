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

- Both packaged checker suites: 126 tests each. Their checker and test sources are byte-identical.
- Repository/tool tests, metadata/link validation and migration checks were run; GitHub required checks bind to the PR's exact head.
- Source ZIP, plugin ZIP, SBOM and checksums were built twice and compared byte-for-byte.
- The worker ledger bug was reproduced before repair: `--allow-generic-worker` passed setup but was dropped before runtime/provenance verification. Regression tests cover the full CLI route and its negative controls.
- Live model, effort, completed-turn and parent-edge receipts were verified locally. Private receipt UUIDs and raw messages are retained outside the public package; this note alone is not independently replayable live-runtime proof.
- One final Spec-axis reviewer exceeded its deadline and was interrupted. Its result was excluded; the root performed both final Standards and Spec passes locally rather than claiming a completed two-agent review.
- No private/connector/provider source was delegated to the public scouts. Privacy enforcement beyond the documented prompt-only boundary was not claimed.
- Implicit discovery, full two-level hierarchy, live continuation activation attribution, cross-account availability, production research throughput and end-to-end token/latency improvement remain unmeasured. The maintenance checks do not imply those outcomes.

Reproduce the local static and fixture gates using `CONTRIBUTING.md`. The raw requests in `tools/evaluation_cases.json` and the skill's `references/evaluation-cases.md` are the maintained starting points for further behavioral evaluation.
