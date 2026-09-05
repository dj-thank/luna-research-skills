# Luna workstream packet

Use this checklist for every new assignment. Put all required context in the spawn message because `fork_turns="none"` and the transitional `fork_context=false` route supply no conversation history.

## Assignment packet

- **Project outcome:** the overall result this workstream supports.
- **Assignment kind:** builder, evidence lane, reviewer, verifier, or operator.
- **Bounded objective:** one deliverable, decision, question, or verification boundary.
- **Inputs:** exact files, artifacts, URLs, commands, or prior decisions to use.
- **Ownership:** files or modules the agent may edit; write `read-only` when it must not edit. This is a behavioral boundary, not proof of an enforced read-only sandbox.
- **Dependencies:** completed inputs and work that remains outside this assignment.
- **Constraints:** user authority, safety, compatibility, style, time, and attempt limits.
- **Timing:** per-assignment deadline, wave deadline, retry allowance, and timeout disposition.
- **Acceptance check:** observable conditions that end this assignment.
- **Validation:** commands or inspections the agent must run.
- **Return:** requested artifacts, diff summary, evidence, residual risks, and status.
- **Peers, when needed:** exact active peer IDs/task paths, permitted links, artifact SHA-256, acknowledgement deadline, message/repair budgets, and root escalation path. Read [peer-collaboration.md](peer-collaboration.md). Peer requests outside assigned ownership go to root.

Append these operating rules:

```text
Use only this task-local context. You are not alone in the workspace: preserve existing and concurrent changes, stay inside the assigned ownership, and do not revert others' work. Do not spawn descendants. Report actual evidence and uncertainty. Stop and return a blocker when completion requires new authority, an overlapping edit, or unavailable external state.
```

For a `$run-diverse-luna-research` sub-budget, replace file ownership with `EVIDENCE_LANE_ONLY` and add:

- one source plane: `local`, `internal_session`, `connector_private`, `public_web`, or `provider`;
- access mode: `sandbox_read_only`, `prompt_only_public`, or `root_only`;
- source universe, independence rule, freshness cutoff, redaction rule, and gap condition;
- packet-only return: no candidate, shared SSOT, stage, commit, provider, browser-write, or gate promotion.

`prompt_only_public` is valid only for `public_web`. `sandbox_read_only` proves the effective filesystem sandbox, not connector/provider tool permissions. Keep `connector_private`, `provider`, secrets, and sensitive personal data `root_only` when external-tool permissions cannot be mechanically proven; do not dispatch a `root_only` row.

## Return packet

Require the agent to return:

1. Status: completed, partial, failed, or blocked.
2. Outcome and artifact paths or evidence locators.
3. Files changed and why, or a declaration of read-only work.
4. Checks run with observed results.
5. Assumptions, integration notes, and conflicts detected.
6. Remaining risks and the smallest next action.

For verifier assignments, return a machine-readable `criterion_results` list keyed by the supplied criterion IDs. Each result contains `status=passed|failed|blocked|not_run`, an exact `evidence_locator`, and `gap_reason` for blocked or not-run work. Prose may explain the packet but never replaces it.

The root appends the exact child thread UUID, turn UUID, role, model, effort, effective sandbox, completion receipt, parent thread UUID, matching parent spawn call ID/non-history route, and accepted/rejected status. The parent call output must contain the child UUID; task-name equality cannot establish the edge. Never relabel a writable effective sandbox as `sandbox_read_only` or “equivalent” because the assignment prohibited edits. Use native continuation for related work. For production-accepted rows, an initial-turn spawn receipt cannot be reused for later turns; keep continuation candidates and root assessment explicit under [v2-runtime.md](v2-runtime.md). Task names, static TOML, opaque message bodies, and agent self-report are not runtime receipts.

## Assignment quality gate

Dispatch only when a different agent could determine success without hidden conversation context and when concurrent ownership is unambiguous.
