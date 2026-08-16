[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][string]$Source
)

$ErrorActionPreference = 'Stop'
$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$discovery = Join-Path $scriptRoot 'Test-LunaSkillDiscovery.ps1'
$installer = Join-Path $scriptRoot 'Install-LunaSkillsUserScope.ps1'

foreach ($script in @($discovery, $installer)) {
    $tokens = $null
    $parseErrors = $null
    [void][Management.Automation.Language.Parser]::ParseFile(
        $script,
        [ref]$tokens,
        [ref]$parseErrors
    )
    if (@($parseErrors).Count -gt 0) {
        throw "PowerShell parse failure in $script`: $($parseErrors[0].Message)"
    }
}

$tempParent = [IO.Path]::GetFullPath([IO.Path]::GetTempPath()).TrimEnd('\', '/')
$tempPath = Join-Path $tempParent ('luna-migration-test-' + [guid]::NewGuid().ToString('N'))
$tempFull = [IO.Path]::GetFullPath($tempPath)
$tempPrefix = $tempParent + [IO.Path]::DirectorySeparatorChar
if (-not $tempFull.StartsWith($tempPrefix, [StringComparison]::OrdinalIgnoreCase)) {
    throw "Unsafe temporary test path: $tempFull"
}

$officialTarget = [IO.Path]::GetFullPath(
    (Join-Path ([Environment]::GetFolderPath('UserProfile')) '.agents\skills')
)
$targetExistedBefore = Test-Path -LiteralPath $officialTarget

try {
    New-Item -ItemType Directory -Path $tempFull | Out-Null
    $jsonPath = Join-Path $tempFull 'discovery.json'
    $markdownPath = Join-Path $tempFull 'discovery.md'
    $missingRoot = Join-Path $tempFull 'missing-skill-root'

    & $discovery `
        -SkillRoot $missingRoot `
        -OutputJson $jsonPath `
        -OutputMarkdown $markdownPath | Out-Null

    $report = Get-Content -LiteralPath $jsonPath -Raw -Encoding UTF8 | ConvertFrom-Json
    $expectedMissing = [IO.Path]::GetFullPath($missingRoot)
    if (@($report.roots) -notcontains $expectedMissing) {
        throw 'Discovery did not preserve the exact missing candidate root.'
    }
    if ((@($report.roots) -join "`n") -match 'Cannot find path') {
        throw 'Discovery serialized an ErrorRecord instead of the missing root path.'
    }
    $markdown = Get-Content -LiteralPath $markdownPath -Raw -Encoding UTF8
    if ($markdown -match '\$\(System\.') {
        throw 'Discovery Markdown contains an unevaluated object interpolation.'
    }
    if ($report.config.exists -and @($report.config.documentedKeys) -notcontains 'agents') {
        throw 'Discovery did not report the [agents] configuration section.'
    }
    if ($report.config.exists -and @($report.config.documentedKeys) -notcontains 'max_concurrent_threads_per_session') {
        throw 'Discovery did not report the canonical subagent concurrency key.'
    }

    $dryRunJson = (& $installer -Source $Source) -join "`n"
    $dryRun = $dryRunJson | ConvertFrom-Json
    if ($dryRun.state -ne 'planned' -or $dryRun.applyRequested) {
        throw 'Installer dry run did not return a planned, non-apply manifest.'
    }
    if (-not $targetExistedBefore -and (Test-Path -LiteralPath $officialTarget)) {
        throw 'Installer dry run created the official user-skill target.'
    }

    & $installer -Source $Source -Apply -WhatIf | Out-Null
    if (-not $targetExistedBefore -and (Test-Path -LiteralPath $officialTarget)) {
        throw 'Installer -WhatIf created the official user-skill target.'
    }

    $externalManifest = Join-Path $tempFull 'external-manifest.json'
    $rejectedExternalManifest = $false
    try {
        & $installer -Source $Source -ManifestPath $externalManifest | Out-Null
    } catch {
        $rejectedExternalManifest = $_.Exception.Message -match 'ManifestPath must be'
    }
    if (-not $rejectedExternalManifest) {
        throw 'Installer accepted a manifest path outside the owned target parent.'
    }

    Write-Output 'PASS: discovery and installer safety tests completed without user-scope mutation.'
} finally {
    if (Test-Path -LiteralPath $tempFull) {
        $resolved = [IO.Path]::GetFullPath($tempFull)
        if (-not $resolved.StartsWith($tempPrefix, [StringComparison]::OrdinalIgnoreCase)) {
            throw "Refusing to remove unsafe test path: $resolved"
        }
        Remove-Item -LiteralPath $resolved -Recurse -Force
    }
}
