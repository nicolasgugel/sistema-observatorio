@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0run_daily_refresh_and_publish.ps1"
exit /b %ERRORLEVEL%
