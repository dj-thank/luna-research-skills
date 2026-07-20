# Luna workstream packet

Use this checklist for every new assignment. Put all required context in the spawn message because `fork_turns="none"` supplies no conversation history.

## Assignment packet

- **Project outcome:** the overall result this workstream supports.
- **Bounded objective:** one deliverable, decision, question, or verification boundary.
- **Inputs:** exact files, artifacts, URLs, commands, or prior decisions to use.
- **Ownership:** files or modules the agent may edit; write `read-only` when it must not edit.
- **Dependencies:** completed inputs and work that remains outside this assignment.
- **Constraints:** user authority, safety, compatibility, style, time, and attempt limits.
- **Acceptance check:** observable conditions that end this assignment.
- **Validation:** commands or inspections the agent must run.
- **Return:** requested artifacts, diff summary, evidence, residual risks, and status.

Append these operating rules:

```text
Use only this task-local context. You are not alone in the workspace: preserve existing and concurrent changes, stay inside the assigned ownership, and do not revert others' work. Do not spawn descendants. Report actual evidence and uncertainty. Stop and return a blocker when completion requires new authority, an overlapping edit, or unavailable external state.
```

## Return packet

Require the agent to return:

1. Status: completed, partial, failed, or blocked.
2. Outcome and artifact paths or evidence locators.
3. Files changed and why, or a declaration of read-only work.
4. Checks run with observed results.
5. Assumptions, integration notes, and conflicts detected.
6. Remaining risks and the smallest next action.

## Assignment quality gate

Dispatch only when a different agent could determine success without hidden conversation context and when concurrent ownership is unambiguous.
