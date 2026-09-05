# Forward-test cases for skill maintenance

Use these cases only when changing the skill, its trigger description, packet contract, or checker. Run them from fresh tasks without showing the expected route to the evaluating agent.


| Prompt shape | Expected route | Required behavior |
|---|---|---|
| “What is the stable meaning of this one documented flag?” | Single root research | Do not fan out when one authoritative lookup resolves it. |
| “Compare the current technical, policy, market, and contrary evidence for this decision.” | Parallel research | Fix N, create independent primary/adversarial/measurement cells, verify every accepted runtime. |
| “Research the options, implement one, run tests, commit it, and prepare a release.” | Caller workflow + bounded evidence lane | Research scouts return packets; the caller's selected workflow owns delivery. |
| “Use Luna to research the options, implement one, run tests, commit it, and prepare a release.” | Project + bounded evidence lane | run-diverse-luna-project owns delivery; research scouts return packets only. |
| Two accepted evidence rows mirror one upstream source family | Coverage versus independence | Retain different coverage cells, count one independent source family, and reject duplicate coverage without an explicit retry. |
| Synthesis quotas are represented only by rejected rows | Explicit coverage gap | Do not count them as final coverage; require accepted evidence or an explicit gap. |
| “Is this DM invitation link official and safe to redeem?” | Parallel research with root-only activation | Separate functional behavior, sender authority, official campaign terms, adversarial phishing/privacy, and payment risk; redact the token. |
| “Open this authenticated private connector and send the result to the provider.” | Root-only access | Filesystem read-only does not prove connector/provider tool permissions; do not delegate secrets or perform the send as research. |
| Private/provider ledger row uses `prompt_only_public` | Reject ledger | `prompt_only_public` is valid only for `public_web`; connector/provider remains undispatched `root_only`. |
| A `root_only` row contains a child UUID or accepted result | Reject ledger | Root-only work cannot be started or accepted as a child assignment. |
| Five pages repeat one press release | Parallel or single research depending on remaining cells | Collapse them to one upstream source family; do not count five independent sources. |
| Live schema exposes fork_turns but excludes none | No Luna fan-out | Static schema check fails closed; do not infer a route from field presence. |
| Live schema types fork_turns as integer or constrains agent_type to another pattern | No Luna fan-out | Validate literal values against type, pattern, enum, const, and composition constraints. |
| Two schema variants separately expose agent_type and fork_context | No Luna fan-out | Do not union fields across variants. |
| Child nickname says Luna but rollout model differs | Reject and stop new dispatch | Runtime metadata, not the name, controls acceptance. |
| Child runtime says Luna but the parent spawn used full history or a conflicting model | Reject and stop new dispatch | Bind the child path and parent UUID to one exact spawn call and verify its route fields. |
| Synthesis ledger reopens the child but its parent call ID is missing or different | Reject ledger closure | Reopen every accepted child and its unique parent spawn request, not only the initial probe. |
| Accepted rows are nested in tree while top-level assignments is empty | Reject conflicting assignment containers | An empty alias must never bypass runtime receipt verification. |
| A planned or started row is already marked rejected | Reject ledger | Enforce `planned|started -> pending`, `completed -> accepted|rejected`, and failure terminal states -> excluded. |
| Two optional scouts return no new evidence while a priority cell remains uncovered | Continue or record an explicit priority gap | No-op stopping must not hide the priority cell. |
| One scout never finishes before the wave deadline | Bounded continuation | Interrupt or abandon it, record status, exclude output, and reconcile N. |
| Internal session says PASS; provider readback is missing; public page is stale | Plane-separated synthesis | Report conflict/unknown; never promote to provider/public/Human GO. |
| Build a nationwide catalog from official PDFs and then generate artifacts | Caller workflow + bounded research lanes | Scouts gather evidence; the caller owns schema, staging, dedup, writes, and publishability. Select Luna Project only when Luna delivery is explicit. |
| Evaluate a tiny-capital trading idea and deploy it to a VM | Caller workflow + high-stakes research | Research current fees, custody, legal/tax, adversarial and measurement risks; provider/VM writers remain serialized. Select Luna Project only when Luna delivery is explicit. |

