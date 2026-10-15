# SPDX-License-Identifier: GPL-2.0-or-later
param([string]$LauncherRoot)
$ErrorActionPreference = 'Stop'
$releaseRoot = Split-Path -Parent $PSScriptRoot
$setup = Join-Path $releaseRoot 'installer\AtlasSetup.exe'
if (-not (Test-Path -LiteralPath $setup -PathType Leaf)) { throw 'Double-click Uninstall.cmd in the extracted Hunter''s Atlas 1.0 package.' }
if (-not $LauncherRoot) { $LauncherRoot = (Read-Host 'Launcher folder containing atlas-install-receipt.json').Trim().Trim('"') }
$LauncherRoot = (Resolve-Path -LiteralPath $LauncherRoot).Path
$receipt = Join-Path $LauncherRoot 'atlas-install-receipt.json'
if (-not (Test-Path -LiteralPath $receipt -PathType Leaf)) { throw 'No Atlas install receipt found in that folder.' }
& $setup uninstall --receipt $receipt
if ($LASTEXITCODE -ne 0) { throw "Uninstall stopped (exit $LASTEXITCODE). Preserve the receipt and rollback folder and read the message above." }
Write-Host 'The original launcher was restored. Your game, saves and settings remain in place.'
