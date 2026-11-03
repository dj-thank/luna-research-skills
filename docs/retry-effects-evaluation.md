# Preserve request identity across a retry

A lost acknowledgment can leave a caller uncertain whether a write completed. Repeating the command may duplicate its effect; deduplicating by payload may instead discard a legitimate different command. This example extends [file-effect evidence](artifact-effects-evaluation.md) to one bounded retry.

The source ZIP contains the [probe, manifests, literal oracle and recorded results](https://github.com/dj-thank/luna-research-skills/tree/main/examples/retry_effects). The plugin includes this guide; execution of the external package is source-only. The requirement-reader runtime is unchanged.

## Actual application task

We use unchanged [TinyDB v4.8.2](https://github.com/msiemens/tinydb/tree/10644a0e07ad180c5b756aba272ee6b0dbd12df8), pinned at10644a0e07ad180c5b756aba272ee6b0dbd12df8. This is a root-designed application using documented insert/get/JSONStorage APIs, **not an upstream defect or upstream repair**. Its [own scope guidance](https://github.com/msiemens/tinydb/blob/10644a0e07ad180c5b756aba272ee6b0dbd12df8/docs/intro.rst) excludes multiprocess/thread access and ACID guarantees.

A logical request carries an explicit request ID and payload. The probe writes only synthetic documents, closes the database after every invocation and reopens it for a retry. A local fault is injected once, either before invocation or after completed storage has closed but before the caller receives the acknowledgment. Every operation has at most two attempts. All policies share a guard rejecting an existing request ID reused with a different payload.

Before executing TinyDB we fixed twelve literal oracles, including empty/Unicode payloads, unrelated initial data, explicit replay, conflicts and distinct requests with identical payloads. Intended policies are separately pinned manifests. Final expected documents and write/attempt limits are independent of the fixture generator.

| Application policy | Matching responses and attempt counts | Correct stored effects | Execution writes |
|---|---:|---:|---:|
| Insert on every invocation | 12/12 | 6/12 | 21 |
| Deduplicate by request ID | 12/12 | 12/12 | 14 |
| Deduplicate by payload alone | 12/12 | 10/12 | 12 |

Each arm also made 14 initialization writes, counted separately, and performed 23 invocations. Counts wrap the real JSONStorage write method. The payload-only arm writes least but drops two distinct-request cases; it is retained as a rejected control. The request-ID arm retains both legitimate requests while avoiding repeated effects of one request.

These are actual writes and closed-file observations, not edited passing receipts. Each result retains every attempt's response, injected-error label, stored state, final documents, canary table and write counts. All three arms ran on Windows/Python3.12.10. Request-ID handling also passed twelve cases on Python3.11.15. The pinned upstream pytest suite passed204 tests; optional lint/type plugins were disabled and no dependency was installed.

## Receiving-question comparison

Both questions require matching code, probe, oracle, runtime and intended manifest, plus all response/attempt checks. The complete question also requires each case's stored-effect check. Proposal identities come from the frozen plan, not the receipt.

Outcome-only handling accepts all three arms. Complete handling rejects repeated insertion and payload-only suppression and accepts the request-ID arm. A separate synthetic control deletes effect-check evidence; complete handling reports INSUFFICIENT/MISSING without partial observations. All four frozen decisions match.

Valid results keep every original observation and qualifier. Both policies read the same source once, 16,807 bytes for request-ID handling. Question bytes grow1,381→1,545 and response bytes17,705→17,765 (+60). These are exposed byte counts, not latency, model cost or reasoning-quality improvements.

The following source-distribution commands run plain-insert outcome/complete, request-ID outcome/complete and payload-only outcome/complete. Expected exit codes:0,1,0,0,0,1. An OBSERVED result under the weak question does not establish correct retry effects.

~~~sh
python tools/read_requirements.py --question examples/retry_effects/plain_insert-outcome.json --sha256 4d76d858a04bd27a76c9c7b26eac5a061975558dcf91b803c5765441ac058a69 --source examples/retry_effects/plain_insert-source.json
python tools/read_requirements.py --question examples/retry_effects/plain_insert-complete.json --sha256 334dcf2be73a8c1fb34faeb11f0567205fb723870287fd381e80ce8ab3d1fa21 --source examples/retry_effects/plain_insert-source.json
python tools/read_requirements.py --question examples/retry_effects/request_key-outcome.json --sha256 18a5b1846536d7220004a86da86a3210db8387d16521fc1c1b35d43b16ba539d --source examples/retry_effects/request_key-source.json
python tools/read_requirements.py --question examples/retry_effects/request_key-complete.json --sha256 9c52e918411eaace5dd46d2ee66b17eb919ffb70192557ad482ab34e2272b4c2 --source examples/retry_effects/request_key-source.json
python tools/read_requirements.py --question examples/retry_effects/payload_key-outcome.json --sha256 5ce4a778f1011dfc0752b34ef49869f5985c7f6f9b12df325ea51d8c0531bb9a --source examples/retry_effects/payload_key-source.json
python tools/read_requirements.py --question examples/retry_effects/payload_key-complete.json --sha256 87bc6398495cef2a495279960caf470f92a7862553be30984513307d943ac476 --source examples/retry_effects/payload_key-source.json
~~~

## Reproduce actual writes

Use a trusted checkout and fresh process: the probe executes the selected package. Use unused destination paths and create the work directory if necessary. Scratch must be a new directory with an existing parent. The runner retains its files and refuses existing scratch data.

~~~sh
git clone --branch v4.8.2 https://github.com/msiemens/tinydb.git work/tinydb-retry
git -C work/tinydb-retry checkout --detach 10644a0e07ad180c5b756aba272ee6b0dbd12df8
python examples/retry_effects/probe.py --repo work/tinydb-retry --manifest examples/retry_effects/request_key.json --manifest-sha256 e345cb437c31b9cd93ce4bd6c09572b91a3217e8218cd385c023affdb581f6b3 --oracle examples/retry_effects/oracle.json --oracle-sha256 f8201e7348fc62a8786b45b6446e20cf7001c97576832f9502f2e4f93c0a0c11 --scratch work/retry-request-key-run
~~~

Use plain_insert.json with digest178d6afdef37c54c0767f953c4a8d7182c17b7e02a7c64fb8916999dd057e10d or payload_key.json with digestffc07e3108c1a359efee4c165330e28fdb7c8861559c95a85cb6f5fb17e504ba for the controls, each in another new scratch directory. Both controls exit1 for the predicted failures; request-ID handling exits0. Review the actual documents and attempt traces, not just the exit status. Source line endings/runtime labels can change exact byte identities; keep fresh receipts rather than relabeling old ones.

## Scope of adoption

[Birrell and Nelson, Implementing Remote Procedure Calls (1984)](https://www.cl.cam.ac.uk/teaching/0708/DigiCommI/birrell1984rpc.pdf), sections3.1–3.2, connects call identities with response correlation and duplicate suppression, while describing uncertainty after failure. We adapt that identity principle; we do not reproduce their protocol or guarantees.

This bounded example has one writer. File close/reopen is not a process restart, a real network failure, crash durability, a transaction, or concurrent duplicate exclusion. The get/insert sequence is not atomic across writers. This is not a production concurrent request processor. No existing service, host configuration, private data or installed skill was changed.

Root designed and reviewed the task; there is no blind solve or fresh independent agent evaluation. The inherited native budget remains6/6. Fewer writes are not sufficient evidence of improvement, as the rejected payload control shows. Portable CI checks replay recorded results, question behavior and fixture bounds; they do not execute TinyDB on every CI OS.
