# Luna skills discovery / user-scope migration runbook

## Scope and evidence

The official Build Skills behavior to validate against the current release is: user-wide skills live under `$HOME/.agents/skills`; repository ancestors may contribute `.agents/skills`; same-name skills do not merge; symlinks are supported; and `[[skills.config]]` entries can disable a path after a restart. The discovery script records these as **observed locally** versus **official behavior to re-confirm**—it does not change either location.

`Test-LunaSkillDiscovery.ps1` is read-only. It inventories the legacy `$HOME/.codex/skills` and candidate `$HOME/.agents/skills` roots, optional roots, `SKILL.md` frontmatter names, SHA-256 manifests, reparse/link targets, duplicate names, repository-ancestor scopes, config/agent TOML keys, and available CLI commands. It emits JSON and optional Markdown without printing file contents or secrets.

## Staged plan

1. Run discovery and save its report outside any skill root.
2. Review duplicate names, link targets, hashes, and the source/target owner. A duplicate is a stop condition; choose one canonical name before applying.
3. Use the installer in its default dry-run mode. `-Source` may be one skill package or a directory whose direct children are skill packages. The target root is constrained to exactly `$HOME/.agents/skills`; the root may already contain unrelated skills, but an existing destination package is always a hard stop.
4. After a human confirms the report, run with `-Apply`. The installer honors PowerShell `ShouldProcess` for both the package root and manifest (`-WhatIf` remains non-mutating), excludes generated `__pycache__`/`.pyc` files, stages every package, and verifies every SHA-256. It atomically creates a new `state=prepared` manifest directly under `$HOME/.agents` before moving any package, updates only that owned manifest after each move, and finishes at `state=applied`. A custom manifest path outside that exact parent, a non-JSON manifest, or any existing manifest is a hard stop. It never deletes, overwrites, or disables legacy skills.
5. Restart the host application only when the official configuration mechanism requires it. Treat selector/name discovery and runtime behavior as separate evidence.

Example (PowerShell 5.1 or 7):

```powershell
$d = Join-Path (Get-Location) 'work\luna-skill-v5\discovery'
& (Join-Path $d 'Test-LunaSkillDiscovery.ps1') `
  -OutputJson (Join-Path (Get-Location) 'work\luna-discovery.json') `
  -OutputMarkdown (Join-Path (Get-Location) 'work\luna-discovery.md')

# Dry run: no target directory is created
& (Join-Path $d 'Install-LunaSkillsUserScope.ps1') -Source 'C:\path\to\repository\.agents\skills'

# Apply only after human review; -WhatIf remains non-mutating
& (Join-Path $d 'Install-LunaSkillsUserScope.ps1') -Source 'C:\path\to\repository\.agents\skills' -Apply -WhatIf

# Real apply is still a separate human gate
& (Join-Path $d 'Install-LunaSkillsUserScope.ps1') -Source 'C:\path\to\repository\.agents\skills' -Apply
```

## Fresh-task verification boundary

Verification must use a fresh projectless task and a fresh nested-repository task. In each, record (a) selector path, (b) selector/name, (c) explicit invocation, and (d) a runtime receipt showing the expected skill actually ran. A static inventory, parser result, health response, or synthetic selector is not a runtime receipt. Re-run after restart if `skills.config` path/disable settings are changed.

Keep legacy and candidate roots distinct until those receipts pass. Only then may a human decide whether to disable a legacy path through the documented config; disabling, deleting, publishing, credential changes, and real external sends remain explicit Human gates. If the `codex` shim is broken or absent, use a directly resolved `pwsh`/`powershell` executable for local read-only checks and record the CLI failure separately; do not repair global PATH or auto-connect settings as part of migration.

## Rollback

The apply manifest records every exact package destination and hash. `prepared` means no move was confirmed yet, `partial` names only destinations already moved before a failure, and `applied` means every listed package moved. If and only if a package destination is listed under `appliedDestinations` and its resolved path remains under `$HOME/.agents/skills`, a human may remove that individual package tree to roll back. Never recursively remove the broad `$HOME/.agents/skills` parent, never touch `$HOME/.codex/skills`, and retain the manifest and discovery report for audit.
