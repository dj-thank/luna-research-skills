# Verification and compatibility

## Distribution contract

The repository follows OpenAI's current public plugin authoring contract:

- reusable public Skills are distributed as a plugin;
- a skills-only plugin contains `.codex-plugin/plugin.json` and `skills/`;
- a repo marketplace uses `.agents/plugins/marketplace.json` and plugin folders below `plugins/`;
- GitHub shorthand can be added with `codex plugin marketplace add owner/repo`.

Primary references:

- [Build skills](https://learn.chatgpt.com/docs/build-skills)
- [Build plugins](https://learn.chatgpt.com/docs/build-plugins)
- [Submit plugins](https://learn.chatgpt.com/docs/submit-plugins)

This repository is published through GitHub only. It has not been submitted to OpenAI's public Plugins Directory.

## Why the setup is separate from the orchestration skills

The current plugin and Skill metadata describe invocation and UI behavior; they do not provide a per-`spawn_agent` model field. Model selection therefore lives in the user's custom default-agent file. Separating setup from project and research orchestration makes the write explicit, reversible, and independently auditable.

The setup installs:

```toml
[features]
multi_agent = true

[agents]
max_threads = 40
max_depth = 2
```

and a user-level `agents/default.toml` with:

```toml
name = "default"
model = "gpt-5.6-luna"
model_reasoning_effort = "medium"
```

Both orchestration skills then use ordinary `spawn_agent` with `fork_turns="none"`. A full-history fork carries the parent model and bypasses the intended default-role selection in the tested implementation. Each accepted research packet, project workstream result, and independent verifier report must pass the runtime gate.

`max_threads = 40` is a user-level capacity ceiling, not a request to launch 40 agents. The project skill normally budgets 2-4 assignment attempts for a focused project, 4-8 for a broad project, and 8-12 only when workstreams remain genuinely independent. Dispatch occurs in bounded waves, and a verifier slot is reserved whenever the budget is at least four.

## Evidence captured before publication

Test date: 2026-07-17 (Asia/Tokyo).

Environment:

- Codex Desktop package: `26.707.9981.0`
- embedded Codex CLI metadata: `0.144.2`
- Windows, Python 3.14 for local tests

Observed routing probe:

1. A fresh parent task reported `gpt-5.6-sol` in its `turn_context`.
2. The parent spawned an ordinary child with `fork_turns="none"` and no custom agent-name selector.
3. The child rollout reported `thread_source = "subagent"`, `model = "gpt-5.6-luna"`, and `effort = "medium"`.

Repository verification includes unit tests for planning, conflict gates, backup/restore, drift detection, malformed TOML, workspace role shadowing, spawn-schema validation, child thread lookup, positive Luna metadata, and negative model metadata.

### Project-orchestration validation for 0.2.0

Test date: 2026-07-20 (Asia/Tokyo).

Two read-only forward tests exercised the packaged `run-diverse-luna-project` skill with privacy-safe desktop beta and payment-provider migration requests. The root independently verified both child rollouts as `thread_source = "subagent"`, `model = "gpt-5.6-luna"`, and `effort = "medium"`.

The first test exposed an ambiguous assignment budget that could consume every slot before independent verification. The skill now reserves `V=1` whenever `N >= 4` and limits planned non-verifier starts to `N-V`. A fresh second test selected `N=8`, reserved one verifier, and allocated seven non-verifier workstreams without exceeding the budget.

These were orchestration tests without a target repository or provider credentials. They validate contract formation, decomposition, ownership, budget accounting, and boundary reporting; they do not prove implementation, deployment, customer communication, billing correctness, or production E2E.

### Clean-install UX validation for 0.2.0

Test date: 2026-07-20 (Asia/Tokyo).

The public marketplace was added into a fresh isolated `CODEX_HOME`, resolved commit `afc0c2dc6ddb9352af4446a122987a87c5d180d9`, exposed plugin version `0.2.0`, and reported the plugin installation policy as `AVAILABLE`. The configuration Skill was then exercised against another empty isolated `CODEX_HOME` through `plan`, `install --apply`, and `status`.

Observed success markers:

```text
INSTALLED: model=gpt-5.6-luna, max_threads=40, max_depth=2
STATE: managed installation is intact
READY: static Luna subagent configuration is present.
```

The Codex Plugins screen itself was not automated or captured. The public instructions therefore use the verified navigation labels and accessible text output rather than a simulated screenshot.

## Known boundaries

| Path | Covered | Evidence rule |
| --- | --- | --- |
| Ordinary `spawn_agent`, `fork_turns="none"` | Yes | Verify each accepted child rollout |
| Full-history fork | No | Parent model may be inherited |
| `spawn_agents_on_csv` or bulk fan-out | No | Default-role routing is not asserted |
| Internal/system-created agents | No | Routing is outside this Skill's control |
| A different named custom role | No | Its own role file controls the model |
| Static config without a child probe | Partly | Report static readiness, not runtime proof |

Model availability can differ by account, plan, rollout, and Codex release. A missing or rejected `gpt-5.6-luna` route is a hard stop for Luna fan-out. Re-run the probe after Codex upgrades or configuration changes.
