# Select evidence from a question's requirements

`tools/read_requirements.py` selects observations from a local JSON register by
the exact subject and the requirements approved for one question. It returns
every matching record, including negative facts and qualifiers. Missing, unknown
or conflicting required values produce an explicit insufficiency result without
partial observations. The CLI ships in the source archive and plugin and needs
Python 3.11+. It makes no network/model calls, writes or acceptance decisions.

Use it when evidence already has reviewed subject/requirement tags. For arbitrary
JSON documents, use the [pointer-based reader](on-demand-evidence.md). Preparing
the register and deciding what each question needs are additional work; this
tool does not parse natural language into a complete requirement set.

## Try the fictional example

From the repository or extracted plugin root:

```sh
python tools/read_requirements.py --question tools/fixtures/requirement_question.json --sha256 d2f72c253e91dcaa04f7879d6faf648c0e1c84b1c61745cdfe4a9aff47986d5e --source tools/fixtures/requirement_source.json
```

Use `py -3` on Windows or `python3` on macOS/Linux if needed. The example asks
about `candidate-r4`. Its question selects the change, tests, findings and writer
release, retaining qualifications such as the need to check actual writer
release. The same register contains another revision and two other subjects;
their successful observations cannot substitute for this candidate's evidence.
All records are illustrative, not live execution receipts or permission grants.

## Prepare and review the contract

1. Root defines the question and exact subject. Before viewing a proposed
   shortened answer, enumerate the facts needed to answer and the guards that
   could change that answer: for example failures, unaccepted findings, age,
   ownership, remaining budget or prerequisite acceptance where relevant.
2. Check those requirements against original evidence and known counterexamples.
   Do not reuse a universal field list or accept a sender's completeness claim.
   Keep an unresolved fact explicitly unknown. Review the source's subject tags,
   requirements and qualifiers: the tool cannot establish that they are true or
   complete. A distinct revision needs a distinct subject or an explicit guard.
3. Preserve a stable, single-owner snapshot and approve its SHA256 separately.
   Write a question like the [example](../tools/fixtures/requirement_question.json),
   with that source pin. Approve the question's SHA256 independently of the
   arriving handoff; this is the CLI's `--sha256` value.
4. Run the reader against the explicit local paths. Review the returned facts
   and limitations before deciding. `OBSERVED` with failed tests, no remaining
   budget or a pending provider gate still requires a negative/waiting decision
   under the applicable workflow. Never convert exit code 0 into approval.
5. On insufficiency, reopen the original evidence and resolve the gap through
   the existing owner. Preserve the failed attempt. Do not remove a requirement
   merely to obtain a successful read. A changed contract needs fresh review.

## Input and result contracts

The question has exactly `schema_version: 1`, `question_id`, `question`, `subject`,
`source_sha256`, `max_source_bytes`, `max_result_bytes` and `requirements`.
Each requirement has a unique `id` and `purpose: answer` or `guard`. At least one
of each purpose is required, with at most 32 requirements. This is a structural
check, not proof that the chosen guards are sufficient. The question text is a
description, never executed or used for automatic semantic matching.

The register has exactly `schema_version: 1` and an `observations` array. Every
observation has exactly these fields:

| Field | Meaning |
| --- | --- |
| `id` | Globally unique record identifier within this register |
| `subject` | Exact target identifier, with no fallback to another target |
| `requirement` | Identifier matched to the reviewed question requirement |
| `state` | `known` or `unknown` |
| `value` | JSON value; `unknown` requires null; a known null remains unresolved |
| `qualifiers` | Array of strings, retained in full without interpretation |

IDs use 1–128 ASCII characters: letters/digits first, then letters/digits or
`_`, `.`, `:`, `-`. The question description is nonblank and at most 4096
characters. The entire question is at most 16 KiB. Both declared byte limits
must be integers from 1 to 4 MiB; booleans are not accepted as integers.
JSON must be UTF-8 with unique keys, finite numbers and no lossy decimal parsing.
Represent precision-sensitive decimal values as strings.

All source records are validated, even unrelated ones. For each requirement,
the reader retains **all** exact subject/requirement matches in source order:

| Condition | Status / exit code | Output |
| --- | --- | --- |
| Every required value is known and consistent | `OBSERVED` / 0 | All matching records and qualifiers |
| No matching record | `INSUFFICIENT` / 1 | `MISSING` gap, no observations |
| Any matching value is unknown or null | `INSUFFICIENT` / 1 | `UNKNOWN` gap, no observations |
| Known values disagree | `INSUFFICIENT` / 1 | `CONFLICT` gap, no observations |
| Pin, schema, read or successful-result limit fails | `REFUSED` / 2 | Diagnostic, no observations |

Unknown takes precedence over conflict if both occur. Conflicts compare typed
JSON values: false differs from zero, and integer 1 differs from float 1.0;
object key order does not matter. Equal-value records retain distinct IDs and
all qualifiers, even when qualifiers differ. The tool cannot interpret conflicts
expressed only in prose qualifiers; root must read them. It never chooses the
newest or successful record, deduplicates records, or fills a missing value.

Successful responses carry `scope: declared_requirements_only`, the question
and subject IDs, both verified digests, and read counts/bytes. The successful
result limit includes metadata and the final newline. Diagnostics are separate
from this limit and never contain partial observations. Invalid CLI arguments
use argparse's stderr/exit 2 rather than the JSON result contract.

## What the comparison establishes

X26 fixed 25 new synthetic cases before implementation: seven complete views,
six insufficiency cases and twelve refusals. Questions covered integration,
dispatch and method adoption over 17 meaningful records, including a related
archived revision. Controls included failed tests, zero budget, busy ownership,
missing/renamed requirements, unrelated successful receipts, unknown/null facts,
conflicts, duplicate records, sender coverage claims and altered pins/limits.

All 25 matched the fixed statuses and expected observations/gaps. The seven
complete views preserved every selected value, type, record and qualifier.
Question plus presented result totaled **26,098 → 13,890 bytes (46.78% less)**
against the same question plus the full original register. Each question stayed
within 2 KiB and each successful response within 4 KiB; the preregistered gate
required at least 20% aggregate reduction and no loss of required information.

Both methods read the source seven times, totaling 22,889 bytes. The selector
additionally read seven question files, totaling 3,209 bytes. This measures
exposed bytes, not fewer file reads, token counts, latency, cost or model quality.
Small registers and broad questions can yield larger responses. No comparison
against every possible manual selection method is claimed.

Frozen comparison SHA256:
`706b81c6697bdb7746c21ee924f3b3c5866d775eea620c88a3ae1d3a24852810`.
Tests in `tools/test_read_requirements.py` retain the behavioral controls; the
example above is a public synthetic register, not private agent history. The
comparison was root-run within the existing exhausted delegation budget, with
no fresh independent agent review or model runs.

[Sufficient Context (ICLR 2025), sections 3–3.1](https://proceedings.iclr.cc/paper_files/paper/2025/file/33dffa2e3d2ab74a783d1a8c292f66d9-Paper-Conference.pdf)
motivates checking whether supplied information can support an answer. Our
explicit requirement contract is a local engineering inference, not a replication
of that paper's model evaluation or evidence of general semantic discovery.

Hashes establish byte identity relative to trusted pins, not truth, freshness,
authority or completeness. Static nonregular/reparse leaf files are refused;
hostile concurrent path replacement and ancestor aliases are outside the stable
snapshot contract. The original evidence, ownership and acceptance procedures
remain necessary.
