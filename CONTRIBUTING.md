# Contributing

Keep the repository source-first and read-only by default. The `.agents/skills/` and `.codex/agents/` directories are the canonical repository-scoped source; an installed or cloud-discovered copy becomes runtime authority only after current Codex discovery and receipt verification.

- Keep README guidance aligned with both source packages and verify that their checker/test copies remain byte-identical.
- Do not add credentials, private session rollouts, personal data, or machine-specific filesystem paths.
- Do not claim a model or routing guarantee from a task name, nickname, static config, or historical run alone.
- When changing the spawn instructions, inspect the live Codex schema and document the supported fresh-context route.
- Recheck the current Codex configuration and subagent documentation before changing the Quick Start.
- Include a dated runtime probe or explicitly mark the result as unverified; do not present local prompt review as runtime proof.

Before opening a pull request, inspect the Markdown files as UTF-8, check that all referenced local files exist, run both packaged checker suites and Skill validators, and review the diff for stale model, schema, privacy, and licensing claims.

From the repository root, the release gate is:

```powershell
$env:PYTHONUTF8 = '1'
$env:PYTHONDONTWRITEBYTECODE = '1'
python .agents/skills/run-diverse-luna-research/scripts/test_check_setup.py
python .agents/skills/run-diverse-luna-project/scripts/test_check_setup.py
python -m unittest discover -s tools -p 'test_*.py'
python tools/validate_repository.py
pwsh -NoProfile -File tools/Test-LunaMigrationTools.ps1 -Source (Resolve-Path '.agents/skills').Path
python tools/build_release.py --output release-check
python tools/stress_contracts.py --iterations 25
```

Also run the bundled Skill Creator `quick_validate.py` against both Skill directories, validate the generated plugin manifest/archive, rebuild release assets twice and compare their SHA-256, and run `git diff --check`. Keep `release-check`, Python caches, runtime rollouts, discovery reports containing machine paths, and migration journals out of commits.

Routing or description changes require fresh, task-local forward evaluation against both `references/evaluation-cases.md` files. Record expected versus observed Skill selection, route, N/C/W/V, exact completed Luna/medium receipts, ownership collisions, latency, and false completion claims. A static case manifest or checker unit test complements but does not replace live runtime evidence.
