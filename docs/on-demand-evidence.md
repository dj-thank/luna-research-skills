# Read evidence when a decision needs it

`tools/read_evidence.py` opens a local JSON snapshot and returns the exact fields
approved for one question, including its required qualifications. It ships in
the source archive and plugin, uses Python 3.11+, and performs no network calls,
model calls, writes, publication or automatic acceptance.

If evidence is already organized into subject/requirement records, the optional
[requirement selector](requirement-selection.md) retrieves all matching records
and detects missing, unknown or conflicting required values. It still requires
a root-reviewed question contract; it does not discover semantic guards for you.

Use a scoped view when the full evidence is large and the next decision is narrow.
For a small packet, returning the whole file can be simpler and smaller. Keep the
original evidence: a partial view is not a replacement for it.

## Try the copyable example

From the repository or extracted plugin root:

```sh
python tools/read_evidence.py --request tools/fixtures/evidence_request.json --sha256 b970eb676501a2bc6fbe90e689bada463ee6766d62b1215b4bc35ba39bc6e981 --source tools/fixtures/evidence_source.json
```

Use `py -3` on Windows or `python3` on macOS/Linux if needed. The fixture is an
illustration with `acceptance_status: pending`. A successful read preserves that
pending status; it does not approve the candidate.

The command's **`--sha256` pins the request**, not the evidence file. The approved
request contains the source's separate `source_sha256` and the allowed selections.
Do not derive the trusted request pin solely from an arriving sender's message.

## Prepare a decision-specific request

1. Root states the question and fixes its acceptance conditions. Review which
   source fields can change the answer, including counterevidence, uncertainty,
   pending/rejected status, scope, revision, ownership and remaining budget when
   relevant. Do this before measuring the size of the proposed view.
2. Reopen and approve the source identity using the existing
   [handoff procedure](swarm-experiments.md#bind-the-handoff-to-the-artifact-being-consumed).
   Preserve a stable snapshot after verifying writer release.
3. Write one request like the [example](../tools/fixtures/evidence_request.json).
   Set `schema_version: 1`, the approved `source_sha256`, `max_source_bytes`,
   `max_result_bytes`, and `selections`. Each selection has a unique simple `id`,
   a `pointer`, and `purpose: answer` or `purpose: guard`. At least one of each
   purpose is required. Include complete qualifier objects when individual leaves
   would lose context. Root decides sufficiency; the tool cannot discover omitted
   contradictions or judge whether the chosen fields answer the question.
4. Review and pin the request independently. Hand off its locator and approved
   digest with the explicit source locator. The receiver runs the command only
   when it needs that decision's evidence. No path or command inside the JSON is
   executed or followed.
5. Consume all returned guards alongside the answer. Reopen the full source or
   review a new request when the question, source, owner or scope changes. Old
   timestamps, gates and budget fields remain historical facts, not fresh grants.

Pointers use [RFC6901 JSON-string syntax](https://www.rfc-editor.org/info/rfc6901/):
`/items/0` selects an array element, `~1` represents a slash in a key and `~0` a
tilde. `""` selects the whole document; `/` selects an empty object key. URI
fragments, array leading zeros and unresolved pointers are refused. Null, false
and empty containers are values, never replaced with defaults.

## Read the result and limits

Exit `0` means `status: VERIFIED`: request and source digests matched and **every**
requested value was read from the same bytes. `scope: selected_fields_only`, both
digests, the selections with their purposes, and read metrics accompany the values.
This proves neither policy adoption nor task completion, execution authenticity,
freshness, authorization or completeness of the selected evidence.

Exit `2` with `status: REFUSED` contains no partial `values`. Causes include a
missing or changed file, malformed request, missing guard, invalid pointer,
duplicate JSON keys or a byte limit. CLI syntax errors use argparse's stderr and
exit `2`. Refusal diagnostics are not subject to the successful-result byte cap.
Do not truncate an oversized result or silently remove guards; revise the question
and reapprove the request, or retain the full-file workflow.

Requests are limited to 16 KiB and 32 selections. Source/result bounds are positive
integers up to 4 MiB. JSON must be UTF-8; duplicate keys, non-finite numbers, and
decimals which would change value when serialized by Python are refused. Exact
decimal values can be represented as strings in an independently approved source.
Detected non-regular leaf files, symbolic links and reparse points are refused.

The command reads the request once and the source at most once. It reads the
**whole source** to verify its digest, then selects fields from those same bytes.
An overflowing read stops after its bound plus one probe byte. Metrics count
successful opens and bytes returned by completed reads, not physical disk I/O,
tokens or model costs. The successful-result limit counts its encoded JSON plus
the trailing newline, including metadata and guards.

Use stable files with one owner. Metadata checks and reads are not an atomic
filesystem snapshot or protection against hostile concurrent swaps or ancestor
path aliases. This is not a privacy/redaction boundary: approved fields may include
sensitive data, and unrequested fields remain in the source.

## What was compared

Five new decision queries over retained native results were fixed before the
implementation, with their exact answers and required qualifications. The
baseline reopened the approved source and exposed its full contents. Both modes
counted the same request bytes; the candidate exposed the verified scoped result.
This represents the full-file manual workflow, not every possible manual excerpt.

All five queries preserved their fixed values and provenance. Seventeen additional
refusal cases returned no partial values. Requests fit 2 KiB and results fit 4 KiB.
Across the five valid queries, request plus exposed result decreased from 22,115
to 11,175 bytes (49.47%). Both modes read 19,994 source bytes in five source reads;
the candidate additionally read 2,121 request bytes in five reads. Small packets
can grow because of metadata; the measured benefit is aggregate exposed content,
not fewer filesystem bytes or universally shorter messages.

An adversarial regression test found silent decimal rounding in the initial
reader. The accepted reader refuses lossy decimals, and the fixed comparison was
rechecked without changing its labels. The private original packets, first
results and failure are retained; the public fixtures are fictional.

[ReAct, section3.1](https://arxiv.org/html/2210.03629v3) motivates explicit retrieval
of observations for a question. This helper does not implement ReAct's reasoning
loop or reproduce its model results. No new native agents or models were run for
this comparison; content retention and exposed bytes do not establish reasoning,
token, latency or monetary improvements.
