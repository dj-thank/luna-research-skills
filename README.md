# Luna Research Skills

Codex の通常サブエージェントを **GPT-5.6 Luna** に固定して広範調査を行い、各子タスクの実行メタデータまで検証する、コミュニティ製の skills-only plugin です。

This community skills-only plugin safely pins fresh ordinary Codex subagents to **GPT-5.6 Luna**, then verifies each accepted scout from runtime metadata during diverse research.

## 1つのプロンプトから、6〜20件の調査タスクを動かす

セットアップは最初の1回だけです。以後は調べたいテーマを**1つのプロンプトで頼むだけ**。親エージェントが問いを重ならない小さなテーマへ分解し、標準的な深掘りなら **6〜10件**、徹底調査なら **12〜20件**の調査タスクを Luna のサブエージェントへ割り当てます。

短い依頼でも始められます。

```text
$run-diverse-luna-research AIコーディングエージェント市場を一次資料中心に徹底調査して
```

観点や欲しい成果物も、同じ1つのプロンプトで細かく指定できます。

```text
$run-diverse-luna-research 2025〜2026年のAIコーディングエージェント市場を、
公式仕様・価格・ベンチマーク・セキュリティ・導入事例・反証の観点から
一次資料中心に調べ、意思決定向けの比較表と引用付き結論にまとめて
```

> **入力は1回。** 内部では一次資料、反証、地域・時系列、欠落証拠を別々のサブエージェントが並行して分担し、最後に親エージェントが原典を再確認して1本のレポートへ統合します。

```mermaid
flowchart TD
    P["1つのプロンプト<br/>調べたいことを一度伝える"] --> C["親エージェント<br/>問いを重ならないテーマへ分解"]
    C --> F["6〜20件の調査タスク<br/>各観点に複数の担当"]
    F --> A["一次資料担当<br/>公式文書・原論文"]
    F --> B["反証担当<br/>弱点・矛盾・否定的証拠"]
    F --> D["網羅性担当<br/>地域・時系列・専門領域"]
    F --> G["抜け漏れ担当<br/>欠落証拠・測定品質"]
    A --> V["モデル検証<br/>採用する全員が GPT-5.6 Luna か確認"]
    B --> V
    D --> V
    G --> V
    V --> R["親エージェントで再検証<br/>原典確認・重複排除・信頼度調整"]
    R --> O["1本の最終レポート<br/>引用・比較・矛盾・不明点・結論"]
```

特に、技術動向や文献の横断調査、競合・市場比較、製品選定、政策比較、デューデリジェンスのように、**一人で検索すると視点が偏りやすい調査**に向いています。全タスクのうち、一次資料確認と反証確認にそれぞれ20%以上を割り当てます。

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

### One prompt launches 6-20 verified research tasks

After the one-time setup, give Codex one research prompt. The root coordinator splits it into distinct questions and delegates **6-10 focused research tasks** for a standard deep dive or **12-20** for an exhaustive investigation. Separate Luna subagents cover primary sources, adversarial evidence, domain or regional perspectives, and missing evidence; the root then reopens conclusion-grade sources and produces one cited report.

Start with a short request:

```text
$run-diverse-luna-research Thoroughly research the AI coding-agent market using primary sources.
```

Or specify the perspectives and output you want in the same prompt:

```text
$run-diverse-luna-research Compare the 2025-2026 AI coding-agent market using
official specifications, pricing, benchmarks, security evidence, adoption cases,
and adversarial findings, then produce a decision-ready table and cited conclusion.
```

Every accepted scout passes the Luna runtime gate shown above. At least 20% of the assignment budget targets primary-source verification and at least 20% targets adversarial or disconfirming evidence.

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
