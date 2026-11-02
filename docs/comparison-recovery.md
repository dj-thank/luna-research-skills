# Inspect a retained comparison run

An interrupted producer can leave incomplete files, a complete staged bundle, or
a published bundle whose success message was lost. Directory existence and process
exit alone cannot distinguish those states. The [saving recipe](comparison-reports.md#export-a-review-comparison-without-hand-counting-checks)
reserves a fresh run directory and retains its artifacts for inspection.

`tools/inspect_comparison_run.py` checks the reserved **parent run directory**.
It ships in the source archive and plugin, requires Python 3.11+, and is offline
and read-only. It never executes a producer, publishes, renames, repairs, retries
or deletes anything.

After reviewing the expected evidence and source identity, replace the digest
placeholder below with the approved 64-character lowercase SHA-256:

```sh
python tools/inspect_comparison_run.py --run work/review-export --sha256 APPROVED_EVIDENCE_SHA256
```

On Windows use `py -3` if needed; on macOS/Linux use `python3`. Point `--run` at
`work/review-export`, not its `accepted` or `.pending` child. The expected digest
must come from trusted review; do not use the directory's own sidecar as the sole
authority for its identity. A local digest is not proof of who produced the data.

## Read the state, not just the exit code

| State | Exit | Meaning |
| --- | --- | --- |
| `COMPLETE_PUBLISHED` | `0` | A matching, consistent bundle was found under `accepted` |
| `COMPLETE_STAGED` | `0` | A matching, consistent bundle was found under `.pending`; it has not been published at `accepted` |
| `INCOMPLETE` | `1` | The run, known bundle location or a required artifact is absent |
| `CONFLICT` | `1` | Locations are ambiguous, path types are unsuitable, or a present bundle is malformed or inconsistent |
| `ERROR` | `2` | Invalid caller arguments, an unsuitable run root, or a filesystem read error |

The JSON includes `state`, `complete`, `published`, a diagnostic `reason` and
`passes_case_gate`. A complete result also includes fingerprints of the three
artifact files. `complete` means their consistency under the supplied pin; it does
not mean a task, model run or policy adoption is complete. Exit zero includes
staged results: **inspect `state` before treating a bundle as published**.

A valid negative comparison remains complete evidence with
`passes_case_gate: false`. The tool never changes that rejected-policy result into
approval. Similarly, `COMPLETE_PUBLISHED` describes the files found at a named
location; it does not authenticate a publication event or its timing.

## What is checked

Only the `accepted` and `.pending` locations and the three named artifacts are
inspected: `evidence.json`, `evidence.sha256`, and `report.json`. Extra files are
ignored, not validated. Both locations present is always a conflict, even if one
looks complete or both have identical bytes. The tool does not pick by timestamp
or prefer whichever copy passes.

Detected symbolic links, reparse points and special files are refused. Ordinary
missing files produce `INCOMPLETE` before their remaining contents are parsed;
unsuitable path types take precedence over missing-file classification. When all
three ordinary files exist, their sidecar must agree with the caller's pin, the
evidence bytes must match that pin, and the supplied report must match the
existing [comparison checker](comparison-reports.md). A report is mandatory:
JSON `null`, duplicate keys and malformed documents are conflicts.

An older run with artifacts directly in its root has no recognized bundle location
and is `INCOMPLETE` for this tool. Use `check_comparison.py` directly for that older
layout; nothing is migrated automatically. `ERROR` is distinct from a missing
artifact so an unreadable directory is not mistaken for a safe fresh start.

## Use the result conservatively

Keep incomplete and conflicting artifacts for diagnosis. A complete staged result
can inform an authorized recovery decision; this command does not make that
decision or publish it. A lost success message after publication need not trigger
a new producer execution when the expected published bytes can be verified.

Inspect a stable directory with one owner. Metadata checks and reads are not an
atomic filesystem snapshot or a sandbox against hostile concurrent path swaps.
Reopen the evidence before a later action if state may have changed. No disk
durability, freshness, independent labels or authentic execution is established
by these checks. No model, latency or cost improvement is implied.

[RIFL's primary paper](https://web.stanford.edu/~ouster/cgi-bin/papers/rifl.pdf)
distinguishes operation identity, retained results and retry states after a lost
reply. That motivates inspecting stored evidence; this helper implements neither
RIFL nor exactly-once RPC execution.

Development fixed 28 controls before implementation using saved interrupted runs
and explicit mutations. Six complete bundles were retained (four published, two
staged), with eight incomplete, twelve conflicting and two invalid-input cases.
All classifications matched; two complete negative comparisons stayed negative.
An explicit directory-exists ablation incorrectly marked twenty cases complete.
The existing manual guide already required content checks: that ablation is not
the previous workflow. No producer replay or further process termination was
needed, and the full input inventory remained unchanged.
