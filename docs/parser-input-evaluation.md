# Check what actually reaches the parser

Raw files can match while preprocessing removes the feature a regression test must exercise. This source-only example extends the [raw input relation](json-input-transfer.md) with a case-keyed relation on the exact final string passed to the parser. The existing reader is unchanged.

[uiri/toml issue110](https://github.com/uiri/toml/issues/110) reports failures on escaped quotes. We compare parent `1e68e881801e7c33e79edfc51ddc9ca9398962dd` and accepted [fix2b6e188](https://github.com/uiri/toml/commit/2b6e1881c5b6027fe4790d582e32227eac5b6a5f). The full accepted diff and MIT license are included. For example, TOML `test = "\"one\""` must decode to a string containing both quote characters, `"one"`.

## Frozen comparison

Before importing the target, we froze ten raw payloads, literal expected parser strings, literal answers, two permitted newline transformations, four explicit adverse rewrites and the expected decisions. Four regression cases put quotes at the beginning, end or both ends, including Japanese text. Controls cover an equivalent literal string, a plain string, a backslash, integer/boolean values, a reserved escape error and an empty document.

| Actual run | Correct outputs | Raw identities match | Parser inputs match | Raw-bound decision | Parser-bound decision |
|---|---:|---:|---:|---|---|
| Original code, declared preprocessing | 6/10 | 10/10 | 10/10 | INSUFFICIENT | INSUFFICIENT |
| Accepted fix, declared preprocessing | 10/10 | 10/10 | 10/10 | OBSERVED | OBSERVED |
| Original code, four same-value rewrites | 10/10 | 10/10 | 6/10 | OBSERVED | INSUFFICIENT |

The adverse preprocessor converts the four escaped basic strings to TOML literal strings before calling the original parser. It preserves the expected decoded values, but discards the syntax needed to exercise the quote-handling bug. **The loss here is required test coverage, not the resulting string value.** Every raw file is identical across the three runs. This isolates the gap in raw-file validation.

The baseline already binds code, probe, manifest, oracle, runtime, outputs and raw inputs. The candidate adds only `expected_parser_inputs == actual_parser_inputs`, keyed by case ID. Each parser identity contains type `str`, character count, UTF-8 byte count, SHA256 and the bounded captured text. Expected text is independently literal in the frozen contract; it is never inferred from the target's observed input. Across these three actual runs, the extra relation removes one false acceptance while retaining the valid fix. This is a bounded result, not a general accuracy estimate.

CRLF-to-LF normalization is explicitly permitted for the Japanese quote and number/boolean cases. The expected parser strings already contain LF. Both pass on the fix even though their raw-file hashes differ from parser-input hashes. Thus the rule does not require all transformations to preserve bytes; it requires the **declared final representation** to match.

Two separately labeled synthetic receipt controls remove parser-input evidence or swap the basic/literal same-value case mappings. Raw inputs and outputs stay identical; the swap retains the same bag of parser hashes. Both are rejected. These are receipt edits, not additional target runs. Every observation and qualification is retained on OBSERVED; failed relations expose no success-shaped requirements view.

The fixed-run source is 14,510 bytes and is read once by each policy. The question grows from 1,582 to 1,762 bytes; the response grows from 15,453 to 15,512 bytes. No speed, token-cost or reasoning improvement was measured.

## Replay saved handoffs

From the **source archive**, run the following commands. Expected exit codes are `1, 1, 0, 0, 0, 1`:

```sh
python tools/read_requirements.py --question examples/parser_input/base-raw.json --sha256 02ab41fbf951f9f6da7ac2b1099de6a1f2a84c102369e89081ba058ce8037dcc --source examples/parser_input/base-source.json
python tools/read_requirements.py --question examples/parser_input/base-parser.json --sha256 b0c70a5cebfe873add65a400409a03831a0ba70543d829b6be98e4a26b66dfda --source examples/parser_input/base-source.json
python tools/read_requirements.py --question examples/parser_input/fixed-raw.json --sha256 8f4df40b72bb34d26b37a353f46b390e0afeef5b61245668aa7170c7c342eb97 --source examples/parser_input/fixed-source.json
python tools/read_requirements.py --question examples/parser_input/fixed-parser.json --sha256 a7dc3b55f29944f72433a81c976caa444e63eb2e083aa2039afee05d6bed0475 --source examples/parser_input/fixed-source.json
python tools/read_requirements.py --question examples/parser_input/rewritten-raw.json --sha256 f7af2b97a80c9ab2ac42edce3798552d27c7e421f3ee63b2347808f621dee805 --source examples/parser_input/rewritten-source.json
python tools/read_requirements.py --question examples/parser_input/rewritten-parser.json --sha256 f02cf3466b847550078786af9047b8077a4dd7f89e854deff4e1dd4ae6d15769 --source examples/parser_input/rewritten-source.json
```

CI checks saved evidence, relation failures, exact fixture bytes, all-observation retention and instrumented parser entry on three OSes. CI does not execute historical TOML across those OSes. The plugin contains this documentation and the generic reader; the task's fixtures, probe and snapshot helper are in the source archive.

## Reproduce the actual task

Use Python3.11+ and Git supporting `--no-lazy-fetch`, with new clone/export directories. The recorded external runs used Windows/CPython3.12.10:

```sh
git clone --no-checkout https://github.com/uiri/toml.git sample-source
python tools/prepare_source_snapshot.py --repo sample-source --manifest examples/parser_input/fixed-source-manifest.json --sha256 9bd13eda2f037d2a9259ef9f867474fd041635416067094e23b8ce443d5f1c24 --target prepared-fixed --apply
python examples/parser_input/probe.py --repo prepared-fixed --inputs examples/parser_input/inputs --manifest examples/parser_input/manifest.json --manifest-sha256 6fa4ab3267463303cea7f68b0baf9c74c4861196b619cbf0857743c715971f13 --oracle examples/parser_input/oracle.json --oracle-sha256 f2d6b3518c0959421a4cb271a97ead1e45e484f6b9b86ccd13efd5b237d3a969 --mode declared
```

The [snapshot helper](canonical-source-preparation.md) exports three pinned raw Git blobs: `toml.py`, the upstream CLI adapter `tests/decoding_test.py` and the license. The probe imports the exact prepared module, records its path and checks the source scope again after execution. No third-party dependencies are installed; the standard library depends on the recorded runtime.

Payloads are read once as binary fixtures. The probe applies UTF-8 decoding and only declared newline normalization, followed by the explicitly selected adverse control if requested. Immediately before `loads`, it records the final immutable string and passes that same object to the parser. Portable tests instrument both capture and parser entry, including exceptions. This boundary is the public `loads(str)` call, not every internal lexer buffer or downstream transformation.

To repeat the original run, prepare `base-source-manifest.json` using its independent pin `68f82d5581fc9ac837229c468f6da37959a5e381629a89df81b1dd1e88e79bb0` into a fresh directory, then select that directory with `--mode declared`. For the adverse control, use the same original source and raw inputs with `--mode rewrite_quotes`. Probe exit0 means outputs match; parser-bound acceptance is a separate check.

The unchanged upstream CLI decoding adapter also produced independently frozen tagged answers for one plain case on original code and two cases on the fix (plain and escaped quotes). These are **adapter smoke checks**, not upstream unit tests. The full upstream suite was not run. A historical test commit mentioned in discussion could not be resolved and is not claimed as executed evidence.

## Method and limits

The [TOML0.4.0 specification](https://toml.io/en/v0.4.0), corresponding to this historical module's declared spec, defines escaped basic strings, unescaped literal strings and LF/CRLF newlines. These rules justify the literal oracle and the permitted transformations.

[Chen, Cheung and Yiu (1998), Metamorphic Testing](https://arxiv.org/abs/2002.12543), introduction, preliminaries and conclusion, motivates additional tests derived from apparently successful cases using domain knowledge. It does not make checker acceptance proof of correctness. We use literal oracles and explicit controls; we do not demonstrate the paper's overhead condition or a general metamorphic-testing methodology. The original PDF text was read through alphaXiv with font extraction artifacts; no full-paper or equation-based claim is made.

Root read the published fix and authored the experiment. This is a known-answer reproduction, not a blind solve or a fresh independent agent evaluation. The inherited native delegation budget remains6/6. Stable local paths and honest records are trusted: hashes establish consistency, not authenticity of execution or a filesystem sandbox. Earlier failures and results remain preserved. No reader semantics, installed skills or global settings were changed.
