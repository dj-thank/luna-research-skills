# 2026-10-14 compatibility checks

この記録は、公開スキルの変更を支える確認範囲を説明します。個人のファイルパス、ユーザー名、thread UUID、raw rollout、認証情報は収録しません。

## 実行して確認したこと

Windows の Codex desktop（native V2）で、次の共通経路を実行しました。

1. 組み込み `default` 役割へ `model="gpt-6.1-sol"`、`reasoning_effort="low"`、`fork_turns="none"` を明示。
2. 担当が Research の単一の公式資料確認と、Project の適用条件の分類を行い、完了。
3. 親が完了した初回 turn、実際のモデル・推論強度、親の起動記録、子との対応を取得。
4. 両スキルのチェッカーで同じ実記録を照合し、受理。
5. 独立した互換性レビューを行い、V2 が通常の実行へ追加条件にならないよう修正して再確認。

確認された実効サンドボックスは `workspace-write` でした。担当に変更を求めない範囲で実行しましたが、技術的な読み取り専用とは表現しません。後続の再確認は native `followup_task` の結果として扱い、初回起動の証明を後続 turn に流用していません。

## ローカルの回帰検査

| 検査 | Research | Project |
|---|---:|---:|
| 設定・schema・実行記録・台帳の検査 | 166件 | 166件 |
| 分業試行予算の検査 | 9件 | 9件 |

上の表は導入済みスキルの実行結果で、合計350件が通過しました。GitHub 公開版では workspace 設定にも同時上限6を適用し、上限6の受理・7以上の拒否を確認するケースを各スキルに1件追加しました。公開版は設定検査167件＋予算検査9件を各パッケージで実行し、合計352件が通過しました。公開版と導入済み版の追加差分は、このガードと回帰ケースです。公開版の2つのパッケージの checker / test コピーは一致しています。Skill Creator の形式検証も両スキルに対して通過しました。

これらのテストは、拒否すべき入力、モデル・親子関係の不一致、予算超過などの**合成ケース**です。全ケースが実際のモデルを起動するテストではありません。repository 側では、両 dispatch suite の CI・stress・Cloud smoke への包含、欠落・片側改変の拒否、配布物への包含を検査します。[開発・検証手順](../CONTRIBUTING.md)

## 今回、実行していないもの

- 多数の出典を使う Research 全体の完了
- 大きな Project 全体の実装・統合・closure
- 入れ子の調整役による再帰起動
- Windows 以外での live Codex 起動
- さまざまな依頼での暗黙のスキル選択
- 速度、費用、消費枠の削減率

標準の `default` 初回 turn で動いたことを、すべての役割・モデル・環境への保証へ広げません。利用する環境の live tool declaration と、実際に完了した子の記録を各実行で確認してください。

## Windows の表示差

同じ端末でも、通常ユーザーとサンドボックス内で Python、PATH、読める依存パッケージ、CLI の設定表示が異なることを確認しました。設定と表示が食い違う場合は、現在のチャットと別プロセスの結果を区別します。V2 を有効にしたという保存設定だけでも、別 CLI の表示だけでも、現在の子の実行を証明しません。[環境の確認手順](../.agents/skills/run-diverse-luna-research/references/environment-check.md)

## 公式仕様との境界

スキルの選択・読み込み、サブエージェントの設定は [Codex の公式仕様](https://learn.chatgpt.com/docs/agent-configuration/subagents)と[スキルの仕様](https://developers.openai.com/plugins/concepts/skills)を参照します。Sol / low の固定、N/C/W/V、実行記録のチェッカーは、このリポジトリの作業方針です。
