# Luna Research Skills

Codex の通常サブエージェントを **GPT-5.6 Luna** に固定して広範調査を行い、各子タスクの実行メタデータまで検証する、コミュニティ製の skills-only plugin です。

This community skills-only plugin safely pins fresh ordinary Codex subagents to **GPT-5.6 Luna**, then verifies each accepted scout from runtime metadata during diverse research.

> [!IMPORTANT]
> このリポジトリは OpenAI 公式製品ではありません。2026-07-17 時点の Codex の挙動を利用しており、モデル名やサブエージェントのルーティング仕様は将来変わる可能性があります。

## 日本語

### 何を解決するか

公開 Skill の manifest には、`spawn_agent` ごとのモデルを直接指定する項目がありません。この plugin は次の三段階で、その制約を回避せずに検証可能な形へ落とします。

1. `~/.codex/agents/default.toml` に Luna 固定の default role を安全に導入する。
2. 通常の `spawn_agent` を必ず `fork_turns="none"` で起動し、その role を選ばせる。
3. 各 child rollout の `turn_context.model` が `gpt-5.6-luna` であることを確認してから、調査結果を採用する。

名前や nickname をモデルの証拠にはしません。実行メタデータが証拠です。

### インストール

必要条件は Python 3.11 以上と、plugin marketplace に対応した現在の Codex です。公開リポジトリの読み取りに GitHub ログインは不要です。

```bash
codex plugin marketplace add dj-thank/luna-research-skills
codex plugin add luna-research-skills@luna-research-skills
```

その後、新しい Codex タスクを開始してください。CLI ラッパーが利用できない環境では、ChatGPT デスクトップの Codex で Plugins を開き、marketplace と `Luna Research Skills` を選択してインストールできます。

### 使い方

最初に、明示呼び出し専用の設定 Skill を使います。

```text
$configure-luna-subagents
```

Skill はまず read-only の plan を表示します。実適用では次の設定を行います。

- `features.multi_agent = true`
- `agents.max_threads = 40`
- `agents.max_depth = 2`
- `agents/default.toml` の `model = "gpt-5.6-luna"`

既存値が衝突する場合は停止し、承認された replacement flag がある時だけ変更します。変更前ファイルは `CODEX_HOME/backups/luna-research-skills/` に保存され、書き込みは原子的です。

Codex を再起動するか新しいタスクを開いた後、調査 Skill を使います。

```text
$run-diverse-luna-research 量子誤り訂正の最新アプローチを一次資料中心に比較して
```

この Skill は最初の有用な scout を runtime probe として使い、Luna が確認できた場合だけ次の wave を開始します。以後も採用する全 scout を検証します。

### 重要な影響範囲

`agents/default.toml` は研究専用ではなく、`fork_turns="none"` で default role を選ぶ全ての通常サブエージェントに作用します。親の履歴を丸ごと継承する fork、CSV 一括 fan-out、内部エージェント、別の custom role はこの保証範囲に含まれません。

復元する場合は、明示的に次を依頼します。

```text
$configure-luna-subagents を使って設定を復元して
```

管理後に対象ファイルが編集されていた場合、復元は停止してその編集を保護します。

### 検証

```bash
python -m unittest discover -s tests -v
python -m compileall -q plugins
```

テストは Linux / Windows、Python 3.11 / 3.13 の GitHub Actions でも実行します。互換性の根拠と既知の境界は [docs/verification.md](docs/verification.md) にまとめています。

## English

### Install

Require Python 3.11+ and a current Codex build with plugin marketplaces:

```bash
codex plugin marketplace add dj-thank/luna-research-skills
codex plugin add luna-research-skills@luna-research-skills
```

Then open a new Codex task. If the CLI wrapper is unavailable, install `Luna Research Skills` from the Plugins view in Codex.

### Use

Invoke `$configure-luna-subagents` explicitly. It shows a read-only plan, discloses the global default-role blast radius, and applies only after explicit authorization. Existing conflicting values require separate replacement flags and are backed up before atomic writes.

After restarting Codex or opening a new task, invoke `$run-diverse-luna-research` with the research question. The skill uses only ordinary `spawn_agent` calls with `fork_turns="none"`, verifies the first useful scout before fan-out, and validates every accepted scout's rollout metadata.

### Guarantee boundary

The plugin controls a user-level default agent role because the current public Skill/plugin manifest does not expose a per-spawn model selector. The guarantee covers fresh ordinary default-role subagents spawned with `fork_turns="none"`. It does not cover full-history forks, bulk CSV fan-out, internal agents, or other custom roles.

## License

[MIT](LICENSE). Security reports should follow [SECURITY.md](SECURITY.md).
