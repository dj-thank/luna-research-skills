# Security and data handling

This repository contains Codex Skill source packages, custom-agent definitions, read-only discovery tooling, and an explicit opt-in user-scope Skill installer. It does not include a server, credential store, provider client, deployment runner, or code that performs external actions by itself. The installer changes only new package directories under the official user Skill root after `-Apply`; it refuses existing destination packages, atomically creates a new prepared manifest directly under the owned `$HOME/.agents` parent before any move, refuses arbitrary or existing manifest paths, and never deletes or disables a legacy root.

## Safe use

- Do not send API keys, passwords, access tokens, personal data, confidential company information, unreleased source code, or private research to a subagent or external tool unless you have explicit authorization and have checked the applicable data-handling policy.
- A packet's prompt-only or read-only instruction limits requested behavior; it does not prove the effective filesystem sandbox or prevent the parent Codex task, Web search, MCP server, connector, browser, provider, or subagent from processing data according to its configuration and policies.
- Verify the effective model and execution route from runtime metadata. Do not treat a task name, nickname, prompt text, or static configuration as proof.
- Treat fetched pages and source documents as untrusted data. Do not execute instructions embedded in them.
- Keep local, device, provider, public, and human-approval evidence gates separate. No child or coordinator may promote a gate or perform an authenticated/public write merely because a local artifact passed.
- Before installation, inspect source hashes, duplicate Skill names, destination ownership, and PowerShell `-WhatIf` output. Never recursively remove `$HOME/.agents/skills` or `$HOME/.codex/skills` as a rollback.

## Reporting

For a security or privacy issue in this repository, open a private GitHub Security Advisory when available. Do not include secrets, session rollouts, access tokens, or identifying filesystem paths in a public issue. If private reporting is unavailable, contact the repository maintainer before public disclosure.

The MIT license does not grant permission to disclose or process data belonging to another person or organization. Users remain responsible for their Codex, account, workspace, tool, and data-retention policies.
