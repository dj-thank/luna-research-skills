# Luna skills discovery / user-scope migration runbook

## Scope and evidence

The official Build Skills behavior to validate against the current release is: user-wide skills live under `$HOME/.agents/skills`; repository ancestors may contribute `.agents/skills`; same-name skills do not merge; symlinks are supported; and `[[skills.config]]` entries can disable a path after a restart. The discovery script records these as **observed locally** versus **official behavior to re-confirm**—it does not change either location.

`Test-LunaSkillDiscovery.ps1` never changes config, skills, agents, or links. It inventories the legacy `$HOME/.codex/skills` and candidate `$HOME/.agents/skills` roots, optional roots, `SKILL.md` frontmatter names, SHA-256 manifests, duplicate names, repository-ancestor scopes, config/agent TOML keys, and available CLI commands. Root or nested reparse points are reported but never traversed, hashed, or resolved; `linkTarget` stays redacted. When output paths are explicitly supplied it creates new JSON/Markdown report files with `CreateNew` only below `RepoRoot` or the OS temporary directory, rejects reparse ancestors, holds an exclusive sibling lock while writing, refuses overwrite, and does not print source contents or secrets.

## Staged plan

1. Run discovery and save its report outside any skill root.
2. Review duplicate names, link targets, complete package hashes, and the source/target owner. Different same-name packages are a hard stop. Byte-identical repository/user or legacy/user copies may coexist only during a documented migration/overlap window; record every root and the selected runtime path, then disable the redundant scope when practical.
3. Use the installer in its default dry-run mode. `-Source` may be one skill package or a directory whose direct children are skill packages. The target root is constrained to exactly `$HOME/.agents/skills`; the root may already contain unrelated skills, but an existing destination package is always a hard stop.
4. After a human confirms the report, run with `-Apply`. The installer honors PowerShell `ShouldProcess` (`-WhatIf` remains non-mutating), rejects root and nested source reparse points, excludes generated `__pycache__`/`.pyc` files, reads each source through a no-write/no-delete shared handle into one bounded snapshot, and writes only bytes whose SHA-256 still matches inventory. It holds exclusive lock files in the owned target parent/root, rechecks path chains and staged trees immediately before each same-volume atomic directory rename, and verifies the installed tree and hashes again afterward. It durably creates a new `state=prepared` journal directly under `$HOME/.agents`; before each rename it records `pendingDestination`, then atomically replaces only that owned journal after the move. It finishes at `state=applied`, or preserves `partial`/`failed` recovery state. Cleanup is deliberately non-recursive: an empty owned stage is removed, while a non-empty, raced, or unsafe stage is left at the exact journaled `stagingPath` for inspection. A manifest outside that exact parent, a non-JSON manifest, an existing manifest, an existing destination, or a destination race is a hard stop. It never deletes, overwrites, or disables legacy skills.
5. Restart the host application only when the official configuration mechanism requires it. Treat selector/name discovery and runtime behavior as separate evidence.

Example (PowerShell 5.1 or 7):

```powershell
$repo = (Resolve-Path '.').Path
$d = Join-Path $repo 'tools'
& (Join-Path $d 'Test-LunaSkillDiscovery.ps1') `
  -SkillRoot (Join-Path $repo '.agents\skills') `
  -OutputJson (Join-Path $repo 'luna-discovery.json') `
  -OutputMarkdown (Join-Path $repo 'luna-discovery.md')

# Dry run: no target directory is created
& (Join-Path $d 'Install-LunaSkillsUserScope.ps1') -Source (Join-Path $repo '.agents\skills')

# Apply only after human review; -WhatIf remains non-mutating
& (Join-Path $d 'Install-LunaSkillsUserScope.ps1') -Source (Join-Path $repo '.agents\skills') -Apply -WhatIf

# Real apply is still a separate human gate
& (Join-Path $d 'Install-LunaSkillsUserScope.ps1') -Source (Join-Path $repo '.agents\skills') -Apply

# Maintainer safety suite: performs real apply and injected partial failure only in verified OS-temp profiles
& (Join-Path $d 'Test-LunaMigrationTools.ps1') -Source (Join-Path $repo '.agents\skills')
```

## Fresh-task verification boundary

Verification must use a fresh projectless task and a fresh nested-repository task. In each, record (a) selector path, (b) selector/name, (c) explicit invocation, and (d) a runtime receipt showing the expected skill actually ran. A static inventory, parser result, health response, or synthetic selector is not a runtime receipt. Re-run after restart if `skills.config` path/disable settings are changed.

Keep legacy and candidate roots distinct until those receipts pass. During the overlap, accept no runtime result unless the complete package hashes match and the selected absolute Skill path is recorded. Only then may a human decide whether to disable a legacy path through the documented config; disabling, deleting, publishing, credential changes, and real external sends remain explicit Human gates. If the `codex` shim is broken or absent, use a directly resolved `pwsh`/`powershell` executable for local read-only checks and record the CLI failure separately; do not repair global PATH or auto-connect settings as part of migration.

## Rollback

The journal records every exact package destination, hash, lock path, and any preserved `stagingPath`. `prepared` means no move was attempted; `applying` records one exact `pendingDestination`; `partial` reconciles destinations already moved before failure; and `applied` means every listed package moved and passed post-move verification. To roll back, first verify that the resolved destination remains under `$HOME/.agents/skills`, compare every file/hash and check for extras, then move that one package to a quarantine directory. Do not automatically delete a changed package or recursively clean a preserved stage; inspect it and remove only known entries after reparse checks. Never recursively remove the broad `$HOME/.agents/skills` parent, never touch `$HOME/.codex/skills`, and retain the journal and discovery report for audit.
