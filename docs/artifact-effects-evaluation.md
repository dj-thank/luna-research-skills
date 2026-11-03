# Verify file effects and exception recovery

A matching return value does not establish that a file contains the intended data. This example extends the [input/configuration checks](configuration-scope-evaluation.md) with exact file contents and a narrowly specified recovery condition.

The source ZIP contains the [probe, independent oracle, input manifest, patches and results](https://github.com/dj-thank/luna-research-skills/tree/main/examples/artifact_effects). The plugin includes this guide; executing the external package requires the source example.

## Known task and actual runs

[python-dotenv issue360](https://github.com/theskumar/python-dotenv/issues/360) reports that adding a key to a file without a final newline joins two bindings, although set_key returns success. Accepted [PR361](https://github.com/theskumar/python-dotenv/pull/361) inserts the missing separator. We pinned its immediate parent fc138ce8a430b758f4f2c89bc8104f259e2cba38 and fix45848bb780c26ef0adf7898656f7d3d3f4e2d8ae.

Root inspected that solution before freezing 12 literal answers: four missing-newline repairs, six preservation cases and two exception cases. The latter inject an exception after the first parsed binding has been written. They require the original file bytes to remain unchanged and the temporary output to be removed. Every file is synthetic, confined to a fresh disposable directory and retained for inspection.

| Actual variant | Matching returns / expected exceptions | Correct file effects | Role |
|---|---:|---:|---|
| Original upstream code | 12/12 | 8/12 | Reproduces the reported newline defect |
| Accepted upstream fix | 12/12 | 12/12 | Retains normal writes and bounded recovery |
| Fix with direct in-place rewriting | 12/12 | 10/12 | Deliberately rejected recovery regression |

The in-place variant is an explicit negative control, **not an upstream change or an adopted implementation**. It returns the expected results during normal operation and raises the expected exception, but leaves a partially overwritten file in both recovery cases. These are actual file executions, not edited successful receipts.

Initial bytes are UTF-8/LF. The separate oracle records POSIX and Windows native-text output bytes for successful writes; recovery must preserve the original bytes exactly on either platform. Inputs and answers were pinned before execution. All three variants ran on Windows/Python 3.12.10; the fixed 12 cases also passed on Python 3.11.15. Untouched upstream parser/variable subsets passed 49 tests on each original/fixed checkout. The full upstream suite was not run: mock and sh are absent, and no dependencies were installed.

## Receiving-question comparison

Both policies bind the intended package code, manifest, oracle, probe and runtime, and require all return/exception checks. The complete policy also requires every case's artifact check. Intended identities come from the frozen plan, not the receipt.

Outcome-only questions accept all three actual variants. Complete questions reject the original newline defect and the in-place recovery regression, and retain the correct variant. A separate synthetic control removes the artifact-check field from a fixed receipt; complete handling returns INSUFFICIENT with MISSING, without partial observations.

All four preregistered decisions matched. A valid handoff keeps every original observation and qualifier. Both policies read the same source once (8,701 bytes for fixed). Question bytes grow 1,386→1,555; response bytes 9,595→9,658 (+63). This measures exposed bytes, not latency, cost or reasoning quality.

The commands below run original outcome/complete, fixed outcome/complete and in-place outcome/complete policies. Expected exit codes are 0,1,0,0,0,1; OBSERVED under the weak policy does not certify file correctness.

~~~sh
python tools/read_requirements.py --question examples/artifact_effects/original-outcome.json --sha256 36c71d1b27a3a94f54a896d03dfb0a339c23cd5189cd439e3447a6e784a81e68 --source examples/artifact_effects/original-source.json
python tools/read_requirements.py --question examples/artifact_effects/original-complete.json --sha256 4430d76039fdd6bc3bd8bdf43c1c5a87945219097632d978c156eb58659422be --source examples/artifact_effects/original-source.json
python tools/read_requirements.py --question examples/artifact_effects/fixed-outcome.json --sha256 4760a0d2cd49f7172c50ef7d8c60af062a39aca3fc37d2bef61c6d04a76f533a --source examples/artifact_effects/fixed-source.json
python tools/read_requirements.py --question examples/artifact_effects/fixed-complete.json --sha256 24f2ae4b723a4f60deb0ae766b9f25d353147c27f0a85f4e3009116c9f076d56 --source examples/artifact_effects/fixed-source.json
python tools/read_requirements.py --question examples/artifact_effects/inplace-outcome.json --sha256 35395c200aeb8e57215709c8f4d06e78be8936c60f9d59495a1814b4dd4d0887 --source examples/artifact_effects/inplace-source.json
python tools/read_requirements.py --question examples/artifact_effects/inplace-complete.json --sha256 1dd7f6bf3d5d6cb9db06333bca96b76bb8564dc41ad20281c1d8185ee8eb628f --source examples/artifact_effects/inplace-source.json
~~~

## Run new actual observations

Use a trusted checkout in a fresh process; the probe executes its Python code. Start from the source distribution root and use unused destination paths. Create the work directory if necessary. Each probe needs a **new** scratch directory with an existing parent; it never overwrites or deletes an existing scratch directory. Full patch context is retained.

~~~sh
git clone https://github.com/theskumar/python-dotenv.git work/dotenv-effects
git -C work/dotenv-effects checkout --detach fc138ce8a430b758f4f2c89bc8104f259e2cba38
python examples/artifact_effects/probe.py --repo work/dotenv-effects --manifest examples/artifact_effects/manifest.json --manifest-sha256 580f038b7ac383458adacff3ff543b0228777d96d6abc40d7ef02460888fda03 --oracle examples/artifact_effects/oracle.json --oracle-sha256 c00cb94f36e834380c4bfa835c0f0aba3904d790cb6848539a2b68a7c3e80c81 --scratch work/effects-original-run
git -C work/dotenv-effects worktree add --detach ../dotenv-effects-fixed fc138ce8a430b758f4f2c89bc8104f259e2cba38
git -C work/dotenv-effects-fixed apply ../../examples/artifact_effects/fixed.patch
python examples/artifact_effects/probe.py --repo work/dotenv-effects-fixed --manifest examples/artifact_effects/manifest.json --manifest-sha256 580f038b7ac383458adacff3ff543b0228777d96d6abc40d7ef02460888fda03 --oracle examples/artifact_effects/oracle.json --oracle-sha256 c00cb94f36e834380c4bfa835c0f0aba3904d790cb6848539a2b68a7c3e80c81 --scratch work/effects-fixed-run
~~~

The original probe exits 1 for the four reproduced failures; fixed exits 0. To reproduce the rejected control, create another worktree at the same parent and apply inplace.patch instead. Review actual before/after bytes and the package scope. Source checkout line endings and runtime labels affect byte identities; do not relabel a stored receipt to match a new run. Synthetic scratch files and a separate canary remain available. The probe does not discover real .env files or export the host environment.

## Evidence limits

[Mohan et al., OSDI 2018](https://arxiv.org/html/1810.02904), sections 4.1–4.4 and 5.1, motivate bounded workloads and comparison of recovered data against an oracle. Here that principle is applied only to an application exception. We do not simulate power loss, reboot, filesystem crash consistency or durable commit, and we do not claim their results.

This is a known-answer root evaluation with no fresh independent reviewer or blind agent solve. The inherited native delegation budget remains 6/6. Scope covers seven reviewed package Python files and explicit synthetic inputs, not all environment state or authenticated receipts. A forged list of passing IDs is not evidence: validate the producer and actual artifact rows separately. Portable CI checks replay saved observations, question behavior and fixture guards; they do not run the upstream package on every CI OS.

The existing requirement-reader runtime is unchanged. The adopted addition is an executable procedure and regression evidence for checking file effects alongside outcomes.
