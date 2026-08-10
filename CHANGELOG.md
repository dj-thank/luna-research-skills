# Changelog

このプロジェクトの主な変更を記録します。形式は [Keep a Changelog](https://keepachangelog.com/ja/1.1.0/) を参考にし、バージョン番号は [Semantic Versioning](https://semver.org/lang/ja/) に従います。

## [Unreleased]

## [1.3.2] - 2026-08-10

### Removed

- リポジトリ内の公開告知テンプレートとREADMEからの参照。

## 1.3.1 - 2026-08-10

### Added

- Codex Desktop / Multi-Agent V2でLunaだけが `spawn_agent` allowlistから除外される場合の診断・バックアップ・復元ガイド。
- 公式 `models_cache.json` を直接編集せず、専用 `model_catalog_json` のLunaエントリだけを `v1` から `v2` へ変更するコミュニティ製の暫定回避策。
- 公式ドキュメントと `openai/codex` 公開issueに基づく一次情報調査ノート。

### Changed

- READMEのLuna復旧順序に、fresh task／再起動と、direct model availability／native child runtime proofの区別を追加。
- Lunaのtask名、nickname、静的設定をruntime proofとして扱わない境界を維持したまま、V1/V2 catalog mismatchを説明。

### Verification

- Windowsのfresh CLI processからdefault childを起動し、child rolloutのruntime metadataで `thread_source=subagent`、`model=gpt-5.6-luna`、`effort=medium`、Multi-Agent `v2` を確認。
- 専用カタログは、コピー元へLunaのversionを戻したsemantic comparisonで、Luna `v1` → `v2` 以外の差分がないことを確認。

### Boundaries

- `multi_agent_version` の書き換えはOpenAI公式の修正ではなく、2026-08-10時点のコミュニティ製暫定回避策。
- 古いタスクはallowlistを保持することがあるため、反映確認には再起動後の新しいタスクが必要。
- custom catalogは作成時点のモデル一覧を固定するため、公式修正またはCodex更新後に解除・再生成が必要。

## [1.3.0] - 2026-08-06

### Added

- paste-onlyのDiverse Project Prompt。
- Multi-Agent V2 routing caveatと、runtime metadataを使ったLuna検証境界。

## [1.2.0] - 2026-08-02

### Changed

- bounded hierarchy、assignment budget、descendant allowance、root verificationを明確化。

[Unreleased]: https://github.com/dj-thank/luna-research-skills/compare/v1.3.2...HEAD
[1.3.2]: https://github.com/dj-thank/luna-research-skills/releases/tag/v1.3.2
[1.3.0]: https://github.com/dj-thank/luna-research-skills/compare/v1.2.0...v1.3.0
[1.2.0]: https://github.com/dj-thank/luna-research-skills/releases/tag/v1.2.0
