---
name: run-diverse-luna-research
description: "Research unfamiliar fields and current, multi-source questions with bounded Luna evidence scouts and source verification. Use for deep comparisons or adversarial fact-checks; keep simple lookups at the root and delivery in the caller workflow."
---

# Run Diverse Luna Research

The default delegated model is **GPT-6 Luna / low** (`gpt-6-luna`). Use Luna for focused parallel work; the parent retains its selected model and owns final judgment. Names and historical receipts do not establish runtime identity. Read [model policy](references/model-policy.md) when the user explicitly selects Sol or mixed coordinators.

For a new Windows runtime or a failed environment check, read [the environment diagnostic](references/environment-check.md). Keep saved configuration, separate CLI processes, live tools and completed execution distinct.

Produce a source-backed answer to the user's decision, with uncertainty that matches the evidence. Research scouts return evidence only; the root owns synthesis and authorized changes. Keep the caller's selected model, including GPT-6 Astra, unchanged; terminal evidence specialists remain Luna/low, and any mixed coordinator policy must be explicit. API model capabilities do not establish which tools a Codex task exposes.

## Multi Agent V2

When V2 is requested, read [the native runtime contract](references/v2-runtime.md) first. Verify saved enablement, current per-level tools and observed execution separately. Use native continuation for related work, fresh agents for independent audits, and recursive delegation within the declared depth and subtree budget when actually exposed. Keep the parent model unchanged.

The installed `multi-agent-v2` skill can own general orchestration; this skill owns only its bounded Luna evidence lane. Neither skill changes the caller's model policy implicitly.

## Dispatch policy

Use C<=6, normally W=1-2 (at most 3), and one objective-wide N=6 by default (at most 12), including followups and retries. Read [the trace preflight](references/parent-efficiency.md#dispatch-limits-and-trace-preflight) before the first child and every additional dispatch batch. Keep required verification; when dispatch is exhausted, the parent completes remaining mandatory work. A continuation keeps the same state and budget.

## Anchor the answer before choosing a route

Identify what the user will decide or produce, the few claims that could change it, and the evidence needed to settle them. Use the conversation first; ask only when a missing constraint would materially change the work, and continue independent research meanwhile. A post, an implementation choice, and a literature review need different depth even on the same topic.

When the field is unfamiliar or the user does not yet know what to investigate, first build a short orientation map from authoritative overviews: core concepts, background, working examples and open problems. Use that map to choose distinct evidence questions; adapt the angles to the field. The user need not provide its taxonomy before research can begin. Continue into the requested investigation rather than stopping at the map.

When the user corrects the target, retain relevant evidence, stop the affected assignments, and give remaining work the corrected question. A completed source inventory is not completion of the user's answer.

For OpenAI product/API changes, model availability, or official-docs comparisons, read [OpenAI research](references/openai-research.md). This conditional lane covers retrieval and contract triangulation; keep ordinary research on the routes below.

## Choose the smallest useful route

- **Single lookup or ordered source chain:** research directly at the root. Open the relevant authority, answer with citations, and stop. No scout setup, quotas, or assignment ledger is required for this route.
- **Parallel evidence:** use when two or more bounded cells can examine different questions independently and improve the answer. Before any spawn, read [the execution contract](references/workflow.md) and [the packet and ledger contract](references/research-packet.md). Create the feasible ledger and verify one useful Luna/low child before wider dispatch. Budget is a ceiling: leave unused attempts unspent when the answer is supported.
  For a heavy parent or sustained goal, apply [parent efficiency](references/parent-efficiency.md): delegate autonomous evidence cells, preserve one budget across continuations, and return compact verified packets instead of repeated parent research.
- **Research plus delivery:** hand the caller a supported change, affected target, acceptance check, and unresolved gate, then continue authorized local implementation and verification in its workflow. A findings list alone does not finish a requested improvement. Use `run-diverse-luna-project` only if the user explicitly selected delegated implementation. Mentioning the workflow as the object being repaired is not a request to use Luna builders.

Skill selection does not override the active session's delegation restrictions. If dispatch is unavailable or disallowed, do the useful work at the root and disclose the unexecuted lane.

## Preserve these acceptance boundaries

For conflicting or dependent cells, use [peer evidence clarification](references/peer-evidence.md) after the initial independent packets are recorded. Root authorizes exact peers and limits; scouts may clarify evidence directly, but agreement adds no source independence and unresolved conflicts return to root.

For parallel work, count every started attempt against one global budget, reserve verification, and give each cell a unique question and deadline. The exact completed child turn and parent spawn edge must prove the expected model and effort: Luna/low for terminal specialists, and the explicitly selected policy for coordinators. A role name, requested model, or static read-only TOML is insufficient. If the probe fails, stop further dispatch and continue safely at the root.

Keep private/connector/provider evidence at the root unless the execution contract's access requirements can be mechanically satisfied. Public scouts in a writable runtime use a clearly labeled behavioral no-mutation boundary. Keep the parent's chosen model and global configuration unchanged.

Before synthesis, verify conclusion-grade sources and every accepted runtime receipt. Reuse a root-opened source snapshot within its freshness window; reopen when the claim, version, access state, or evidence changes. A scout summary or search snippet alone is not a verified source. Distinguish **coverage** (which questions were answered) from **independence** (which upstream authorities support a claim). Different official sections can answer different questions while counting as one source family. Repeated pages or retries add no independent corroboration. Record gaps and contradictions rather than forcing an unsupported consensus.

For access failures, shared source retrieval, claim sufficiency, and additional waves, follow the execution contract. Lead with the answer, citations, and practical uncertainty. Put detailed accounting in a method artifact when it would obscure the answer. Report only observed evidence gates.

When an angle contains several independent questions, read [recursive delegation](references/recursive-delegation.md) and assign that angle to a coordinator with explicit descendant credits and depth inside the same global budget. A capable coordinator may partition and dispatch its leased questions, collect their evidence and return it upward. Terminal specialists return proposed splits to their coordinator; they stay within their assigned scope.

Use [model composition](references/model-policy.md) only when the user explicitly authorizes Astra coordinators with Luna specialists. The default remains Luna/low throughout; terminal specialists use the explicitly selected profile. A mixed result is never reported as a Luna-only run.

## Maintenance

Use [evaluation cases](references/evaluation-cases.md) only when editing this skill. Run `scripts/test_check_setup.py`, the bundled Skill Creator `quick_validate.py`, and checker `--version`; compare both scripts' hashes with the Project sibling when installed. Preserve standalone installation. Full parallel runs still load the execution and packet contracts: a shorter entrypoint alone is not proof of lower end-to-end token use.
