[CmdletBinding(SupportsShouldProcess=$true, ConfirmImpact='High')]
param(
    [Parameter(Mandatory=$true)][string]$Source,
    [string]$TargetRoot,
    [string]$ManifestPath,
    [switch]$Apply
)

$ErrorActionPreference = 'Stop'

function Get-FullPath([string]$Path) {
    $resolved = Resolve-Path -LiteralPath $Path -ErrorAction SilentlyContinue |
        Select-Object -ExpandProperty Path -First 1
    if ($resolved) {
        return [IO.Path]::GetFullPath($resolved)
    }
    return [IO.Path]::GetFullPath($Path)
}

function Get-SkillName([string]$SkillFile) {
    $lines = @(Get-Content -LiteralPath $SkillFile -Encoding UTF8 -TotalCount 40)
    if ($lines.Count -lt 3 -or $lines[0].Trim() -ne '---') {
        throw "Missing YAML frontmatter in $SkillFile"
    }
    $closing = -1
    for ($i = 1; $i -lt $lines.Count; $i++) {
        if ($lines[$i].Trim() -eq '---') {
            $closing = $i
            break
        }
    }
    if ($closing -lt 2) {
        throw "Unclosed YAML frontmatter in $SkillFile"
    }
    $nameLine = @($lines[1..($closing - 1)] | Where-Object { $_ -match '^\s*name\s*:' })
    if ($nameLine.Count -ne 1) {
        throw "Expected exactly one frontmatter name in $SkillFile"
    }
    $name = ($nameLine[0] -replace '^\s*name\s*:\s*', '').Trim().Trim('"').Trim("'")
    if (-not $name -or $name -notmatch '^[A-Za-z0-9][A-Za-z0-9._-]*$') {
        throw "Invalid skill name '$name' in $SkillFile"
    }
    return $name
}

