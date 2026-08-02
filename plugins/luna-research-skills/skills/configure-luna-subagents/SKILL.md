---
name: configure-luna-subagents
description: Configure, audit, migrate, or restore Codex-native subagent defaults so spawned agents use GPT-5.6 Luna at medium reasoning with a 40-thread session ceiling. Use for first-time Luna setup, migration from the legacy default-agent file, routing repair, compatibility checks after a Codex update, or removal of this managed configuration.
---

# Configure Luna Subagents

Use the bundled installer as the single source of truth. It manages only `config.toml`, preserves unrelated TOML and line endings, backs up changed bytes, writes atomically, and restores only when managed files have not drifted.

## 1. Inspect the target

Resolve this skill directory and run:

```text
python <skill-dir>/scripts/configure_luna.py plan
```

Use `--codex-home <path>` when `CODEX_HOME` or `~/.codex` is not the intended target. Report every `CHANGE`, `CONFLICT`, and required replacement flag.

Explain the blast radius before applying: the four `[agents]` values are user-level defaults for spawned agents, not only research scouts. Explicit model or reasoning values supplied by a spawn, and custom-agent files that set their own model, take precedence. Use `fork_turns="none"` when the active schema exposes it; otherwise use `agent_type="default"` with `fork_context=false`.

Completion criterion: the user knows every value that would change, whether `--replace-settings` is required, and which explicit spawn or custom-role settings can override the defaults.

## 2. Apply an authorized plan

Treat a request to inspect, explain, or audit as read-only. When the user has explicitly authorized configuration, run the exact plan with the required acknowledgement and only the conflict flags shown by the planner:

```text
python <skill-dir>/scripts/configure_luna.py install --apply
```

Add `--replace-settings` only for approved changes to `agents.enabled`, `agents.max_concurrent_threads_per_session`, `agents.default_subagent_model`, or `agents.default_subagent_reasoning_effort`.

Preserve the reported backup path. A write failure triggers rollback; an existing managed state that drifted stops a second installation.

Completion criterion: the installer exits successfully and reports `model=gpt-5.6-luna`, `reasoning_effort=medium`, and `max_concurrent_threads_per_session=40`, or it stops without changing the target and reports one actionable conflict.

## Migrate a managed v1 installation

When `plan` reports an intact managed v1 installation, review the same conflicts and run:

```text
python <skill-dir>/scripts/configure_luna.py migrate --apply
```

Add `--replace-settings` only when the plan names conflicting pre-v1 values and the user approves replacing them. Migration first verifies v1 hashes and backups, restores the pre-v1 bytes including any previous `agents/default.toml`, then installs the v2 config-only state. Drift fails closed.

## 3. Cross the reload boundary

Ask the user to restart Codex or open a new task after installation. Run:

```text
python <skill-dir>/scripts/configure_luna.py status
```

Static readiness is necessary but not runtime proof. Use `$run-diverse-luna-research` to create a bounded probe with the supported fresh-context route and verify the child's rollout metadata before broad fan-out.

Completion criterion: static status is `READY`, and any claim that a child actually ran Luna is backed by child runtime metadata rather than its task name or nickname.

## Restore branch

When the user explicitly requests removal, preview the target with `status`, then run:

```text
python <skill-dir>/scripts/configure_luna.py uninstall --apply
```

The restore proceeds only while both managed files match their installed hashes. If either file drifted, preserve it and report the retained timestamped backup for manual recovery.
