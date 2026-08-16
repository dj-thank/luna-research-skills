[CmdletBinding()]
param(
    [string]$OutputJson,
    [string]$OutputMarkdown,
    [string[]]$SkillRoot,
    [switch]$SkipDefaultRoots,
    [string]$RepoRoot = (Get-Location).Path,
    [string]$ConfigPath = (Join-Path $HOME '.codex\config.toml'),
    [string]$AgentRoot = (Join-Path $HOME '.codex\agents')
)

$ErrorActionPreference = 'Stop'
$MaximumFilesPerSkill = 5000
if ($OutputJson -and (Test-Path -LiteralPath $OutputJson)) { throw "Refusing to overwrite existing discovery output: $OutputJson" }
if ($OutputMarkdown -and (Test-Path -LiteralPath $OutputMarkdown)) { throw "Refusing to overwrite existing discovery output: $OutputMarkdown" }
if ($OutputJson -and $OutputMarkdown -and ([IO.Path]::GetFullPath($OutputJson).Equals([IO.Path]::GetFullPath($OutputMarkdown), [StringComparison]::OrdinalIgnoreCase))) { throw 'OutputJson and OutputMarkdown must be different files.' }
$legacyRoot = Join-Path $HOME '.codex\skills'
$candidateRoot = Join-Path $HOME '.agents\skills'
$roots = if ($SkipDefaultRoots) { @($SkillRoot) } else { @($legacyRoot, $candidateRoot) + @($SkillRoot) }
$roots = @(
    $roots | Where-Object { $_ } | ForEach-Object {
        [IO.Path]::GetFullPath([string]$_)
    } | Select-Object -Unique
)

