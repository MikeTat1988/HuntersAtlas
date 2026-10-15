param([Parameter(Mandatory=$true)][string]$OutputDir)
$ErrorActionPreference='Stop'
$source=$PSScriptRoot
if(Test-Path -LiteralPath $OutputDir){throw 'OutputDir must be new; existing builds are preserved.'}
$vswhere=Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio\Installer\vswhere.exe'
if(-not(Test-Path -LiteralPath $vswhere)){throw 'Install Visual Studio Build Tools with the C++ desktop workload and Windows SDK.'}
$installation=& $vswhere -latest -products '*' -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
if(-not $installation){throw 'MSVC x64 build tools were not found.'}
$dev=Join-Path $installation 'Common7\Tools\VsDevCmd.bat'
New-Item -ItemType Directory -Path $OutputDir|Out-Null
$OutputDir=(Resolve-Path -LiteralPath $OutputDir).Path
Copy-Item -LiteralPath (Join-Path $source 'bloodborne.ico') -Destination (Join-Path $OutputDir 'bloodborne.ico')
[IO.File]::WriteAllText((Join-Path $OutputDir 'launcher.rc'),'1 ICON "bloodborne.ico"')
$command="@echo off`r`ncall `"$dev`" -arch=x64 -no_logo`r`nif errorlevel 1 exit /b 1`r`nrc.exe /nologo /fo launcher.res launcher.rc`r`nif errorlevel 1 exit /b 1`r`ncl.exe /nologo /O1 /MT `"$(Join-Path $source 'launcher_wrapper.c')`" /link /SUBSYSTEM:WINDOWS /OUT:AtlasLiteLauncher.exe launcher.res user32.lib kernel32.lib`r`nexit /b %errorlevel%`r`n"
[IO.File]::WriteAllText((Join-Path $OutputDir 'build.cmd'),$command,[Text.Encoding]::ASCII)
Push-Location $OutputDir
try{& $env:ComSpec /d /c build.cmd;if($LASTEXITCODE -ne 0){throw 'Wrapper build failed.'}}finally{Pop-Location}
Get-FileHash -LiteralPath (Join-Path $OutputDir 'AtlasLiteLauncher.exe') -Algorithm SHA256
