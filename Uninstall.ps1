# SPDX-License-Identifier: GPL-2.0-or-later
param([string]$LauncherRoot)
$ErrorActionPreference = 'Stop'
$releaseRoot = $PSScriptRoot
$setup = Join-Path $releaseRoot 'installer\AtlasSetup.exe'
if (-not (Test-Path -LiteralPath $setup -PathType Leaf)) { throw 'Run Uninstall.ps1 from the root of the extracted v1.4.0-beta2 release, beside installer\ and adapter\.' }
if (-not $LauncherRoot) { $LauncherRoot = (Read-Host 'Launcher folder containing atlas-install-receipt.json').Trim().Trim('"') }
$LauncherRoot = (Resolve-Path -LiteralPath $LauncherRoot).Path
$receipt = Join-Path $LauncherRoot 'atlas-install-receipt.json'
if (-not (Test-Path -LiteralPath $receipt -PathType Leaf)) { throw 'No Atlas install receipt found in that folder.' }
& $setup uninstall --receipt $receipt
if ($LASTEXITCODE -ne 0) { throw "Uninstall stopped (exit $LASTEXITCODE). Preserve the receipt and rollback folder and read the message above." }
Write-Host 'The original launcher was restored. Your game, saves and settings remain in place.'
