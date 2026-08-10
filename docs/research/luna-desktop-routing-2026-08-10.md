# Luna / Desktop Multi-Agent V2 routing 調査（2026-08-10）

## 結論

OpenAI公式ドキュメントは `gpt-5.6-luna` をsubagent向けモデルとして案内し、custom agent fileや `[agents]` のモデル指定も公開しています。一方、Codex Desktop / CLIの一部では、トップレベルでLunaを利用できても、native Multi-Agent V2の `spawn_agent` がLunaを候補から除外する事象が公開issueで報告されています。

2026-08-10の検証環境では、公式モデルキャッシュ上のLunaが `multi_agent_version: v1`、SolとTerraが `v2` でした。同じタスクの `spawn_agent` は `Unknown model gpt-5.6-luna` とSol / Terraだけのallowlistを返しましたが、direct Luna実行は成功しました。公式キャッシュのコピーからLunaだけを `v2` にした専用カタログをfresh processで読み込むと、native childのruntime metadataで `gpt-5.6-luna / medium / v2` を確認できました。

ただし、Lunaの `multi_agent_version` をローカルで書き換えることはOpenAI公式の修正手順ではありません。コミュニティ製の一時的・可逆な互換回避策としてのみ扱います。

## 1. Lunaとsubagent設定について公式に確認できること

OpenAIの [Subagents](https://learn.chatgpt.com/docs/agent-configuration/subagents) は、`gpt-5.6-luna` を高速で範囲の狭い、明確・反復的・大量の作業向けに案内しています。同ページは次も説明しています。

- custom agent fileで `model` と `model_reasoning_effort` を設定できる。
- custom agent fileの値、明示的spawn値、`[agents]` の既定値、親の値という優先順でモデル設定を解決する。
- `[agents].default_subagent_model` と `[agents].default_subagent_reasoning_effort` をglobal subagent defaultとして設定できる。
- Luna / mediumを使う `docs_researcher` や `code_mapper` のcustom agent例がある。

OpenAIの [Configuration Reference](https://learn.chatgpt.com/docs/config-file/config-reference) は、`model_catalog_json` を「起動時に読み込むJSONモデルカタログへの任意のパス」として公開しています。

これらは、Lunaをagentへ指定することと、独自モデルカタログを読み込む設定キーが公式に存在することの根拠です。しかし、Lunaエントリの `multi_agent_version` を利用者が変更することを公式に推奨する根拠ではありません。

## 2. LunaだけがV2 allowlistから外れる公開報告

`openai/codex` の公開issueには、同じ症状が複数報告されています。

- [#35097: gpt-5.6-luna is marked as MultiAgent V1, so V2 spawn_agent rejects it](https://github.com/openai/codex/issues/35097) は、Lunaがcatalog上でV1に分類され、V2 sessionの `spawn_agent` が `Available models: gpt-5.6-sol, gpt-5.6-terra` と拒否する事象を報告しています。
- [#34399: spawn_agent model allowlist omits gpt-5.6-luna](https://github.com/openai/codex/issues/34399) は、host model catalogやDesktop thread toolではLunaが見える一方、native `spawn_agent` allowlistからだけ欠落する事象を報告しています。
- [#34964: spawn_agent does not expose gpt-5.6-luna](https://github.com/openai/codex/issues/34964) は、Desktopのmodel selectorにはLunaがあるのに、subagent model overrideがSol / Terraだけになる事象を報告しています。
- [#34909: Codex CLI 0.145.0 spawn_agent rejects Luna even though /model lists it](https://github.com/openai/codex/issues/34909) は、CLI/TUIでも同種の不一致を報告しています。

issueは利用者の再現報告であり、OpenAIによる全環境向けの仕様保証ではありません。ただし、トップレベルのモデル提供状況とnative subagent allowlistが一致しない事象が複数の実行面で観測されている根拠になります。

## 3. fresh-contextとruntime metadata

Codexの公開ソース [`multi_agents_spec.rs`](https://github.com/openai/codex/blob/main/codex-rs/core/src/tools/handlers/multi_agents_spec.rs) は、Multi-Agent V2の `agent_type`、`fork_turns`、`model`、`reasoning_effort` を定義しています。公開schemaに `fork_turns` がある面では、`fork_turns="none"` が親の履歴を渡さないfresh-context routeです。

custom role名、task名、nickname、静的設定は、実効モデルの証拠ではありません。受理する調査結果は、利用可能なchild session metadataで次を確認します。

```text
thread_source = subagent
model         = gpt-5.6-luna
effort        = medium
```

古いタスクは起動時のmodel allowlistを保持することがあります。設定またはcatalogを変更した後の確認は、Codexを再起動したfresh task / fresh processで行います。

## 4. 専用カタログ回避策の根拠と限界

公式に確認できる要素は次の2点です。

1. `model_catalog_json` で起動時のモデルカタログを指定できる。
2. Lunaをsubagent modelとして設定できる。

今回の回避策は、この2点と公開issueのV1/V2不一致を組み合わせ、公式キャッシュのコピーにあるLunaエントリだけを `v1` から `v2` へ変更します。

次は公式に確認できないため、明確に非主張とします。

- OpenAIがこの書き換えをサポートまたは推奨している。
- すべてのアカウント、workspace、OS、Codex versionで動作する。
- custom catalogの静的設定だけでchildの実効モデルを証明できる。
- direct CLIのLuna成功がnative child threadのLuna成功と同じである。

## 5. 安全条件

- 公式 `models_cache.json` を直接編集しない。
- `config.toml`、custom agent file、コピー元catalogを事前にバックアップし、SHA-256を記録する。
- 専用catalogはコピー元とsemantic comparisonし、Luna `v1` → `v2` 以外の差分がないことを確認する。
- direct Lunaが失敗する環境では回避策を適用しない。
- Codex更新後は公式catalogを再確認し、修正済みなら `model_catalog_json` を外す。
- custom catalogは作成時点のモデル一覧を固定するため、必要なら最新公式cacheから再生成する。
- 復元後もfresh processでcatalogとnative child runtimeを再確認する。

実際のPowerShell手順とrollbackは [Luna Desktop V2 compatibility workaround](../luna-desktop-v2-workaround.md) に分離しています。

## 6. 2026-08-10のruntime evidence

検証したWindows環境:

```text
Codex Desktop  26.803.5235.0
Codex CLI      0.147.0-alpha.6.5
before         native spawn_agent => Sol / Terra only
direct Luna    success
custom catalog only semantic change => Luna v1 to v2
fresh child    thread_source=subagent
fresh child    model=gpt-5.6-luna
fresh child    effort=medium
fresh child    multi_agent_version=v2
```

この調査ノートを作成したbackground research hierarchyも、永続session metadataでroot `gpt-5.6-luna / high / v2`、child `thread_source=subagent / gpt-5.6-luna / medium / v2` を確認しました。raw thread ID、rollout全文、個人パスは公開していません。

この記録は当該日・当該環境の観測値です。将来のCodex releaseや他のworkspaceへ一般化せず、利用時に再検証してください。