function Test-IsReparse([IO.FileSystemInfo]$Item) {
    return ($Item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0
}

function Test-PathWithin([string]$Candidate, [string]$Parent) {
    $candidateFull = [IO.Path]::GetFullPath($Candidate)
    $parentFull = [IO.Path]::GetFullPath($Parent).TrimEnd('\', '/')
    return $candidateFull.Equals($parentFull, [StringComparison]::OrdinalIgnoreCase) -or
        $candidateFull.StartsWith(
            $parentFull + [IO.Path]::DirectorySeparatorChar,
            [StringComparison]::OrdinalIgnoreCase
        )
}

function Assert-DirectExistingPath([string]$Path, [string]$Label) {
    $cursor = [IO.Path]::GetFullPath($Path)
    $root = [IO.Path]::GetPathRoot($cursor).TrimEnd('\', '/')
    while (Test-Path -LiteralPath $cursor) {
        $item = Get-Item -LiteralPath $cursor -Force -ErrorAction Stop
        if (Test-IsReparse $item) {
            throw "$Label traverses a reparse point, symlink, or junction: $cursor"
        }
        if ($cursor.TrimEnd('\', '/').Equals($root, [StringComparison]::OrdinalIgnoreCase)) {
            return
        }
        $parent = [IO.Directory]::GetParent($cursor)
        if ($null -eq $parent) { return }
        $cursor = $parent.FullName
    }
}

function Get-SafeFileHash([string]$Path, [string]$Root) {
    if (-not (Test-PathWithin -Candidate $Path -Parent $Root)) {
        throw "Inventory path escaped the skill root: $Path"
    }
    Assert-DirectExistingPath -Path $Path -Label 'Inventory file path'
    $before = Get-Item -LiteralPath $Path -Force -ErrorAction Stop
    if (Test-IsReparse $before) {
        throw "Inventory encountered a reparse point, symlink, or junction: $Path"
    }
    $stream = [IO.File]::Open($before.FullName, [IO.FileMode]::Open, [IO.FileAccess]::Read, [IO.FileShare]::Read)
    try {
        Assert-DirectExistingPath -Path $Path -Label 'Inventory file path'
        $after = Get-Item -LiteralPath $Path -Force -ErrorAction Stop
        if (Test-IsReparse $after) {
            throw "Inventory path changed to a reparse point before hashing: $Path"
        }
        $sha = [Security.Cryptography.SHA256]::Create()
        try {
            return ([BitConverter]::ToString($sha.ComputeHash($stream))).Replace('-', '')
        } finally {
            $sha.Dispose()
        }
    } finally {
        $stream.Dispose()
    }
}

function Get-FrontMatterName([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path)) { return $null }
    $item = Get-Item -LiteralPath $Path -Force -ErrorAction Stop
    if (Test-IsReparse $item) { return $null }
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
    Assert-DirectExistingPath -Path $Root -Label 'Skill root path'
    $rootItem = Get-Item -LiteralPath $Root -Force -ErrorAction Stop
    if (Test-IsReparse $rootItem) {
        return ,([ordered]@{
            root = $Root; directory = '(root)'; path = $Root; link = $true
            linkTarget = $null; frontmatterName = $null; skillMdExists = $false; files = @()
            scanError = 'Skill root is a reparse point and was not traversed.'
        })
    }
    Get-ChildItem -LiteralPath $Root -Directory -Force -ErrorAction Stop | ForEach-Object {
        $skill = $_
        $readme = Join-Path $skill.FullName 'SKILL.md'
        $link = Test-IsReparse $skill
        $hashes = @()
        $scanError = $null
        if (-not $link) {
            try {
                $pending = @($skill)
                while ($pending.Count -gt 0) {
                    $current = $pending[0]
                    if ($pending.Count -eq 1) {
                        $pending = @()
                    } else {
                        $pending = @($pending[1..($pending.Count - 1)])
                    }
                    Assert-DirectExistingPath -Path $current.FullName -Label 'Skill inventory directory'
                    foreach ($entry in @(Get-ChildItem -LiteralPath $current.FullName -Force -ErrorAction Stop | Sort-Object FullName)) {
                        Assert-DirectExistingPath -Path $entry.FullName -Label 'Skill inventory entry'
                        if (Test-IsReparse $entry) {
                            throw "Nested reparse point, symlink, or junction was not traversed: $($entry.FullName)"
                        }
                        if (-not (Test-PathWithin -Candidate $entry.FullName -Parent $skill.FullName)) {
                            throw "Inventory entry escaped the skill root: $($entry.FullName)"
                        }
                        if ($entry.PSIsContainer) {
                            $pending = @($pending) + @($entry)
                            continue
                        }
                        $hashes += ,([ordered]@{
                            path = $entry.FullName.Substring($skill.FullName.Length).TrimStart([char]'\', [char]'/')
                            sha256 = Get-SafeFileHash -Path $entry.FullName -Root $skill.FullName
                        })
                        if ($hashes.Count -gt $MaximumFilesPerSkill) {
                            throw "File count exceeds the safety limit of $MaximumFilesPerSkill."
                        }
                    }
                }
            } catch {
                $scanError = $_.Exception.Message
            }
        } else {
            $scanError = 'Skill directory is a reparse point and was not traversed.'
        }
        $items += ,([ordered]@{
            root = $Root
            directory = $skill.Name
            path = $skill.FullName
            link = $link
            linkTarget = $null
            frontmatterName = if (-not $link -and -not $scanError) { Get-FrontMatterName $readme } else { $null }
            skillMdExists = (-not $link -and -not $scanError -and (Test-Path -LiteralPath $readme -PathType Leaf))
            files = $hashes
            scanError = $scanError
        })
    }; return $items
}

function Write-NewUtf8Output([string]$Path, [string]$Text) {
    $outputFull = [IO.Path]::GetFullPath($Path)
    $parent = Split-Path $outputFull -Parent
    if (-not (Test-Path -LiteralPath $parent -PathType Container)) {
        throw "Discovery output parent does not exist: $parent"
    }
    $allowedRoots = @(
        [IO.Path]::GetFullPath($RepoRoot),
        [IO.Path]::GetFullPath([IO.Path]::GetTempPath())
    )
    if (-not ($allowedRoots | Where-Object { Test-PathWithin -Candidate $outputFull -Parent $_ })) {
        throw 'Discovery output must stay under RepoRoot or the OS temporary directory.'
    }
    Assert-DirectExistingPath -Path $parent -Label 'Discovery output parent'
    $encoding = New-Object System.Text.UTF8Encoding($false)
    $lockPath = Join-Path $parent ('.luna-discovery-output-' + [guid]::NewGuid().ToString('N') + '.lock')
    $lock = [IO.File]::Open($lockPath, [IO.FileMode]::CreateNew, [IO.FileAccess]::ReadWrite, [IO.FileShare]::None)
    try {
        Assert-DirectExistingPath -Path $parent -Label 'Discovery output parent'
        $stream = [IO.File]::Open($outputFull, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write, [IO.FileShare]::None)
        try {
            Assert-DirectExistingPath -Path $parent -Label 'Discovery output parent'
            $writer = New-Object IO.StreamWriter($stream, $encoding)
            try {
                $writer.Write($Text)
                $writer.Flush()
                $stream.Flush($true)
            } finally {
                $writer.Dispose()
            }
        } finally {
            $stream.Dispose()
        }
    } finally {
        $lock.Dispose()
        if (Test-Path -LiteralPath $lockPath -PathType Leaf) {
            [IO.File]::Delete($lockPath)
        }
    }
}
function Get-AncestorScopes([string]$Start) {
    $out=@(); $p=[IO.Path]::GetFullPath($Start)
    while ($p) { $out += [ordered]@{ path=$p; skillsPath=(Join-Path $p '.agents\skills'); exists=(Test-Path -LiteralPath (Join-Path $p '.agents\skills') -PathType Container) }; $next=[IO.Directory]::GetParent($p); if($null -eq $next){break}; $p=$next.FullName }; return $out
}
function Get-TextKeys([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { return @() }
    $item = Get-Item -LiteralPath $Path -Force -ErrorAction Stop
    if (Test-IsReparse $item) { return @() }
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
$agentFiles = @()
if (Test-Path -LiteralPath $AgentRoot -PathType Container) {
    $agentRootItem = Get-Item -LiteralPath $AgentRoot -Force -ErrorAction Stop
    if (Test-IsReparse $agentRootItem) {
        $agentFiles = @([ordered]@{ path = $AgentRoot; keys = @(); scanError = 'Agent root reparse point was not traversed.' })
    } else {
        $agentFiles = @(
            Get-ChildItem -LiteralPath $AgentRoot -Filter '*.toml' -File -Force -ErrorAction Stop |
                ForEach-Object {
                    if (Test-IsReparse $_) {
                        [ordered]@{ path = $_.FullName; keys = @(); scanError = 'Agent file reparse point was not read.' }
                    } else {
                        [ordered]@{ path = $_.FullName; keys = Get-TextKeys $_.FullName; scanError = $null }
                    }
                }
        )
    }
}
$result=[ordered]@{ generatedAt=(Get-Date).ToUniversalTime().ToString('o'); roots=$roots; skills=$all; duplicateNames=$duplicates; ancestorRepoScopes=Get-AncestorScopes $RepoRoot; config=[ordered]@{path=$ConfigPath; exists=(Test-Path -LiteralPath $ConfigPath); documentedKeys=Get-TextKeys $ConfigPath; skillsConfigMentioned=((Get-TextKeys $ConfigPath) -contains 'skills.config')}; agentToml=$agentFiles; cliCandidates=@(Get-Command codex,pwsh,powershell -ErrorAction SilentlyContinue | ForEach-Object {[ordered]@{name=$_.Name; source=$_.Source; commandType=$_.CommandType}}); notes=@('Read-only inventory; no config, skill, or link changes made.','Hashes are SHA-256 and paths are relative to each skill directory.')}
$json=$result | ConvertTo-Json -Depth 8
if($OutputJson){Write-NewUtf8Output -Path $OutputJson -Text $json}
if($OutputMarkdown){$md=@('# Luna skill discovery','',"Generated: $($result.generatedAt)",'','## Summary',"- Skill directories: $($all.Count)","- Duplicate frontmatter names: $($duplicates.Count)","- Repo ancestor scopes checked: $(@($result.ancestorRepoScopes).Count)",'','## Skills'); foreach($s in $all){$display=$s.frontmatterName; if(-not $display){$display='(no frontmatter name)'}; $md += ('- **{0}** — `{1}`; link={2}; files={3}; scanError={4}' -f $display, $s.path, $s.link, @($s.files).Count, $s.scanError)}; $md += @('','## Safety','This report only writes explicitly requested new report files. It never changes config, skills, agents, or links.',''); Write-NewUtf8Output -Path $OutputMarkdown -Text ($md -join "`r`n")}
$json
