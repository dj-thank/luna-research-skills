[CmdletBinding(SupportsShouldProcess = $true, ConfirmImpact = 'High')]
param(
    [Parameter(Mandatory = $true)][string]$Source,
    [string]$TargetRoot,
    [string]$ManifestPath,
    [switch]$Apply,
    [string]$TestUserProfile,
    [int]$TestFailAfterMoves = -1,
    [string]$TestInjectStageJunctionTarget
)

$ErrorActionPreference = 'Stop'
$MaximumPackageFiles = 5000
$MaximumFileBytes = 16MB
$MaximumPackageBytes = 128MB

function Get-NormalizedPath([string]$Path) {
    $resolved = Resolve-Path -LiteralPath $Path -ErrorAction SilentlyContinue |
        Select-Object -ExpandProperty Path -First 1
    if ($resolved) {
        return [IO.Path]::GetFullPath($resolved)
    }
    return [IO.Path]::GetFullPath($Path)
}

function Test-PathWithin([string]$Candidate, [string]$Parent) {
    $candidateFull = [IO.Path]::GetFullPath($Candidate)
    $parentFull = [IO.Path]::GetFullPath($Parent).TrimEnd('\', '/')
    $prefix = $parentFull + [IO.Path]::DirectorySeparatorChar
    return $candidateFull.Equals($parentFull, [StringComparison]::OrdinalIgnoreCase) -or
        $candidateFull.StartsWith($prefix, [StringComparison]::OrdinalIgnoreCase)
}

function Assert-NotReparsePoint([IO.FileSystemInfo]$Item, [string]$Label) {
    if (($Item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
        throw "$Label contains a reparse point, symlink, or junction: $($Item.FullName)"
    }
}

function Assert-ExistingPathChainIsDirect([string]$Path, [string]$StopAt) {
    $stopFull = [IO.Path]::GetFullPath($StopAt).TrimEnd('\', '/')
    $cursor = [IO.Path]::GetFullPath($Path)
    while (Test-Path -LiteralPath $cursor) {
        $item = Get-Item -LiteralPath $cursor -Force
        Assert-NotReparsePoint -Item $item -Label 'Destination path'
        if ($cursor.Equals($stopFull, [StringComparison]::OrdinalIgnoreCase)) {
            return
        }
        $parent = [IO.Directory]::GetParent($cursor)
        if ($null -eq $parent) {
            break
        }
        $cursor = $parent.FullName
    }
    if (-not (Test-PathWithin -Candidate $Path -Parent $StopAt)) {
        throw "Destination path escaped the selected user profile: $Path"
    }
}

function Get-SkillName([string]$SkillFile) {
    $skillItem = Get-Item -LiteralPath $SkillFile -Force -ErrorAction Stop
    Assert-NotReparsePoint -Item $skillItem -Label 'Source SKILL.md'
    $lines = @(Get-Content -LiteralPath $SkillFile -Encoding UTF8 -TotalCount 40)
    if ($lines.Count -lt 3 -or $lines[0].Trim() -ne '---') {
        throw "Missing YAML frontmatter in $SkillFile"
    }

    $closing = -1
    for ($index = 1; $index -lt $lines.Count; $index++) {
        if ($lines[$index].Trim() -eq '---') {
            $closing = $index
            break
        }
    }
    if ($closing -lt 2) {
        throw "Unclosed YAML frontmatter in $SkillFile"
    }

    $nameLines = @(
        $lines[1..($closing - 1)] |
            Where-Object { $_ -match '^\s*name\s*:' }
    )
    if ($nameLines.Count -ne 1) {
        throw "Expected exactly one frontmatter name in $SkillFile"
    }

    $name = ($nameLines[0] -replace '^\s*name\s*:\s*', '').Trim().Trim('"').Trim("'")
    if (-not $name -or $name -notmatch '^[A-Za-z0-9][A-Za-z0-9._-]*$') {
        throw "Invalid skill name '$name' in $SkillFile"
    }
    return $name
}

function Read-VerifiedSourceSnapshot([string]$Path, [string]$PackageRoot) {
    if (-not (Test-PathWithin -Candidate $Path -Parent $PackageRoot)) {
        throw "Source file escaped its package root: $Path"
    }
    $before = Get-Item -LiteralPath $Path -Force -ErrorAction Stop
    Assert-NotReparsePoint -Item $before -Label 'Source file'
    if ($before.PSIsContainer) {
        throw "Expected a source file, found a directory: $Path"
    }
    if ($before.Length -gt $MaximumFileBytes) {
        throw "Source file exceeds the $MaximumFileBytes byte safety limit: $Path"
    }

    $stream = [IO.File]::Open(
        $before.FullName,
        [IO.FileMode]::Open,
        [IO.FileAccess]::Read,
        [IO.FileShare]::Read
    )
    try {
        # The open handle denies delete/write sharing. Re-check the lexical path
        # before reading so a path swapped to a reparse point is never hashed.
        $after = Get-Item -LiteralPath $Path -Force -ErrorAction Stop
        Assert-NotReparsePoint -Item $after -Label 'Source file'
        $memory = New-Object IO.MemoryStream
        try {
            $stream.CopyTo($memory)
            $bytes = $memory.ToArray()
        } finally {
            $memory.Dispose()
        }
    } finally {
        $stream.Dispose()
    }
    if ($bytes.Length -gt $MaximumFileBytes) {
        throw "Source file grew beyond the $MaximumFileBytes byte safety limit: $Path"
    }
    $sha = [Security.Cryptography.SHA256]::Create()
    try {
        $digest = ([BitConverter]::ToString($sha.ComputeHash($bytes))).Replace('-', '')
    } finally {
        $sha.Dispose()
    }
    return [pscustomobject]@{ bytes = [byte[]]$bytes; sha256 = $digest; length = $bytes.Length }
}

function Copy-VerifiedSourceFile(
    [string]$SourcePath,
    [string]$DestinationPath,
    [string]$ExpectedSha256,
    [string]$PackageRoot
) {
    $snapshot = Read-VerifiedSourceSnapshot -Path $SourcePath -PackageRoot $PackageRoot
    if ($snapshot.sha256 -ne $ExpectedSha256) {
        throw "Source changed after inventory: $SourcePath"
    }
    $destination = [IO.File]::Open(
        $DestinationPath,
        [IO.FileMode]::CreateNew,
        [IO.FileAccess]::Write,
        [IO.FileShare]::None
    )
    try {
        $destination.Write($snapshot.bytes, 0, $snapshot.bytes.Length)
        $destination.Flush($true)
    } finally {
        $destination.Dispose()
    }
}

function Assert-TreeContainsNoReparse([string]$Root, [string]$Label) {
    $rootItem = Get-Item -LiteralPath $Root -Force -ErrorAction Stop
    Assert-NotReparsePoint -Item $rootItem -Label $Label
    $rootFull = [IO.Path]::GetFullPath($rootItem.FullName)
    $pending = @($rootItem)
    $count = 0
    while ($pending.Count -gt 0) {
        $current = $pending[0]
        if ($pending.Count -eq 1) {
            $pending = @()
        } else {
            $pending = @($pending[1..($pending.Count - 1)])
        }
        foreach ($item in @(Get-ChildItem -LiteralPath $current.FullName -Force -ErrorAction Stop)) {
            Assert-NotReparsePoint -Item $item -Label $Label
            if (-not (Test-PathWithin -Candidate $item.FullName -Parent $rootFull)) {
                throw "$Label escaped its root: $($item.FullName)"
            }
            $count++
            if ($count -gt $MaximumPackageFiles) {
                throw "$Label exceeds the $MaximumPackageFiles entry safety limit: $rootFull"
            }
            if ($item.PSIsContainer) {
                $pending = @($pending) + @($item)
            }
        }
    }
}

function Get-SafePackageFiles([IO.DirectoryInfo]$PackageDirectory) {
    Assert-NotReparsePoint -Item $PackageDirectory -Label 'Source package'
    $packageRoot = [IO.Path]::GetFullPath($PackageDirectory.FullName).TrimEnd('\', '/')
    $pending = @($PackageDirectory)
    $files = @()
    [long]$totalBytes = 0

    while ($pending.Count -gt 0) {
        $current = $pending[0]
        if ($pending.Count -eq 1) {
            $pending = @()
        } else {
            $pending = @($pending[1..($pending.Count - 1)])
        }

        foreach ($item in @(Get-ChildItem -LiteralPath $current.FullName -Force -ErrorAction Stop)) {
            Assert-NotReparsePoint -Item $item -Label 'Source package'
            if (-not (Test-PathWithin -Candidate $item.FullName -Parent $packageRoot)) {
                throw "Source package entry escaped its package root: $($item.FullName)"
            }
            if ($item.PSIsContainer) {
                if ($item.Name -ne '__pycache__') {
                    $pending = @($pending) + @($item)
                }
                continue
            }
            if ($item.Extension -in @('.pyc', '.pyo')) {
                continue
            }
            $relative = $item.FullName.Substring($packageRoot.Length).TrimStart('\', '/')
            if (-not $relative -or [IO.Path]::IsPathRooted($relative) -or $relative -match '(^|[\\/])\.\.([\\/]|$)') {
                throw "Unsafe relative source path: $($item.FullName)"
            }
            $snapshot = Read-VerifiedSourceSnapshot -Path $item.FullName -PackageRoot $packageRoot
            $totalBytes += $snapshot.length
            if ($totalBytes -gt $MaximumPackageBytes) {
                throw "Source package exceeds the $MaximumPackageBytes byte safety limit: $packageRoot"
            }
            $files += [ordered]@{
                path = $relative
                sha256 = $snapshot.sha256
                length = $snapshot.length
                source = $item.FullName
            }
            if ($files.Count -gt $MaximumPackageFiles) {
                throw "Source package exceeds the $MaximumPackageFiles file safety limit: $packageRoot"
            }
        }
    }
    return @($files | Sort-Object path)
}

function Write-DurableUtf8File([string]$Path, [string]$Text, [switch]$CreateNew) {
    $encoding = New-Object System.Text.UTF8Encoding($false)
    if ($CreateNew) {
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
                $stream.Flush($true)
            } finally {
                $writer.Dispose()
            }
        } finally {
            $stream.Dispose()
        }
        return
    }

    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        throw "Atomic manifest update requires an existing owned file: $Path"
    }
    $parent = Split-Path $Path -Parent
    $temporary = Join-Path $parent ('.luna-manifest-' + [guid]::NewGuid().ToString('N') + '.tmp')
    $backup = Join-Path $parent ('.luna-manifest-backup-' + [guid]::NewGuid().ToString('N') + '.tmp')
    try {
        Write-DurableUtf8File -Path $temporary -Text $Text -CreateNew
        [IO.File]::Replace($temporary, $Path, $backup, $true)
    } finally {
        if (Test-Path -LiteralPath $temporary -PathType Leaf) {
            Remove-Item -LiteralPath $temporary -Force
        }
        if (Test-Path -LiteralPath $backup -PathType Leaf) {
            Remove-Item -LiteralPath $backup -Force
        }
    }
}

function Write-Manifest([string]$Path, [Collections.IDictionary]$Manifest, [switch]$CreateNew) {
    $json = $Manifest | ConvertTo-Json -Depth 12
    Write-DurableUtf8File -Path $Path -Text $json -CreateNew:$CreateNew
}

function Test-SafeStagePath([string]$StagePath, [string]$AllowedParent) {
    $stageFull = [IO.Path]::GetFullPath($StagePath)
    $parentFull = [IO.Path]::GetFullPath($AllowedParent).TrimEnd('\', '/')
    $leaf = Split-Path $stageFull -Leaf
    return (Test-PathWithin -Candidate $stageFull -Parent $parentFull) -and
        $leaf.StartsWith('.luna-skills-stage-', [StringComparison]::Ordinal)
}

function Open-ExclusiveInstallLock([string]$Path) {
    return [IO.File]::Open(
        $Path,
        [IO.FileMode]::CreateNew,
        [IO.FileAccess]::ReadWrite,
        [IO.FileShare]::None
    )
}

function Remove-EmptyOwnedStage([string]$StagePath, [string]$AllowedParent) {
    if (-not (Test-Path -LiteralPath $StagePath)) {
        return $true
    }
    if (-not (Test-SafeStagePath -StagePath $StagePath -AllowedParent $AllowedParent)) {
        throw "Refusing to remove an unsafe staging path: $StagePath"
    }
    $item = Get-Item -LiteralPath $StagePath -Force -ErrorAction Stop
    Assert-NotReparsePoint -Item $item -Label 'Staging root cleanup'
    # Intentionally non-recursive. A non-empty or raced stage is preserved for
    # exact journal-based inspection rather than following attacker-controlled
    # descendants during cleanup.
    [IO.Directory]::Delete($item.FullName, $false)
    return $true
}

$userProfile = if ($TestUserProfile) {
    $testProfileFull = [IO.Path]::GetFullPath($TestUserProfile)
    $temporaryRoot = [IO.Path]::GetFullPath([IO.Path]::GetTempPath()).TrimEnd('\', '/')
    $testLeaf = Split-Path $testProfileFull -Leaf
    if (-not (Test-PathWithin -Candidate $testProfileFull -Parent $temporaryRoot) -or
        $testLeaf -notmatch '^luna-skills-test-profile-[0-9a-f]{32}$') {
        throw 'TestUserProfile must be a uniquely prefixed child of the OS temporary directory.'
    }
    $testProfileFull
} else {
    [Environment]::GetFolderPath('UserProfile')
}
if (-not $userProfile) {
    throw 'Could not resolve the current user profile.'
}
if ($TestFailAfterMoves -ge 0 -and -not $TestUserProfile) {
    throw 'TestFailAfterMoves is allowed only with TestUserProfile.'
}
if ($TestInjectStageJunctionTarget -and -not $TestUserProfile) {
    throw 'TestInjectStageJunctionTarget is allowed only with TestUserProfile.'
}

$allowedRoot = Get-NormalizedPath (Join-Path $userProfile '.agents\skills')
if (-not $TargetRoot) {
    $TargetRoot = $allowedRoot
}
$targetRootFull = [IO.Path]::GetFullPath($TargetRoot)
if (-not $targetRootFull.Equals($allowedRoot, [StringComparison]::OrdinalIgnoreCase)) {
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

$sourceFull = Get-NormalizedPath $Source
if (-not (Test-Path -LiteralPath $sourceFull -PathType Container)) {
    throw "Source directory does not exist: $Source"
}
$sourceItem = Get-Item -LiteralPath $sourceFull -Force
Assert-NotReparsePoint -Item $sourceItem -Label 'Source root'

$sourceSkill = Join-Path $sourceFull 'SKILL.md'
$packageDirectories = @()
if (Test-Path -LiteralPath $sourceSkill -PathType Leaf) {
    $packageDirectories = @($sourceItem)
} else {
    foreach ($candidate in @(Get-ChildItem -LiteralPath $sourceFull -Directory -Force -ErrorAction Stop | Sort-Object Name)) {
        Assert-NotReparsePoint -Item $candidate -Label 'Source package candidate'
        $candidateSkill = Join-Path $candidate.FullName 'SKILL.md'
        if (Test-Path -LiteralPath $candidateSkill -PathType Leaf) {
            $candidateSkillItem = Get-Item -LiteralPath $candidateSkill -Force
            Assert-NotReparsePoint -Item $candidateSkillItem -Label 'Source SKILL.md'
            $packageDirectories += $candidate
        }
    }
}
if ($packageDirectories.Count -eq 0) {
    throw "No direct skill packages containing SKILL.md were found in $sourceFull"
}

$seenNames = @{}
$packages = @()
foreach ($packageDirectory in $packageDirectories) {
    Assert-NotReparsePoint -Item $packageDirectory -Label 'Source package'
    $skillFile = Join-Path $packageDirectory.FullName 'SKILL.md'
    $skillName = Get-SkillName $skillFile
    if ($packageDirectory.Name -ne $skillName) {
        throw "Package folder '$($packageDirectory.Name)' must match frontmatter name '$skillName'."
    }
    $nameKey = $skillName.ToLowerInvariant()
    if ($seenNames.ContainsKey($nameKey)) {
        throw "Duplicate skill name in source: $skillName"
    }
    $seenNames[$nameKey] = $true

    $destination = Join-Path $targetRootFull $packageDirectory.Name
    if (Test-Path -LiteralPath $destination) {
        throw "Refusing to overwrite existing skill package: $destination"
    }
    $packageFiles = @(Get-SafePackageFiles -PackageDirectory $packageDirectory)
    if ($packageFiles.Count -eq 0) {
        throw "Skill package contains no files: $($packageDirectory.FullName)"
    }
    $packages += [ordered]@{
        name = $skillName
        source = $packageDirectory.FullName
        destination = $destination
        fileCount = $packageFiles.Count
        files = $packageFiles
    }
}

$manifestPackages = @(
    $packages | ForEach-Object {
        [ordered]@{
            name = $_.name
            source = $_.source
            destination = $_.destination
            fileCount = $_.fileCount
            files = @(
                $_.files | ForEach-Object {
                    [ordered]@{ path = $_.path; sha256 = $_.sha256; length = $_.length }
                }
            )
        }
    }
)
$manifest = [ordered]@{
    schemaVersion = 6
    state = 'planned'
    createdAt = (Get-Date).ToUniversalTime().ToString('o')
    source = $sourceFull
    targetRoot = $targetRootFull
    manifestPath = $manifestOut
    packageCount = $packages.Count
    packages = $manifestPackages
    appliedDestinations = @()
    pendingDestination = $null
    interruptedDestination = $null
    stagingPath = $null
    parentLockPath = $null
    targetLockPath = $null
    applyRequested = [bool]$Apply
    legacyRootsModified = $false
    rollback = 'Validate each listed destination and hash, then quarantine only that package. Never recursively delete a skill root.'
}

if (-not $Apply) {
    $manifest | ConvertTo-Json -Depth 12
    Write-Verbose 'Dry run only. No directories or files were created.'
    return
}

$approved = $true
if (-not $TestUserProfile) {
    $action = "Install $($packages.Count) Luna skill package(s) after staging and SHA-256 verification"
    $approved = $PSCmdlet.ShouldProcess($targetRootFull, $action) -and
        $PSCmdlet.ShouldProcess(
            $manifestOut,
            'Create a new durable migration journal without overwriting an existing file'
        )
}
if (-not $approved) {
    $manifest | ConvertTo-Json -Depth 12
    return
}

$stage = Join-Path $targetParent ('.luna-skills-stage-' + [guid]::NewGuid().ToString('N'))
if (-not (Test-SafeStagePath -StagePath $stage -AllowedParent $targetParent)) {
    throw "Unsafe staging path: $stage"
}

$applied = @()
$manifestCreated = $false
$moveCount = 0
$parentLock = $null
$targetLock = $null
$parentLockPath = Join-Path $targetParent '.luna-skills-install.lock'
$targetLockPath = Join-Path $targetRootFull '.luna-skills-root.lock'
try {
    New-Item -ItemType Directory -Path $targetParent -Force | Out-Null
    Assert-ExistingPathChainIsDirect -Path $targetParent -StopAt $userProfile
    $parentLock = Open-ExclusiveInstallLock -Path $parentLockPath
    $manifest['parentLockPath'] = $parentLockPath
    New-Item -ItemType Directory -Path $stage | Out-Null
    $manifest['stagingPath'] = $stage

    foreach ($package in $packages) {
        $stagePackage = Join-Path $stage $package.name
        New-Item -ItemType Directory -Path $stagePackage | Out-Null
        foreach ($file in $package.files) {
            $stagedFile = Join-Path $stagePackage $file.path
            if (-not (Test-PathWithin -Candidate $stagedFile -Parent $stagePackage)) {
                throw "Staged file escaped its package root: $($file.path)"
            }
            $stagedParent = Split-Path $stagedFile -Parent
            New-Item -ItemType Directory -Path $stagedParent -Force | Out-Null
            Assert-ExistingPathChainIsDirect -Path $stagedParent -StopAt $targetParent
            Copy-VerifiedSourceFile `
                -SourcePath $file.source `
                -DestinationPath $stagedFile `
                -ExpectedSha256 $file.sha256 `
                -PackageRoot $package.source
        }
        Assert-TreeContainsNoReparse -Root $stagePackage -Label 'Staged package'
    }

    foreach ($package in $packages) {
        $stagePackage = Join-Path $stage $package.name
        foreach ($file in $package.files) {
            $stagedFile = Join-Path $stagePackage $file.path
            if (-not (Test-Path -LiteralPath $stagedFile -PathType Leaf)) {
                throw "Staging missing: $($package.name)/$($file.path)"
            }
            if ((Get-FileHash -LiteralPath $stagedFile -Algorithm SHA256).Hash -ne $file.sha256) {
                throw "Staging hash mismatch: $($package.name)/$($file.path)"
            }
        }
    }

    $manifest['state'] = 'prepared'
    $manifest['preparedAt'] = (Get-Date).ToUniversalTime().ToString('o')
    Write-Manifest -Path $manifestOut -Manifest $manifest -CreateNew
    $manifestCreated = $true

    if ($TestInjectStageJunctionTarget) {
        if ([Environment]::OSVersion.Platform -ne [PlatformID]::Win32NT) {
            throw 'TestInjectStageJunctionTarget requires Windows junction support.'
        }
        $testTarget = [IO.Path]::GetFullPath($TestInjectStageJunctionTarget)
        $temporaryRoot = [IO.Path]::GetFullPath([IO.Path]::GetTempPath())
        if (-not (Test-PathWithin -Candidate $testTarget -Parent $temporaryRoot) -or
            -not (Test-Path -LiteralPath $testTarget -PathType Container)) {
            throw 'TestInjectStageJunctionTarget must be an existing OS-temporary directory.'
        }
        $injected = Join-Path (Join-Path $stage $packages[0].name) '.test-injected-junction'
        New-Item -ItemType Junction -Path $injected -Target $testTarget | Out-Null
    }

    New-Item -ItemType Directory -Path $targetRootFull -Force | Out-Null
    Assert-ExistingPathChainIsDirect -Path $targetRootFull -StopAt $userProfile
    $targetLock = Open-ExclusiveInstallLock -Path $targetLockPath
    $manifest['targetLockPath'] = $targetLockPath
    foreach ($package in $packages) {
        $stagePackage = Join-Path $stage $package.name
        Assert-ExistingPathChainIsDirect -Path $targetRootFull -StopAt $userProfile
        Assert-TreeContainsNoReparse -Root $stagePackage -Label 'Staged package before move'
        if (-not ([IO.Path]::GetFullPath((Split-Path $package.destination -Parent))).Equals(
            $targetRootFull,
            [StringComparison]::OrdinalIgnoreCase
        )) {
            throw "Destination parent changed unexpectedly: $($package.destination)"
        }
        if (Test-Path -LiteralPath $package.destination) {
            throw "Destination appeared during apply: $($package.destination)"
        }

        $manifest['state'] = 'applying'
        $manifest['pendingDestination'] = $package.destination
        Write-Manifest -Path $manifestOut -Manifest $manifest

        # Directory.Move is an atomic rename on the same volume and fails if the
        # destination appears; unlike Move-Item it never moves inside that directory.
        [IO.Directory]::Move($stagePackage, $package.destination)
        Assert-ExistingPathChainIsDirect -Path $package.destination -StopAt $userProfile
        Assert-TreeContainsNoReparse -Root $package.destination -Label 'Installed package after move'
        foreach ($file in $package.files) {
            $installedFile = Join-Path $package.destination $file.path
            $installedSnapshot = Read-VerifiedSourceSnapshot `
                -Path $installedFile `
                -PackageRoot $package.destination
            if ($installedSnapshot.sha256 -ne $file.sha256) {
                throw "Installed package hash mismatch after atomic move: $($package.name)/$($file.path)"
            }
        }
        $moveCount++
        if ($TestFailAfterMoves -ge 0 -and $moveCount -ge $TestFailAfterMoves) {
            throw "Injected failure after move $moveCount"
        }

        $applied += $package.destination
        $manifest['appliedDestinations'] = @($applied)
        $manifest['pendingDestination'] = $null
        Write-Manifest -Path $manifestOut -Manifest $manifest
    }

    Remove-EmptyOwnedStage -StagePath $stage -AllowedParent $targetParent | Out-Null
    $manifest['stagingPath'] = $null
    $manifest['state'] = 'applied'
    $manifest['appliedAt'] = (Get-Date).ToUniversalTime().ToString('o')
    $manifest['pendingDestination'] = $null
    Write-Manifest -Path $manifestOut -Manifest $manifest
    $manifest | ConvertTo-Json -Depth 12
} catch {
    $originalError = $_.Exception.Message
    if ($manifestCreated) {
        $pending = [string]$manifest['pendingDestination']
        if ($pending -and (Test-Path -LiteralPath $pending -PathType Container) -and
            $applied -notcontains $pending) {
            $applied += $pending
            $manifest['interruptedDestination'] = $pending
        }
        $manifest['state'] = if ($applied.Count -gt 0) { 'partial' } else { 'failed' }
        $manifest['failedAt'] = (Get-Date).ToUniversalTime().ToString('o')
        $manifest['failure'] = $originalError
        $manifest['appliedDestinations'] = @($applied)
        if (Test-Path -LiteralPath $stage) {
            $manifest['stagingPath'] = $stage
        }
        try {
            Write-Manifest -Path $manifestOut -Manifest $manifest
        } catch {
            Write-Warning "Could not update the durable recovery journal: $manifestOut"
        }
    }
    throw "Migration stopped safely. Inspect the exact recovery journal '$manifestOut'. $originalError"
} finally {
    if ($targetLock) {
        $targetLock.Dispose()
        if (Test-Path -LiteralPath $targetLockPath -PathType Leaf) {
            [IO.File]::Delete($targetLockPath)
        }
    }
    if (Test-Path -LiteralPath $stage) {
        try {
            Remove-EmptyOwnedStage -StagePath $stage -AllowedParent $targetParent | Out-Null
        } catch {
            Write-Warning "Preserved non-empty or unsafe staging path for journal-based inspection: $stage"
        }
    }
    if ($parentLock) {
        $parentLock.Dispose()
        if (Test-Path -LiteralPath $parentLockPath -PathType Leaf) {
            [IO.File]::Delete($parentLockPath)
        }
    }
}
