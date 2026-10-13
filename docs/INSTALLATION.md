# Installation and updates

このリポジトリの2つのSkillは、リポジトリ単位・ユーザー単位・pluginのいずれでも利用できます。最初に必要な範囲だけを選び、既存のSkillやCodex設定を暗黙に置き換えないでください。

## リポジトリ内だけで使う

```sh
git clone https://github.com/dj-thank/luna-research-skills.git
cd luna-research-skills
```

このディレクトリをCodexで開くと、`.agents/skills`のSkillがリポジトリスコープで読み込まれます。`.codex/agents`のカスタム役割は任意であり、利用可能かどうかは実行中のCodex surfaceで確認します。

## ユーザースコープへ新規導入する

Python 3.11以上を使い、リポジトリまたは展開したsource/plugin ZIPのルートで、まず変更を伴わないplanを確認します。macOS、Linux、Windowsで同じコマンドを使えます。

```sh
python tools/install_luna_skills.py
```

planに表示されたsource、target、Skill名、ファイル数を確認した後、明示的に適用します。

```sh
python tools/install_luna_skills.py --apply
python tools/install_luna_skills.py --verify
```

既定の配置先は公式のユーザースコープである `$HOME/.agents/skills` です。別の検証用ディレクトリへ入れる場合は `--target-root` を指定できます。

```sh
python tools/install_luna_skills.py \
  --target-root /path/to/disposable/.agents/skills \
  --apply
```

自動化では `--json` を付けると、plan・導入・検証の結果を1つのJSON objectとして受け取れます。

```sh
python tools/install_luna_skills.py --verify --json
```

### Python導入器の境界

- 既定動作はdry-runで、`--apply`がなければディスクを変更しません。
- 同名の配置先が存在する場合は、ファイル内容にかかわらず上書きしません。
- sourceとtargetの任意symlink、junction、reparse point、非regular file、サイズ上限超過、大小文字だけが異なるpath collisionを拒否します。macOS標準のroot-owned `/etc`・`/tmp`・`/var` aliasだけは、既知の `/private/...` 実体と一致する場合に限り許可します。
- source bytesを検査時にsnapshotし、各ファイルを新規作成専用で書き込みます。
- `SKILL.md`は全supporting fileの後に書き込み、途中状態がSkillとして見える時間を最小化します。
- 途中で失敗した場合、導入器自身が作成し、かつ内容が変わっていないpackageだけを巻き戻します。検出した別プロセスの追加・変更は削除せず、手動確認が必要なpathとして報告します。
- Skill packageだけを導入します。`.codex/agents`、親モデル、`~/.codex/config.toml`、provider設定は変更しません。

## 既存スキルを更新する

### 1. 取得元を更新する

この手順は macOS・Linux・Windows 共通です。clone したリポジトリのルートで、最初に現在の変更を確認します。

```sh
git status --short
```

出力がある場合は、その変更を別途保存するか、変更のない別の clone を取得して比較します。以下は**変更のない取得元**で実行します。merge conflict や fast-forward 不能が出たら、`reset --hard` で消さずに内容を確認してください。

```sh
git switch main
git pull --ff-only
```

Release ZIP を使っていた場合は、新しい main を別のフォルダーへ clone します。Release は固定した版なので、古い ZIP の中身は自動更新されません。

### 2. 実際の導入先を確認して比較する

リポジトリ内だけで使う場合は `.agents/skills` が更新済みです。このフォルダーを Codex で開き、新しいチャットで README の準備チェックへ進みます。

ユーザースコープへコピーしている場合は、導入器の plan で source と target を確認します。既定の導入先は、次のコマンドでも表示できます。

```sh
python tools/install_luna_skills.py
python -c "from pathlib import Path; print(Path.home() / '.agents' / 'skills')"
```

次は比較例です。`<導入先>` は上で確認したディレクトリへ置き換えます。差分があると `git diff --no-index` の終了コードは1になります。比較中にファイルは変更されません。

