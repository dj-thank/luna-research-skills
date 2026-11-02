# Check a known-answer comparison report

`tools/check_comparison.py` derives a report from a caller-pinned evidence file,
or checks a supplied report against that derivation. It catches aggregate gains
that hide individual losses, omitted calibration work and changed evidence.
It does not run agents, judge open-ended answers or authorize a deployment.

## Try the portable example

From a source checkout or extracted plugin, use Python 3.11 or newer. On Windows
replace `python` with `py -3` when needed; on macOS/Linux use `python3`.

```sh
python tools/check_comparison.py --evidence tools/fixtures/comparison_evidence.json --sha256 a1341c81e895bd870fdc0c79c84f26f9521beb4e9778b3788c2cb25a9f13b56d
python tools/check_comparison.py --evidence tools/fixtures/comparison_evidence.json --sha256 a1341c81e895bd870fdc0c79c84f26f9521beb4e9778b3788c2cb25a9f13b56d --report tools/fixtures/comparison_report.json
```

The first command prints a derived summary; the second checks the saved report.
Both read files without writing them. The five hand-labelled synthetic cases
include a recovery, a repaired wrong answer, an absent correct answer and a
missed available answer. Correct choices increase from 1 to 3 with no loss of a
baseline success. Evaluation calls fall from 9 to 8, but 2 calibration calls make
the candidate's total **10**, versus **9**. Passing the case gate is not a cost
improvement. These counts are illustrative, not measurements of model quality.

## Prepare trusted evidence before checking a report

1. Freeze answer labels independently of the policy's accepting judge. Preserve
   the original proposals, input fixture, source revision and expectations in your
   experiment archive. A judge's `passed` flag is not an answer key.
2. Export every case's final choice and all recorded call attempts, including
   calibration and failed calls. Include abandoned/rejected comparisons. Exclude
   cache hits from new calls. Keep actual deterministic calls and simulated table
   lookups in separate comparisons.
3. Review this export against the archived source records, then pin its exact
   byte SHA-256 in a separate trusted task record. Pass that value as `--sha256`.
   Do not obtain the trust anchor from the report being checked.
4. Derive a summary, or pass `--report` to verify an existing one. Retain rejected
   policies' accurate reports as evidence; a failed case gate is useful data.

The [example evidence](../tools/fixtures/comparison_evidence.json) defines the
version 1 format. Version 2 adds source fingerprints as described below. Every
field for the selected version is required and unknown fields are rejected:

| Field | Meaning |
| --- | --- |
| `schema_version` | Integer `1`, or `2` with the additional `source` object |
| `evidence_kind` | `synthetic_known_answer` only |
| `work_unit` | `deterministic_oracle_call` or `simulated_judge_lookup` |
| `policies` | Distinct names for the `baseline` and `candidate` roles |
| `per_case_budget` | Positive integer ceiling on each role's evaluation calls per case |
| `cases` | Nonempty list with unique `id`, `valid_answers`, `available_answers`, and `choices` for both roles |
| `work` | Recorded attempts with unique `id`, role in `policy`, `phase`, and `case_id` |

Version 2 also requires `source` with exactly `fixture_sha256`, `review_sha256`,
`validator_sha256` and `exporter_sha256`. These must be lowercase SHA-256 strings.
They are included in the derived report and in its byte pin. Version 1 remains
supported. The checker preserves these fingerprints; it does not fetch the source
files or authenticate their execution.

Answer lists contain unique strings. Choices must be available answers or `null`
for abstention. A valid answer can be absent from available answers. An
`evaluation` event names an existing case; a `calibration` event uses `case_id:
null`. Each event counts as one attempt. The per-case ceiling excludes calibration,
which is counted separately and included in total work. Calibration sharing or
amortization requires a different, explicitly defined experiment.

The checker recomputes correct choices, false accepts, abstentions, missed
available answers, evaluation/calibration/total calls, and sorted recovery/loss
case IDs. The fixed `passes_case_gate` requires at least one recovery, zero lost
baseline successes and zero candidate false accepts. It does not require lower
work. Report fields and types must match exactly; boolean `true` is not an integer
count. Duplicate JSON keys, unknown cases, repeated event IDs, over-budget work
and malformed evidence are rejected.

