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

For handoffs, [define the receiving question before reviewing the sender's
checklist](receiver-questions.md). Its paired example shows why all declared
checks can match while a required relationship is still omitted.
When facts must be checked against multiple original registers, use the
[cross-source reader](cross-source-requirements.md) to name the sources required
for each fact and retain their separate provenance.

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

The v1 question has exactly `schema_version: 1`, `question_id`, `question`, `subject`,
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

## Optional relationships between requirements

A complete view may still contain tests for another revision, or evidence that
does not cover all required targets. Root can declare these relationships in a
v2 question. It uses the same fields as v1, with `schema_version: 2` and one
additional `relations` array. Existing v1 questions and outputs are unchanged.

```sh
python tools/read_requirements.py --question tools/fixtures/relation_question.json --sha256 3ed4977efdfe81f241f7211b4ac1ce54032e674951e3f8a9ef3d6cf5088fa8e4 --source tools/fixtures/relation_source.json
```

This fictional example checks test revision, artifact identity, prerequisite
artifact identity and target coverage. It also includes a typed-value check.
Source records retain their schema version 1. The question must be independently
reviewed and pinned, including its relations. There are no implicit relations.

Each relation has exactly a unique `id`, an `operator`, and `left`/`right`
operands. Each operand has exactly `requirement` (an already declared ID) and
`pointer` (an RFC6901 JSON string pointer **inside that requirement's value**).
Empty pointers select the whole value; `~1` and `~0` escape slash and tilde.
There must be 1–32 relations, and a relation cannot compare identical operands.
No expressions, commands, external files, literal overrides or fallback values
are executed. The two supported operators are:

| Operator | Required relationship |
| --- | --- |
| `equal` | Typed JSON values must be equal, ignoring object key order |
| `subset` | Both operands must be arrays of strings; every left string must occur on the right |

For example, required targets are the left operand and tested targets the right.
Subset comparison ignores array order and repetitions, allows additional right
targets, and is case sensitive. An empty left set is a valid subset; this does
not establish that the root selected meaningful requirements. Full original
arrays and qualifiers are retained in successful output. Equality still treats
false and zero, or integer 1 and float 1.0, as different values.

Relations run only after all required observations are known and nonconflicting.
All observations for a requirement must already have the same typed value; the
reader never resolves a disagreement by picking the first record. A relation
failure returns `INSUFFICIENT`/exit 1, with `relation_gaps` containing its ID and
`MISSING` (pointer absent), `UNKNOWN` (selected operand is null), `TYPE` (invalid
subset operands), or `MISMATCH` (relationship fails). No observations or partial
successful relation checks are returned. Malformed relation contracts are
`REFUSED` before the source is read.

Successful v2 output keeps all observations and adds `relation_checks` with
`id`, `operator` and `status: MATCH`; its scope is
`declared_requirements_and_relations_only`. The result envelope remains schema
version 1, and the full successful output including relation metadata must fit
`max_result_bytes`. A matching relation does not turn a pending prerequisite,
failed test, stale permission or unknown real-world fact into approval. Root
must still interpret every fact and qualifier and review missing relationships.

X27 fixed 32 new cases before implementation. All matched their expected views,
gaps or refusals: eight valid views, eight relation gaps, three unresolved
requirement cases and thirteen refusals. The valid cases include reordered,
extra, repeated and empty scopes, plus a pending prerequisite that must remain
pending. The current v1 reader already preserves these facts for manual review;
its absence of a relation diagnostic is **not** a false approval or a measured
human/model error. The gain is eight additional automatic diagnostics with no
false gap in the eight valid cases.

Across the eight complete views, response bytes increased **14,088 → 16,808**
(340 extra bytes each); question bytes increased **3,640 → 9,856**. Source reads
stayed at eight/9,360 bytes for each method. The preregistered bounds were at most
1 KiB additional response bytes, 4 KiB per complete response/question, correct
diagnostics and exact retention of all required values/qualifiers. This is an
opt-in check with measured overhead, not a context, speed or accuracy improvement.
The existing 25 X26 cases are regression controls for unchanged v1 behavior.

X27 frozen SHA256:
`804ed476e10e9c99c03da027288d53b3ae78076a85c4091a95c80419d580f2d3`.
[Chain-of-Verification v2, sections 3.3–3.4 and 6](https://arxiv.org/abs/2309.11495v2)
motivates explicit cross-checking and acknowledges remaining errors and added
computation. Our deterministic relation contract is an engineering inference;
it does not reproduce that paper's LLM experiment. Existing native budget 6/6
was retained; this experiment used root checks, not a fresh independent model.

## What the field-selection comparison establishes

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
