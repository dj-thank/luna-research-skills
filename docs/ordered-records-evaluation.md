# Verify every ordered record, not just the count

An ordered multimap can lose values while its key count stays unchanged. This external task requires exact key/value occurrences and their order in a receiving question. It extends the [repair/preservation example](marker-roundtrip-evaluation.md) with duplicate values, representation-equivalent inputs, and a separate order-only diagnostic.

The source ZIP contains the [probe, literal oracle, full patches and receipts](https://github.com/dj-thank/luna-research-skills/tree/main/examples/ordered_records). The plugin includes this guide; external execution is source-only. The requirement reader is unchanged.

## Actual external regression

[Boltons PR531](https://github.com/mahmoud/boltons/pull/531) describes `OrderedMultiDict.update` losing the first value of a new repeated key. **That PR was not merged directly.** The fix was reimplemented in commit `bbadc7ae1dcfbb0e71ec3a852e8bca3a6f75199b` inside [merged PR609](https://github.com/mahmoud/boltons/pull/609). We compare its actual sole parent `40fffc5ba0a84315c79813daa47db35157d64556` with that accepted commit. GitHub ancestry confirms that the selected commit belongs to the merged history.

The commit also fixes other dictionary behaviors; we retain its full three-file diff and do not attribute all upstream test changes to this one regression. It repairs both `dictutils.OrderedMultiDict` and the embedded implementation used by `urlutils.QueryParamDict`.

Updating an empty mapping with `[("tag", "r1"), ("tag", "r2")]` should preserve both pairs. Before the fix, only `("tag", "r2")` remains. `len(mapping)` is1 either way because it counts distinct keys. The accepted fix records every first-seen key, including a key absent from the destination, so later occurrences do not delete earlier new values.

We froze twelve literal cases before execution and ran each against both implementations: **24 observations per variant**. Cases cover repeated new keys, interleaving, triples, one-shot iterators, empty/unique inputs, repeated existing keys, keyword overrides, untouched identical occurrences, and equivalent OMD input. QueryParamDict additionally must emit the exact ordered query string. All inputs are fabricated strings; URL text is serialized locally and never fetched.

| Actual code | Key count, return, iterator consumption and supplied-pair-list checks | Exact ordered records/query strings |
|---|---:|---:|
| Parent before fix | 24/24 | 16/24 |
| Accepted upstream fix | 24/24 | 24/24 |
| Fix plus `dict(E).items()` deduplication control | 24/24 | 10/24 |

The deduplication control collapses repeated iterable keys to their last value. It also loses valid repeats under existing keys, including identical values that must occur twice. It is retained as a rejected alternative. Keyword overrides intentionally replace all values under their key; those cases still pass.

The list, one-shot iterator and equivalent OMD represent the same ordered pairs. Only the fixed variant produces the same records across all three representations, for both implementations. This relation supplements literal answers: implementations can agree and still be wrong.

All variants ran on Windows/Python 3.12.10. The fixed 24 observations also matched on Python 3.11.15. Untouched upstream dictutils/urlutils tests plus their module doctests passed: **176 before and 184 after**. The full upstream suite was not run, and no dependencies were installed.

## Receiving-question comparison

Both questions bind all 30 package Python files, probe, manifest, oracle and runtime, then compare the complete count/return/consumption observations. The complete question also directly compares the expected and actual ordered records and query strings. It uses the records themselves, not a self-reported pass count. Intended values come from the frozen literal oracle, independently of the receipts.

Count handling accepts all three actual variants. Complete handling rejects both defective variants and accepts the published fix. Two separate **synthetic receipt controls** remove the records field or reorder one valid result without changing its count or multiset. Complete handling refuses them as MISSING or MISMATCH, respectively, with no partial observations. These are diagnostics, not additional executions of Boltons. All five predeclared decisions matched.

Valid observations and qualifiers are retained exactly. Both questions read the same fixed source once, 23,172 bytes. Question bytes grow 1,396→1,558 and response bytes 24,069→24,122 (+53). These are exposed byte counts, not measured latency, cost or agent-reasoning gains.

The six source-distribution commands run parent count/complete, fixed count/complete and dedup count/complete. Expected exit codes: 0,1,0,0,0,1. OBSERVED under the count question does not establish record preservation.

~~~sh
python tools/read_requirements.py --question examples/ordered_records/base-count.json --sha256 a396ea20925d31b48d5b8e99277cd05a7e159b3393c6c136f44abcc5f3c67109 --source examples/ordered_records/base-source.json
python tools/read_requirements.py --question examples/ordered_records/base-complete.json --sha256 36fe5477c888d8d80f5245dd954c01676d70b3fdb29d392ac77e7d6fcdb56d47 --source examples/ordered_records/base-source.json
python tools/read_requirements.py --question examples/ordered_records/fixed-count.json --sha256 f158505aaad654a807255124b5a8c06e8faed7c418e137f607e1f073f57e7e94 --source examples/ordered_records/fixed-source.json
python tools/read_requirements.py --question examples/ordered_records/fixed-complete.json --sha256 132893c443b8609f101138a8330d56f4b88038e5f92a0d84850b25c71065bfc8 --source examples/ordered_records/fixed-source.json
python tools/read_requirements.py --question examples/ordered_records/dedup-count.json --sha256 449e45b921aad5fcbe8c23be7c2dbb848bb06ce7284c249f6ea073351e6691ec --source examples/ordered_records/dedup-source.json
python tools/read_requirements.py --question examples/ordered_records/dedup-complete.json --sha256 f1b447d86458582abd2fdb247830aa720440bc1468f43ebf11e173c5805e8453 --source examples/ordered_records/dedup-source.json
~~~

## Reproduce actual updates

Use a trusted checkout and fresh process: the probe executes selected package code. Use an unused destination and create the work directory if necessary. The Git options are process-scoped and do not modify user configuration.

~~~sh
git -c core.autocrlf=false clone https://github.com/mahmoud/boltons.git work/boltons-records
git -C work/boltons-records -c core.autocrlf=false checkout --detach 40fffc5ba0a84315c79813daa47db35157d64556
python examples/ordered_records/probe.py --repo work/boltons-records --manifest examples/ordered_records/manifest.json --manifest-sha256 68d9da5c7714839b03571c61c50cb7e7960b3b1299bf7fc92c47f18f7ec970be --oracle examples/ordered_records/oracle.json --oracle-sha256 3959beac45f2b6f770b0b73b9f9cc35001098196d58521b27305896d75577751
git -C work/boltons-records apply ../../examples/ordered_records/fixed.patch
python examples/ordered_records/probe.py --repo work/boltons-records --manifest examples/ordered_records/manifest.json --manifest-sha256 68d9da5c7714839b03571c61c50cb7e7960b3b1299bf7fc92c47f18f7ec970be --oracle examples/ordered_records/oracle.json --oracle-sha256 3959beac45f2b6f770b0b73b9f9cc35001098196d58521b27305896d75577751
~~~

The parent exits 1 with eight failed observations; fixed exits 0. For the negative control, apply `dedup.patch` to another fresh parent checkout instead; it exits 1 with fourteen failures. Both patches start at the parent, not one on top of the other. Preserve full patch context and the included upstream license.

Raw identities use LF source bytes. Before original execution and fresh packaged patch replays, all 30 Python files were normalized and verified against the intended source. Different raw bytes or runtimes require fresh receipts; do not relabel saved evidence. Windows index/status markers alone are not the source-identity oracle.

## Evidence boundary

[Chen, Cheung and Yiu, Metamorphic Testing: A New Approach for Generating Next Test Cases](https://arxiv.org/abs/2002.12543) is the 1998 HKUST report archived in 2020. Its abstract motivates related follow-up inputs that expose faults left hidden by successful cases. Here we use representation-equivalent inputs together with explicit literal answers. This is not a reproduction of the paper's results.

Adopt the receiving-question pattern that requires ordered occurrences and serialized output when they are part of the task. The external patch remains an example; the lossy control is rejected. Root read the solution before freezing. There is no blind solve, fresh independent agent review, full upstream suite, general preservation proof, or performance comparison. Native attempts remain 6/6. Portable CI checks saved evidence, public commands and input bounds; it does not execute external Boltons on every CI OS. No installed skill or host setting changed.
