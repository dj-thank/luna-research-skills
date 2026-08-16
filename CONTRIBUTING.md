# Contributing

Keep the repository source-first and read-only by default. The `.agents/skills/` and `.codex/agents/` directories are the canonical repository-scoped source; an installed or cloud-discovered copy becomes runtime authority only after current Codex discovery and receipt verification.

- Keep README guidance aligned with both source packages and verify that their checker/test copies remain byte-identical.
- Do not add credentials, private session rollouts, personal data, or machine-specific filesystem paths.
- Do not claim a model or routing guarantee from a task name, nickname, static config, or historical run alone.
- When changing the spawn instructions, inspect the live Codex schema and document the supported fresh-context route.
- Recheck the current Codex configuration and subagent documentation before changing the Quick Start.
- Include a dated runtime probe or explicitly mark the result as unverified; do not present local prompt review as runtime proof.

Before opening a pull request, inspect the Markdown files as UTF-8, check that all referenced local files exist, run both packaged checker suites and Skill validators, and review the diff for stale model, schema, privacy, and licensing claims.
