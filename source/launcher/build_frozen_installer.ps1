param(
    [string]$Python = (Join-Path $PSScriptRoot '..\..\..\tools\map-build\msys64\clang64\bin\python.exe')
)

$ErrorActionPreference = 'Stop'
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
New-Item -ItemType Directory -Path $installerNotices -Force | Out-Null
Copy-Item (Join-Path $pythonBin '../share/licenses/python3.14/LICENSE') `
    (Join-Path $installerNotices 'Python-3.14.8-PSF-2.0.txt')
Copy-Item (Join-Path $pythonBin '../lib/tk8.6/demos/license.terms') `
    (Join-Path $installerNotices 'Tcl-Tk-license.terms')

& $Python (Join-Path $sourceRoot 'verify_frozen_installer.py')
if ($LASTEXITCODE -ne 0) {
    throw "Frozen Atlas installer verification failed with exit code $LASTEXITCODE"
}
Write-Host "Self-contained installer staged at $(Join-Path $buildRoot 'installer-dist/AtlasSetup.exe')"
