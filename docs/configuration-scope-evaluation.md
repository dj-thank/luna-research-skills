# Bind a test receipt to its inputs and settings

The [package-code example](execution-scope-evaluation.md) checks imported files. This next task uses a **different repository**, python-dotenv, to show that identical code can produce a different answer when its input, environment fixture or mode changes.

The source ZIP includes the [probe, fixtures, literal oracle, accepted upstream patch and results](https://github.com/dj-thank/luna-research-skills/tree/main/examples/dotenv_task). The plugin includes this guide; the external execution example is source-only.

## Actual task and fixed answers

[Issue 282](https://github.com/theskumar/python-dotenv/issues/282) describes inconsistent precedence: `load_dotenv(override=False)` keeps an existing environment variable but interpolates dependent values from the file. The accepted [upstream fix, PR 287](https://github.com/theskumar/python-dotenv/pull/287), uses the same precedence for expansion and assignment.

We pinned the fix's immediate parent `17dba65244c1d4d10f591fe37c924bd2c6fd1cfc` and fixed commit `26ff5b74c676dbed391eb535ad2a591ecf98d3c6`. This isolates the precedence change from the preceding parser refactor. Root inspected the accepted solution before writing four repair obligations and eight preservation obligations. These are known answers, not a blind solve or an independent agent evaluation.

Each case specifies its complete text input, fabricated `X35_` environment values, `override` and `interpolate` flags. A separate, literal oracle specifies the expected resulting environment and return value. Both were pinned before execution; expected answers were not computed from the fixture generator or revised after failures.

| Actual execution | Repair tests | Preservation tests |
|---|---:|---:|
| Original code, intended inputs | 0/4 | 8/8 |
| Accepted fix, intended inputs | 4/4 | 8/8 |
| Same fix, wrong override mode in repair cases | 0/4 | 8/8 |
| Same fix, changed environment values in repair cases | 0/4 | 8/8 |
| Same fix, wrong Unicode input value | 4/4 | 7/8 |
| Same fix, added input comment with identical values | 4/4 | 8/8 |

All six executions used Windows / Python 3.12.10. The fixed 12 cases also passed on Python 3.11.15. The untouched upstream parser and variable test files passed **49 tests each on original and fixed code**. The full historical upstream suite was not run: its collection requires `mock` and `sh`, absent from this environment. No dependency was installed for this comparison.

## What changes in the handoff

Both receiving questions compare package-code hashes, probe/oracle hashes, runtime labels and every required test ID. The complete question also compares the exact execution-manifest SHA256. The intended manifest is obtained independently of the receipt; copying the receipt's claimed settings into the proposal would defeat this check.

There are six direct handoffs from the actual runs and three **synthetic receipt replays**. Each replay pairs a changed mode, input or environment proposal with the correct run's earlier passing receipt. Both questions reject the actual failing test records. Only the manifest-bound question rejects all three reused passing receipts, reporting `execution-manifest: MISMATCH` without a partial success view.

The intended fixed input and the independently reviewed equivalent input each retain their own matching passing receipt. All **nine preregistered outcomes** match. Different bytes are not automatically a bad task: the caller can choose another intended manifest, but must obtain matching evidence for it.

For each valid handoff, source reads stay at one / **5,409 bytes**. The complete question grows **1,385 → 1,558 bytes** and the response **6,321 → 6,385 bytes**. Every original record and qualifier remains intact. The 64-byte response increase is below the fixed 1,024-byte bound. These measurements describe this fixture, not agent reasoning quality, latency or price.

## Run the external example

Use a source checkout of this repository, Python 3.11 or newer, Git, and unused paths. The probe executes reviewed external Python code. It does not download, install, modify a checkout, search for a real `.env` file or export the host environment. Each case runs with only its fabricated environment inside a process-local scope that is restored afterwards.

```sh
git clone --no-checkout https://github.com/theskumar/python-dotenv.git work/dotenv-base
git -C work/dotenv-base checkout --detach 17dba65244c1d4d10f591fe37c924bd2c6fd1cfc
python examples/dotenv_task/probe.py --repo work/dotenv-base --manifest examples/dotenv_task/manifest.json --manifest-sha256 6650739b49f6a511d7175ee8b281db9aa60095dc0103eeefadcdb2a89c9ba023 --oracle examples/dotenv_task/oracle.json --oracle-sha256 d989dd4c1a7ba7a1c58472735f7d414d29b1178a4e5ec4062aae4a3ec51cc779
git -C work/dotenv-base worktree add --detach ../dotenv-fixed 17dba65244c1d4d10f591fe37c924bd2c6fd1cfc
git -C work/dotenv-fixed apply ../../examples/dotenv_task/fix.patch
python examples/dotenv_task/probe.py --repo work/dotenv-fixed --manifest examples/dotenv_task/manifest.json --manifest-sha256 6650739b49f6a511d7175ee8b281db9aa60095dc0103eeefadcdb2a89c9ba023 --oracle examples/dotenv_task/oracle.json --oracle-sha256 d989dd4c1a7ba7a1c58472735f7d414d29b1178a4e5ec4062aae4a3ec51cc779
python examples/dotenv_task/probe.py --repo work/dotenv-fixed --manifest examples/dotenv_task/wrong-mode.json --manifest-sha256 37eddc28c5da39a4955b176e652a50ec1cd3b93fce328b609d3c3ce98b12ba14 --oracle examples/dotenv_task/oracle.json --oracle-sha256 d989dd4c1a7ba7a1c58472735f7d414d29b1178a4e5ec4062aae4a3ec51cc779
```

Expected exits are **1, 0, 1**, with **8/12, 12/12, 8/12** passing. The patch is the upstream accepted code change; its BSD notices are retained in `UPSTREAM-LICENSE.txt`. The other input variants and their pins are listed in `contract.json` and `results.json`. To execute them, replace only the manifest path and its independently checked digest.

If pytest and click are already available, the bounded upstream check is:

```sh
python -c "import os,pathlib,subprocess,sys; p=pathlib.Path('work/dotenv-fixed').resolve(); e=dict(os.environ,PYTHONPATH=str(p/'src'),PYTHONDONTWRITEBYTECODE='1',PYTEST_DISABLE_PLUGIN_AUTOLOAD='1'); raise SystemExit(subprocess.call([sys.executable,'-m','pytest','-q','-p','no:cacheprovider','tests/test_parser.py','tests/test_variables.py'],cwd=p,env=e))"
```

The command sets the source path and disables bytecode and unrelated pytest plugins only for the test process. It is a subset, not the full upstream suite.

## Replay the receiving questions without external code

```sh
python tools/read_requirements.py --question examples/dotenv_task/replay-narrow.json --sha256 76cb9fa597226335c721ae0343e3d1728bb7d584a6f5751eb36371ac3895116b --source examples/dotenv_task/replay-source.json
python tools/read_requirements.py --question examples/dotenv_task/replay-complete.json --sha256 84de0d056eec80b03669d36f05c60413f27cab3a6af6cc44a01acfbbbc33973d --source examples/dotenv_task/replay-source.json
python tools/read_requirements.py --question examples/dotenv_task/fixed-complete.json --sha256 eaf37c242b8b233021db01525e6585a820ef12f1af97711b58cc43381c9b68e5 --source examples/dotenv_task/fixed-source.json
python tools/read_requirements.py --question examples/dotenv_task/equivalent-complete.json --sha256 e05610e9c1b956a906be9ddfc330937d2b74c201c47931e2dfa1f87861170204 --source examples/dotenv_task/equivalent-source.json
```

Expected exits: **0, 1, 0, 0**. The narrow replay still exposes the differing manifest hashes in its returned facts. `OBSERVED` means its declared relations matched; it does not establish that the full task was satisfied.

Repository CI checks these saved receipts, input guards and environment isolation on Windows, macOS and Linux. It does not execute the external project on all those OSes. The probe records the eight reviewed package Python files, module origins and runtime labels; it does not attest the interpreter, OS, complete dependency graph or external services. Matching hashes do not authenticate a fabricated receipt. Raw line endings can affect source hashes, so retain the bytes actually executed.

[Sandve et al. (2013), rules 1, 3–5 and 9](https://doi.org/10.1371/journal.pcbi.1003285) motivate recording exact inputs, parameters, code versions and links to results. This example applies that principle to a bounded handoff comparison. The existing requirement readers are unchanged; the inherited native budget remains 6/6 with root-only execution.

Packaging inspection caught an initial serialization mistake: Windows CRLF bytes had been pinned, but Git and the release builder normalize JSON to LF. The original X35 inputs and results were preserved. X35R2 freezes canonical UTF-8/LF bytes before re-execution; parsed inputs, literal answers and all expected outcomes are unchanged. The source example's `format-repair.json` records both sets of pins, and CI checks the pinned files against the actual release canonicalization function.

Frozen X35R2 record SHA256: `dbe144c83804f2edf3697d7b23ff0f2aa67c947ce162063bc3d5a82ac037592c`. Earlier experiments and rejected controls remain preserved.
