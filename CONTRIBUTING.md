# Contributing

Keep the repository source-first and read-only by default. The `.agents/skills/` and `.codex/agents/` directories are the canonical repository-scoped source; an installed or cloud-discovered copy becomes runtime authority only after current Codex discovery and receipt verification.

- Keep README guidance aligned with both source packages and verify that their checker/test copies remain byte-identical.
- Keep the cross-platform new-install path and the PowerShell migration path explicit and separate. Neither installer may overwrite an existing Skill, follow a reparse target, or silently change Codex model/configuration state.
- Do not add credentials, private session rollouts, personal data, or machine-specific filesystem paths.
- Do not claim a model or routing guarantee from a task name, nickname, static config, or historical run alone.
- When changing the spawn instructions, inspect the live Codex schema and document the supported fresh-context route.
- Recheck the current Codex configuration and subagent documentation before changing the Quick Start.
- Include a dated runtime probe or explicitly mark the result as unverified; do not present local prompt review as runtime proof.

Before opening a pull request, inspect the Markdown files as UTF-8, check that all referenced local files exist, run both packaged checker suites and Skill validators, and review the diff for stale model, schema, privacy, installation, release-metadata, and licensing claims.

From the repository root, run these portable checks with Python 3.11 or newer.
Use `py -3` on Windows or `python3` on macOS/Linux if `python` does not select that
interpreter. Run each command separately and stop on a nonzero exit status; a
shell's final exit code can hide an earlier native-command failure.

```sh
python .agents/skills/run-diverse-luna-research/scripts/test_check_setup.py
python .agents/skills/run-diverse-luna-project/scripts/test_check_setup.py
python .agents/skills/run-diverse-luna-research/scripts/test_dispatch_budget.py
python .agents/skills/run-diverse-luna-project/scripts/test_dispatch_budget.py
python .agents/skills/run-diverse-luna-research/scripts/test_plan_swarm.py
python .agents/skills/run-diverse-luna-project/scripts/test_plan_swarm.py
python tools/benchmark_swarm.py
python tools/benchmark_review.py
python tools/benchmark_communication.py
python tools/benchmark_delivery.py
python -m unittest discover -s tools -p 'test_*.py'
python tools/validate_repository.py
python tools/release_metadata.py
python tools/build_release.py --output release-check
python tools/stress_contracts.py --iterations 25
```

On Windows, also run the migration tests with PowerShell 7:

```powershell
pwsh -NoProfile -File tools/Test-LunaMigrationTools.ps1 -Source (Resolve-Path '.agents/skills').Path
```

CI repeats the Python checks on Windows, macOS and Linux with Python 3.11–3.13,
and runs migration checks with both PowerShell 7 and Windows PowerShell 5.1.
The benchmark CLIs use fixed synthetic answers and make no agent/tool-service
calls. Inspect their case outcomes as well as their exit status: unsuccessful
comparison policies are intentionally retained. See [the experiment guide](docs/swarm-experiments.md).

Before freezing generated benchmark cases, use the [fixture preparation checks](docs/fixture-integrity.md)
to compare construction orders and separately reviewed inputs/answers. Keep the
reviewed oracle independent of the generator; retain invalidated fixtures and
explain repairs instead of silently rewriting expected values. The source-only
helper and its positive/negative examples run in the tools unit suite.

The tools unit suite checks the portable [comparison report example](docs/comparison-reports.md)
and replays the saved [external repair receipts](docs/external-task-evaluation.md).
The latter keeps repair and preservation obligations separate, rejects missing or
skipped required tests and binds source/probe hashes. Its CI checks do not execute
the external repository; use the source-only probe for new actual task runs.

The [execution-scope example](docs/execution-scope-evaluation.md) additionally
binds imported package files and observed runtime labels. Keep actual code runs
separate from receipt replays, preserve earlier fixed contracts, and do not turn
this reviewed package inventory into a claim of whole-environment capture.

The [input/configuration example](docs/configuration-scope-evaluation.md) pins a
separate literal oracle and explicit synthetic execution manifests. Keep intended
inputs independent of receipts, never export the host environment, and retain
the distinction between upstream subset checks and a full external test suite.

The [file-effects example](docs/artifact-effects-evaluation.md) separates return
values from exact artifact contents and bounded exception recovery. Preserve both
newline-specific literal oracles, reject missing effect evidence, and use fresh
disposable directories. Application exception tests do not prove crash durability.

The [sequential retry example](docs/retry-effects-evaluation.md) must keep request
identity separate from payload equality. Preserve every attempt and stored state,
count setup writes separately, and reject fewer writes that drop valid requests.
Its single-writer file-reopen runs do not establish network, crash or ACID guarantees.

The [cancellation example](docs/cancellation-effects-evaluation.md) separates a
request name from its execution generation. Preserve captured-callback traces,
late-cancellation effects and legitimate replacements. Empty queues are not proof
of no late effects; these sequential batches do not test concurrent interruption.

The [marker round-trip example](docs/marker-roundtrip-evaluation.md) separates repair
from preservation obligations. Freeze literal semantic answers before execution,
retain quote/case regressions, and bind the reviewed package inventory. A repaired
reported input does not establish preserved behavior; never discard failed controls.

