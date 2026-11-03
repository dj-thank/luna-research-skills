# Check cancellation at the point of effect

Removing a scheduled job can leave a callable in an already captured batch. A cancellation acknowledgment and an empty queue therefore do not prove that its old work stopped writing. This example extends [retry-effect evidence](retry-effects-evaluation.md) to cancellation and replacement generations.

The source ZIP contains the [probe, manifests, literal oracle and recorded results](https://github.com/dj-thank/luna-research-skills/tree/main/examples/cancellation_effects). The plugin includes this guide; executing the external package is source-only. The requirement-reader runtime is unchanged.

## Actual application task

We use unchanged [schedule 1.2.2](https://github.com/dbader/schedule/tree/82a43db1b938d8fdf60103bd41f329e06c8d3651), pinned at `82a43db1b938d8fdf60103bd41f329e06c8d3651`. Its `Scheduler.run_all` iterates a copy of scheduled jobs, while `cancel_job` removes a job from the live list. This is a root-designed application using those APIs, **not an upstream bug or upstream repair**.

Each synthetic request carries a name, increasing generation and payload. A controller runs first in the initial batch and can cancel a captured old job or register a replacement. The old callable may still enter. A second batch executes newly registered jobs. All callbacks return `CancelJob`; the real scheduler is never patched. We append effects to new task-owned JSONL files, close each append, then read the exact recorded effects. An unrelated canary file is preserved.

Before executing the package, we fixed twelve literal answers covering captured cancellation, empty/Unicode payloads, replacement under the same name or payload, a repeated stale cancellation, other requests, cancellation before capture, and cancellation after an already completed effect. The latter must preserve the existing effect: cancellation is not rollback.

| Application policy | Acknowledgments, callback counts and empty queues | Correct file effects | Appends |
|---|---:|---:|---:|
| Unschedule only | 12/12 | 4/12 | 17 |
| Check current active generation before append | 12/12 | 12/12 | 9 |
| Permanently suppress a cancelled name | 12/12 | 8/12 | 5 |

Each arm executes 17 work callbacks and 12 controller callbacks. The name-only control appends least but suppresses four legitimate replacement cases; it is rejected. The generation guard checks eligibility at callback entry, immediately before the synchronous append. A stale cancellation names its old generation and cannot deactivate a newer one. Input validation rejects reused or decreasing generation numbers.

All three policies actually ran on Windows/Python 3.12.10. The twelve generation-guard cases also passed on Python 3.11.15 with identical task observations. The upstream suite was **not run**: its pinned `test_schedule.py` unconditionally calls `time.tzset`, which is unavailable on Windows. We did not shim that API, change upstream source, or install dependencies.

## Receiving-question comparison

Both questions bind code, probe, oracle, runtime and intended manifest, then require the acknowledgment/callback/queue checks. The complete question also requires exact file effects for every case. Intended identities come from the frozen plan, independently of the receipt.

Outcome-only handling accepts all three policies. Complete handling rejects late writes and the loss of valid replacement work, and accepts the generation guard. A separate synthetic control deletes effect evidence; complete handling reports INSUFFICIENT/MISSING without partial observations. All four frozen decisions match.

Valid results retain every original observation and qualifier. Both policies read the same source once, 14,004 bytes for the generation guard. Question bytes grow 1,396→1,567 and response bytes 14,918→14,985 (+67). These are exposed byte counts, not measured latency, model cost or reasoning-quality gains.

The six source-distribution commands below run unschedule-only outcome/complete, generation-guard outcome/complete and name-only outcome/complete. Expected exit codes: 0,1,0,0,0,1. OBSERVED under the weak question does not establish cancellation safety.

~~~sh
python tools/read_requirements.py --question examples/cancellation_effects/unschedule_only-outcome.json --sha256 4d1c293bfcbb4b868e7464069b73bddde4ed5e60695e28a01dc0fa54d17e7498 --source examples/cancellation_effects/unschedule_only-source.json
python tools/read_requirements.py --question examples/cancellation_effects/unschedule_only-complete.json --sha256 095e9a1f7f060a3e2be47646435e90f8b9338b3fb783a70879f8132b5be77259 --source examples/cancellation_effects/unschedule_only-source.json
python tools/read_requirements.py --question examples/cancellation_effects/generation_guard-outcome.json --sha256 970b88bc5d69ec44923e399585fd104d5c69fd33f9be5808469046f563f0aefd --source examples/cancellation_effects/generation_guard-source.json
python tools/read_requirements.py --question examples/cancellation_effects/generation_guard-complete.json --sha256 a4395c6d4a8b6ac1e0240b9b438b82c7c5684c52d5f4103c0450397d4d5e9ca7 --source examples/cancellation_effects/generation_guard-source.json
python tools/read_requirements.py --question examples/cancellation_effects/name_tombstone-outcome.json --sha256 c9640945dce30c4e0a3c86e5ebaaaf01e5a8cca393e99c42d1dda8408396d5ec --source examples/cancellation_effects/name_tombstone-source.json
python tools/read_requirements.py --question examples/cancellation_effects/name_tombstone-complete.json --sha256 2783de12875217d8353ef1244caf260a65930e0a95c7a7697892f3da16319c28 --source examples/cancellation_effects/name_tombstone-source.json
~~~

## Reproduce actual callbacks and writes

Use a trusted checkout and fresh process: the probe executes the selected package. Use unused destination paths; create the work directory if needed. Scratch must be a new directory with an existing parent. Existing scratch data is refused, and all generated files are retained.

~~~sh
git clone --branch 1.2.2 https://github.com/dbader/schedule.git work/schedule-cancel
git -C work/schedule-cancel checkout --detach 82a43db1b938d8fdf60103bd41f329e06c8d3651
python examples/cancellation_effects/probe.py --repo work/schedule-cancel --manifest examples/cancellation_effects/generation_guard.json --manifest-sha256 dd422572f6536927615e83f3569916d81b5796b00ba943e9fdeea44a148a365d --oracle examples/cancellation_effects/oracle.json --oracle-sha256 afcd3a5e283ba0ce98af13504943474c84c4923e63496c914f43993dee953c96 --scratch work/cancellation-generation-run
~~~

Use `unschedule_only.json` with digest `409b69898a790bf86e8524eb57de87da17d65a4383d8d304c3b4c4afcb5dbd5e` or `name_tombstone.json` with digest `c6b175ec4508a4a5941162339c00bbc85870dec67867a2d2e370a3accab241e7` for the controls, each with another new scratch directory. Both controls exit1 for their predicted failures; the generation guard exits0. Inspect command/callback traces, `still_scheduled`, validity decisions and file effects as well as the exit status. Line endings and runtime labels can change exact byte identities; retain fresh receipts instead of relabeling old ones.

## Scope of adoption

[Burrows, The Chubby lock service for loosely-coupled distributed systems (OSDI 2006)](https://www.usenix.org/legacy/event/osdi06/tech/full_papers/burrows/burrows_html/), section2.4, describes checking generation validity at the recipient to reject stale work. We adapt that principle locally; this is not a reproduction of Chubby's protocol or guarantees.

This experiment is sequential, using two real `run_all(delay_seconds=0)` calls. It does not test wall-clock deadlines, interrupt running code, undo completed effects, or establish thread, process-crash, network or distributed atomicity guarantees. A check followed by an append is not atomic with a concurrent cancellation. No service, host configuration, private data or installed skill changed.

Root designed and reviewed the task; there is no blind solve or fresh independent agent evaluation. The inherited native budget remains6/6. Portable CI validates saved receipts, documented questions and input bounds; it does not execute schedule on every CI OS.