function Test-SafeStagePath([string]$StagePath, [string]$AllowedParent) {
    $stageFull = [IO.Path]::GetFullPath($StagePath)
    $parentFull = [IO.Path]::GetFullPath($AllowedParent).TrimEnd('\', '/')
    $prefix = $parentFull + [IO.Path]::DirectorySeparatorChar
    $leaf = Split-Path -Leaf $stageFull
    return $stageFull.StartsWith($prefix, [StringComparison]::OrdinalIgnoreCase) -and
        $leaf.StartsWith('.luna-skills-stage-', [StringComparison]::Ordinal)
}

function Write-NewUtf8File([string]$Path, [string]$Text) {
    $encoding = New-Object System.Text.UTF8Encoding($false)
    $stream = [IO.File]::Open(
        $Path,
        [IO.FileMode]::CreateNew,
        [IO.FileAccess]::Write,
        [IO.FileShare]::None
    )
    try {
        $writer = New-Object IO.StreamWriter($stream, $encoding)
        try {
            $writer.Write($Text)
            $writer.Flush()
        } finally {
            $writer.Dispose()
        }
    } finally {
        if ($stream) { $stream.Dispose() }
    }
}

function Write-OwnedUtf8File([string]$Path, [string]$Text) {
    $encoding = New-Object System.Text.UTF8Encoding($false)
    [IO.File]::WriteAllText($Path, $Text, $encoding)
}

$userProfile = [Environment]::GetFolderPath('UserProfile')
if (-not $userProfile) {
    throw 'Could not resolve the current user profile.'
}

$allowedRoot = Get-FullPath (Join-Path $userProfile '.agents\skills')
if (-not $TargetRoot) {
    $TargetRoot = $allowedRoot
}
$targetRootFull = [IO.Path]::GetFullPath($TargetRoot)
if ($targetRootFull -ne $allowedRoot) {
    throw "TargetRoot must be exactly the official user skill root: $allowedRoot"
}
$targetParent = [IO.Path]::GetFullPath((Split-Path $targetRootFull -Parent))
$manifestOut = if ($ManifestPath) {
    [IO.Path]::GetFullPath($ManifestPath)
} else {
    $stamp = (Get-Date).ToUniversalTime().ToString('yyyyMMddTHHmmssZ')
    $suffix = [guid]::NewGuid().ToString('N').Substring(0, 8)
    Join-Path $targetParent "luna-skills-migration-manifest-$stamp-$suffix.json"
}
$manifestParent = [IO.Path]::GetFullPath((Split-Path $manifestOut -Parent))
if (-not $manifestParent.Equals($targetParent, [StringComparison]::OrdinalIgnoreCase)) {
    throw "ManifestPath must be a new JSON file directly under: $targetParent"
}
if ([IO.Path]::GetExtension($manifestOut) -ne '.json') {
    throw 'ManifestPath must use the .json extension.'
}
if (Test-Path -LiteralPath $manifestOut) {
    throw "Refusing to overwrite an existing manifest: $manifestOut"
}

$sourceFull = Get-FullPath $Source
if (-not (Test-Path -LiteralPath $sourceFull -PathType Container)) {
    throw "Source directory does not exist: $Source"
}

$sourceSkill = Join-Path $sourceFull 'SKILL.md'
if (Test-Path -LiteralPath $sourceSkill -PathType Leaf) {
    $packageDirs = @((Get-Item -LiteralPath $sourceFull))
} else {
    $packageDirs = @(Get-ChildItem -LiteralPath $sourceFull -Directory -Force |
        Where-Object { Test-Path -LiteralPath (Join-Path $_.FullName 'SKILL.md') -PathType Leaf } |
        Sort-Object Name)
}
if ($packageDirs.Count -eq 0) {
    throw "No direct skill packages containing SKILL.md were found in $sourceFull"
}

$seenNames = @{}
$packages = @()
foreach ($packageDir in $packageDirs) {
    $skillFile = Join-Path $packageDir.FullName 'SKILL.md'
    $skillName = Get-SkillName $skillFile
    if ($packageDir.Name -ne $skillName) {
        throw "Package folder '$($packageDir.Name)' must match frontmatter name '$skillName'."
    }
    $nameKey = $skillName.ToLowerInvariant()
    if ($seenNames.ContainsKey($nameKey)) {
        throw "Duplicate skill name in source: $skillName"
    }
    $seenNames[$nameKey] = $true
    $destination = Join-Path $targetRootFull $packageDir.Name
    if (Test-Path -LiteralPath $destination) {
        throw "Refusing to overwrite existing skill package: $destination"
    }

    $packageFiles = @(
        Get-ChildItem -LiteralPath $packageDir.FullName -File -Recurse -Force |
        Where-Object {
            $_.Extension -ne '.pyc' -and
            $_.FullName -notmatch '(^|[\\/])__pycache__([\\/]|$)'
        } |
        Sort-Object FullName |
        ForEach-Object {
            [ordered]@{
                path = $_.FullName.Substring($packageDir.FullName.Length).TrimStart('\', '/')
                sha256 = (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash
                source = $_.FullName
            }
        }
    )
    if ($packageFiles.Count -eq 0) {
        throw "Skill package contains no files: $($packageDir.FullName)"
    }
    $packages += [ordered]@{
        name = $skillName
        source = $packageDir.FullName
        destination = $destination
        fileCount = $packageFiles.Count
        files = $packageFiles
    }
}

$manifestPackages = @($packages | ForEach-Object {
    [ordered]@{
        name = $_.name
        source = $_.source
        destination = $_.destination
        fileCount = $_.fileCount
        files = @($_.files | ForEach-Object {
            [ordered]@{ path = $_.path; sha256 = $_.sha256 }
        })
    }
})
$manifest = [ordered]@{
    schemaVersion = 3
    state = 'planned'
    createdAt = (Get-Date).ToUniversalTime().ToString('o')
    source = $sourceFull
    targetRoot = $targetRootFull
    manifestPath = $manifestOut
    packageCount = $packages.Count
    packages = $manifestPackages
    appliedDestinations = @()
    applyRequested = [bool]$Apply
    legacyRootsModified = $false
    rollback = 'Remove only package destinations listed in this manifest after validating their exact paths. Never remove the target root or a legacy root recursively.'
}

if (-not $Apply) {
    $manifest | ConvertTo-Json -Depth 8
    Write-Verbose 'Dry run only. No directories or files were created.'
    return
}

$action = "Install $($packages.Count) Luna skill package(s) after staging and SHA-256 verification"
$targetApproved = $PSCmdlet.ShouldProcess($targetRootFull, $action)
$manifestApproved = $PSCmdlet.ShouldProcess(
    $manifestOut,
    'Create a new prepared/applied migration manifest without overwriting'
)
if (-not ($targetApproved -and $manifestApproved)) {
    $manifest | ConvertTo-Json -Depth 8
    return
}

$stage = Join-Path $targetParent ('.luna-skills-stage-' + [guid]::NewGuid().ToString('N'))
if (-not (Test-SafeStagePath -StagePath $stage -AllowedParent $targetParent)) {
    throw "Unsafe staging path: $stage"
}

$applied = @()
$manifestCreated = $false
try {
    New-Item -ItemType Directory -Path $targetParent -Force | Out-Null
    New-Item -ItemType Directory -Path $stage -Force | Out-Null
    foreach ($package in $packages) {
        $stagePackage = Join-Path $stage $package.name
        New-Item -ItemType Directory -Path $stagePackage -Force | Out-Null
        foreach ($file in $package.files) {
            $stagedFile = Join-Path $stagePackage $file.path
            $stagedParent = Split-Path $stagedFile -Parent
            New-Item -ItemType Directory -Path $stagedParent -Force | Out-Null
            Copy-Item -LiteralPath $file.source -Destination $stagedFile
        }
    }

    foreach ($package in $packages) {
        foreach ($file in $package.files) {
            $stagedFile = Join-Path (Join-Path $stage $package.name) $file.path
            if (-not (Test-Path -LiteralPath $stagedFile -PathType Leaf)) {
                throw "Staging missing: $($package.name)/$($file.path)"
            }
            if ((Get-FileHash -LiteralPath $stagedFile -Algorithm SHA256).Hash -ne $file.sha256) {
                throw "Hash mismatch: $($package.name)/$($file.path)"
            }
        }
    }

    $manifest['state'] = 'prepared'
    $manifest['preparedAt'] = (Get-Date).ToUniversalTime().ToString('o')
    Write-NewUtf8File -Path $manifestOut -Text ($manifest | ConvertTo-Json -Depth 8)
    $manifestCreated = $true

    New-Item -ItemType Directory -Path $targetRootFull -Force | Out-Null
    foreach ($package in $packages) {
        $stagePackage = Join-Path $stage $package.name
        Move-Item -LiteralPath $stagePackage -Destination $package.destination
        $applied += $package.destination
        $manifest['appliedDestinations'] = @($applied)
        Write-OwnedUtf8File -Path $manifestOut -Text ($manifest | ConvertTo-Json -Depth 8)
    }

    $manifest['state'] = 'applied'
    $manifest['appliedAt'] = (Get-Date).ToUniversalTime().ToString('o')
    Write-OwnedUtf8File -Path $manifestOut -Text ($manifest | ConvertTo-Json -Depth 8)
    Write-Output "Applied $($packages.Count) package(s) to $targetRootFull; manifest: $manifestOut"
} catch {
    $originalError = $_.Exception.Message
    if ($manifestCreated) {
        $manifest['state'] = if ($applied.Count -gt 0) { 'partial' } else { 'failed' }
        $manifest['failedAt'] = (Get-Date).ToUniversalTime().ToString('o')
        $manifest['appliedDestinations'] = @($applied)
        try {
            Write-OwnedUtf8File -Path $manifestOut -Text ($manifest | ConvertTo-Json -Depth 8)
        } catch {
            Write-Warning "Could not update owned recovery manifest: $manifestOut"
        }
    }
    if ($applied.Count -gt 0) {
        Write-Error "Installation stopped after moving: $($applied -join ', '). Do not delete them automatically; use the prepared manifest and exact-path checks for recovery. Original error: $originalError"
    }
    throw
} finally {
    if ((Test-Path -LiteralPath $stage) -and (Test-SafeStagePath -StagePath $stage -AllowedParent $targetParent)) {
        Remove-Item -LiteralPath $stage -Recurse -Force
    }
}
