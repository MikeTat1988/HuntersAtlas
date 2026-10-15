# SPDX-License-Identifier: GPL-2.0-or-later
param([string]$LauncherRoot)
$ErrorActionPreference = 'Stop'
$releaseRoot = Split-Path -Parent $PSScriptRoot
$setup = Join-Path $releaseRoot 'installer\AtlasSetup.exe'
if (-not (Test-Path -LiteralPath $setup -PathType Leaf)) { throw 'Double-click Uninstall.cmd in the extracted Hunter''s Atlas 1.0 package.' }
$releaseRoot = (Resolve-Path -LiteralPath $releaseRoot).Path
$stateRoot = if ($env:ATLAS_INSTALL_STATE_ROOT) { $env:ATLAS_INSTALL_STATE_ROOT } else { Join-Path $env:LOCALAPPDATA 'HuntersAtlas' }
$location = Join-Path $stateRoot 'install-location.json'
function Test-AtlasReceipt([string]$folder) {
    if (-not $folder -or -not (Test-Path -LiteralPath $folder -PathType Container)) { return $false }
    $candidate = Join-Path $folder 'atlas-install-receipt.json'
    if (-not (Test-Path -LiteralPath $candidate -PathType Leaf)) { return $false }
    try {
        $record = Get-Content -LiteralPath $candidate -Raw | ConvertFrom-Json
        return $record.state -eq 'installed' -and
            [string]::Equals($record.atlas_folder, $releaseRoot, [StringComparison]::OrdinalIgnoreCase) -and
            [string]::Equals($record.launcher_root, (Resolve-Path -LiteralPath $folder).Path, [StringComparison]::OrdinalIgnoreCase)
    } catch { return $false }
}
if (-not $LauncherRoot) {
    $candidates = @()
    if (Test-Path -LiteralPath $location -PathType Leaf) {
        try {
            $saved = Get-Content -LiteralPath $location -Raw | ConvertFrom-Json
            if ([string]::Equals($saved.atlas_folder, $releaseRoot, [StringComparison]::OrdinalIgnoreCase) -and
                (Test-AtlasReceipt $saved.launcher_root)) { $candidates += $saved.launcher_root }
        } catch { Write-Warning 'Saved uninstall location could not be read; checking nearby launcher folders.' }
    }
    if (-not $candidates) {
        $parent = Split-Path -Parent $releaseRoot
        if (Test-AtlasReceipt $parent) { $candidates += $parent }
        foreach ($folder in (Get-ChildItem -LiteralPath $parent -Directory -ErrorAction Stop)) {
            if (Test-AtlasReceipt $folder.FullName) { $candidates += $folder.FullName }
        }
    }
    if ($candidates.Count -ne 1) { throw 'Could not uniquely find this Atlas installation. Run Uninstall.cmd with the launcher folder containing atlas-install-receipt.json.' }
    $LauncherRoot = $candidates[0]
}
$LauncherRoot = (Resolve-Path -LiteralPath $LauncherRoot).Path
$receipt = Join-Path $LauncherRoot 'atlas-install-receipt.json'
if (-not (Test-AtlasReceipt $LauncherRoot)) { throw 'No installed Atlas receipt for this package was found in that launcher folder.' }
Write-Host "Launcher: $LauncherRoot"
& $setup uninstall --receipt $receipt
if ($LASTEXITCODE -ne 0) { throw "Uninstall stopped (exit $LASTEXITCODE). Preserve the receipt and rollback folder and read the message above." }
if (Test-Path -LiteralPath $location -PathType Leaf) {
    try {
        $saved = Get-Content -LiteralPath $location -Raw | ConvertFrom-Json
        if ([string]::Equals($saved.atlas_folder, $releaseRoot, [StringComparison]::OrdinalIgnoreCase) -and
            [string]::Equals($saved.launcher_root, $LauncherRoot, [StringComparison]::OrdinalIgnoreCase)) {
            Remove-Item -LiteralPath $location -Force
        }
    } catch { Write-Warning "Uninstalled, but could not clear the saved uninstall location: $_" }
}
Write-Host 'The original launcher was restored. Your game, saves and settings remain in place.'
