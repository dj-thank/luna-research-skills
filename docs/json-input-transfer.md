# Transfer input-bound evidence to a JSON parsing regression

A JSON payload can decode to the expected value without exercising the requested bug. This example transfers the [configuration-input relation](input-provenance-evaluation.md) unchanged to a second repository: simplejson's historical handling of a UTF-8 byte order mark (BOM).

[PR 101](https://github.com/simplejson/simplejson/pull/101) reports a failure when loading BOM-prefixed JSON. Its submitted patch was followed by [commit 925cae7](https://github.com/simplejson/simplejson/commit/925cae72acd6a0d2a789cdc363736ed826f8ffa6), which generalizes handling into the decoder. We compare original `b7486b82233ed2ec1a614dcf8944d376d12d04bf` with that finalized commit, not the intermediate PR patch. The full accepted diff and upstream MIT license are included.

## Fixed comparison

Before importing the target, we froze ten literal payloads, their expected values or JSONDecodeError, parser routes, source manifests and permitted substitutions. Four cases cover BOM-prefixed object, array, scalar and Japanese content through `load`/`loads`, using text and byte inputs. Six controls cover plain object/array, a BOM inside a string, empty input, malformed JSON and a doubled leading BOM. The inner BOM must survive as data; invalid inputs must still fail.

| Actual run | Output matches | Requested input identity matches | Code + output question | Input-bound question |
|---|---:|---:|---|---|
| Original code, requested payloads | 6/10 | 10/10 | INSUFFICIENT | INSUFFICIENT |
| Finalized fix, requested payloads | 10/10 | 10/10 | OBSERVED | OBSERVED |
| Original code, four BOM-stripped payloads | 10/10 | 6/10 | OBSERVED | INSUFFICIENT |

The stale-input run uses the same original code. Removing the leading BOM from only the four valid BOM cases hides all four original failures while preserving their expected values. This substitution is explicit experimental input, not preprocessing in the probe.

The stronger question adds the same case-keyed equality relation for `expected_inputs` and `actual_inputs` used in the previous task. Each identity contains the logical path, byte count and SHA256. The other relations already bind code, probe, manifest, oracle, runtime and outputs. Across these three actual runs, input binding removes one false acceptance and retains the valid fix. This is a bounded transfer result, not a general accuracy estimate.

Two additional **synthetic receipt controls** remove input identities or swap the BOM-object and plain-object case bindings. The swapped inputs decode to the same object and retain the same bag of file hashes. Both controls are rejected by the input relation; neither is another target execution. Every observation and qualification is preserved when the result is OBSERVED, and failed relations do not expose a success-shaped requirements view.

The fixed-run source is 10,457 bytes and is read once by each policy. The question grows from 1,401 to 1,560 bytes; the response grows from 11,350 to 11,402 bytes. No speed, token-cost or reasoning improvement was measured. The reader implementation is unchanged.

## Reproduce the handoff checks

From the source archive, run these commands in order. Expected exit codes are `1, 1, 0, 0, 0, 1`:

```sh
python tools/read_requirements.py --question examples/json_input_transfer/base-code.json --sha256 12328f82b96db1d0292028d7dd27780b0e61dd4a0ec44b21f3a65c9ac79988df --source examples/json_input_transfer/base-source.json
python tools/read_requirements.py --question examples/json_input_transfer/base-inputs.json --sha256 854bbc5e2600b217b17941282ddd06732c366d421394fe70b29a9ba5ef6cdd9b --source examples/json_input_transfer/base-source.json
python tools/read_requirements.py --question examples/json_input_transfer/fixed-code.json --sha256 8170d820fc0b9e90ed1b83422c573639d61a2ab856dbfa41d2a645b8dbb82ea7 --source examples/json_input_transfer/fixed-source.json
python tools/read_requirements.py --question examples/json_input_transfer/fixed-inputs.json --sha256 4919b80512073c092a49c66847593861245c28e161a46666a5d5208f7bf65d1e --source examples/json_input_transfer/fixed-source.json
python tools/read_requirements.py --question examples/json_input_transfer/stale-code.json --sha256 95062f9494445d92438f515c0c258f769c2279815d51579151813b618cd17bc9 --source examples/json_input_transfer/stale-source.json
python tools/read_requirements.py --question examples/json_input_transfer/stale-inputs.json --sha256 910abfd1aa3eaf52ae5d6bd77b0f01785a9ef7904c0de10d3cc701ab6508eb26 --source examples/json_input_transfer/stale-source.json
```

CI checks the saved receipts, input bytes, parser-route manifest, binding failures and observation retention across its three-OS matrix. CI does not execute historical simplejson on all three OSes.

## Reproduce the actual JSON task

Use Python 3.11+ and Git supporting `--no-lazy-fetch`. The recorded run used Windows and CPython 3.12.10. Use fresh directories for both clone and export:

```sh
git clone --no-checkout https://github.com/simplejson/simplejson.git sample-source
python tools/prepare_source_snapshot.py --repo sample-source --manifest examples/json_input_transfer/fixed-source-manifest.json --sha256 439634fc4dbe7c784a324f8962bf5935696f9e89c4b020027737c266eb80694a --target prepared-fixed --apply
python examples/json_input_transfer/probe.py --repo prepared-fixed --inputs examples/json_input_transfer/inputs --manifest examples/json_input_transfer/manifest.json --manifest-sha256 ac62922a276850eee75154d6b24ef690b7cff117ae893bd1fb47597a969e2e79 --oracle examples/json_input_transfer/oracle.json --oracle-sha256 c3df40cc3ef136c70644e53dd004d5984cc733914e91f7ef53057ed5693bd65a
```

The [snapshot helper](canonical-source-preparation.md) verifies nine raw Git blobs: six package modules, two selected test files and the license. The probe rejects C speedups or imported target modules outside its pinned scope, and confirms source hashes after observation. No third-party dependency is installed. The standard library remains dependent on the recorded runtime.

Each payload is read once in binary mode. Its exact buffer is hashed and passed to the unmodified parser, either as bytes or decoded with `utf-8`. Text decoding deliberately retains the BOM; `utf-8-sig` would erase the feature being tested. `.bin` stores JSON payloads as binary fixtures so Git and archive creation preserve their exact bytes, including BOMs and the empty file.

The base source manifest and `stale-inputs` directory reproduce the other runs. Prepare the base manifest into another fresh directory, then select `inputs` for the original or `stale-inputs` for the misleading output-success control. Probe exit 0 means only that the outputs match; input-bound acceptance remains a separate check. Two selected encoding tests pass on original code; those tests plus the upstream BOM test pass on the finalized fix. The full upstream suite and compiled extension were not tested.

## Method and limits

[RFC 7159 section 8.1](https://www.rfc-editor.org/rfc/rfc7159#section-8.1) permits parsers to ignore a BOM for interoperability; it does not require them to do so. Our oracle tests simplejson's published compatibility behavior, not a universal requirement for every JSON parser.

[McKeeman, Differential Testing for Software (1998)](https://www.cs.swarthmore.edu/~bylvisa1/cs97/f13/Papers/DifferentialTestingForSoftware.pdf), indexed primary-paper abstract, motivates comparing comparable systems on common inputs and investigating disagreements. Here the exact input relation is essential to that common-input premise. We use fixed literal answers instead of deriving truth from implementation agreement. This small regression comparison does not implement the paper's random test generation. Direct PDF retrieval failed, so no full-paper reading is claimed.

Root read the public issue and fix and authored the probe before execution. This is a known-answer reproduction, not a blind repair or fresh independent agent evaluation. The inherited native delegation budget remains 6/6. Local stable files and honest execution records are trusted: hashes establish consistency of declared identities, not authenticity of the execution or a general filesystem sandbox. Prior failures and experimental records remain preserved. No reader semantics, installed skills or global settings were changed.
