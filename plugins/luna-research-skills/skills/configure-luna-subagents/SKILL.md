---
name: configure-luna-subagents
description: Configure, audit, or restore Codex ordinary subagent routing so fresh non-full-history subagents use GPT-5.6 Luna with multi-agent depth 2 and a 40-thread ceiling. Use for first-time Luna setup, routing repair, compatibility checks after a Codex update, or removal of this managed configuration.
---

# Configure Luna Subagents

Use the bundled installer as the single source of truth. It plans first, preserves unrelated TOML, backs up changed files, writes atomically, and restores only when managed files have not drifted.

## 1. Inspect the target

Resolve this skill directory and run:

```text
python <skill-dir>/scripts/configure_luna.py plan
```

Use `--codex-home <path>` when `CODEX_HOME` or `~/.codex` is not the intended target. Report every `CHANGE`, `CONFLICT`, and required replacement flag.

Explain the blast radius before applying: `agents/default.toml` affects every ordinary fresh subagent that selects the default role, not only research scouts. The runtime must pass `fork_turns="none"`; a full-history fork inherits the parent context and may bypass this role.

Completion criterion: the user knows the exact files and existing values that would change, whether `--replace-default` or `--replace-settings` is required, and that the change applies to all fresh default-role subagents.

## 2. Apply an authorized plan

Treat a request to inspect, explain, or audit as read-only. When the user has explicitly authorized configuration, run the exact plan with the required acknowledgement and only the conflict flags shown by the planner:

```text
python <skill-dir>/scripts/configure_luna.py install --apply
```

Add `--replace-default` only for an approved existing `agents/default.toml` replacement. Add `--replace-settings` only for approved changes to `features.multi_agent`, `agents.max_threads`, or `agents.max_depth`.

Preserve the reported backup path. A write failure triggers rollback; an existing managed state that drifted stops a second installation.

Completion criterion: the installer exits successfully and reports `model=gpt-5.6-luna`, `max_threads=40`, and `max_depth=2`, or it stops without changing the target and reports one actionable conflict.

## 3. Cross the reload boundary

Ask the user to restart Codex or open a new task after installation. Run:

```text
python <skill-dir>/scripts/configure_luna.py status
```

Static readiness is necessary but not runtime proof. Use `$run-diverse-luna-research` to create a bounded probe with `fork_turns="none"` and verify the child's rollout metadata before broad fan-out.

Completion criterion: static status is `READY`, and any claim that a child actually ran Luna is backed by child runtime metadata rather than its task name or nickname.

## Restore branch

When the user explicitly requests removal, preview the target with `status`, then run:

```text
python <skill-dir>/scripts/configure_luna.py uninstall --apply
```

The restore proceeds only while both managed files match their installed hashes. If either file drifted, preserve it and report the retained timestamped backup for manual recovery.
