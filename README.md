# Luna Research Prompt for Codex

Codex のネイティブなサブエージェントを **GPT-5.6 Luna** で動かし、一次資料・反証・抜け漏れ確認を分担するための、自己完結したコミュニティ製プロンプトです。

インストーラー、Python、plugin、marketplace、MCP は使いません。必要なのは `config.toml` の設定と [`PROMPT.md`](PROMPT.md) だけです。

> [!IMPORTANT]
> このリポジトリは OpenAI 公式製品ではありません。Codex の設定名、モデルの提供状況、サブエージェント機能は将来変わる可能性があります。

## 使い方

### 1. `config.toml` を編集する

Codex のユーザー設定ファイルを開きます。

- Windows: `%USERPROFILE%\.codex\config.toml`
- macOS / Linux: `~/.codex/config.toml`

既存の `[agents]` セクションへ次の4項目を追加または統合してください。

```toml
[agents]
enabled = true
max_concurrent_threads_per_session = 40
default_subagent_model = "gpt-5.6-luna"
default_subagent_reasoning_effort = "medium"
```

`[agents]` がすでにある場合、同じ見出しをもう1つ作らず、その中の値を更新します。`40` は同時に40件起動する指定ではなく、1セッションで開いておける子タスクの上限です。実際のプロンプトは小さな wave で起動します。

> [!WARNING]
> この既定値は研究専用ではありません。モデルを個別指定していない通常のサブエージェントは、ほかのタスクでも Luna になります。Luna を利用できないアカウントや実行環境では、この設定だけで利用可能になるわけではありません。

### 2. Codex を再起動する

設定を読み直すため、Codex を再起動するか新しいタスクを開始します。

### 3. プロンプトを貼る

[`PROMPT.md`](PROMPT.md) のコードブロック全体をコピーし、末尾の `RESEARCH REQUEST` を自分の質問に書き換えて Codex に貼り付けます。

これだけです。プロンプトは Codex のネイティブな subagent runner を使い、利用可能な実行面では独立した Luna scout を並列に動かします。

プロンプトは設定ファイルを編集せず、Skill、plugin、checker、helper script も生成・インストールしません。

## `config.toml` とプロンプトの役割

`config.toml` は、明示的なモデル指定を持たない子エージェントの既定モデルと推論強度を設定します。調査の分解、証拠形式、反証枠、統合手順は `PROMPT.md` が担当します。

つまり、設定だけでは調査 workflow は生えません。一方、プロンプトだけを別環境へ持っていった場合も best-effort で動きますが、その環境にサブエージェント機能や Luna がなければ、Luna 実行を名乗らず root-only fallback として報告します。

## 保証の境界

- 個別 spawn の明示モデルや custom agent の設定は、`[agents]` の既定値より優先されます。
- task name や nickname は、実際のモデルを証明しません。
- 実行メタデータを確認できない環境では、プロンプトは「Luna 未検証」と明記します。
- Web、MCP、外部サービス、ファイル変更、公開、購入などの権限は、この設定やプロンプトによって拡張されません。
- ChatGPT の通常チャットなど、Codex の `config.toml` と subagent runner を持たない環境では同じルーティング保証はありません。

設定項目の現在の定義は Codex の [Configuration Reference](https://learn.chatgpt.com/docs/config-file/config-reference) と [Subagents](https://learn.chatgpt.com/docs/agent-configuration/subagents) を確認してください。

## 旧 plugin 版

Python installer と3つの Skill を含む旧版は、Git 履歴と [`v0.3.0`](https://github.com/dj-thank/luna-research-skills/releases/tag/v0.3.0) に保存されています。main ブランチの v1.0 以降は prompt-first です。

## License

[MIT](LICENSE)
