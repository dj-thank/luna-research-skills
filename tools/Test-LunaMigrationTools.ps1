[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$Source
)

$ErrorActionPreference = 'Stop'
$toolRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$discovery = Join-Path $toolRoot 'Test-LunaSkillDiscovery.ps1'
$installer = Join-Path $toolRoot 'Install-LunaSkillsUserScope.ps1'
$temporaryRoot = [IO.Path]::GetFullPath([IO.Path]::GetTempPath()).TrimEnd('\', '/')
$testRoot = [IO.Path]::GetFullPath(
    (Join-Path $temporaryRoot ('luna-migration-test-' + [guid]::NewGuid().ToString('N')))
)

function Assert-True([bool]$Condition, [string]$Message) {
    if (-not $Condition) {
        throw $Message
    }
}

function Assert-SafeTestPath([string]$Path, [string]$ExpectedPrefix) {
    $full = [IO.Path]::GetFullPath($Path)
    $prefix = $temporaryRoot + [IO.Path]::DirectorySeparatorChar
    Assert-True -Condition $full.StartsWith($prefix, [StringComparison]::OrdinalIgnoreCase) `
        -Message "Test path escaped the OS temporary directory: $full"
    Assert-True -Condition ((Split-Path $full -Leaf) -match $ExpectedPrefix) `
        -Message "Unexpected test path name: $full"
}

function Assert-ScriptParses([string]$Path) {
    $tokens = $null
    $errors = $null
    [void][Management.Automation.Language.Parser]::ParseFile(
        $Path,
        [ref]$tokens,
        [ref]$errors
    )
    Assert-True -Condition (@($errors).Count -eq 0) -Message "PowerShell parse failure: $Path"
}

function Assert-InstalledHashes([object]$Manifest) {
    foreach ($package in @($Manifest.packages)) {
        Assert-True -Condition (Test-Path -LiteralPath $package.destination -PathType Container) `
            -Message "Installed package is missing: $($package.destination)"
        foreach ($file in @($package.files)) {
            $installed = Join-Path $package.destination $file.path
            Assert-True -Condition (Test-Path -LiteralPath $installed -PathType Leaf) `
                -Message "Installed file is missing: $installed"
            $actual = (Get-FileHash -LiteralPath $installed -Algorithm SHA256).Hash
            Assert-True -Condition ($actual -eq $file.sha256) `
                -Message "Installed file hash mismatch: $installed"
        }
    }
}

Assert-SafeTestPath -Path $testRoot -ExpectedPrefix '^luna-migration-test-[0-9a-f]{32}$'

try {
    New-Item -ItemType Directory -Path $testRoot | Out-Null

    foreach ($script in @($discovery, $installer, $MyInvocation.MyCommand.Path)) {
        Assert-ScriptParses -Path $script
    }

    $discoveryJson = Join-Path $testRoot 'discovery.json'
    $discoveryMarkdown = Join-Path $testRoot 'discovery.md'
    & $discovery `
        -SkipDefaultRoots `
        -SkillRoot (Join-Path $testRoot 'missing-skill-root') `
        -OutputJson $discoveryJson `
        -OutputMarkdown $discoveryMarkdown | Out-Null
    Assert-True -Condition (Test-Path -LiteralPath $discoveryJson -PathType Leaf) `
        -Message 'Discovery JSON output was not created.'
    Assert-True -Condition (Test-Path -LiteralPath $discoveryMarkdown -PathType Leaf) `
        -Message 'Discovery Markdown output was not created.'

    $overwriteRejected = $false
    try {
        & $discovery -OutputJson $discoveryJson | Out-Null
    } catch {
        $overwriteRejected = $_.Exception.Message -match 'overwrite'
    }
    Assert-True -Condition $overwriteRejected -Message 'Discovery accepted an existing output path.'

    $dryRunText = (& $installer -Source $Source) -join [Environment]::NewLine
    $dryRun = $dryRunText | ConvertFrom-Json
    Assert-True -Condition ($dryRun.state -eq 'planned') -Message 'Installer dry-run did not return planned state.'
    Assert-True -Condition ($dryRun.schemaVersion -eq 6) -Message 'Installer dry-run returned the wrong schema version.'

    & $installer -Source $Source -Apply -WhatIf | Out-Null

    $whatIfProfile = Join-Path $testRoot ('luna-skills-test-profile-' + [guid]::NewGuid().ToString('N'))
    & $installer `
        -Source $Source `
        -Apply `
        -TestUserProfile $whatIfProfile `
        -WhatIf | Out-Null
    Assert-True -Condition (-not (Test-Path -LiteralPath $whatIfProfile)) `
        -Message 'Disposable -WhatIf bypassed ShouldProcess and changed the filesystem.'

    $profile = Join-Path $testRoot ('luna-skills-test-profile-' + [guid]::NewGuid().ToString('N'))
    $manifestPath = Join-Path (Join-Path $profile '.agents') 'apply.json'
    $applyText = (& $installer `
        -Source $Source `
        -Apply `
        -TestUserProfile $profile `
        -ManifestPath $manifestPath) -join [Environment]::NewLine
    $applied = $applyText | ConvertFrom-Json
    Assert-True -Condition ($applied.state -eq 'applied') -Message 'Disposable real apply did not complete.'
    Assert-True -Condition ($applied.appliedDestinations.Count -eq $applied.packageCount) `
        -Message 'Applied destination count does not reconcile with package count.'
    Assert-InstalledHashes -Manifest $applied
    $durableManifest = Get-Content -LiteralPath $manifestPath -Encoding UTF8 -Raw | ConvertFrom-Json
    Assert-True -Condition ($durableManifest.state -eq 'applied') -Message 'Durable manifest is not applied.'
    Assert-True -Condition (-not (Test-Path -LiteralPath $applied.parentLockPath)) `
        -Message 'Parent install lock remained after successful apply.'
    Assert-True -Condition (-not (Test-Path -LiteralPath $applied.targetLockPath)) `
        -Message 'Target install lock remained after successful apply.'

    $existingDestinationRejected = $false
    try {
        & $installer -Source $Source -Apply -TestUserProfile $profile | Out-Null
    } catch {
        $existingDestinationRejected = $_.Exception.Message -match 'existing skill package'
    }
    Assert-True -Condition $existingDestinationRejected `
        -Message 'Installer accepted an existing destination package.'

    $partialProfile = Join-Path $testRoot ('luna-skills-test-profile-' + [guid]::NewGuid().ToString('N'))
    $partialManifestPath = Join-Path (Join-Path $partialProfile '.agents') 'partial.json'
    $injectedFailureObserved = $false
    try {
        & $installer `
            -Source $Source `
            -Apply `
            -TestUserProfile $partialProfile `
            -ManifestPath $partialManifestPath `
            -TestFailAfterMoves 1 | Out-Null
    } catch {
        $injectedFailureObserved = $_.Exception.Message -match 'Injected failure after move 1'
    }
    Assert-True -Condition $injectedFailureObserved -Message 'Injected move failure was not observed.'
    $partial = Get-Content -LiteralPath $partialManifestPath -Encoding UTF8 -Raw | ConvertFrom-Json
    Assert-True -Condition ($partial.state -eq 'partial') -Message 'Partial install did not preserve partial state.'
    Assert-True -Condition ($partial.appliedDestinations.Count -eq 1) `
        -Message 'Partial install did not reconcile the moved destination.'
    Assert-True -Condition ([string]$partial.interruptedDestination -eq [string]$partial.appliedDestinations[0]) `
        -Message 'Partial install did not identify the interrupted destination.'
    Assert-True -Condition (Test-Path -LiteralPath $partial.interruptedDestination -PathType Container) `
        -Message 'Interrupted destination recorded in the journal does not exist.'

    $externalManifestRejected = $false
    try {
        & $installer `
            -Source $Source `
            -TestUserProfile (Join-Path $testRoot ('luna-skills-test-profile-' + [guid]::NewGuid().ToString('N'))) `
            -ManifestPath (Join-Path $testRoot 'outside.json') | Out-Null
    } catch {
        $externalManifestRejected = $_.Exception.Message -match 'ManifestPath'
    }
    Assert-True -Condition $externalManifestRejected -Message 'Installer accepted an external manifest path.'

    if ([Environment]::OSVersion.Platform -eq [PlatformID]::Win32NT) {
        $outside = Join-Path $testRoot 'outside-package'
        $linkSource = Join-Path $testRoot 'linked-source'
        New-Item -ItemType Directory -Path $outside | Out-Null
        New-Item -ItemType Directory -Path $linkSource | Out-Null
        Set-Content -LiteralPath (Join-Path $outside 'SKILL.md') -Encoding UTF8 -Value @(
            '---',
            'name: linked-skill',
            'description: test only',
            '---'
        )
        $junction = Join-Path $linkSource 'linked-skill'
        New-Item -ItemType Junction -Path $junction -Target $outside | Out-Null
        $reparseRejected = $false
        try {
            & $installer -Source $linkSource | Out-Null
        } catch {
            $reparseRejected = $_.Exception.Message -match 'reparse point|symlink|junction'
        }
        Assert-True -Condition $reparseRejected -Message 'Installer accepted a reparse-point source package.'

        $nestedSource = Join-Path $testRoot 'nested-source'
        $nestedPackage = Join-Path $nestedSource 'nested-skill'
        $nestedOutside = Join-Path $testRoot 'nested-outside'
        New-Item -ItemType Directory -Path $nestedPackage -Force | Out-Null
        New-Item -ItemType Directory -Path $nestedOutside -Force | Out-Null
        Set-Content -LiteralPath (Join-Path $nestedPackage 'SKILL.md') -Encoding UTF8 -Value @(
            '---',
            'name: nested-skill',
            'description: test only',
            '---'
        )
        Set-Content -LiteralPath (Join-Path $nestedOutside 'secret.txt') -Encoding UTF8 -Value 'must-not-be-hashed'
        $nestedJunction = Join-Path $nestedPackage 'nested-link'
        New-Item -ItemType Junction -Path $nestedJunction -Target $nestedOutside | Out-Null
        $nestedRejected = $false
        try {
            & $installer -Source $nestedSource | Out-Null
        } catch {
            $nestedRejected = $_.Exception.Message -match 'reparse point|symlink|junction'
        }
        Assert-True -Condition $nestedRejected -Message 'Installer accepted a nested reparse-point source.'

        $nestedDiscoveryPath = Join-Path $testRoot 'nested-discovery.json'
        & $discovery -SkipDefaultRoots -SkillRoot $nestedSource -RepoRoot $testRoot -OutputJson $nestedDiscoveryPath | Out-Null
        $nestedDiscovery = Get-Content -LiteralPath $nestedDiscoveryPath -Encoding UTF8 -Raw | ConvertFrom-Json
        $nestedRow = @($nestedDiscovery.skills | Where-Object { $_.path -eq $nestedPackage })[0]
        Assert-True -Condition ([bool]$nestedRow) -Message 'Discovery omitted the nested reparse fixture.'
        Assert-True -Condition ([string]$nestedRow.scanError -match 'reparse point|symlink|junction') `
            -Message 'Discovery did not fail closed on a nested reparse point.'
        Assert-True -Condition (-not $nestedRow.linkTarget) -Message 'Discovery disclosed a reparse target path.'
        Assert-True -Condition (-not (($nestedRow | ConvertTo-Json -Depth 8) -match 'must-not-be-hashed')) `
            -Message 'Discovery read content behind a nested reparse point.'

        $chainTarget = Join-Path $testRoot 'root-chain-target'
        $chainSkills = Join-Path $chainTarget 'skills'
        $chainPackage = Join-Path $chainSkills 'chain-skill'
        New-Item -ItemType Directory -Path $chainPackage -Force | Out-Null
        Set-Content -LiteralPath (Join-Path $chainPackage 'SKILL.md') -Encoding UTF8 -Value @(
            '---',
            'name: chain-skill',
            'description: must not be read through a parent junction',
            '---'
        )
        $chainJunction = Join-Path $testRoot 'root-chain-link'
        New-Item -ItemType Junction -Path $chainJunction -Target $chainTarget | Out-Null
        $chainRejected = $false
        try {
            & $discovery -SkipDefaultRoots -SkillRoot (Join-Path $chainJunction 'skills') -RepoRoot $testRoot | Out-Null
        } catch {
            $chainRejected = $_.Exception.Message -match 'reparse point|symlink|junction'
        }
        Assert-True -Condition $chainRejected -Message 'Discovery followed a parent-chain junction.'
        [IO.Directory]::Delete($chainJunction, $false)

        $stageProfile = Join-Path $testRoot ('luna-skills-test-profile-' + [guid]::NewGuid().ToString('N'))
        $stageManifest = Join-Path (Join-Path $stageProfile '.agents') 'stage-junction.json'
        $stageOutside = Join-Path $testRoot 'stage-outside'
        New-Item -ItemType Directory -Path $stageOutside | Out-Null
        $sentinel = Join-Path $stageOutside 'sentinel.txt'
        Set-Content -LiteralPath $sentinel -Encoding UTF8 -Value 'preserve-me'
        $stageRejected = $false
        try {
            & $installer `
                -Source $Source `
                -Apply `
                -TestUserProfile $stageProfile `
                -ManifestPath $stageManifest `
                -TestInjectStageJunctionTarget $stageOutside | Out-Null
        } catch {
            $stageRejected = $_.Exception.Message -match 'reparse point|symlink|junction'
        }
        Assert-True -Condition $stageRejected -Message 'Installer accepted an injected staging junction.'
        Assert-True -Condition (Test-Path -LiteralPath $sentinel -PathType Leaf) `
            -Message 'Staging cleanup followed a junction and removed the outside sentinel.'
        $stageJournal = Get-Content -LiteralPath $stageManifest -Encoding UTF8 -Raw | ConvertFrom-Json
        Assert-True -Condition ($stageJournal.state -eq 'failed') -Message 'Staging junction failure was not journaled.'
        Assert-True -Condition (Test-Path -LiteralPath $stageJournal.stagingPath -PathType Container) `
            -Message 'Unsafe/non-empty stage was not preserved for exact inspection.'
        $injectedJunction = Join-Path (Join-Path $stageJournal.stagingPath $stageJournal.packages[0].name) '.test-injected-junction'
        Assert-True -Condition (Test-Path -LiteralPath $injectedJunction) -Message 'Injected junction fixture is missing.'
        [IO.Directory]::Delete($injectedJunction, $false)
    }

    Write-Output 'PASS: parse, discovery outputs, dry-run/WhatIf, disposable apply, hashes, atomic journal, partial recovery, exclusive locks, nested/staging reparse guards.'
} finally {
    if (Test-Path -LiteralPath $testRoot) {
        Assert-SafeTestPath -Path $testRoot -ExpectedPrefix '^luna-migration-test-[0-9a-f]{32}$'
        Remove-Item -LiteralPath $testRoot -Recurse -Force
    }
}
