param(
    [string]$Python = $env:ATLAS_PYTHON
)

$ErrorActionPreference = 'Stop'
if (-not $Python) { throw 'Pass -Python with the full path to your build Python interpreter.' }
$sourceRoot = $PSScriptRoot
$pythonBin = Split-Path -Parent (Resolve-Path $Python).Path
$env:PATH = "$pythonBin;$env:PATH"
$buildRoot = Join-Path $sourceRoot 'build'
$dependencyRoot = Join-Path $sourceRoot '.builddeps'
$pythonPath = $env:PYTHONPATH
if ($pythonPath) {
    $env:PYTHONPATH = "$dependencyRoot;$sourceRoot;$pythonPath"
} else {
    $env:PYTHONPATH = "$dependencyRoot;$sourceRoot"
}

& $Python -c "import PyInstaller; print(PyInstaller.__version__)"
if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller is not installed. Run: `"$Python`" -m pip install --target `"$dependencyRoot`" pyinstaller"
}

New-Item -ItemType Directory -Path $buildRoot -Force | Out-Null
$pyArgs = @(
    '-m', 'PyInstaller', '--noconfirm', '--clean', '--windowed',
    '--name', 'Bloodborne',
    '--contents-directory', '_atlas_internal',
    '--icon', (Join-Path $sourceRoot 'bloodborne.ico'),
    '--distpath', (Join-Path $buildRoot 'dist'),
    '--workpath', (Join-Path $buildRoot 'work'),
    '--specpath', (Join-Path $buildRoot 'spec'),
    '--paths', $sourceRoot,
    '--hidden-import', 'bbport_lang_more',
    '--hidden-import', 'bbport_steam',
    '--hidden-import', 'atlas_addon',
    '--hidden-import', 'tkinter',
    '--hidden-import', 'tkinter.ttk',
    '--hidden-import', 'tkinter.filedialog',
    '--hidden-import', 'tkinter.messagebox',
    # run.py loads preparation scripts dynamically; patches.py needs XML support.
    '--hidden-import', 'xml.etree.ElementTree',
    '--collect-all', 'PIL',
    (Join-Path $sourceRoot 'bbport_launcher_win.py')
)
& $Python @pyArgs
if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller failed with exit code $LASTEXITCODE"
}

$package = Join-Path $buildRoot 'dist/Bloodborne'
Copy-Item (Join-Path $sourceRoot 'run.py') $package
$noticeDir = Join-Path $package '_atlas_internal/THIRD-PARTY-NOTICES'
& $Python (Join-Path $sourceRoot 'collect_build_notices.py') --output $noticeDir
if ($LASTEXITCODE -ne 0) { throw 'Could not collect the selected interpreter notices.' }
& $Python (Join-Path $sourceRoot 'verify_frozen_sources.py')
if ($LASTEXITCODE -ne 0) {
    throw "Frozen-source verification failed with exit code $LASTEXITCODE"
}
Write-Host "Frozen launcher staged at $package"