| CLI status | Meaning |
| --- | --- |
| `0` | Summary derived or supplied report consistent, **even if `passes_case_gate` is false** |
| `1` | Caller pin mismatch or inconsistent report |
| `2` | Unreadable file or malformed/unsupported input |

## Export a review comparison without hand-counting checks

From a **source checkout**, the producer runs the deterministic review benchmark
for just the baseline and the selected candidate. This command prints version 2
evidence without writing files:

```sh
python tools/export_review_comparison.py --sha256 8b24fe12e113f019e35931ebefc7ab3fa48dee41055f84fa1dce1a1fc0506824
```

The digest above pins the shipped review fixture. For another fixture, review and
pin its bytes before execution, then pass `--cases PATH --sha256 APPROVED_DIGEST`.
Changed bytes are rejected before scoring. The default candidate is
`unique_critique`; use `--candidate checked_minority` to export the preserved
negative comparison. An accurate export of that candidate succeeds even though
the consumer's case gate rejects it. Only the selected pair executes: 46 actual
scorer calls for critic/reuse, or 48 for critic/minority on the shipped fixture.
There is no calibration in this producer.

Attempt records begin at the scorer boundary. Cache hits and unchecked decisions
do not count as new work; failed calls do. The producer checks frozen choices,
expected call counts and separate truth labels before exporting complete evidence.
On a scoring error or mismatch it exits `2`, emits `complete: false` with an audit
and attempted/failed call counts, and emits no evidence document. Ordinary Python
exceptions are retained; process termination can prevent any output. Keep an error
audit instead of passing it to the comparison checker. Successful export exits `0`.

To preserve exact bytes on every OS, save the following as a Python script in the
source root and run it with Python 3.11+. It creates a fresh directory and refuses
to overwrite an earlier run. Review the resulting evidence and source fingerprints
before treating its digest as a trusted pin for reports from other parties.

```python
import hashlib
from pathlib import Path
import subprocess
import sys

run = Path("work/review-export")
run.mkdir(parents=True, exist_ok=False)
fixture_pin = "8b24fe12e113f019e35931ebefc7ab3fa48dee41055f84fa1dce1a1fc0506824"
data = subprocess.check_output([sys.executable, "tools/export_review_comparison.py", "--sha256", fixture_pin])
evidence = run / "evidence.json"
with evidence.open("xb") as stream:
    stream.write(data)
pin = hashlib.sha256(data).hexdigest()
(run / "evidence.sha256").write_text(pin + "\n", encoding="utf-8")
command = [sys.executable, "tools/check_comparison.py", "--evidence", str(evidence), "--sha256", pin]
report = run / "report.json"
with report.open("xb") as stream:
    stream.write(subprocess.check_output(command))
subprocess.run(command + ["--report", str(report)], check=True)
```

The plugin includes the consumer; the producer and benchmark engine require the
source checkout. Source fingerprints record the local files observed before and
after the run, not proof of which code ran in memory. The producer does not infer
label independence or authenticate a supplied fixture. Exporting and checking a
report from one process is useful consistency testing, not independent review.

## Evidence limits

Identity and consistency do not establish authenticity or completeness. The
checker cannot discover calls omitted from the trusted export, authenticate a
source, establish label independence or verify that a policy really executed.
Changing both the evidence and its trusted pin deliberately selects new evidence;
it does not preserve the earlier experiment. Keep the source archive and the
review decision. Native runtime receipts still need the
[separate verification procedure](swarm-experiments.md).

This contract implements reporting requirements already described in the
[adoption guide](swarm-experiments.md#promotion-and-reporting). During development,
14 predeclared report controls included five faithful reports and nine misleading
ones, based on saved positive/rejected synthetic comparisons and the portable
example. The checker accepted all five faithful reports and rejected all nine
misleading reports. An intentionally weakened checker that examined only case
count and correct-answer totals accepted six misleading reports. That ablation
was not a previously shipped implementation. These are bounded regression results,
not an estimate of real-world detection accuracy or independent agent review.
