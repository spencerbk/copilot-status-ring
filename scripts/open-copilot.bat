@echo off
setlocal

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0open-copilot.ps1"
set "exit_code=%ERRORLEVEL%"

if not "%exit_code%"=="0" (
    echo.
    echo open-copilot.ps1 failed with exit code %exit_code%.
    pause
)

exit /b %exit_code%
