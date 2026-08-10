# Luna Desktop V2 compatibility workaround

> Status: community workaround, verified on one Windows environment on 2026-08-10. This is not an OpenAI-supported fix.

Codex Desktop / CLI の一部では、トップレベルのモデルとして `gpt-5.6-luna` を利用できても、native Multi-Agent V2 の `spawn_agent` が次のように拒否することがあります。

```text
Unknown model gpt-5.6-luna for spawn_agent.
Available models: gpt-5.6-sol, gpt-5.6-terra
```

OpenAI の [Subagents ドキュメント](https://learn.chatgpt.com/docs/agent-configuration/subagents) は、Lunaを高速で範囲の狭い反復・大量処理向けのsubagentモデルとして案内し、custom agent fileの `model` / `model_reasoning_effort` と `[agents].default_subagent_model` を説明しています。[Configuration Reference](https://learn.chatgpt.com/docs/config-file/config-reference) は、起動時に読み込むJSONモデルカタログを `model_catalog_json` で指定できることを説明しています。

一方、公開 issue [#35097](https://github.com/openai/codex/issues/35097) では、Lunaがモデルカタログ上でMulti-Agent V1として扱われ、V2 `spawn_agent` の候補から除外される事象が報告されています。同じ `Sol / Terra only` の症状は [#34399](https://github.com/openai/codex/issues/34399) と [#34964](https://github.com/openai/codex/issues/34964) にもあります。

この文書の回避策は、公式 `models_cache.json` を直接編集しません。その時点のキャッシュを専用ファイルへコピーし、コピー側のLunaエントリだけを `v1` から `v2` へ変更して、`model_catalog_json` から明示的に読み込みます。

## 適用条件

次のすべてを満たす場合だけ検討してください。

1. 新しいCodexタスクでも同じエラーが出る。
2. Codexを安全に再起動し、更新を確認しても再現する。
3. `codex debug models` には `gpt-5.6-luna` が存在する。
4. direct CLI probeではLunaが応答する。
5. native `spawn_agent` だけがSol / Terra allowlistで拒否する。

direct probeの例です。これはnative child threadの証拠ではなく、Luna自体の利用可能性だけを確認します。

```powershell
codex exec --model gpt-5.6-luna --sandbox read-only --skip-git-repo-check `
  "Reply with exactly: LUNA_DIRECT_OK"
```

direct probeも失敗する場合、この回避策を適用しないでください。アカウント、workspace、クライアント、サービス側の提供状況を確認します。

## 1. Codexを終了してバックアップする

実行中タスクを保存または完了してからCodex Desktopを完全に終了します。モデルキャッシュはアプリが自動更新するため、コピー中の競合を避けます。

Windows PowerShellの例です。

```powershell
$codexRoot = Join-Path $env:USERPROFILE '.codex'
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$backupDir = Join-Path $codexRoot "backups\luna-v2-$stamp"
$cachePath = Join-Path $codexRoot 'models_cache.json'
$configPath = Join-Path $codexRoot 'config.toml'
$customPath = Join-Path $codexRoot 'models_catalog_luna_v2.json'

New-Item -ItemType Directory -Path $backupDir | Out-Null
Copy-Item -LiteralPath $cachePath -Destination (Join-Path $backupDir 'models_cache.json.source')
Copy-Item -LiteralPath $configPath -Destination (Join-Path $backupDir 'config.toml.before')

$defaultAgent = Join-Path $codexRoot 'agents\default.toml'
if (Test-Path -LiteralPath $defaultAgent) {
  Copy-Item -LiteralPath $defaultAgent -Destination (Join-Path $backupDir 'default.toml.before')
}

Get-ChildItem -LiteralPath $backupDir -File |
  Get-FileHash -Algorithm SHA256 |
  Select-Object Path, Hash
```

## 2. 専用カタログを作る

次の処理は、バックアップしたソースを読み、Lunaエントリがちょうど1件で現在値が `v1` であることを確認してから専用カタログを書き出します。公式キャッシュは変更しません。

```powershell
$sourcePath = Join-Path $backupDir 'models_cache.json.source'
$catalog = Get-Content -LiteralPath $sourcePath -Raw -Encoding UTF8 | ConvertFrom-Json
$luna = @($catalog.models | Where-Object { $_.slug -eq 'gpt-5.6-luna' })

if ($luna.Count -ne 1) {
  throw "Expected one gpt-5.6-luna entry; found $($luna.Count)."
}
if ($luna[0].multi_agent_version -ne 'v1') {
  throw "Expected Luna multi_agent_version v1; found $($luna[0].multi_agent_version). Recheck whether the workaround is still needed."
}

$luna[0].multi_agent_version = 'v2'
$json = $catalog | ConvertTo-Json -Depth 100
$utf8NoBom = New-Object System.Text.UTF8Encoding -ArgumentList $false
[System.IO.File]::WriteAllText($customPath, $json, $utf8NoBom)
```

意図した変更だけか、バックアップを基準にsemantic diffを確認します。

```powershell
$baseline = Get-Content -LiteralPath $sourcePath -Raw -Encoding UTF8 | ConvertFrom-Json
$candidate = Get-Content -LiteralPath $customPath -Raw -Encoding UTF8 | ConvertFrom-Json
$candidateLuna = @($candidate.models | Where-Object { $_.slug -eq 'gpt-5.6-luna' })

if ($candidateLuna.Count -ne 1 -or $candidateLuna[0].multi_agent_version -ne 'v2') {
  throw 'Custom catalog does not contain exactly one Luna v2 entry.'
}

$candidateLuna[0].multi_agent_version = 'v1'
$baselineJson = $baseline | ConvertTo-Json -Depth 100 -Compress
$candidateJson = $candidate | ConvertTo-Json -Depth 100 -Compress

if ($baselineJson -cne $candidateJson) {
  throw 'The custom catalog contains changes other than Luna v1 to v2.'
}
```

## 3. `config.toml` から専用カタログを指定する

`config.toml` のトップレベルへ、実際の絶対パスを指定します。TOMLのsingle-quoted literal stringならWindowsのバックスラッシュを二重化する必要はありません。

```toml
model_catalog_json = 'C:\Users\YOUR_NAME\.codex\models_catalog_luna_v2.json'
```

既存の `[agents]` テーブルがある場合は、新しい見出しを増やさず同じテーブル内を更新します。

```toml
[agents]
enabled = true
default_subagent_model = "gpt-5.6-luna"
default_subagent_reasoning_effort = "medium"
```

custom `default` agentを利用している場合、そのagent fileの `model` は `[agents]` の既定値より優先されます。既存ファイルをバックアップした上で、次の値も確認してください。

```toml
model = "gpt-5.6-luna"
model_reasoning_effort = "medium"
```

## 4. fresh processで検証する

Codex Desktopを再起動し、新しいタスクを作成します。古いタスクは起動時のmodel allowlistを保持している場合があるため、設定反映の判定には使いません。

まずカタログを確認します。

```powershell
$models = codex debug models | ConvertFrom-Json
$models.models |
  Where-Object { $_.slug -in @('gpt-5.6-sol', 'gpt-5.6-terra', 'gpt-5.6-luna') } |
  Select-Object slug, multi_agent_version
```

次に、fresh-contextのdefault subagentへ固定文字列を返させます。現在の `spawn_agent` schemaに存在する引数だけを使い、`fork_turns="none"` があればそれを、別世代で `fork_context=false` が公開されていればその経路を使います。

成功判定はnicknameやtask名ではなく、child sessionのruntime metadataで行います。

```text
thread_source = subagent
model         = gpt-5.6-luna
effort        = medium
```

2026-08-10のWindows検証では、Codex Desktop `26.803.5235.0`、CLI `0.147.0-alpha.6.5` において、変更前のnative `spawn_agent` はSol / Terraのみを許可しました。専用カタログを読み込んだfresh CLI processからdefault childを起動すると、child rolloutの `turn_context` で `gpt-5.6-luna / medium`、Multi-Agent `v2` を確認できました。これは1環境の観測結果であり、全アカウントや将来版を保証しません。

## 更新と復元

専用カタログは作成時点のモデル一覧を固定します。Codex更新後は、まず公式カタログでLunaがV2対応になったか確認してください。

- 公式側で修正済みなら、`config.toml` の `model_catalog_json` を削除し、専用カタログを外します。
- まだ必要なら、最新の公式キャッシュから専用カタログを作り直し、semantic diffを再確認します。
- バックアップ後に `config.toml` を変更していない場合は、`config.toml.before` を復元できます。
- バックアップ後に別設定を変更した場合は、ファイル全体を上書きせず `model_catalog_json` とLuna関連値だけを手動で戻します。

復元後もCodexを再起動し、新しいタスクでmodel catalogとnative spawnを確認してください。

## 非主張

- OpenAIがこの `v1` から `v2` の書き換えを公式回避策として推奨している、とは主張しません。
- direct CLIのLuna成功だけでは、native child threadのLuna成功を証明しません。
- custom catalogの静的設定だけでは、childの実効モデルを証明しません。
- この手順はモデル権限、課金、workspace policy、sandbox、外部サービス権限を変更しません。

一次情報の整理は [research note](research/luna-desktop-routing-2026-08-10.md) を参照してください。
