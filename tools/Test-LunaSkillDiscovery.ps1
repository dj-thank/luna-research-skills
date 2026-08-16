[CmdletBinding()]
param(
    [string]$OutputJson,
    [string]$OutputMarkdown,
    [string[]]$SkillRoot,
    [string]$RepoRoot = (Get-Location).Path,
    [string]$ConfigPath = (Join-Path $HOME '.codex\config.toml'),
    [string]$AgentRoot = (Join-Path $HOME '.codex\agents')
)

$ErrorActionPreference = 'Stop'
$legacyRoot = Join-Path $HOME '.codex\skills'
$candidateRoot = Join-Path $HOME '.agents\skills'
$roots = @($legacyRoot, $candidateRoot) + @($SkillRoot)
$roots = @(
    $roots | Where-Object { $_ } | ForEach-Object {
        $rootPath = [string]$_
        try {
            (Resolve-Path -LiteralPath $rootPath -ErrorAction Stop).Path
        } catch {
            [IO.Path]::GetFullPath($rootPath)
        }
    } | Select-Object -Unique
)

function Get-FrontMatterName([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path)) { return $null }
    $lines = Get-Content -LiteralPath $Path -Encoding UTF8 -TotalCount 40
    if ($lines.Count -gt 0 -and $lines[0] -match '^---\s*$') {
        $end=[Math]::Min(39, $lines.Count - 1); for($i=1; $i -le $end; $i++){ $line=$lines[$i]
            if ($line -match '^name\s*:\s*(.+?)\s*$') {
                $name = ([string]$Matches[1]).Trim()
                if ($name.Length -ge 2) {
                    $first = $name.Substring(0, 1)
                    $last = $name.Substring($name.Length - 1, 1)
                    if (($first -eq '"' -and $last -eq '"') -or ($first -eq "'" -and $last -eq "'")) {
                        $name = $name.Substring(1, $name.Length - 2).Trim()
                    }
                }
                return $name
            }
            if ($line -match '^---\s*$') { break }
        }
    }
    return $null
}
function Get-SkillInventory([string]$Root) {
    if (-not (Test-Path -LiteralPath $Root -PathType Container)) { return @() }
    $items = @()
    Get-ChildItem -LiteralPath $Root -Directory -Force | ForEach-Object {
        $skill = $_; $readme = Join-Path $skill.FullName 'SKILL.md'; $link = ($skill.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0
        $hashes = @(); Get-ChildItem -LiteralPath $skill.FullName -File -Recurse -Force -ErrorAction SilentlyContinue | ForEach-Object { $hashes += ,([ordered]@{ path=$_.FullName.Substring($skill.FullName.Length).TrimStart([char]'\',[char]'/'); sha256=(Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash }) }
        $items += ,([ordered]@{ root=$Root; directory=$skill.Name; path=$skill.FullName; link=$link; linkTarget=if($link){ try { (Resolve-Path -LiteralPath $skill.FullName -ErrorAction Stop).Path } catch { $null } } else { $null }; frontmatterName=Get-FrontMatterName $readme; skillMdExists=(Test-Path -LiteralPath $readme); files=$hashes })
    }; return $items
}
function Get-AncestorScopes([string]$Start) {
    $out=@(); $p=[IO.Path]::GetFullPath($Start)
    while ($p) { $out += [ordered]@{ path=$p; skillsPath=(Join-Path $p '.agents\skills'); exists=(Test-Path -LiteralPath (Join-Path $p '.agents\skills') -PathType Container) }; $next=[IO.Directory]::GetParent($p); if($null -eq $next){break}; $p=$next.FullName }; return $out
}
function Get-TextKeys([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { return @() }
    $allow = @(
        'agents', 'approval_policy', 'command', 'default_subagent_model',
        'default_subagent_reasoning_effort', 'disable', 'enabled',
        'max_concurrent_threads_per_session', 'max_threads', 'model',
        'model_reasoning_effort', 'name', 'path', 'sandbox_mode',
        'service_tier', 'skill', 'skills', 'skills.config'
    )
    $found = @()
    Get-Content -LiteralPath $Path -Encoding UTF8 | ForEach-Object {
        $line = [string]$_
        if ($line -match '^\s*\[\[?\s*([A-Za-z][A-Za-z0-9_.-]*)\s*\]\]?\s*(?:#.*)?$') {
            $key = $Matches[1]
            if ($allow -contains $key -or $key -like 'skills*') { $found += $key }
        } elseif ($line -match '^\s*([A-Za-z][A-Za-z0-9_.-]*)\s*=') {
            $key = $Matches[1]
            if ($allow -contains $key -or $key -like 'skills*') { $found += $key }
        }
    }
    return @($found | Sort-Object -Unique)
}
$all=@(); foreach($r in $roots){$all += Get-SkillInventory $r}
$duplicates = @(
    $all |
        Where-Object { $_.frontmatterName } |
        Group-Object -Property { ([string]$_.frontmatterName).ToLowerInvariant() } |
        Where-Object Count -gt 1 |
        ForEach-Object {
            [ordered]@{
                name = [string]$_.Group[0].frontmatterName
                normalizedName = [string]$_.Name
                paths = @($_.Group.path)
            }
        }
)
$agentFiles=@(); if(Test-Path -LiteralPath $AgentRoot){$agentFiles=@(Get-ChildItem -LiteralPath $AgentRoot -Filter '*.toml' -File -Recurse -ErrorAction SilentlyContinue | ForEach-Object {[ordered]@{path=$_.FullName; keys=Get-TextKeys $_.FullName}})}
$result=[ordered]@{ generatedAt=(Get-Date).ToUniversalTime().ToString('o'); roots=$roots; skills=$all; duplicateNames=$duplicates; ancestorRepoScopes=Get-AncestorScopes $RepoRoot; config=[ordered]@{path=$ConfigPath; exists=(Test-Path -LiteralPath $ConfigPath); documentedKeys=Get-TextKeys $ConfigPath; skillsConfigMentioned=((Get-TextKeys $ConfigPath) -contains 'skills.config')}; agentToml=$agentFiles; cliCandidates=@(Get-Command codex,pwsh,powershell -ErrorAction SilentlyContinue | ForEach-Object {[ordered]@{name=$_.Name; source=$_.Source; commandType=$_.CommandType}}); notes=@('Read-only inventory; no config, skill, or link changes made.','Hashes are SHA-256 and paths are relative to each skill directory.')}
$json=$result | ConvertTo-Json -Depth 8
if($OutputJson){$json | Set-Content -LiteralPath $OutputJson -Encoding UTF8}
if($OutputMarkdown){$md=@('# Luna skill discovery','',"Generated: $($result.generatedAt)",'','## Summary',"- Skill directories: $($all.Count)","- Duplicate frontmatter names: $($duplicates.Count)","- Repo ancestor scopes checked: $(@($result.ancestorRepoScopes).Count)",'','## Skills'); foreach($s in $all){$display=$s.frontmatterName; if(-not $display){$display='(no frontmatter name)'}; $md += ('- **{0}** — `{1}`; link={2}; files={3}' -f $display, $s.path, $s.link, @($s.files).Count)}; $md += @('','## Safety','This report is read-only. Hashes identify files but no secret values are emitted.',''); $md -join "`r`n" | Set-Content -LiteralPath $OutputMarkdown -Encoding UTF8}
$json
