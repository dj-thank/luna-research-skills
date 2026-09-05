# Multi Agent V2: runtime and orchestration contract

Use this reference when the user names Multi Agent V2 or when a run needs coordination,
nested delegation, continuation, steering, cancellation, or parallel collection.
It separates official product behavior, the callable surface, and this skill's policies.

## Evidence and configuration

Official sources, reviewed 2026-09-05:

- [Subagents](https://learn.chatgpt.com/docs/agent-configuration/subagents): specialized agents, parallel work, model resolution, orchestration, follow-up, sandbox inheritance, agent configuration.
- [Configuration reference](https://learn.chatgpt.com/docs/config-file/config-reference): supported configuration fields and precedence. Public documentation is not an exhaustive reference for every desktop/runtime tool name.
- [Skills](https://developers.openai.com/codex/skills): focused descriptions, progressive disclosure, optional scripts and dependencies.

Before dispatch, inspect three separate layers:

1. **Saved configuration:** use the installed native executable's `features list` and
   parsed `config.toml`. On a binary exposing it, `features.multi_agent_v2=true`
   enables the V2 feature. `agents.enabled=true` permits agents;
   `agents.max_concurrent_threads_per_session` caps children, excluding root.
   Change only user-authorized settings, preserving models and unrelated fields.
2. **Current surface:** read the live tool declarations at each level. Record the
   exact names, allowed arguments, context-fork routes and tool availability.
   A config flag, installed custom role, or root's tool list does not prove that
   its child can spawn. Do not invent `max_depth` or other obsolete settings.
3. **Observed execution:** check session metadata for `multi_agent_version`, exact
   parent/depth, completed turns and real tool calls. State unknown when absent.
   Opening an older task can retain a different tool surface from a newly started
   process. A successful new CLI probe proves that CLI run, not an old desktop turn.

Use `check_setup.py --require-v2` when this run promises V2: it checks saved enablement
and, when given a runtime receipt, its V2 metadata. It does not prove child tool exposure;
a bounded useful child must demonstrate that separately. The checker still verifies Luna/max
only for the Luna lane. General V2 does not require Luna or a fixed reasoning effort.

## Native tool semantics on the current V2 surface

| Intent | Tool | What to verify |
|---|---|---|
| Start independent work | `spawn_agent` | Pass full bounded context and explicit fresh fork route; retain returned actual ID/path. Roles do not enforce filesystem isolation. |
| Inform an active peer | `send_message` | Delivery does not restart an idle peer, acknowledge ownership, or complete work. |
| Continue existing context | `followup_task` | Idle agents start a new turn; running agents receive steering at safe boundaries. Inspect current status first. |
| Stop an active turn | `interrupt_agent` | Stops that turn; the agent remains available. It does not undo edits or prove external processes stopped. |
| Inspect the team | `list_agents` | Use actual paths/status; avoid guessing names. Scope by path when supported. |
| Wait for updates | `wait_agent` | A mailbox wake-up is not the result itself. Consume delivered messages/status, then reassess readiness. |

Use only tools actually exposed. Other surfaces may expose `send_input`, `wait`,
`resume_agent` or `close_agent`; inspect their own semantics instead of renaming V2
calls mechanically. This surface has no `close_agent`; do not pretend interruption
deletes a task or frees a configured thread slot. Codex app `create_thread` is a
user-owned task operation, not a substitute for internal delegation.

## Pick a topology from the work

- **Root only:** ordered work, a tiny fix, or one shared mutable resource.
- **Flat:** independent leaves; root dispatches ready cells before waiting and collects all.
- **Hierarchy:** coordinator partitions a bounded workstream, dispatches only its
  leased children, and collects their results. Root handles integration across workstreams.
  Consider hierarchy with six or more ready cells, but do not force it or spawn filler.
- **Peer collaboration:** root permits exact directed links for interfaces and findings;
  use the peer contract. Sharing conclusions makes subsequent evidence dependent.

A coordinator packet includes global N/C/W/V, exact descendant credits and planned IDs,
permitted roles, disjoint ownership, deadlines, return contract, and no-grandchildren
for leaves. The root's budget includes descendants and resumptions; coordinators cannot
mint credits. Track **threads created**, **activation/steering requests**, **completed
turns**, and **accepted results** separately. Messaging does not create a thread.

A useful workflow is:

```text
root defines result + constraints
  -> coordinator delegates disjoint implementation/research cells
  -> cells work concurrently; authorized peers clarify interfaces
  -> independent reviewer inspects frozen candidate
  -> same owner continues repairs through followup_task when appropriate
  -> reviewer reruns the counterexample; fresh final verifier checks acceptance
  -> coordinator collects every leased result; root integrates exact bytes
```

Use dependency edges for artifact readiness. Do not serialize independent work merely
because the skill lists steps. Do not run review against a file while its owner is still
changing it; freeze/hash the input. Keep a single owner of each shared checkout,
device, authenticated browser, provider, or deployment.

## Continuation and evidence

Use `followup_task` for a related repair or refinement that benefits from the agent's
existing context. Send only the new scope, changed constraints, current artifact revision,
remaining deadline and budget. Use fresh context for an independent audit or a materially
different question. Do not spawn a replacement just to avoid using native continuation.

Record each continuation's tool-call ID, target, status before sending, resulting turn
when visible, changed artifacts and observed checks. A running-agent steer can affect
the current turn; it is not automatically a new completed turn.

The present Luna production receipt format binds `spawn_kind=spawn_agent` to the
**initial child turn only**. A later turn must never borrow that initial call's proof.
If the runtime lacks a structured causal link from a followup call to the exact child
turn, keep its output as a candidate with operational evidence. Root can inspect and
integrate the candidate under its existing authority, with a fresh independently verified
final acceptance check. Record that root assessment separately; do not mark an unbound
followup result as a fully attributed child receipt. A future receipt extension must
prove the activation edge rather than infer it from timestamps or task names.

## Recovery and completion

When tools are unavailable in a child, return its capability gap and unstarted cell IDs.
Root may run the remaining ready cells flat with the same budget. It may separately
diagnose a fresh authorized runtime, but must not silently switch runtimes/models or
count a CLI success as desktop proof. Never use another API or shell launch inside a
restricted child to evade the missing native capability.

On interruption or timeout: stop new dependent dispatch, collect the exact affected paths,
inspect partial edits and owned processes, and resume/reassign only the remaining scope.
Recheck current hashes before integration. Do not bulk-kill processes or revert other work.
After one unanswered retry or the agreed repair limit, escalate the evidence and decision
to root. At closure every started agent/turn has a terminal disposition, every mandatory
criterion has a status, and the resulting artifact passes its real acceptance check.

Budgets, two-level hierarchy, exact receipt policy and evidence gate names are local
workflow controls. They are not universal OpenAI platform requirements. Report a feature
as documented, exposed, executed, or unverified rather than collapsing these categories.
