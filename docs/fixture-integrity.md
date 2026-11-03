# Check fixture generation before freezing answers

A digest preserves the bytes you selected. It cannot tell whether a later test
case already changed an earlier case's input or answer through a shared object.
A live experiment in this repository exposed that failure: shallow copies
retained mutable dictionaries across cases. Its contaminated results were
invalidated and preserved; a separate repaired experiment was checked before use.

For independent cases, construct the same cases in forward, reverse, rotated,
and repeated forward order. Compare each completed case by ID with the other
constructions **and with separately reviewed inputs and expected answers**.
Only then freeze the artifacts used for evaluation. Preserve failed artifacts;
changing an oracle after seeing a result requires an explained invalidation and
a new experiment record.

## Reproduce the preparation checks

From the repository or source ZIP root, run:

```text
python tools/example_fixture_builder.py
python tools/example_fixture_builder.py --variant shared-input
python -m unittest discover -s tools -p test_fixture_integrity.py
```

The isolated builder returns `CONSISTENT` and exits 0. The intentionally shared
input returns `MISMATCH` and exits 1: multiple IDs retain the last mutated source.
The test command exits 0 when both positive and negative expectations hold.
These developer tools are in the source ZIP, **not the plugin ZIP**.

The [reviewed fixture](../tools/fixtures/fixture_integrity_oracle.json) and the
source package's `tools/example_fixture_builder.py` preserve all 12 controls:

| Builders | Expected acceptance |
| --- | --- |
| Isolated objects, JSON round-trip, reordered dictionary keys | 3 accepted |
| Shared input, shared answer, accumulating per-case state | 3 rejected |
| Stable wrong answer, stable wrong input, integer changed to float | 3 rejected |
| Missing, duplicate, extra case ID | 3 rejected |

On this fixed comparison, all 12 classifications matched. Byte-hash preservation
alone accepted all 12, including nine corrupt builders; it only checks identity
and is not an existing semantic validator. The new check rejected those nine
and retained all three valid builders. The three stable wrong variants also
passed order invariance, demonstrating why the reviewed oracle remains necessary.
The baseline constructed each builder once (12 calls); the candidate used four
constructions each (48 calls). This is extra preparation work, with no speed,
cost, token or model-quality claim. Root ran this finite experiment; no new
independent agent review or model execution was performed.

## Apply to your own generator

Import `check_builder` from `tools/fixture_integrity.py`
in your source-level preparation test. Pass a trusted callable `build(order)`,
at least two distinct case IDs, and a separately reviewed list of
`{"id": ..., "input": ..., "expected": ...}` records. Each invocation must reset
its per-build state. Return the complete list; the helper snapshots it immediately.
Do not generate the reviewed answers by calling the builder under test.

The helper reports order changes, oracle mismatches, malformed output and build
exceptions separately. It compares full JSON records; booleans, integers, floats,
nulls and strings are distinct, and array order stays significant. Dictionary key
order and outer case order do not matter. Missing/duplicate/extra IDs, non-JSON
values and nonfinite numbers fail. A malformed oracle fails before builder execution.

Use only bounded, side-effect-free builders you trust: this is an **in-process
test helper**, not an execution sandbox or timeout mechanism. It does not run the
system being benchmarked or prove that the reviewed oracle is true or complete.
The selected permutations are finite, not exhaustive. Later mutations outside
these snapshots still require immutable saved artifacts and digest checks.
A deliberately sequential scenario belongs inside one case; do not reorder its
events or assume an order-independent property that its domain does not have.

This procedure is an engineering application of Chen, Cheung and Yiu,
[Metamorphic Testing, HKUST-CS98-01 (1998), archived v1](https://arxiv.org/abs/2002.12543v1),
introduction/preliminaries (PDF pp.2–3) and the transformation example (p.9),
read 2026-11-03. The paper motivates domain-specific follow-up tests alongside
existing checks. Our independent-case permutation rule and exact-oracle check
are choices for this repository, not a replication of its examples or efficiency
assumptions.
