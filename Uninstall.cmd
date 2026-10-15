@echo off
setlocal
title Hunter's Atlas - Uninstall
if not exist "%~dp0manifest.json" (
 echo Run Uninstall.cmd from the extracted Play ZIP used during installation.
 pause
 exit /b 2
)
set "PSModulePath=%SystemRoot%\System32\WindowsPowerShell\v1.0\Modules"
"%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe" -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0installer\Manage-Atlas.ps1" -Mode Uninstall %*
set "liteExit=%errorlevel%"
pause
exit /b %liteExit%
