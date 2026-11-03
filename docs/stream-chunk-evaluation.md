# Verify the chunks actually delivered, in order

A correct whole buffer does not establish which streaming boundaries were exercised. This source-only example extends [parser-boundary evidence](parser-input-evaluation.md) to the ordered bytes actually returned to an incremental consumer. The generic reader is unchanged; the candidate adds one equality relation on case-keyed delivery traces.

## A real streaming regression

[SSEClient issue9](https://github.com/mpetazzoni/sseclient/issues/9) concerns Unicode data loss. Accepted [fix f262d14](https://github.com/mpetazzoni/sseclient/commit/f262d1432e7e0d805a1e5af644428193a653d752) also defers UTF-8 decoding until chunks have been reassembled. We reproduce that split-codepoint failure against parent `f39f74aed04883db4cd2b507de710afaf3f05a1d` and the accepted fix. The full diff and Apache2.0 license are included. The fix's separate Unicode-line-separator behavior is outside this experiment.

Before importing either target, we froze twelve literal byte streams, their allowed chunk sequences, literal event answers, expected failures and adoption conditions. Cases cover 2/3/4-byte UTF-8 splits, Japanese text, a second split of the same euro sign, a whole-buffer control, split ASCII fields, two ordered events, repeated fragments, metadata/comments, multiline CRLF and empty input. Each schedule is a separate declared case; arbitrary segmentation is not claimed.

| Actual run | Correct outputs | Raw files match | Delivered buffers match | Ordered deliveries match | Buffer policy | Chunk policy |
|---|---:|---:|---:|---:|---|---|
| Original, declared chunks | 7/12 | 12/12 | 7/12 | 7/12 | INSUFFICIENT | INSUFFICIENT |
| Accepted fix, declared chunks | 12/12 | 12/12 | 12/12 | 12/12 | OBSERVED | OBSERVED |
| Original, coalesced chunks | 12/12 | 12/12 | 12/12 | 4/12 | OBSERVED | INSUFFICIENT |
| Fix, reordered repeated fragments | 12/12 | 12/12 | 12/12 | 11/12 | OBSERVED | INSUFFICIENT |
| Fix, dropped first event | 11/12 | 12/12 | 11/12 | 11/12 | INSUFFICIENT | INSUFFICIENT |

The original raises UnicodeDecodeError before pulling the rest of each split-character stream. Its receipt contains only the delivered prefix, and records that exhaustion was not observed. Coalescing makes the unfixed implementation succeed, concealing required boundary coverage. Reordering `A` and `AA` in `[data: , A, AA, LF LF]` preserves the bag of chunks, concatenated bytes and output `AAA`, but loses the requested order and boundaries. These two controls lose **test conditions**, not decoded output values. Dropping the first of two events demonstrates actual output loss; the baseline already rejects that case.

The baseline binds code, probe, manifest, oracle, runtime, literal outputs, raw file identities and concatenated **actually delivered** bytes. The candidate additionally requires `expected_deliveries == actual_deliveries`: a case-keyed ordered list of chunk type, byte count, SHA256 and bounded hex, plus whether the consumer pulled to exhaustion. Expected lists are literal fixtures independent of observed receipts. In five actual variants, decisions improve from 3/5 to 5/5 under the frozen contract, removing two false acceptances and retaining the valid fix. This is not a general accuracy estimate.

Three allowed segmentations of the euro event (two chunks, three chunks and one whole chunk) all remain accepted on the fix. Two separately labeled **synthetic receipt edits** remove delivery evidence or change exhaustion to false; both are rejected without changing outputs. They are not extra target executions. OBSERVED preserves all observations and qualifications. Failed relations do not expose a success-shaped requirements view.

The fixed source is 28,421 bytes, read once by each policy. Questions grow from 1,742 to 1,913 bytes; responses from 29,416 to 29,472 bytes. No speed, token-cost or reasoning improvement was measured.

## Replay saved handoffs

Use the source archive. Expected exits are `1,1,0,0,0,1,0,1,1,1`:

```sh
python tools/read_requirements.py --question examples/stream_chunks/base-buffer.json --sha256 b8dea6d2c8648b430c07713b6ec4f2ce9adfec33f12f5249ce5b4018b0dab80a --source examples/stream_chunks/base-source.json
python tools/read_requirements.py --question examples/stream_chunks/base-chunks.json --sha256 013de42f5c9a5763c2aa9859a798670dd8773cfa88b6d1bfc4d9320969463949 --source examples/stream_chunks/base-source.json
python tools/read_requirements.py --question examples/stream_chunks/fixed-buffer.json --sha256 18edb18ed7d8ca5a246fb7498cb4c82f7ae85964ebb6120c78598e4def757b60 --source examples/stream_chunks/fixed-source.json
python tools/read_requirements.py --question examples/stream_chunks/fixed-chunks.json --sha256 42d8ada540ba6f883b31475dac427cedd72fb2c0e44733a9c37127291d3ad44c --source examples/stream_chunks/fixed-source.json
python tools/read_requirements.py --question examples/stream_chunks/coalesced-buffer.json --sha256 03d709a04f17c07e076b38ca60c1c356e1c44304308e777017afab9303d933b2 --source examples/stream_chunks/coalesced-source.json
python tools/read_requirements.py --question examples/stream_chunks/coalesced-chunks.json --sha256 eb0e3cded125086e84d26c66c7cfb7fd7092a14193710d6d048acbdbfbf69a93 --source examples/stream_chunks/coalesced-source.json
python tools/read_requirements.py --question examples/stream_chunks/reordered-buffer.json --sha256 f9995ab7fc7f812f055c8c2a97a6ae15a7601bd1114d362a7cae366739281783 --source examples/stream_chunks/reordered-source.json
python tools/read_requirements.py --question examples/stream_chunks/reordered-chunks.json --sha256 793987b62bf483076f0c817317e781bbd193066271a5ffa6dd222e56771a87bd --source examples/stream_chunks/reordered-source.json
python tools/read_requirements.py --question examples/stream_chunks/dropped-buffer.json --sha256 580240470348341071eb5097edbc4468dcaf7a6512022460dbb652da704f6454 --source examples/stream_chunks/dropped-source.json
python tools/read_requirements.py --question examples/stream_chunks/dropped-chunks.json --sha256 e238070319ef0bfd5bddcff140773e62f36d9d442a0bb183a954689d92fbcc09 --source examples/stream_chunks/dropped-source.json
```

CI validates saved observations, literal fixtures, both policies, partial-delivery capture, object identity at iterator return and documentation commands on three OSes. It does not execute historical SSEClient on all three OSes. The plugin includes this documentation and the generic reader; fixtures, probe and snapshot helper are source-archive content.

## Reproduce the actual task

Use Python3.11+ and Git supporting `--no-lazy-fetch`, with fresh directories. Recorded target runs used Windows/CPython3.12.10, no third-party dependencies:

```sh
git clone --no-checkout https://github.com/mpetazzoni/sseclient.git sample-source
python tools/prepare_source_snapshot.py --repo sample-source --manifest examples/stream_chunks/fixed-source-manifest.json --sha256 3b1b0d3bfd1dcef796f11738c1062c4a710fe32948de1393e9b767f8ffa5908a --target prepared-fixed --apply
python examples/stream_chunks/probe.py --repo prepared-fixed --inputs examples/stream_chunks/inputs --manifest examples/stream_chunks/manifest.json --manifest-sha256 03656053a1458d63c9b7202a275f52f382d3130c98dfc249852dea9cec1ce82e --oracle examples/stream_chunks/oracle.json --oracle-sha256 ad9ec3539a26f57e0afe75560aa657b94d9f057ef2a23ed03f9a4dddd6911335 --mode declared
```

The [snapshot helper](canonical-source-preparation.md) exports the exact upstream module and license. The probe imports that module and verifies its source hash after execution. To run the original, prepare `base-source-manifest.json` with pin `631aea92dc60b48dcb6f5abcd081479246cce899ee30fcebc0af8aaf20f5d0f8` in a different directory. Original plus `--mode coalesce` is the boundary-erasing control. Fixed plus `--mode reorder` swaps only the repeated fragments; `--mode drop` removes only the first event chunk. Exit0 means output agreement, not delivery acceptance.

Capture happens after all transformations, inside the iterator's `__next__`, immediately before returning the same immutable bytes object to SSEClient. No unrequested chunks are recorded. End-of-stream acknowledgement is recorded only on a consumer pull that raises StopIteration. Partial events and delivered prefixes survive consumer exceptions. Tests instrument the capture and consumer, including early failure; the trace is not reconstructed from intended splits or just the source file.

The pinned upstream tree has no tests, so no upstream unit suite is claimed. This exercises the real synchronous SSEClient API with finite byte iterators, not live HTTP, async scheduling, timing, cancellation, retries or backpressure. Those need separate tasks. The fixed historical client is not asserted to implement all SSE semantics.

## Method and evidence limits

The [2015 W3C SSE recommendation, sections6/7](https://www.w3.org/TR/2015/REC-eventsource-20150203/) supplies UTF-8 framing and received-order rules for the literal oracle. Library metadata is evaluated in its actual public representation (for example retry is a string). It is not a browser conformance test.

[Chen, Cheung and Yiu (1998), Metamorphic Testing](https://arxiv.org/abs/2002.12543) motivates deriving checks from domain relationships. We reuse the introduction/preliminaries/conclusion reading recorded for the preceding experiment, without rereading unchanged inputs. The current test uses independent literal oracles and controlled schedule changes; it does not validate the paper's overhead property.

The root saw the published fix before authoring this known-answer experiment. This is not a blind solve or independent fresh-agent review; the inherited native budget remains6/6. Stable paths and honest receipts are trusted. Hashes prove consistency, not execution authenticity or a filesystem sandbox. Earlier failures and examples remain preserved; generic reader semantics, installed skills and global settings are unchanged.
