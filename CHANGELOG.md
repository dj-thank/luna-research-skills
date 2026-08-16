# Changelog

このプロジェクトの主な変更を記録します。形式は [Keep a Changelog](https://keepachangelog.com/ja/1.1.0/) を参考にし、バージョン番号は [Semantic Versioning](https://semver.org/lang/ja/) に従います。

## [Unreleased]

## [2.0.4] - 2026-08-17

### Fixed

- release builderがWindows working treeのCRLFをarchiveへ持ち込み、同一commitのUbuntu buildとSHA-256が一致しなかった問題を修正した。UTF-8 text entryをLFへcanonicalizeし、LF/CRLF fixtureからsource ZIP、plugin ZIP、SBOM、SHA256SUMSが完全一致することをfailure testで固定した。
- `.gitattributes`でtext checkoutをLFに固定し、binary assetを明示した。builderのcanonicalizationは既存checkoutやglobal Git設定に依存しないため、長寿命Windows worktreeでも同じartifactを生成する。

## [2.0.3] - 2026-08-17

### Security

- GitHub Immutable releasesをrepository設定で有効化し、公開後のtag移動、release assetの変更・削除を禁止した。Release workflowは全asset添付後に公開し、GitHub APIの`isImmutable=true`を受入条件として検査する。
- Dependabot security updatesを有効化し、既存のDependabot alerts、CodeQL、secret scanning、push protection、private vulnerability reportingと組み合わせた。
- GitHub Actions設定で外部Actionのfull-length commit SHA pinningを強制した。repository内のworkflowは既に全外部Actionを40桁SHAで固定している。

## [2.0.2] - 2026-08-17

### Fixed

- user-scopeへ既に導入済みの端末でもmigration safety suiteを再実行できるようにした。production-pathの`-Apply -WhatIf`は、clean profileでは従来どおり完了し、既存packageがある場合は安全な上書き拒否を期待結果として扱う。disposable-profileの非変更テストは引き続き必須。

## [2.0.1] - 2026-08-17

### Fixed

- 非対話PowerShell hostでuser-scope installerの`-Apply`が確認UIを開こうとして`ShouldProcess`のnull-referenceになる問題を修正。`-Apply`そのものを明示的な変更承認として扱い、必要な場合だけ`-Confirm`で追加確認を要求できるようにした。
- `TestUserProfile`が`ShouldProcess`を迂回していたため本番経路を検証できなかった問題を修正。disposable applyも本番と同じgateを通し、`-WhatIf`がディスクへ変更を加えないことをPowerShell 7/5.1統合テストで固定した。

## [2.0.0] - 2026-08-17

### Added

- 実行可能な `run-diverse-luna-research` / `run-diverse-luna-project` source packages と、Luna coordinator / builder / reviewer custom-agent definitions。
- 全tree共通の `N`、同時実行capacity `C`、wave width `W`、verifier reserve `V`、depth 2、exact runtime receiptを使うhierarchical fan-out/fan-in契約。
- read-only discovery、dry-run/`ShouldProcess`、staging hash検証、既存package拒否、非変更failure testsを備えたuser-scope migration tools。
- Codex cloudとrepository taskで自動発見できる`.agents/skills` / `.codex/agents`配置と、Python契約・TOML・Markdown link・PowerShell migration safetyを検査する最小権限GitHub Actions workflow。
- built-in `worker` を明示的に Luna/medium/fresh-contextへ固定する、custom role非公開surface向けの検証済みcapability fallback。
- 決定的source ZIP、installable plugin ZIP、SHA-256 manifest、SPDX 2.3 SBOM、tag refからだけ明示dispatchできるGitHub Release workflow。
- Python 3.11/3.12/3.13をUbuntu/Windows/macOSで走らせる契約matrix、PowerShell 7/5.1 migration tests、CodeQL、Dependabot。
- 4,225 contract casesと5回のdisposable migration攻撃fixtureを反復する、bounded stress jobs。

### Changed

- READMEをprompt-first説明から、flat/hierarchical research/project Skillの配布・安全・検証案内へ置換。
- v2 checkerを `N/C/W/V` 全tree予算、計画済みrow、`V=max(1,ceil(.15*N))`、live attemptを含む同時実行、wave幅、deadline、research/project closure、exact parent-edge receiptでfail-closed化。期限後に開始またはacceptedになった出力を拒否し、未dispatchのroot-only gapを `not_dispatched/excluded` で終端化。researchでは一次情報・反証を各`ceil(20%*N)`、測定/欠損を1件以上、unique coverage、priority accepted-or-gapとして検査。
- projectを唯一のimplicit router、researchを明示呼出し／project handoff専用にし、packet-only、mixed delivery、曖昧時root-onlyの決定的なtie-breakを追加。
- installerは任意manifest上書きを廃止し、package move前にowned `state=prepared` manifestを新規作成、partial/applied stateを追跡する方式へ変更。
- installerはsource reparse pointを拒否し、`pendingDestination` journal、durable flush、atomic manifest replacement、same-volume atomic directory move、destination race拒否、OS-temp real-apply/partial-failure testsを追加。
- research/projectのtriggerを決定的に分離し、packet-only researchとcode/artifact/test/releaseを含むmixed deliveryを明確に分離。built-in `default` を上書きしていた公開custom agent定義を削除。
- 配布・運用契約から非公式 `max_depth` と旧custom model-catalog依存を外し、depth 2をworkflow/ledger policyとしてのみ扱うよう整理。

### Removed

- 現行Skillと重複・矛盾していたpaste-only `PROMPT.md`、`PROMPT.en.md`、`PROJECT-PROMPT.md`。
- 2026-08-10時点のモデルカタログ書換え回避策とrouting観測文書。履歴とv1.3.2以前のtagには残る。

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

[Unreleased]: https://github.com/dj-thank/luna-research-skills/compare/v2.0.4...HEAD
[2.0.4]: https://github.com/dj-thank/luna-research-skills/compare/v2.0.3...v2.0.4
[2.0.3]: https://github.com/dj-thank/luna-research-skills/compare/v2.0.2...v2.0.3
[2.0.2]: https://github.com/dj-thank/luna-research-skills/compare/v2.0.1...v2.0.2
[2.0.1]: https://github.com/dj-thank/luna-research-skills/compare/v2.0.0...v2.0.1
[2.0.0]: https://github.com/dj-thank/luna-research-skills/compare/v1.3.2...v2.0.0
[1.3.2]: https://github.com/dj-thank/luna-research-skills/releases/tag/v1.3.2
[1.3.0]: https://github.com/dj-thank/luna-research-skills/compare/v1.2.0...v1.3.0
[1.2.0]: https://github.com/dj-thank/luna-research-skills/releases/tag/v1.2.0
