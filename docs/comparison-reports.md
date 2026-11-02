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
version 1 format. Every field is required and unknown fields are rejected:

| Field | Meaning |
| --- | --- |
| `schema_version` | Integer `1` |
| `evidence_kind` | `synthetic_known_answer` only |
| `work_unit` | `deterministic_oracle_call` or `simulated_judge_lookup` |
| `policies` | Distinct names for the `baseline` and `candidate` roles |
| `per_case_budget` | Positive integer ceiling on each role's evaluation calls per case |
| `cases` | Nonempty list with unique `id`, `valid_answers`, `available_answers`, and `choices` for both roles |
| `work` | Recorded attempts with unique `id`, role in `policy`, `phase`, and `case_id` |

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
