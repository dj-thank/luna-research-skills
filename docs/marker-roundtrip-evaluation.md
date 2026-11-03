# Preserve semantics while repairing serialization

A patch can fix every reported failure while changing valid behavior elsewhere. This example separates **repair obligations** from **preservation obligations** in the receiving question, using a real published parser fix. Both sets are required before accepting the result.

The source ZIP contains the [probe, literal oracle, patches and receipts](https://github.com/dj-thank/luna-research-skills/tree/main/examples/marker_roundtrip). The plugin includes this guide; external execution is source-only. The requirement-reader runtime is unchanged.

## Actual external task

[pypa/packaging PR1213](https://github.com/pypa/packaging/pull/1213) repairs marker quote serialization. We use the fix's actual sole parent `2497782b2bb03812d2a12ae882a4390c61ec5061` and accepted squash commit `5b583e309996a085ad3b5b045f3bf50a09c11b58`, rather than the PR API's potentially different base snapshot.

The published input contains an entire expression inside a single quoted literal:

~~~text
'a" == os_name or python_version >= "0" or "b' == os_name
~~~

With the synthetic `os_name=posix` and `python_version=3.12`, its original evaluation is false. The old serializer places double quotes around the embedded double quotes. Re-parsing then introduces operators and evaluates true. This is a parsing experiment: no package is installed and no URL is fetched.

Before execution we froze twelve literal answers: four repairs for this marker, the same input in a requirement, an embedded quote, and refusal of a direct Value containing both quote characters; eight preservation cases for plain/version/single-quote values, machine and implementation case, normalized extra names, and requirement URL/name/extras. We compare parsed literals and requirement fields as well as evaluation under a complete synthetic environment. Matching one evaluation alone would be weaker evidence. All twelve environment keys are supplied explicitly; receipts never export the host environment.

| Actual variant | Repairs | Preserved behavior | Total |
|---|---:|---:|---:|
| Parent before fix | 0/4 | 8/8 | 8/12 |
| Published quote-selection fix | 4/4 | 8/8 | 12/12 |
| Fix plus blanket casefold control | 4/4 | 6/8 | 10/12 |

The fixed serializer chooses a delimiter absent from the value and rejects a value containing both quote characters. The negative control applies `casefold()` first: it repairs quoting but changes `AMD64` and `CPython`, causing two true evaluations to become false after re-parsing. Intentional normalization of `extra == "Foo_Bar"` to `foo-bar` remains valid. The control is retained for comparison and rejected for adoption.

All three variants ran on Windows/Python3.12.10. The fixed twelve cases also passed on Python3.11.15 with identical observations. The untouched upstream marker/requirement subsets passed: **7,614 tests before the fix and 7,620 after**. The full upstream suite was not run. The accepted commit adds six upstream tests; our separate twelve-case oracle was frozen before our execution, after root had read that published solution.

## Receiving-question comparison

Both questions bind all22 package Python files, probe, manifest, oracle and runtime, then require every repair case. The complete question additionally requires all eight preservation cases. Intended identities come from the pre-execution frozen record, independently of execution receipts.

Repair-only handling rejects the old version but accepts both fixed and casefold variants. Complete handling also rejects the casefold regression. A separate synthetic missing-preservation receipt is refused with INSUFFICIENT/MISSING and no partial observations. All four planned decisions matched. Valid results retain every observation and qualifier.

Both questions read the same fixed source once,15,635 bytes. Question bytes grow1,405→1,582 and response bytes16,537→16,596 (+59). These are exposed byte counts, not measured latency, model cost or reasoning-quality improvements.

Run these source-distribution commands in order: base repair/complete, fixed repair/complete, casefold repair/complete. Expected exit codes:1,1,0,0,0,1. OBSERVED under repair-only handling does not establish preservation.

~~~sh
python tools/read_requirements.py --question examples/marker_roundtrip/base-repair.json --sha256 a9a024e060460df738d39998e5a26edb5a541bd43bfda53fe509acc380d65834 --source examples/marker_roundtrip/base-source.json
python tools/read_requirements.py --question examples/marker_roundtrip/base-complete.json --sha256 22d0f96e482420163c27affbec0a6595fc47cff5837f591c1e57ffe08a1f92f4 --source examples/marker_roundtrip/base-source.json
python tools/read_requirements.py --question examples/marker_roundtrip/fixed-repair.json --sha256 1a69552cb95cd4cb84352033ac93609311bb4445fd5f1e822048fe2ce7c0d36f --source examples/marker_roundtrip/fixed-source.json
python tools/read_requirements.py --question examples/marker_roundtrip/fixed-complete.json --sha256 2e36734d7c6735cc5d58b5d7d2746fab79788cbed99c214c85ccc0d0b6394199 --source examples/marker_roundtrip/fixed-source.json
python tools/read_requirements.py --question examples/marker_roundtrip/casefold-repair.json --sha256 330781100dd09758869cc7de8a7016fa78d6e461db72f255f1aec9ea5d2607e0 --source examples/marker_roundtrip/casefold-source.json
python tools/read_requirements.py --question examples/marker_roundtrip/casefold-complete.json --sha256 c320685245917b303d2f3b0a74ae0449d90fecb2db577cd3ad907ae9d6f2c573 --source examples/marker_roundtrip/casefold-source.json
~~~

## Reproduce the external execution

Use a trusted checkout and fresh process: this probe executes package code. Use an unused destination and create the work directory if needed. The process-scoped Git options avoid changing user configuration. No dependencies are installed.

~~~sh
git -c core.autocrlf=false clone https://github.com/pypa/packaging.git work/packaging-markers
git -C work/packaging-markers -c core.autocrlf=false checkout --detach 2497782b2bb03812d2a12ae882a4390c61ec5061
python examples/marker_roundtrip/probe.py --repo work/packaging-markers --manifest examples/marker_roundtrip/manifest.json --manifest-sha256 9f7ebbac3e08093f686d3baa1062bae3a2c1ce47858d2e094f7e5888463060d4 --oracle examples/marker_roundtrip/oracle.json --oracle-sha256 a4d8997cdc5856b59b9f728f51168caff0a1cf55bcb80ac118bb72bb294bf73f
git -C work/packaging-markers apply ../../examples/marker_roundtrip/fixed.patch
python examples/marker_roundtrip/probe.py --repo work/packaging-markers --manifest examples/marker_roundtrip/manifest.json --manifest-sha256 9f7ebbac3e08093f686d3baa1062bae3a2c1ce47858d2e094f7e5888463060d4 --oracle examples/marker_roundtrip/oracle.json --oracle-sha256 a4d8997cdc5856b59b9f728f51168caff0a1cf55bcb80ac118bb72bb294bf73f
~~~

The first probe exits1 with four expected failures; the second exits0. For the negative control, use another fresh parent checkout and apply `casefold.patch` instead of `fixed.patch`; it exits1 with two preservation failures. Both patches are based on the parent, not stacked. Preserve full patch context and the included upstream license notices.

Execution inventories use raw LF source bytes. Source setup verified every original Python file against its Git blob; fresh packaged patch replays normalize source line endings before identity checks. Two pre-execution source-setup assertions encountered Windows index/status markers despite equal bytes and empty semantic diffs. Those failures were retained; external Git status is not presented as clean. Different raw bytes or runtimes require fresh receipts, not relabeling of saved ones.

## Scope of adoption

[Fu et al., Behavioral Regression Detection for Pull Requests via Structured Oracles](https://arxiv.org/html/2610.35223v1), sectionsIII-A–III-C, motivates separating intended changes from behavior that must remain unchanged before differential execution. This manually constructed comparison adopts that distinction; it does not reproduce ORION or its reported benchmark results.

Adopt the receiving-question pattern that requires both repair and preservation evidence. The external fix remains an upstream example, and the casefold alternative remains rejected. Twelve hand-authored cases do not prove general semantic equivalence. Root read the published solution before freezing and reviewed the integration; there is no blind solve or fresh independent agent evaluation. The inherited native budget remains6/6. Portable CI checks saved evidence, documented commands and input bounds; it does not run external packaging on every CI OS. No installed skill or host setting changed.
