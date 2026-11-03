# Define the receiving question before reviewing the handoff

A sender can return `OBSERVED` with every declared relationship marked `MATCH`
while omitting a relationship needed for your decision. The original facts may
still be visible. Root should define the receiving question's requirements and
relationships before using the sender's proposed checklist.

This procedure uses the existing [requirement reader](requirement-selection.md).
It adds no automatic requirement discovery or acceptance decision.

## A reproducible omitted-check example

The fictional package is revision `q4`, but its test receipt is for `q3`. The
sender's question checks target coverage and artifact authorization, omitting
the test revision relationship. From the repository or extracted plugin root:

```sh
python tools/read_requirements.py --question tools/fixtures/handoff_sender_question.json --sha256 2a8a085839b2b41c0186f134e2e591a4b2a64689f514438824ff6760f5cfdb83 --source tools/fixtures/handoff_source.json
```

Expected: `OBSERVED`, exit 0, and two `MATCH` results. Both revisions are retained
in the returned observations, and authorization remains `pending`. This is not
approval, a hidden fact or a false claim by the reader: the question never asked
it to compare revisions.

The receiving question includes that required relationship:

```sh
python tools/read_requirements.py --question tools/fixtures/handoff_receiver_question.json --sha256 e49e8da56efc428994cebfb347f22756aa00f8ed4ad09674c0308056e9d0ab9d --source tools/fixtures/handoff_source.json
```

Expected: `INSUFFICIENT`, **exit 1**, with `test-revision: MISMATCH` and no partial
observations. Exit 1 is the intended outcome of this example. Both commands use
the same source bytes and the same reader. Use `py -3` on Windows or `python3`
on macOS/Linux if needed. The hashes above are for these fictional questions;
they do not authorize a real handoff.

## Apply the procedure to a real decision

1. Start from the user's question and the existing acceptance conditions. Write
   the requirements and critical relationships needed by the receiver before
   reading the sender's chosen checks. Use question-specific obligations, not a
   universal list or a count of checks. Review facts that may prevent acceptance.
2. Obtain the original evidence through the existing ownership/provenance
   procedure and preserve a stable snapshot. Verify the source identity before
   binding its digest into the receiving question. The source pin is filled when
   the evidence exists; future evidence is not preapproved.
3. Review and pin the receiving question independently. A sender's question pin
   establishes identity of that question, not completeness for your decision.
   Never replace your requirements merely because the sender reports `MATCH`.
4. Run the receiving question against the same approved source. Inspect every
   returned fact and qualifier. Resolve insufficiency through the evidence owner;
   preserve the failed attempt rather than removing a check to make it pass.

The receiving contract still needs judgment. Correct tags, necessary obligations,
authority and freshness cannot be inferred from successful comparisons. No tool
here establishes that an arbitrary natural-language question has been fully
translated into constraints.

## Known-answer comparison and limits

X28R2 fixed 21 new synthetic cases across integration, dispatch and method
adoption. Nine omitted checks concealed a mismatching relationship from the
sender's **automatic diagnostics**; the facts themselves remained present.
The receiving contracts diagnosed all nine. Nine valid cases retained every
required value, type, record and qualifier, including pending/busy conditions;
three unknown cases remained insufficient under both questions.

Across the 21 questions, the sender declared 51 of 63 independently enumerated
critical bindings, and the receiver declared 63 of 63 with no extra bindings.
These are finite declared obligations, not 63 successful executions: the three
unknown cases skip relation evaluation. The comparison includes renamed and
reordered sender checks, so relation labels are not treated as semantic proof.

For the nine complete views, question plus response bytes increased
**23,471 → 24,000**. Both methods read the source nine times, totaling 8,766 bytes.
The preregistered bounds required correct outcomes and exact information
retention, questions/responses each within 4 KiB, and at most 1 KiB extra context
per valid case. This demonstrates added finite diagnostic coverage with measured
overhead, not improved human/model accuracy, speed, token use or financial cost.

The first X28 run was **invalidated**: shared mutable fixture objects contaminated
earlier expected values and later source cases. Its inputs and failed results
were retained. X28R2 isolated each source seed and expected view, froze a new
record, and passed a separate integrity check against serialized evidence and
direct family-specific predicates before invoking the reader. The intended
mutations, status/gap labels and adoption bounds were retained; invalid and
repaired results are not pooled. Benchmark authors should copy each mutable case,
freeze serialized inputs and expected answers, and check their consistency before
testing a proposed method.

X28R2 frozen SHA256:
`91878caf0894aeaa6bc2d4ccd4e38523a84574662cbebf3c00ad0d53a480f148`.
The earlier invalid record remains
`eaf20240b974750a62b31be39034ca24982fdbb42d540619c2188cb8f9debd42`.
The existing delegation budget remained 6/6: root authored and checked these
synthetic contracts, with no fresh independent agent reviewer or model run.

[Chain-of-Verification v2, sections 3.2–3.4 and 6](https://arxiv.org/abs/2309.11495v2)
motivates separating verification planning from answer-conditioned execution and
acknowledges residual errors and overhead. This receiving-question procedure is
an engineering inference, not a replication of its LLM experiments.
