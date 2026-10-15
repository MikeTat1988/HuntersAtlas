# SPDX-License-Identifier: GPL-2.0-or-later
param([string]$LauncherRoot, [string]$RollbackRoot, [string]$GameRoot)
$ErrorActionPreference = 'Stop'
$releaseRoot = Split-Path -Parent $PSScriptRoot
$setup = Join-Path $releaseRoot 'installer\AtlasSetup.exe'
$adapter = Join-Path $releaseRoot 'adapter'
if (-not (Test-Path -LiteralPath $setup -PathType Leaf)) {
    throw 'This is source code. Download Hunters-Atlas-1.0.zip from GitHub Releases, extract it, and double-click Install.cmd.'
}
$requiredAtlasPaths = @('manifest.json', 'runtime', 'art', 'maps', 'settings', 'tools')
foreach ($relativePath in $requiredAtlasPaths) {
    $path = Join-Path $releaseRoot $relativePath
    $expectedType = if ($relativePath -eq 'manifest.json') { 'Leaf' } else { 'Container' }
    if (-not (Test-Path -LiteralPath $path -PathType $expectedType)) {
        throw "The extracted release is incomplete: '$relativePath' is missing. Extract the full Hunters-Atlas-1.0.zip archive and double-click Install.cmd."
    }
}
$atlas = $releaseRoot
if (-not $LauncherRoot) { $LauncherRoot = (Read-Host 'Existing launcher folder containing Bloodborne.exe').Trim().Trim('"') }
$LauncherRoot = (Resolve-Path -LiteralPath $LauncherRoot).Path
if (-not (Test-Path -LiteralPath (Join-Path $LauncherRoot 'Bloodborne.exe') -PathType Leaf)) { throw 'Bloodborne.exe was not found in that folder.' }
$existingReceipt = Join-Path $LauncherRoot 'atlas-install-receipt.json'
if (Test-Path -LiteralPath $existingReceipt -PathType Leaf) {
    $existing = Get-Content -LiteralPath $existingReceipt -Raw | ConvertFrom-Json
    if ($existing.state -eq 'installed') { throw 'Atlas is already installed here. Close the launcher and run Uninstall.cmd from the installed package before installing again.' }
}
if (-not $RollbackRoot) { $RollbackRoot = Join-Path (Split-Path -Parent $LauncherRoot) ('HuntersAtlas-rollback-' + (Get-Date -Format 'yyyyMMdd-HHmmss')) }
$settingsRoot = if ($env:BB_LAUNCHER_SETTINGS_ROOT) { $env:BB_LAUNCHER_SETTINGS_ROOT } else { Join-Path $env:APPDATA 'bbport-launcher' }
$settingsFile = Join-Path $settingsRoot 'settings.json'
if (-not $GameRoot -and (Test-Path -LiteralPath $settingsFile -PathType Leaf)) {
    try { $GameRoot = (Get-Content -LiteralPath $settingsFile -Raw | ConvertFrom-Json).game_dir } catch { throw "Launcher settings could not be read: $settingsFile" }
}
if (-not $GameRoot -or -not (Test-Path -LiteralPath (Join-Path $GameRoot 'eboot.bin') -PathType Leaf)) {
    $GameRoot = (Read-Host 'Game folder containing eboot.bin').Trim().Trim('"')
}
if (-not (Test-Path -LiteralPath (Join-Path $GameRoot 'eboot.bin') -PathType Leaf)) { throw 'eboot.bin was not found in that game folder.' }
$GameRoot = (Resolve-Path -LiteralPath $GameRoot).Path
Write-Host 'Close Bloodborne and its launcher before continuing.'
Write-Host "Launcher: $LauncherRoot"
Write-Host "Atlas: $atlas"
Write-Host "Original launcher backup: $RollbackRoot"
Write-Host 'Preparing maps can take about 10 minutes. Progress and details are saved to the rollback folder.'
& $setup install --launcher-root $LauncherRoot --adapter-root $adapter --atlas-folder $atlas --rollback-root $RollbackRoot --game-dir $GameRoot
if ($LASTEXITCODE -ne 0) { throw "Installation stopped (exit $LASTEXITCODE). No success is claimed; read the installer message above." }
$stateRoot = if ($env:ATLAS_INSTALL_STATE_ROOT) { $env:ATLAS_INSTALL_STATE_ROOT } else { Join-Path $env:LOCALAPPDATA 'HuntersAtlas' }
try {
    New-Item -ItemType Directory -Path $stateRoot -Force | Out-Null
    $location = Join-Path $stateRoot 'install-location.json'
    $temporary = Join-Path $stateRoot 'install-location.json.tmp'
    @{ atlas_folder = $atlas; launcher_root = $LauncherRoot; receipt = $existingReceipt } |
        ConvertTo-Json | Set-Content -LiteralPath $temporary -Encoding UTF8
    Move-Item -LiteralPath $temporary -Destination $location -Force
} catch {
    Write-Warning "Installed, but could not save the automatic uninstall location: $_"
}
Write-Host "Installed. Open your usual launcher, enable Hunter's Atlas, and press Play."
