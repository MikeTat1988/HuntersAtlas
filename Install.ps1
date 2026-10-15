# SPDX-License-Identifier: GPL-2.0-or-later
param([string]$LauncherRoot, [string]$RollbackRoot)
$ErrorActionPreference = 'Stop'
$releaseRoot = $PSScriptRoot
$setup = Join-Path $releaseRoot 'installer\AtlasSetup.exe'
$adapter = Join-Path $releaseRoot 'adapter'
$atlas = Join-Path $releaseRoot "Hunter's Atlas"
if (-not (Test-Path -LiteralPath $setup -PathType Leaf)) {
    throw 'This is the source checkout. Download and extract the ready-to-install beta ZIP from GitHub Releases, then run its Install.ps1.'
}
if (-not $LauncherRoot) { $LauncherRoot = (Read-Host 'Existing launcher folder containing Bloodborne.exe').Trim().Trim('"') }
$LauncherRoot = (Resolve-Path -LiteralPath $LauncherRoot).Path
if (-not (Test-Path -LiteralPath (Join-Path $LauncherRoot 'Bloodborne.exe') -PathType Leaf)) { throw 'Bloodborne.exe was not found in that folder.' }
$existingReceipt = Join-Path $LauncherRoot 'atlas-install-receipt.json'
if (Test-Path -LiteralPath $existingReceipt -PathType Leaf) {
    $existing = Get-Content -LiteralPath $existingReceipt -Raw | ConvertFrom-Json
    if ($existing.state -eq 'installed') { throw 'Atlas is already installed here. For an upgrade, first run Uninstall.ps1 from the previous release to restore the stock launcher; then run this installer.' }
}
if (-not $RollbackRoot) { $RollbackRoot = Join-Path (Split-Path -Parent $LauncherRoot) ('HuntersAtlas-rollback-' + (Get-Date -Format 'yyyyMMdd-HHmmss')) }
Write-Host 'Close Bloodborne and its launcher before continuing.'
Write-Host "Launcher: $LauncherRoot"
Write-Host "Atlas: $atlas"
Write-Host "Original launcher backup: $RollbackRoot"
& $setup install --launcher-root $LauncherRoot --adapter-root $adapter --atlas-folder $atlas --rollback-root $RollbackRoot
if ($LASTEXITCODE -ne 0) { throw "Installation stopped (exit $LASTEXITCODE). No success is claimed; read the installer message above." }
Write-Host "Installed. Open your usual launcher, browse to '$atlas' in Mods & patches, prepare maps, enable Atlas and press Play."
