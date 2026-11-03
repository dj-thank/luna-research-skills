# Partial output and cleanup at an exception boundary

An expected exception does not establish that the operation released its resources or preserved the output produced before failure. This source-only comparison executes a historical more-itertools API migration against twelve literal answers frozen before execution.

[Issue121](https://github.com/more-itertools/more-itertools/issues/121) explains why wrapping a context manager as an iterator does not ensure its exit runs when a consumer fails. [Merged PR123](https://github.com/more-itertools/more-itertools/pull/123) removed that API and documented explicit `with` statements. We use its actual first parent `c8e2cb4e7c7b294d72a617f910d8a0d690553b94` and merged commit `042e67bc9b4f0b26be67c97c809c3b35da5f33ab`. The complete upstream diff and license are included.

This is an API migration with explicit call-site changes, not a drop-in repair of the removed function. `base.py` uses the historical `context()`; `fixed.py` uses the documented `with` replacement; `swallow.py` adds an intentionally rejected exception handler. The latter two run against the accepted package.

| Actual call site | Terminal exception | Prefix and cleanup | Both |
|---|---:|---:|---:|
| Historical context iterator | 12/12 | 4/12 | 4/12 |
| Documented with migration | 12/12 | 12/12 | 12/12 |
| Exception-swallowing control | 4/12 | 12/12 | 4/12 |

Four normal cases cover empty, single, duplicate and Unicode strings. Four source faults and four consumer faults occur at different positions. Each answer specifies the yielded prefix, written content, consumed source prefix, source-finalization flag, resource-close flag and exit event, plus the exact terminal exception.

The historical context iterator is retained until readback. This exposes the defect deterministically instead of relying on garbage-collection timing. The snapshot occurs before explicit harness teardown. An input generator suspended at a consumer fault remains unfinalized in every variant at that point; the with statement manages the resource, not the input generator. All resources and retained iterators are closed afterward.

The complete question requires direct equality with those literal answers, not a producer's pass count. It rejects the original cleanup defect while retaining rejection of swallowed exceptions. Separate synthetic receipts remove state or remove an output prefix while preserving the exception: both are rejected without partial observations. These two diagnostics are not extra upstream executions.

## Replay the saved handoffs

Use the source repository/archive, Python 3.11+, and existing offline reader. A zero exit means `OBSERVED`; exit 1 means `INSUFFICIENT`. Expected exits in order: **0, 1, 0, 0, 1, 1**.

```sh
python tools/read_requirements.py --question examples/partial_failure/base-terminal.json --sha256 5b3fd1d5031ae341741577b5b6b5092fb53f9b2ea908a89f32794ff96770472e --source examples/partial_failure/base-source.json
python tools/read_requirements.py --question examples/partial_failure/base-complete.json --sha256 48b7ac2ec92fb3235b41cf081b8900e5c60e75994633219bd9988687d6b036c6 --source examples/partial_failure/base-source.json
python tools/read_requirements.py --question examples/partial_failure/fixed-terminal.json --sha256 0c51e31908011d39608429e6fd51444ab2415891d2a9f8845100df2a1e7890b6 --source examples/partial_failure/fixed-source.json
python tools/read_requirements.py --question examples/partial_failure/fixed-complete.json --sha256 528ff18c0ea88bf10e08771df55a3a7d672eee5da06f3108326586eb1a038dbe --source examples/partial_failure/fixed-source.json
python tools/read_requirements.py --question examples/partial_failure/swallow-terminal.json --sha256 404cb303a7c70f713d299ed76622b5c5a1df5f32e3283135615a57c079d0968d --source examples/partial_failure/swallow-source.json
python tools/read_requirements.py --question examples/partial_failure/swallow-complete.json --sha256 e76271a865c2c90d083601e03c2ec109c1da78d68d817819388c42b52adeb3ae --source examples/partial_failure/swallow-source.json
```

All valid observations and qualifiers survive unchanged. Fixed-case source reads remain 1 and 12,314 bytes. Question size is 1,738→1,894 bytes and response size is 13,323→13,374 bytes. These byte counts are not latency, token billing or reasoning measurements.

## Reproduce actual execution

Use trusted disposable checkouts of the two pinned upstream commits. Normalize the six `more_itertools/**/*.py` files to their original Git blob bytes; their hashes are recorded in `results.json`. Run the probe from the source archive. The existing dependency is six 1.17.0, whose file digest is also recorded. No dependency installation is part of the probe.

```sh
python examples/partial_failure/probe.py --repo PATH_TO_BASE --variant base --manifest examples/partial_failure/manifest.json --manifest-sha256 848a343f0e8fa51e120cd191ab0637eefca3f3ba504adaf33a16a1148b94d493 --oracle examples/partial_failure/oracle.json --oracle-sha256 c48c306f42af22df705932846f3afd6ea61c8f8a564aa7999c9b742df4519962
```

Repeat with the fixed checkout and `--variant fixed` or `--variant swallow`. Expected exits are 1, 0, 1. The recorded actual execution used Windows/Python 3.12.10. The probe records all six package hashes, call-site bytes, six version/hash and runtime, and checks the imported package locations. The local comparison separately matches these observations to the preregistered values. It does not capture the whole host environment.

Unmodified function doctests passed: base `context`+`side_effect`, 20 examples; fixed `side_effect`, 16 examples. The counts differ because the API was removed; they are not a before/after coverage improvement. The full upstream suite was not run (its nose dependency was unavailable and not installed).

The first local handoff formatter put `subject` at the document level instead of each observation. The reader refused it. Those failed receipts and the formatter are retained in the local work record; only the schema serialization was corrected, with frozen inputs, expected outcomes and actual executions unchanged.

## Basis and limits

[Cornu, Seinturier and Monperrus (2015)](https://doi.org/10.1016/j.infsof.2014.08.004) use exception contracts and fault injection during tests to study error handling. The publisher abstract/introduction/method excerpts informed the explicit injection positions and state oracles here. This is not their Java experiment or catch-stretching method, and swallowing exceptions is not adopted.

Root read the published fix before freezing. There is no blind solve or fresh independent agent; the original delegation budget remains 6/6. Portable CI validates saved receipts, questions and bounded inputs, without executing historical more-itertools on every OS. No general recovery guarantee, latency, cost or model-quality improvement is claimed. Existing readers, installed skills and previous examples remain unchanged.
