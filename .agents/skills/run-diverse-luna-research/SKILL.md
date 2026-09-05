---
name: run-diverse-luna-research
description: "Research current, multi-source questions with bounded Luna evidence scouts and source verification. Use for deep comparisons or adversarial fact-checks; keep simple lookups at the root and delivery in the caller workflow."
---

# Run Diverse Luna Research

Produce a source-backed answer to the user's decision, with uncertainty that matches the evidence. Research scouts return evidence only; the root owns synthesis and authorized changes. Keep the caller's selected model, including GPT-6 Astra, unchanged; the Luna/max policy applies only to this skill's delegated evidence lane. API model capabilities do not establish which tools a Codex task exposes.

## Multi Agent V2

When V2 is requested, read [the native runtime contract](references/v2-runtime.md) first. Verify saved enablement, current per-level tools and observed execution separately. Use native continuation for related work, fresh agents for independent audits, and bounded child delegation when actually exposed. Keep the parent model unchanged.

The installed `multi-agent-v2` skill can own general orchestration; this skill owns only its bounded Luna evidence lane. Neither skill changes the caller's model policy implicitly.

## Anchor the answer before choosing a route

Identify what the user will decide or produce, the few claims that could change it, and the evidence needed to settle them. Use the conversation first; ask only when a missing constraint would materially change the work, and continue independent research meanwhile. A post, an implementation choice, and a literature review need different depth even on the same topic.

When the user corrects the target, retain relevant evidence, stop the affected assignments, and give remaining work the corrected question. A completed source inventory is not completion of the user's answer.

## Choose the smallest useful route

- **Single lookup or ordered source chain:** research directly at the root. Open the relevant authority, answer with citations, and stop. No scout setup, quotas, or assignment ledger is required for this route.
- **Parallel evidence:** use when two or more bounded cells can examine different questions independently and improve the answer. Before any spawn, read [the execution contract](references/workflow.md) and [the packet and ledger contract](references/research-packet.md). Create the feasible ledger and verify one useful Luna/max child before wider dispatch. Budget is a ceiling: leave unused attempts unspent when the answer is supported.
- **Research plus delivery:** return the evidence to the caller's implementation workflow. Use `run-diverse-luna-project` only if the user explicitly requested Luna implementation. Mentioning Luna as the object being repaired is not a request to use Luna builders.

Skill selection does not override the active session's delegation restrictions. If dispatch is unavailable or disallowed, do the useful work at the root and disclose the unexecuted lane.

## Preserve these acceptance boundaries

For conflicting or dependent cells, use [peer evidence clarification](references/peer-evidence.md) after the initial independent packets are recorded. Root authorizes exact peers and limits; scouts may clarify evidence directly, but agreement adds no source independence and unresolved conflicts return to root.

For parallel work, count every started attempt against one global budget, reserve verification, and give each cell a unique question and deadline. The exact completed child turn and parent spawn edge must prove Luna/max. A role name, requested model, or static read-only TOML is insufficient. If the probe fails, stop further dispatch and continue safely at the root.

Keep private/connector/provider evidence at the root unless the execution contract's access requirements can be mechanically satisfied. Public scouts in a writable runtime use a clearly labeled behavioral no-mutation boundary. Keep the parent's chosen model and global configuration unchanged.

Before synthesis, verify conclusion-grade sources and every accepted runtime receipt. Reuse a root-opened source snapshot within its freshness window; reopen when the claim, version, access state, or evidence changes. A scout summary or search snippet alone is not a verified source. Distinguish **coverage** (which questions were answered) from **independence** (which upstream authorities support a claim). Different official sections can answer different questions while counting as one source family. Repeated pages or retries add no independent corroboration. Record gaps and contradictions rather than forcing an unsupported consensus.

For access failures, shared source retrieval, claim sufficiency, and additional waves, follow the execution contract. Lead with the answer, citations, and practical uncertainty. Put detailed accounting in a method artifact when it would obscure the answer. Report only observed evidence gates.

## Maintenance

Use [evaluation cases](references/evaluation-cases.md) only when editing this skill. Run `scripts/test_check_setup.py`, the bundled Skill Creator `quick_validate.py`, and checker `--version`; compare both scripts' hashes with the Project sibling when installed. Preserve standalone installation. Full parallel runs still load the execution and packet contracts: a shorter entrypoint alone is not proof of lower end-to-end token use.
