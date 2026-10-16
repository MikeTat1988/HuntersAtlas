@echo off
setlocal
title Hunter's Atlas - Combined update
if not exist "%~dp0manifest.json" (
 echo Download and extract the complete Atlas player package before updating.
 pause
 exit /b 2
)
set "PSModulePath=%SystemRoot%\System32\WindowsPowerShell\v1.0\Modules"
"%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe" -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0installer\Update-Atlas.ps1" %*
set "atlasUpdateExit=%errorlevel%"
pause
exit /b %atlasUpdateExit%
