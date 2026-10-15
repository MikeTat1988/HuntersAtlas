@echo off
setlocal
title Hunter's Atlas 1.0 - Install
if not exist "%~dp0installer\AtlasSetup.exe" goto source_only
if not exist "%~dp0manifest.json" goto source_only
set "PSModulePath=%SystemRoot%\System32\WindowsPowerShell\v1.0\Modules"
"%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe" -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0installer\Install.ps1" %*
set "atlasExit=%errorlevel%"
if not "%atlasExit%"=="0" echo Installation stopped. Read the message above.
pause
exit /b %atlasExit%
:source_only
echo This folder contains source code, not the installable Atlas package.
echo Download Hunters-Atlas-1.0.zip from:
echo https://github.com/MikeTat1988/HuntersAtlas/releases/tag/v1.0
echo Extract that ZIP and double-click its Install.cmd.
pause
exit /b 2
