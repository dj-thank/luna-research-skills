# Bind a test receipt to the code it actually used

The [first external task](external-task-evaluation.md) binds a repair to a source file and its tests. This second task demonstrates why another imported file can change the answer while that primary file stays identical.

Source-only [probe, fixed contract, results and patches](https://github.com/dj-thank/luna-research-skills/tree/main/examples/iequals_task) are included in the source ZIP. The plugin includes this guide; it does not include these external execution examples.

## One actual issue, three executed variants

[more-itertools issue 1282](https://github.com/more-itertools/more-itertools/issues/1282) concerns `iequals` hiding `ValueError` from an input iterator or an element comparison. We pinned original commit `bc8be1013ac90fe3c1df8aae646b02605d578818` and fixed four repair tests plus eight preservation tests before running new variants.

The repair distinguishes different lengths using an identity-checked fill marker, while allowing input exceptions to propagate. It continues to call `all_equal`, imported from `recipes.py`. The deliberate dependency control changes that helper to always return true, keeping the repaired `more.py` bytes unchanged.

| Actual code | Repair tests | Preservation tests | Original upstream suite |
|---|---:|---:|---|
| Pinned original | 0/4 | 8/8 | Prior 905-test result reused after base/log verification |
| Fixed `iequals` | 4/4 | 8/8 | New run: 905 passed |
| Same fixed file, changed helper | 2/4 | 5/8 | Not run |

The dependency control fails comparison-error propagation, comparison-truth errors, ordering, unequal values and short-circuit behavior. Its primary-file SHA256 is exactly the same as the correct fix. All three executions used Windows / Python 3.12.10; the correct fix also passed the 12-test probe on Windows / Python 3.11.15.

This is a second known-answer task in the **same external project**, not a test across unrelated repositories or an agent success-rate estimate.

## What the probe records

Before imports, the probe checks a reviewed inventory of all three package Python files:

- `more_itertools/__init__.py`
- `more_itertools/more.py`
- `more_itertools/recipes.py`

It hashes those bytes, checks that the three imported module origins are the expected paths, runs the fixed tests, and compares the package snapshot again. An unexpected/missing Python file, existing package bytecode cache, wrong module origin or observed source change refuses the run. Run it in a fresh, reviewed checkout with one writer.

The receipt retains the file-to-hash map, relative module origins, Python/platform labels, test IDs and statuses. Snapshotting reads the three source files twice; this cost is separate from the receiving question's one register read. Both receiving policies below use the same captured evidence.

This is a **declared package-code scope**. It does not capture the interpreter binary, standard library, OS files, environment variables, external services, dynamic native dependencies or transient changes restored between snapshots. Runtime labels are observations, not full environment identities. A fabricated receipt is not authenticated by a matching hash.

[ReproZip, sections 1 and 3](https://www.usenix.org/system/files/conference/tapp13/tapp13-final16.pdf) motivates connecting execution results with the code, data and dependencies used. Our small Python probe is an engineering application of that principle, not ReproZip's system-call tracing or a reproduction of its portability/performance results.

## Reproduce the code executions

Use this repository's source checkout, Python 3.11 or newer, and unused workspace paths. The probe imports and executes the supplied repository; use reviewed code. It does not download, install or patch anything.

```sh
git clone --no-checkout https://github.com/more-itertools/more-itertools.git work/iequals-base
git -C work/iequals-base checkout --detach bc8be1013ac90fe3c1df8aae646b02605d578818
python examples/iequals_task/probe.py --repo work/iequals-base
git -C work/iequals-base worktree add --detach ../iequals-fixed bc8be1013ac90fe3c1df8aae646b02605d578818
git -C work/iequals-fixed apply ../../examples/iequals_task/fix.patch
python examples/iequals_task/probe.py --repo work/iequals-fixed
git -C work/iequals-base worktree add --detach ../iequals-helper bc8be1013ac90fe3c1df8aae646b02605d578818
git -C work/iequals-helper apply ../../examples/iequals_task/changed-helper-control.patch
python examples/iequals_task/probe.py --repo work/iequals-helper
```

Expected probe exits: **1, 0, 1**. Expected passes: **8/12, 12/12, 7/12**. The last patch includes the same primary fix plus the deliberate helper change. The patches retain upstream MIT notices. Line endings can change the byte hashes across checkouts; retain the actual executed bytes.

To verify the original suite against the correct patch:

```sh
cd work/iequals-fixed
python -m unittest discover -s tests
cd ../..
```

The recorded Windows/Python 3.12.10 run passes all 905 tests. Repository CI replays saved receipts and checks the example's guards; it does not execute this external repository on other OSes.

## Compare a narrow receipt with a package-scoped receipt

Both policies require the primary hash, probe hash, relative module origins, runtime labels and every repair/preservation test. The complete policy additionally compares the package file-to-hash maps using the existing [requirement reader](requirement-selection.md).

A **synthetic receipt replay** pairs the changed-helper candidate's real source identity with the correct fix's real passing receipt. This is distinct from the actual changed-helper test run, whose failures both policies reject. Another replay substitutes the actual Python 3.11 receipt for the Python 3.12 proposal; both policies reject that runtime mismatch.

```sh
python tools/read_requirements.py --question examples/iequals_task/replay-narrow.json --sha256 1cea53a8fca15b05805764451e7d0cde31af051072b6a74090712d00db57c776 --source examples/iequals_task/replay-source.json
python tools/read_requirements.py --question examples/iequals_task/replay-complete.json --sha256 84f833853ab7b43b537b37521ab107daa88c2ee4b0de47c1a80c4b967ff786a4 --source examples/iequals_task/replay-source.json
python tools/read_requirements.py --question examples/iequals_task/fixed-complete.json --sha256 4313efdef13ef3be9d819b6e90569d592f073df663c852c69fe07233658ca98b --source examples/iequals_task/fixed-source.json
```

Expected exits: **0, 1, 0**. The replay's narrow `OBSERVED` view still includes both different helper hashes: they were visible but not compared. The complete view reports `package-code: MISMATCH` without partial observations. The unchanged correct fix remains observed.

All five preregistered handoff outcomes match. On the valid fixed receipt, source reads remain one per policy, **3,132 bytes** each. The complete question grows **1,391 → 1,548 bytes** and the response **4,058 → 4,116 bytes**, retaining every original record and qualifier. The 58-byte response increase satisfies the predeclared 1,024-byte bound. This demonstrates scoped diagnostic coverage, not measured latency, cost or model-quality improvement.

## Carry this into another task

Define the code/data scope and necessary runtime conditions before accepting a receipt. Bind the reviewed candidate and the observed test run to the same scope, including imported helpers. Preserve earlier failures and compare file inventories as well as file hashes. Re-run affected tests when the relevant scope changes; reuse unchanged results only with a verified matching scope and the applicable acceptance policy.

Scope completeness still requires judgment. This example knows the three Python modules in advance; it is not a general dependency finder. Root read the actual issue and authored the probe, with no blind solve or fresh independent agent reviewer. The inherited native budget stays 6/6.

Frozen X34 record SHA256: `831b411e77b65289bf1b2def6190bcf6c408b303eb50c6bd0d02a632304d4203`. Existing X33 inputs, rejected patches, prior results and the original X28 failure remain unchanged.