```sh
git diff --no-index .agents/skills/run-diverse-luna-research "<導入先>/run-diverse-luna-research"
git diff --no-index .agents/skills/run-diverse-luna-project "<導入先>/run-diverse-luna-project"
```

### 3. 保全してから、選んだコピーを更新する

1. 実際に使っている2つのフォルダーと、ローカルの独自変更をバックアップします。バックアップは `.agents/skills` や `.codex/skills` の外へ保存し、古いコピーがもう一つのスキルとして読み込まれないようにします。
2. 差分を確認し、公開版で置き換えるか、独自変更を新しい公開版へ手動で移すかを決めます。公開版全体で置き換える場合は、バックアップを確かめてから対象の2つだけを入れ替えます。他のスキルは触りません。
3. ファイルマネージャー等で、取得元の2つの package の全ファイルを導入先へ反映します。追加だけでなく削除されたファイルも確認します。Windows で権限・旧配置・移行 journal を維持する必要がある場合は、下の PowerShell 移行経路を使います。

Python 導入器は更新操作を自動化しません。`destination already exists` を解消するためだけに既存コピーを消して再実行しないでください。任意の `.codex/agents` 役割を別途導入済みの場合も、自分の設定を確認して更新します。スキルのコピー操作でモデルや役割の設定は変更されません。

### 4. 内容と動作を照合する

公開版をそのまま導入した場合は、取得元のルートで次を実行します。

```sh
python tools/install_luna_skills.py --verify
```

別の導入先には `--target-root "<導入先>"` を追加します。独自変更を保った場合は差分が残るため、同一 bytes の検査が不合格になることがあります。その差分を確認し、同一と報告しないでください。

Codex の新しいチャットで、使うスキルの場所、README の準備チェック、最初の担当の完了記録を確認します。同名コピーが複数ある場合は、古い配置を保全したうえで整理し、選ばれた実体を確かめてください。

## Windowsで移行・詳細検査を行う

PowerShell 7の既存ツールは、旧配置からの移行、journal、staging hash、partial-failure試験を含むWindows向けの詳細経路です。この経路はGitHubリポジトリまたはsource ZIPから実行し、最初にdiscoveryとdry-runを実行します。

```powershell
pwsh -NoProfile -File tools/Test-LunaSkillDiscovery.ps1 -SkillRoot .agents/skills
pwsh -NoProfile -File tools/Install-LunaSkillsUserScope.ps1 -Source .agents/skills
```

内容を確認してから適用します。

```powershell
pwsh -NoProfile -File tools/Install-LunaSkillsUserScope.ps1 `
  -Source .agents/skills `
  -Apply
```

既存packageの更新や旧 `$HOME/.codex/skills` からの移行は、[MIGRATION.md](../tools/MIGRATION.md)の差分・backup・quarantine手順に従ってください。どちらの導入器も既存の同名Skillを自動更新しません。

## Codex cloud・plugin

Codex cloudでは、このGitHubリポジトリと利用するbranchを環境へ接続し、リポジトリ内の `.agents/skills` を使います。Web調査には環境側のネットワーク設定が必要です。

Releaseのplugin ZIPには2つのSkillとPython導入器が含まれますが、`.codex/agents`のカスタム役割とPowerShell移行ツールは含まれません。展開したpluginルートでも導入器が `skills/` を自動検出します。Release assetは同じ版の `SHA256SUMS` と照合してから導入してください。mainは開発中の最新版、Releaseは公開時点を固定したsnapshotです。

## 更新とトラブルシューティング

`destination already exists` は意図的な保護です。既存packageを削除して再実行するのではなく、sourceとの差分、所有者、ローカル変更を確認し、Windowsでは移行手順を使ってください。

導入後にSkillが表示されない場合は、新しいCodex taskを開き、それでも反映されなければCodexを再起動します。Skillが見えることはモデル・sandbox・再委任toolが実行時に使える証明ではありません。採用する各childはSkill内のruntime receipt契約で別途確認します。