The [ordered-record example](docs/ordered-records-evaluation.md) must distinguish
distinct-key counts from value occurrences. Compare exact ordered pairs and query
strings, retain representation-equivalent cases and identical duplicates, and
label synthetic order/missing-field receipts separately from package executions.

The comparison report checks cover pinned evidence, rejected-policy reports and calibration-inclusive work.
Keep the example's digest and report aligned with its exact UTF-8/LF bytes. A report
check exiting zero validates consistency; it does not imply a passing case gate.

The review producer tests instrument actual scorer entry, including failed calls,
and verify both successful and rejected policy exports. Keep its source-fixture
pin aligned with the reviewed fixture; preserve version 1 consumer compatibility
when changing version 2 provenance. Do not replace failed-export audits with
partial success documents.

For PR and post-merge acceptance, use fresh provider check-run readback for the
exact target SHA. The [offline CI evidence checker](docs/ci-evidence.md) can verify
an independently specified required name/app policy. Its example is synthetic;
it does not discover the repository policy or replace GitHub's merge protections.

Changes to the comparison recovery inspector must keep the caller's independent
pin, mandatory report validation, negative-comparison support, explicit staged
versus published states and read-only behavior. Never infer completion from a
directory, select between ambiguous copies, or add automatic recovery mutations.

The [on-demand reader](docs/on-demand-evidence.md) must preserve request/source pins,
exact selected values and all required guards. Refuse missing or lossy values and
oversized results without partial output; do not change approval states or choose
guards from observed benchmark outcomes. Measure exposed bytes separately from
source/request reads. Keep the copyable example executable from the plugin.

The [cross-source reader](docs/cross-source-requirements.md) must require every
explicit source binding and each requirement's per-source coverage. Preserve
original records with their verified source ID/digest; do not count majority,
recency or a successful record as conflict resolution. Keep aggregate read limits,
no partial observations on gaps, and both documented plugin examples executable.

For optional [time constraints](docs/temporal-requirements.md), keep the caller's
fixed as-of clock, half-open boundaries, historical answers and source-conflict
precedence. Unknown endpoints must not imply open-ended validity. Keep version 1
results unchanged, include time metadata in response limits, and verify both
dated plugin examples. Validity windows do not prove current provider state.

For [observation-age constraints](docs/observation-freshness.md), preserve the
fixed question clock, inclusive age boundary, exact integer seconds and earlier
source/time diagnostics. Never substitute receipt time for the declared
observation pointer. Preserve version 1/2 results and all original qualifiers,
and verify both source/plugin examples including metadata byte limits.

Changes to `tools/install_luna_skills.py` must preserve dry-run-by-default behavior, `SKILL.md`-last publication, fail-closed path handling, no-overwrite semantics, and rollback tests for partial writes, concurrent destination creation, and user-modified content. Run its unit tests on Windows, macOS, and Linux through the existing Python matrix.

Also run the bundled Skill Creator `quick_validate.py` against both Skill directories, validate the generated plugin manifest/archive, rebuild release assets twice and compare their SHA-256, and run `git diff --check`. Keep `release-check`, Python caches, runtime rollouts, discovery reports containing machine paths, and migration journals out of commits.

Routing or description changes require fresh, task-local forward evaluation against both `references/evaluation-cases.md` files. Record expected versus observed Skill selection, route, N/C/W/V, exact completed Luna/low receipts, parent spawn output containing the child UUID, ownership collisions, latency, and false completion claims. A static case manifest or checker unit test complements but does not replace live runtime evidence.

The [2026-09-05 maintenance evaluation](docs/research-evaluation-2026-09-05.md) separates observed routing, synthetic fixtures, live public-source execution and untested dimensions. Keep private raw runtime receipts outside public commits.

The [partial-failure example](docs/partial-failure-evaluation.md) must observe the output prefix, terminal exception and resource exit before harness cleanup. Keep explicit historical/new call sites, dependency pins and source-finalization limits. Do not infer resource release from an exception or adopt exception swallowing as recovery.

For exact Git-byte preparation, use the source-only [canonical snapshot helper](docs/canonical-source-preparation.md) with an independently pinned manifest and a new target. Keep binary/CRLF payloads intact; do not normalize away mismatches. Preserve INCOMPLETE outputs and reject existing destinations, indirect modes and source-overlapping paths.

For data-dependent validation, bind each case to the [input bytes actually consumed](docs/input-provenance-evaluation.md). Matching code and outputs can hide a stale fixture that no longer exercises the regression. Keep input identities, case mappings and honest execution limits.

When preprocessing precedes parsing, also bind the [final parser input](docs/parser-input-evaluation.md) to independently expected contents. Capture after every declared transform at the actual API call, retain allowed normalization controls and label syntax-preserving versus syntax-erasing transformations. A raw file hash alone does not establish which parser path was exercised.

For streaming regressions, capture [actual ordered chunk deliveries](docs/stream-chunk-evaluation.md) at the consumer boundary, including partial consumption and observed exhaustion. Freeze allowed schedules before execution, retain valid alternative segmentations, and distinguish output loss from loss of required boundary coverage. Concatenation or a bag of chunk hashes cannot establish delivery order.
