# Luna Hierarchical Skills 2.0

このリポジトリは、Codex のネイティブ subagent を使う調査・開発・監査・移行・リリース作業のための、repository-scoped Skill、optional custom-agent definition、安全な発見・移行ツール、再現可能なrelease assetsを収録します。GitHubをCodex cloudのenvironmentへ接続した場合も、リポジトリrootの公式配置からSkillを発見できます。Luna は、**高速・効率的な高ボリューム fan-out** と、複数の bounded assignment を同時に処理する用途に向きます。ただし、モデル、spawn schema、同時実行上限、利用可能な機能は Codex のsurface・アカウント・workspace・cloud environmentごとに異なります。

canonical source package はこのリポジトリの `.agents/skills/` と `.codex/agents/` です。前者はrepository-scoped Skillです。後者はlocal Codex client向けのoptional project-scoped custom agent sourceであり、repositoryに存在するだけではCodex Cloudでactiveになった証拠になりません。実際に有効なのは、現在のsurfaceが発見・公開したコピーとrouteです。README、静的設定、Git tag、過去の観測記録だけでは、そのセッションでのruntime proofになりません。

## Canonical package layout

source package と公式 user-scope の対応は次のとおりです。

```text
.agents/skills/run-diverse-luna-research/  ->  $HOME/.agents/skills/run-diverse-luna-research/
.agents/skills/run-diverse-luna-project/   ->  $HOME/.agents/skills/run-diverse-luna-project/
.codex/agents/*.toml                       ->  $HOME/.codex/agents/*.toml
```

`$HOME/.agents/skills` が現在の公式 user-scope Skill path です。既存ビルドが `$HOME/.codex/skills` を実際に発見している環境では、fresh task で新pathの発見を確認するまでworking legacy copyを消さないでください。両pathやrepository scopeに同名Skillが見える場合、異なるhashはhard stopです。完全なpackage manifestがbyte-identicalならmigration/repository overlapとして全rootと実際に選ばれたpathを記録できますが、可能な限り冗長scopeを無効化します。restart後にprojectless taskとrepository内taskの双方で明示呼出しを確認し、credential、provider、公開操作はインストール検証と分離します。