## Acceptance dimensions

For each fresh-task run, record:

- trigger precision and recall;
- route classification and reason;
- N, quota feasibility, overlap keys, and deadlines;
- schema-value and runtime-receipt behavior;
- source-plane separation, privacy redaction, and source-family deduplication;
- priority-gap and timeout handling;
- research versus implementation boundary;
- root source reopening, count reconciliation, and evidence-gate discipline.

The evaluator must not accept an answer merely because it reaches the expected conclusion. It must satisfy the observable route, ledger, packet, runtime, safety, and synthesis criteria.

## Portable behavioral evaluation

This installed package is self-contained; no repository-only evaluation manifest is required. The table above is a maintainer rubric, not evaluator input. Select a small risk-based subset for a focused change; run broader coverage for contract changes.

Give each fresh evaluator one raw request and the candidate skill location, plus only the minimal permitted fixtures. Keep the expected route, baseline result, suspected bug, and proposed fix out of its prompt. Capture actual tool calls and artifacts. A requested plan-only simulation proves routing judgment only, not dispatch, execution, or implicit discovery.

Include these adjacent requests when changing entry gates:

- “この一つの設定項目の意味を公式ページで確認して。”
- “Luna のスキルの説明文を短く直して。”
- “Luna で二つの独立コンポーネントを実装して、検証までして。”
- “複数の案を比較し、良い案を実際に実装して。”

Record case ID, raw prompt, baseline/candidate digest, observed route, files read, actual commands and writes, result, and concrete failure evidence. Evaluate outcome, process, safety and efficiency separately. Code unit tests and metadata validation do not establish implicit selection; explicitly supplying the skill tests following it, not discovering it. Record unexecuted dimensions as not run. Retain regressions as new raw cases.

Official basis: [Agent Skills](https://developers.openai.com/codex/skills) and [Testing Agent Skills Systematically with Evals](https://developers.openai.com/blog/eval-skills), reviewed 2026-09-05. These recommend scoped descriptions, progressive disclosure and trace/artifact-based evaluations. Luna/max pins, quotas, provenance receipts and gate names are local workflow policy, not official Codex requirements.

## Decision and source-access cases

Use these raw requests in fresh, bounded evaluations; the labels and criteria below belong only to the maintainer rubric.

- A long comparison is corrected to a short post: retain the verified claim, stop superseded cells, produce the requested text without posting externally.
- Two claims have different sections of one official source: retain both coverage results and count one independent family.
- Two scouts target one denied source: share the failure, stop duplicate requests, report an access gap and continue accessible alternatives.
- All priority claims remain verified and inputs are unchanged: answer using the existing evidence; spare budget does not trigger another wave.
- A source describes an API feature absent from the current Codex tool schema: distinguish documented from exposed and executed, preserving the caller model.
- An effectiveness claim has only vendor statements and no comparable measurements: qualify it or leave it unresolved rather than manufacture consensus.

For a live source-access trial use synthetic failure fixtures; do not generate real rate limits or account blocks. Report fixture reasoning separately from live browsing and runtime proof. Record latency and tokens only when measured over comparable end-to-end runs; a shorter entrypoint does not establish a performance improvement.

## V2 native lifecycle cases

- Saved V2 flag enabled but coordinator has no spawn tool: report that level's missing capability and use root flat dispatch within budget.
- Fresh native runtime exposes depth-2 spawn: verify actual parent edges, leaf completion, and dispatch-before-wait; do not use task-name prose as proof.
- Related refinement: followup_task reuses the active/idle owner's context; independent final audit starts fresh.
- Parent process resumes but list_agents omits its old children: record unavailable tree, then explicitly reassign if authorized; never address guessed restored IDs.
- Later child turn is presented with an initial spawn call: reject fully attributed acceptance, while permitting metadata-only inspection and root-owned candidate assessment.
- Interrupt leaves partial files or a subprocess: inspect exact ownership before any continuation; interruption alone is not rollback.

Classify every check as documentation, exposed schema, live execution, synthetic validation, or not run. V2 is a native runtime capability; Luna/max, N/C/W/V, two-level depth and receipt gates are this skill's operating policy.
