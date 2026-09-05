# Recursive delegation within one work tree

Read when a workstream needs another coordinating level. Delegation depth follows the
problem and the actual tools, rather than a fixed two-edge topology.

## One global plan, smaller subtree grants

Root sets `max_workflow_depth=D`, with `1 <= D <= attempt_budget_N`. Root itself is
depth 0 and is not an assignment row. A direct child is depth 1; every other row is
exactly `parent.depth + 1`. Use D=1 for flat work, D=2 for ordinary teams, or D=3/4
when domains or components need their own subteams. These are examples, not platform
limits. Expand the declared depth only by revising the shared plan before new starts.

A coordinating assignment may create another coordinator when it has
`may_spawn_descendants=true`, a positive `descendant_budget`, remaining depth, a
permitted runtime role and an independent bounded subproblem. A terminal assignment
has zero descendant budget and does not spawn. An agent that discovers a useful split
returns the proposed partition and required credits to its coordinator; the coordinator
can use its unspent grant without requesting a new global budget. Existing terminal
role instructions are not silently promoted into delegation authority.

`descendant_budget` includes the entire subtree below that assignment, not just its
direct children. Starting a child reserves `1 + child.descendant_budget` credits from
the parent's grant. Sum those reservations once per direct edge; the parent cannot
give the same remaining credits to two children. The top-level reservations fit N,
all actual starts share N/C/W/V, and the verification reserve stays protected. Unused
capacity is not a reason to create another level.

Example: a coordinator granted 5 descendant credits can create one subcoordinator
with a grant of 3 and one terminal specialist: `(1 + 3) + (1 + 0) = 5`. Giving that
subcoordinator a grant of 4 would need 6 credits and must be rejected. Giving every
level its own fresh N would inflate the budget and is invalid.

## Plan locally, account globally

Each coordinator chooses its next direct children from the leased workstream, adds
their unique attempt IDs and roles to `planned_child_attempt_ids` before dispatch,
and reports the delta to root's shared ledger. Root need not write every leaf prompt
in advance. Subcoordinators receive a smaller grant, the same global limits and
deadline, exact inputs, disjoint ownership, and the return contract. A budget increase,
overlapping writer, new source plane or external action returns to root.

Logical `role/kind=coordinator` describes the assignment; `agent_role` records the
actual tool-selected role. Do not infer model identity or delegation capability from
either name. Only roles permitted by the current runtime and model policy may run.
Terminal specialists require Luna/max. Coordinators can use [the explicit model
composition policy](model-policy.md) only when user-authorized; another model is never
a hidden fallback.

## Prove the new level, then collect upward

When a coordinator returns an unused grant, root records a plan revision before
reassigning it. Reduce its `descendant_budget` only to the subtree reservation still
committed below it (zero if no child started and no child allocation remains). Record
the previous grant, returned amount and reason in the plan delta. Preserve the prior
plan snapshot. The coordinator's own started attempt is still spent; reducing its
grant below existing child commitments is invalid. Never recycle a started attempt
ID. An existing never-started planned slot can be reassigned with updated ownership
and parent edge before its first dispatch; retain that plan change in the audit trail.
Simply appending replacement rows while leaving the old unused reservation intact
double-reserves credits and is correctly rejected.

At each newly used level/role, inspect the child's actual spawn capability. A tool
available at root or in another model is not proof that this child has it. If missing,
return the capability gap and unused credits. Root can flatten the remaining cells
inside the same budget; do not invoke another API or CLI to evade a missing tool.

Each coordinator collects its direct children after their own subtrees have finished.
`collected_result_ids` contains direct child attempt IDs, not a mixture of children
and grandchildren. A coordinator cannot complete before those children are terminal;
their records lead recursively to all descendants. Root validates every actual
parent edge, declared/runtime depth, model, completed turn and source/artifact before
acceptance. Re-rooting a subtree to conceal depth or spend another budget is rejected.

On correction or timeout, relay the changed scope down the affected subtree, record
actual interruption/disposition and recover unused work. Preserve unrelated branches.
A message acknowledgement is not subtree completion, and interruption is not rollback.
Continuations count as their own attempts and keep their activation-evidence limit.
