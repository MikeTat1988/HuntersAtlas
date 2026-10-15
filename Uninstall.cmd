@echo off
setlocal
title Hunter's Atlas 1.0 - Uninstall
if not exist "%~dp0installer\AtlasSetup.exe" goto source_only
set "PSModulePath=%SystemRoot%\System32\WindowsPowerShell\v1.0\Modules"
"%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe" -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0installer\Uninstall.ps1" %*
set "atlasExit=%errorlevel%"
if not "%atlasExit%"=="0" echo Uninstall stopped. Read the message above.
pause
exit /b %atlasExit%
:source_only
echo Run Uninstall.cmd from the same extracted package used to install Atlas.
pause
exit /b 2
