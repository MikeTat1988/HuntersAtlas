param(
    [string]$Python = $env:ATLAS_PYTHON
)

$ErrorActionPreference = 'Stop'
if (-not $Python) { throw 'Pass -Python with the full path to your build Python interpreter.' }
$sourceRoot = $PSScriptRoot
$pythonBin = Split-Path -Parent (Resolve-Path $Python).Path
$env:PATH = "$pythonBin;$env:PATH"
$dependencyRoot = Join-Path $sourceRoot '.builddeps'
$buildRoot = Join-Path $sourceRoot 'build'
$pythonPath = $env:PYTHONPATH
if ($pythonPath) {
    $env:PYTHONPATH = "$dependencyRoot;$sourceRoot;$pythonPath"
} else {
    $env:PYTHONPATH = "$dependencyRoot;$sourceRoot"
}

& $Python -c "import PyInstaller; print(PyInstaller.__version__)"
if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller is not installed in the selected build environment."
}

$pyArgs = @(
    '-m', 'PyInstaller', '--noconfirm', '--clean', '--onefile', '--console',
    '--name', 'AtlasSetup',
    '--distpath', (Join-Path $buildRoot 'installer-dist'),
    '--workpath', (Join-Path $buildRoot 'installer-work'),
    '--specpath', (Join-Path $buildRoot 'installer-spec'),
    '--paths', $sourceRoot,
    (Join-Path $sourceRoot 'atlas_install.py')
)
& $Python @pyArgs
if ($LASTEXITCODE -ne 0) {
    throw "Frozen Atlas installer build failed with exit code $LASTEXITCODE"
}

$installerNotices = Join-Path $buildRoot 'installer-dist/THIRD-PARTY-NOTICES'
& $Python (Join-Path $sourceRoot 'collect_build_notices.py') --output $installerNotices
if ($LASTEXITCODE -ne 0) { throw 'Could not collect the selected interpreter notices.' }

& $Python (Join-Path $sourceRoot 'verify_frozen_installer.py')
if ($LASTEXITCODE -ne 0) {
    throw "Frozen Atlas installer verification failed with exit code $LASTEXITCODE"
}
Write-Host "Self-contained installer staged at $(Join-Path $buildRoot 'installer-dist/AtlasSetup.exe')"
