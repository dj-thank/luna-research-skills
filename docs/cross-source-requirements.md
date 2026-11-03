# Check each requirement against its declared sources

A complete view of one register can omit a contradictory or limiting fact in
another. `tools/read_requirement_sources.py` reads 2–8 explicitly bound, pinned
local registers and requires each fact from every source named for that
requirement. It retains original record IDs, typed values, qualifiers and verified
source digests. It never chooses the most frequent, newest or successful record.

Use the [single-register reader](requirement-selection.md) for one source. Both
CLIs are offline/read-only and ship in the source and plugin ZIPs. These tools
match reviewed subject/requirement tags; they do not discover relevant sources,
translate natural-language questions or decide which source is authoritative.

For time-dependent questions, an optional version 2 question adds an explicit
[as-of timestamp and validity windows](temporal-requirements.md). Version 1
continues to check agreement without interpreting timestamps.

## Try the fictional examples

From the repository or extracted plugin root, using Python 3.11+:

```sh
python tools/read_requirement_sources.py --question tools/fixtures/cross_question.json --sha256 2c1fa4b8e89a7a9ff4cc55b63355c94474fd4268b33475c6ddd7fb49e187311e --source sender tools/fixtures/cross_sender.json --source registry tools/fixtures/cross_registry.json
python tools/read_requirement_sources.py --question tools/fixtures/cross_conflict_question.json --sha256 43b2601d825323eea13bc30c909a2b929479a5a2cfbfac06ec719da4ea1fcfaa --source sender tools/fixtures/cross_sender.json --source registry tools/fixtures/cross_conflict_registry.json
```

The first returns `OBSERVED`/exit 0. Both sources say authorization is **pending**;
an observed value is not approval. The second returns `INSUFFICIENT`/exit 1 because
the registry says approved while the sender says pending. It exposes no partial
observations. These are fabricated records, not live receipts or permission.

## Define coverage before reading

1. Root identifies the exact subject, answer facts, guards and original sources.
   Specify which sources must supply each requirement before seeing a shortened
   handoff. Separate source IDs or equal hashes do not prove independent origin,
   authenticity, freshness or completeness.
2. Review each stable register and its digest. Use its existing
   [observation schema](requirement-selection.md#input-and-result-contracts).
   IDs must be unique inside each source; the same ID may occur in another source.
   Keep unknown facts explicit and negative/prose qualifiers intact.
3. Prepare and independently pin a question like the
   [example](../tools/fixtures/cross_question.json). Bind local paths on the CLI.
   No paths or URLs inside JSON are followed.
4. Inspect the result and original evidence before an acceptance decision. If a
   source is missing, unknown or contradictory, resolve the gap with its owner.
   Retain failed attempts; do not remove sources or prefer a favorable record to
   get an observed result.

Each question has exactly `schema_version:1`, `question_id`, `question`,
`subject`, `sources`, `requirements`, `max_source_bytes`, `max_result_bytes`.
The sources list contains 2–8 distinct `{"id":..., "sha256":...}` entries.
Each requirement has `id`, `purpose:answer|guard`, and a nonempty `sources`
list of distinct declared source IDs. There are 1–32 distinct requirements,
including both purposes; every declared source must serve a requirement.
Complementary facts may name different sources. Only sources named for a
requirement contribute to it; root must justify any excluded source.

The question is at most 16 KiB; its text is 1–4096 characters. IDs and UTF-8 JSON
follow the single-register rules, including strict typed values, duplicate-key
rejection and refusal of lossy decimals. Each byte limit is 1–4 MiB.
`max_source_bytes` is an **aggregate** limit across all source reads; the reader
may read one extra byte to detect overflow. `max_result_bytes` bounds successful
responses, including metadata and the final newline. Gap/error diagnostics are
separate from that limit and contain no observations. Agreement is checked among
observations with the same requirement ID; relationships between different
requirements are outside this question schema.

| Condition for a requirement | Result |
| --- | --- |
| Any declared source lacks the exact subject/requirement | `INSUFFICIENT`, `MISSING_SOURCE` with missing source IDs |
| Every required source contributes, but any value is unknown/null | `INSUFFICIENT`, `UNKNOWN` |
| Required known values disagree, within or across sources | `INSUFFICIENT`, `CONFLICT` |
| All required observations are known and consistent | `OBSERVED`, all matching records and their origins |
| Pin, schema, binding, file or byte-limit failure | `REFUSED`/exit 2, no partial observations |

The table gives precedence: missing-source coverage, then unknown, then conflict.
No successful records are returned if any requirement has a gap. Reopen the
retained originals to investigate; a gap report is not a replacement for them.
Complete results preserve requirement order, each requirement's source order,
and original record order. Each observation adds an `origin` with verified
source ID/digest; original IDs and qualifiers remain unchanged. Other subjects
cannot cover a missing record. All records in every declared file are validated,
including ones not selected. CLI bindings must name every source exactly once;
duplicates, extras and omissions fail before reading any source.

Equality distinguishes false/0 and integer 1/float 1.0, preserves array order, and
ignores object key order. Conflicting prose qualifiers with equal structured
values remain visible for root review; the tool cannot interpret them. It does
not rank authorities, resolve time/entity ambiguities or count agreement as
independent votes. Sources must be stable, single-owner ordinary files. Leaf
links/reparse points and nonregular files are refused; concurrent swaps and
ancestor aliases remain outside the inherited snapshot contract.

## Bounded comparison and limits

X30 froze 25 new cases before implementation: 6 complete views, 7 conflicts,
2 unknowns, 2 missing-source cases and 8 refusal controls. All 25 matched the
fixed expectations. In the eleven conflict/unknown/missing-source cases, a
sender-only view lacked the registry fact needed for the diagnostic. The new
reader diagnosed the declared gap. One complementary-source case was incomplete
in the sender-only view and complete with its required registry facts.
The eight refusal controls test the new protocol; they do not imply that the
existing single-register reader lacks pin/schema/budget checks.

Across the six complete candidate views, source reads increased from 6 to 12 and
source bytes from 3,838 to 7,868. Response bytes increased from 6,526 to 15,501;
the baseline includes one incomplete response. All candidate values, qualifiers
and origins matched the reviewed records; complete responses fit 8 KiB and questions
fit 4 KiB. This is a coverage/provenance improvement on fixed synthetic cases, with
additional reading and context, not a measured speed, cost or model-quality gain.
The original two readers are byte-unchanged. Root performed the work under the
existing native budget 6/6; no new independent agent review or model run occurred.

[ConflictBank v1](https://arxiv.org/abs/2408.12076v1), sections 2.3–2.5 and 3.2,
read 2026-11-03, motivates distinguishing factual, temporal and semantic conflicts
and checking the evidence itself. Our typed-register contract is an engineering
inference, not its natural-language dataset/classifier or model experiment.
The preparation used the [fixture integrity procedure](fixture-integrity.md)
and a separate root domain check. Neither makes the oracle automatically true.

Frozen comparison SHA256:
`f9a8bc9c6874234d198d8e36f6552d2b2ea69c7818cef4be1f18d1aec3ceb78d`.
