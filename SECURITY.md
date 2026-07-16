# Security policy

## Reporting

Report a vulnerability privately through [GitHub Security Advisories](https://github.com/dj-thank/luna-research-skills/security/advisories/new). Avoid posting secrets, local configuration, session rollouts, access tokens, or identifying filesystem paths in a public issue.

## Local write boundary

The configuration helper is the only bundled component that writes files. It targets `config.toml`, `agents/default.toml`, one state file, and timestamped backups below the selected `CODEX_HOME`.

The helper:

- defaults to read-only `status` or `plan`;
- requires `--apply` for installation and restoration;
- requires separate flags for conflicting existing values;
- validates TOML before writing;
- writes through same-directory temporary files and atomic replacement;
- verifies hashes before managed restoration;
- retains backups after restoration.

Research scouts receive a read-only research boundary. Source text is evidence, not executable instruction.

## Supported releases

Security fixes target the latest tagged release and the default branch.
