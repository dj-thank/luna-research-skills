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
