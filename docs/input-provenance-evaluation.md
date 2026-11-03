# Bind results to the configuration that was actually read

A correct output can come from the wrong test input. [ConfigArgParse issue 164](https://github.com/bw2/ConfigArgParse/issues/164) reports that a command-line boolean option clashes with its opposite in a config file, despite the documented override order. [Merged PR 358](https://github.com/bw2/ConfigArgParse/pull/358) extends overrides to other members of a mutually exclusive group. Same-source conflicts must still fail.

This known-answer example executes original commit `04fb885605a3aaa165b71c8f72fd7bbbc93ca469` and accepted fix `d8ac796b869dddef7beb099acc3434bb73e473ef` on ten frozen cases. A third run uses the **original unfixed code** with three deliberately stale, empty config files. Five cases no longer exercise the conflicting options, while their output remains correct. The other five cases retain their original inputs.

## What changes the acceptance decision

| Actual run | Output matches | Requested input identity matches | Code + output question | Input-bound question |
|---|---:|---:|---|---|
| Original code, requested configs | 5/10 | 10/10 | INSUFFICIENT | INSUFFICIENT |
| Accepted fix, requested configs | 10/10 | 10/10 | OBSERVED | OBSERVED |
| Original code, stale configs | 10/10 | 5/10 | OBSERVED | INSUFFICIENT |

The code/output question already binds the proposal to the observed code, probe, case manifest, output oracle and Python runtime. The stronger question adds one equality relation for `expected_inputs` and `actual_inputs`, keyed by case ID and carrying logical path, byte count and SHA256. Comparing only a bag of file hashes would not establish which input each case consumed.

The input-bound question removes one false acceptance across the three actual runs and preserves the accepted fix. Two additional **synthetic receipt** controls remove input records or swap the case-to-file mappings while retaining the outputs. Both are rejected; they are not additional target executions. The full observations and their qualifications remain unchanged whenever a result is OBSERVED. These labels indicate the declared evidence relations, not an attestation of correct execution.

For the accepted fix, both policies read the same 9,711-byte source once. The question grows from 1,428 to 1,587 bytes, and the response from 10,609 to 10,661 bytes. No speed, token-cost or model reasoning improvement was measured.

## Reproduce the handoff checks

From the source archive, run these in order. Nonzero exits are expected for the two original-code questions and the final stale-input question:

```sh
python tools/read_requirements.py --question examples/input_provenance/base-code.json --sha256 a592325712f6bde237fe9353823e7adc2679c583a57416db3857fb8e7abddae2 --source examples/input_provenance/base-source.json
python tools/read_requirements.py --question examples/input_provenance/base-inputs.json --sha256 9469b30db454fdf295416aa7ada54e9da2903a5f0760f157b0ab49e85b1a147b --source examples/input_provenance/base-source.json
python tools/read_requirements.py --question examples/input_provenance/fixed-code.json --sha256 70d07c34bced583c83c289e157be9d13638c87bcea43413d70adf251f82be4ab --source examples/input_provenance/fixed-source.json
python tools/read_requirements.py --question examples/input_provenance/fixed-inputs.json --sha256 6068752920037024607c5da031085913a7c0c48b7c551780fb599261e7537ca2 --source examples/input_provenance/fixed-source.json
python tools/read_requirements.py --question examples/input_provenance/stale-code.json --sha256 ad7e4745f35106b133fb51d2ef7409b81bf108e33ee34e8a3031884cc907a3db --source examples/input_provenance/stale-source.json
python tools/read_requirements.py --question examples/input_provenance/stale-inputs.json --sha256 bdeb63f2e728409c64d7e8f0499c51fad7d811def5d33da0dd3ec2d970c17ece --source examples/input_provenance/stale-source.json
```

The reader CLI is unchanged. CI verifies these saved receipts, frozen bytes, bindings, missing-data refusal and complete observation retention on its three-OS matrix. It does **not** run historical ConfigArgParse on all three OSes.

## Reproduce an actual target run

Use Python 3.11+ and Git supporting `--no-lazy-fetch`. The recorded external run used Windows and CPython 3.12.10. No third-party dependency was added. The original source module and two upstream test files are identified in the manifests; standard-library behavior is bounded by the recorded runtime.

Use new directories for the clone and prepared source. The [canonical snapshot helper](canonical-source-preparation.md) verifies every selected raw Git blob before creating its destination:

```sh
git clone --no-checkout https://github.com/bw2/ConfigArgParse.git sample-source
python tools/prepare_source_snapshot.py --repo sample-source --manifest examples/input_provenance/fixed-source-manifest.json --sha256 de430cbaa6396da1044426a3728ffba820ab2ae99163ff66ac06c92c3daed399 --target prepared-fixed --apply
python examples/input_provenance/probe.py --repo prepared-fixed --inputs examples/input_provenance/inputs --manifest examples/input_provenance/manifest.json --manifest-sha256 cc500b73ad52df58a7f5fc9d7557ad459a8c687345d12c50d3eb7e25cc61be09 --oracle examples/input_provenance/oracle.json --oracle-sha256 b4cb5c7cd9b7ea9995adbb7957ade9cae90be534af10e71b342907422f659cae
```

The source package also includes the base manifest, stale input directory, full accepted patch and upstream MIT license. To reproduce the stale control, prepare the base manifest into another new directory and pass `examples/input_provenance/stale-inputs` as the input directory. A probe exit of 0 reports matching **outputs only**; the input-bound question is still required for acceptance.

Each case reads the requested file once through ConfigArgParse's public `config_file_open_func` hook. The probe hashes those actual raw bytes and supplies the same UTF-8-decoded content through a named StringIO to the unmodified parser. CLI arguments and environment values are explicit; the real host environment is not used as parser input. This is a trusted local observation hook, not a general filesystem or authenticity sandbox.

Selected, unmodified upstream tests also pass: one existing mutually-exclusive test on the original source, and that test plus the two added override tests on the fixed source. Their unequal counts reflect different test inventories. The complete upstream suite was not run.

## Method and limits

[Buneman, Khanna and Tan, ICDT 2001](https://homepages.inf.ed.ac.uk/opb/papers/ICDT2001.pdf), abstract/introduction pp. 1–2, distinguishes provenance that explains a result from provenance that identifies its source locations. This experiment adapts the source-location concern to case-to-config bindings. It does not reproduce their database formalism or prove general semantic provenance.

The literal inputs, outputs, permitted substitutions and acceptance decisions were frozen before the three executions. Root authored the probe and reviewed the public fix, so this is not a blind solve or an independent agent evaluation. The inherited native delegation budget remains 6/6. The first formatter expected the logical label READY instead of the reader's existing OBSERVED status; the mismatch stopped assembly. That failure and the original receipts were preserved, the label adapter was corrected, and the frozen inputs/oracle and actual runs were not changed or repeated.

Hashes bind declared identities; a fabricated receipt can still lie about execution. Preserve trusted execution records and do not interpret these checks as proof of honesty or complete dependency capture. No installed skills, global configuration or existing reader semantics were changed.
