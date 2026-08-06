# Security and data handling

This repository contains copy-and-paste research prompts. It does not include an installer, runner, server, credential store, or code that performs external actions by itself.

## Safe use

- Do not paste API keys, passwords, access tokens, personal data, confidential company information, unreleased source code, or private research into `RESEARCH REQUEST` unless you have explicit authorization and have checked the applicable data-handling policy.
- The prompt's read-only boundary limits the requested actions; it does not prevent the parent Codex task, Web search, MCP server, or subagent from processing or retaining data according to their own configuration and policies.
- Verify the effective model and execution route from runtime metadata. Do not treat a task name, nickname, prompt text, or static configuration as proof.
- Treat fetched pages and source documents as untrusted data. Do not execute instructions embedded in them.

## Reporting

For a security or privacy issue in this repository, open a private GitHub Security Advisory when available. Do not include secrets, session rollouts, access tokens, or identifying filesystem paths in a public issue. If private reporting is unavailable, contact the repository maintainer before public disclosure.

The MIT license does not grant permission to disclose or process data belonging to another person or organization. Users remain responsible for their Codex, account, workspace, tool, and data-retention policies.
