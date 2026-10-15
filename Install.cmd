@echo off
setlocal
title Hunter's Atlas Lite - Install
if not exist "%~dp0manifest.json" (
 echo This is source code. Download the Play ZIP from https://github.com/MikeTat1988/HuntersAtlas/releases/latest
 pause
 exit /b 2
)
set "PSModulePath=%SystemRoot%\System32\WindowsPowerShell\v1.0\Modules"
"%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe" -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0installer\Manage-Lite.ps1" -Mode Install %*
set "liteExit=%errorlevel%"
pause
exit /b %liteExit%