公式の背景資料: [Subagents](https://learn.chatgpt.com/docs/agent-configuration/subagents) / [Build skills](https://learn.chatgpt.com/docs/build-skills) / [Codex cloud](https://learn.chatgpt.com/docs/cloud)。

## Quick start

用途を先に選びます。

```text
$run-diverse-luna-research 現行仕様を一次資料・反証・測定品質の観点で調査し、証拠パケットだけ返して
$run-diverse-luna-project この機能を調査、実装、テスト、独立レビュー、リリース準備まで進めて
```

- 成果物が証拠・fact-checkだけなら `research`。
- code、artifact、test、migration、integration、release、operationsを一つでも含むなら `project`。
- 狭い一問、一ファイルの小修正、同じmutable stateしか触れない作業には、この広域fan-outを使いません。

runtimeは、公開されているcustom roleを優先します。cloudや一部surfaceでcustom roleが見えない場合でも、live schemaが `worker`、explicit model/effort、fresh contextを公開していれば、Skillはbuilt-in `worker`を `gpt-5.6-luna` / `max` / `fork_turns="none"` に明示固定し、親spawn requestとcompleted child receiptの両方を検査します。親spawnの出力に返された子UUIDが含まれない場合はprovenanceを結べません。custom role名、task名、静的TOMLだけからLunaを推測することはありません。

## Release assets

各 `v*.*.*` GitHub Release は次を配布します。

- `luna-skill-vX.Y.Z.zip`: repository source snapshot。
- `luna-hierarchical-skills-X.Y.Z-plugin.zip`: root `.codex-plugin/plugin.json` と `skills/` を持つinstallable plugin bundle。custom-agent TOMLは含めず、上記のbuilt-in `worker` fallbackで可搬性を保ちます。
- `SHA256SUMS`: 両ZIPの固定SHA-256。
- `luna-skill-vX.Y.Z.spdx.json`: source inventoryのSPDX 2.3 SBOM。

`v2.0.3` 以降のReleaseはGitHubのImmutable releasesを有効にした状態で公開し、公開後のtag移動、asset変更・削除を禁止します。Release workflowはasset付き`gh release create`でdraft作成・全asset upload・publishを順番に行い、最後に`isImmutable=true`を検査します。`v2.0.4` 以降のbuilderはUTF-8 textをarchive内でLFへcanonicalizeし、同一source treeのWindows/macOS/Linux buildを同一bytesへ固定します。ダウンロード後も `SHA256SUMS` を照合してから展開または導入してください。source treeとplugin/user treeに同名Skillを同時に有効化するとselectorが重複します。通常は一scopeだけを使い、repository/user overlapが必要な場合はcomplete package hash一致とselected pathを記録します。

### Codex cloudで使う

1. GitHub上のこのリポジトリをCodex cloudへ接続し、対象branchのenvironmentを作成します。
2. リポジトリrootの`.agents/skills`はrepository scopeとしてclone時に含まれるため、user-scope installerは不要です。セットアップは通常`automatic`で十分です。
3. Pythonを使うenvironmentでは、通常の環境変数として`PYTHONUTF8=1`と`PYTHONDONTWRITEBYTECODE=1`を設定します。秘密値はsetupで本当に必要なものだけをSecretへ置き、通常の環境変数へコピーしません。
4. source-heavy researchが必要ならagent internetをenvironment単位で有効化します。全ドメイン・全methodは強い権限なのでtaskログを確認し、固定smoke以外でrepository bytes、環境変数、credentialを外部へ送信しません。
5. 既知の対象commit SHAをCloud taskへ渡し、次を実行します。Codex Cloudがcheckoutを一時branch `work`として表示しても、期待SHA一致とclean worktreeをprovenanceに使い、branch labelだけでは失敗にしません。

```bash
python tools/cloud_smoke.py \
  --expected-head '<selected commit SHA>' \
  --network \
  --iterations 25
```

`cloud_smoke.py`はGET/HEADに加え、`https://httpbin.org/post`へ固定文字列`codex_cloud_smoke=ok`だけをPOSTします。test/build/compileの書込みはOS temporary directoryへ隔離し、前後のGit treeがcleanでなければ失敗します。`pwsh`がないLinux CloudではPowerShell migration testを`not_run`として明示し、WindowsのPowerShell 7/5.1 GitHub Actions gateを代替証拠として残します。JSON verdictは最大でも`LOCAL_PASS`です。

6. 最初のcloud taskでは、Lunaによる実装・監査・移行・リリースなどを明示的に依頼した場合だけ`$run-diverse-luna-project`を選びます。証拠専用の調査は`$run-diverse-luna-research`を選び、Skill path、公開spawn schema、実効model/effort、permission modeを確認します。
7. 公式Subagents仕様でcustom-agent設定はlocal Codex clientの機能です。`.codex/agents`のcustom roleが現在のCloud surfaceに公開されない場合、Skillは存在しないroleを推測しません。explicit Luna/max/fresh-contextを持つbuilt-in `worker` routeと、親spawn出力に子UUIDを含むexact completed receiptが公開されていればそのrouteを検証付きで使用し、どれかが欠ければroot-onlyへfail closedします。
8. cloud environmentの秘密値、internet access、GitHub write権限はこのリポジトリに含まれません。必要な場合だけenvironment側で個別に設定し、provider/public/HUMAN gateと分離します。

Codex cloudはGitHub repositoryを接続して分離環境でtaskを実行し、結果をreviewしてからPRへ進める仕組みです。このリポジトリを接続しただけでinstaller、provider操作、公開、外部送信が自動実行されることはありません。

### 安全な導入順序

1. [`tools/Test-LunaSkillDiscovery.ps1`](tools/Test-LunaSkillDiscovery.ps1) で、legacy/user/repository scope、同名Skill、hash、custom-agent設定を読み取り専用で確認します。
2. [`tools/Test-LunaMigrationTools.ps1`](tools/Test-LunaMigrationTools.ps1) に `-Source .agents/skills` を渡し、discovery/installerの構文、dry-run、`-WhatIf`、OS-temp real apply、単一snapshot/hash照合、atomic journal、partial failure、排他的target lock、root/nested/staging reparse point拒否、非再帰cleanupを検査します。実user scopeは変更しません。
3. [`tools/Install-LunaSkillsUserScope.ps1`](tools/Install-LunaSkillsUserScope.ps1) に `-Source .agents/skills` を渡して`-Apply`なしで実行し、公式user-scopeへ置かれるpackageとhashを確認します。`-Apply`が非対話実行でも使える明示的な変更承認で、追加の対話確認が必要な場合は`-Confirm`を付けます。`-Apply -WhatIf`は非変更です。real applyでは、同じowner境界にdurable journalを先に作り、排他的lock下で各atomic moveの前後を再検査し、既存manifest・既存package・任意pathを上書きしません。失敗時のnon-empty stageは再帰削除せずjournalのexact pathに保存します。
4. 現在動いている `$HOME/.codex/skills` copyは、fresh taskで公式pathの発見を証明するまで消しません。同名の二重配置が検出された場合は適用を止めます。
5. custom-agent TOMLは既存 `$HOME/.codex/agents` をバックアップ・比較し、同名fileを上書きせずに導入します。Skill installerはagent設定を変更しません。
6. Codexを再起動し、projectless taskとrepository内taskの双方で、明示的なSkill invocation、custom roleの公開有無、Luna/mediumのcompleted runtime receiptを確認します。

詳しい証拠境界とrollbackは [`tools/MIGRATION.md`](tools/MIGRATION.md) にあります。scriptsはlegacy root、設定、credential、providerを変更せず、Skill packageのreal applyは別の明示操作です。

各Skillは自己完結した `scripts/check_setup.py` とfailure-injection testsを含みます。static parseや設定一致だけでruntimeを合格にはせず、v2 ledgerではtree-wide `N/C/W/V`、計画段階のbudget、depth、親子call、coordinator収集、retry、timeout/deadline、未完了状態、accepted child receiptを検査します。期限後に開始またはacceptedになった結果は拒否し、未dispatchのprivate/provider cellは `not_dispatched/excluded` と明示gapで閉じます。research ledgerはさらに、一次情報・反証の各20% quota、測定/欠損cell、重複coverage、priority accepted-or-gapを検査します。

## どの Skill を選ぶか

- `run-diverse-luna-research`: 文献レビュー、比較、一次資料確認、反証、測定品質など、主目的が research の案件。
- `run-diverse-luna-project`: 実装、監査、移行、リリース、複数成果物など、research 以外の作業も含む mixed project。

どちらも、依頼に合わせて小さな flat wave または階層型 wave を選びます。全案件で階層を強制するものではありません。

発見確認後は、任意のprojectless taskまたはrepository内taskから明示的に呼び出せます。両Skillは自動発見可能ですが、researchは証拠専用のまま、projectはユーザーがLunaによる実装・監査・移行・リリース等を明示的に依頼した場合だけdeliveryを所有します。Luna指定のないmixed deliveryは、現在のcaller workflowへpacketを返し、曖昧ならroot-onlyで分類を確定します。これにより、証拠収集とdeliveryの境界を保ったまま、暗黙選択の競合を避けます。

```text
$run-diverse-luna-research 直近仕様を一次資料・反証・測定品質の観点で調査して
$run-diverse-luna-project この機能を調査、実装、テスト、独立レビューまで進めて
```

両descriptionは、狭く安定した一問、単一ソースの順次確認、小さな一修正、共有mutable stateを分割できない作業を除外します。つまり、幅広い独立セルがある案件には自動適用できますが、projectのdelivery所有には明示的なLuna依頼が必要で、何でも無条件にfan-outする設定ではありません。確実に選びたい場合は上の `$run-diverse-luna-*` を明示します。

## Hierarchical fan-out / fan-in

標準的な階層は `root → coordinator → 4–8 leaf` です。root は契約、予算、境界、最終検証を所有し、coordinator は重複しない bounded cell を leaf へ分配し、leaf は証拠または成果物を返します。coordinator が統合した結果を root が再確認して fan-in します。

```mermaid
flowchart TD
  R["root: contract・budget・final verification"]
  C["coordinator: bounded cells・ledger"]
  L1["leaf 1"]
  L2["leaf 2"]
  L3["leaf 3"]
  L4["leaf 4 … 8"]
  F["fan-in: evidence packet / deliverables"]
  R --> C
  C --> L1
  C --> L2
  C --> L3
  C --> L4
  L1 --> F
  L2 --> F
  L3 --> F
  L4 --> F
  F --> R
```

### Flat と hierarchy

- **Flat**: root が leaf を直接並列化。小さな問い、均質な cell、低い統合コストに向く。
- **Hierarchy**: coordinator が 4–8 leaf を束ねる。異なる専門性、複数成果物、独立した反証、明確な fan-in がある案件に向く。

hierarchy は深さや起動数を自動で保証しません。必要性、重複しない所有範囲、停止条件を先に定め、runtime の公開 schema に存在する引数だけを使います。特定の recursive probe や route を必須条件にせず、native route が使えない場合は flat または root-only として報告します。

## 共通ポリシー: N / C / W / V / depth 2

実行開始前に、root が全階層共通の台帳を作ります。

- `N` — 全tree共通の assignment-attempt 総予算。coordinator、leaf、probe、retry、verifier、拒否・失敗を含める。目安は focused 4–8、broad 8–16、large/deep 16–32。32–64は十分な独立性と実測headroomがある例外だけ。
- `C` — 全descendantを含む同時実行capacity。現在のlive/config上限以下にする。設定値はceilingであり、実効throughputの保証ではない。
- `W` — 一waveで開始する全attempt数。`W <= min(C,N)`。広い作業では8–16を標準候補とし、17–32は低重複・十分な予算・rate-limit headroomを実測した場合だけ。
- `V` — optional fan-outが使えない verifier/contradiction reserve。`max(1, ceil(0.15*N))` を確保する。
- `depth 2` — root=0、coordinator=1、leaf=2 を論理上の上限とする。leaf はさらに委任しない。より深い階層はこの配布資料の既定ではなく、明示的な設計・検証が必要。

N/C/W/V はモデル性能やplatform既定値の保証ではありません。この配布物のchecker、台帳、実際のruntime metadataを照合し、未使用予算を返し、完了条件を満たさない結果をacceptedにしないでください。

## Runtime receipt と証拠の境界

Luna を名乗るには、task 名や nickname ではなく、公開されている runtime receipt の `thread_source`、実効 `model`、`reasoning effort` などを確認します。receipt が得られない場合は `Luna unverified` または root-only と扱います。静的設定、README、過去の日付付き observation、health response、公開 repository は runtime proof ではありません。

root は最終回答・成果物の single writer です。child/coordinator は担当範囲の evidence packet と ledger を返し、root が一次資料、差分、テスト、受入条件を再確認してから統合します。外部 API、provider、公開、送信、購入、削除、認証、デプロイなどの external gate は、実際の receipt と明示的な人間の承認が揃うまで未実施として扱います。

## 互換性と安全な縮退

現行の `spawn` schema に `model` / `reasoning_effort` や fresh-context 指定が公開されている場合だけ使用します。存在しない引数や非公開設定を推測して追加・変更しません。Luna が候補にない、metadata が見えない、または route が拒否されたときは、設定を改変せず、flat / root-only fallback と理由を ledger に残します。

過去の配布文書や補助実装を現行 Skill の代わりに再導入しないでください。履歴上の文書は Git tag（例: `v0.3.0`）に保存されています。

## Contributing and history

変更時は [CONTRIBUTING.md](CONTRIBUTING.md)、[SECURITY.md](SECURITY.md)、[CHANGELOG.md](CHANGELOG.md) を確認してください。日付付きの旧回避策、削除済みprompt、plugin-era実装はGit historyとtagにだけ保存します。現在のcanonical Skillと矛盾する履歴を新しい実装としてコピーしないでください。

## License

[MIT](LICENSE)
