@echo off
setlocal EnableDelayedExpansion

:: ============================================================
:: open-terminal.cmd
::
:: Double-click to open a Windows Terminal window for this repo.
::
:: To use in another repo: copy this file to <repo>\scripts\.
:: Optional local override: <repo>\.copilot-launcher.env with TAB_COLOR=#RRGGBB.
:: ============================================================

:: -----------------------------------------------------------
:: Deploy-provided default tab color (hex).
:: -----------------------------------------------------------
set "TAB_COLOR=#963885"

:: -----------------------------------------------------------
:: Derived values (from this script's filesystem location)
:: -----------------------------------------------------------
for %%I in ("%~dp0..") do set "REPO_DIR=%%~fI"
for %%I in ("%~dp0..") do set "REPO_NAME=%%~nxI"

:: -----------------------------------------------------------
:: Repo-local override (optional; exact TAB_COLOR=#RRGGBB lines only)
:: -----------------------------------------------------------
set "LAUNCHER_ENV=%REPO_DIR%\.copilot-launcher.env"
if exist "%LAUNCHER_ENV%" (
    for /f "usebackq tokens=1,* delims==" %%A in (`findstr /R /C:"^TAB_COLOR=#[0-9A-Fa-f][0-9A-Fa-f][0-9A-Fa-f][0-9A-Fa-f][0-9A-Fa-f][0-9A-Fa-f]$" "%LAUNCHER_ENV%"`) do (
        if "%%A"=="TAB_COLOR" set "TAB_COLOR=%%B"
    )
)

:: -----------------------------------------------------------
:: Auto-install WT fragment on first run (idempotent)
:: -----------------------------------------------------------
set "FRAGMENT_DIR=%LOCALAPPDATA%\Microsoft\Windows Terminal\Fragments\MyTerminals"
set "FRAGMENT_PATH=%FRAGMENT_DIR%\%REPO_NAME%.json"

if not exist "%FRAGMENT_PATH%" (
    powershell.exe -NoProfile -Command ^
        "$dir = '%FRAGMENT_DIR%';" ^
        "if (-not (Test-Path $dir)) { New-Item -ItemType Directory -Force -Path $dir | Out-Null };" ^
        "$frag = @{" ^
        "    profiles = @(@{" ^
        "        name = '%REPO_NAME%';" ^
        "        commandline = 'cmd.exe';" ^
        "        startingDirectory = '%REPO_DIR%';" ^
        "        tabTitle = '%REPO_NAME%';" ^
        "        tabColor = '%TAB_COLOR%';" ^
        "        suppressApplicationTitle = $true" ^
        "    })" ^
        "};" ^
        "$frag | ConvertTo-Json -Depth 10 | Set-Content -Path '%FRAGMENT_PATH%' -Encoding utf8;" ^
        "Write-Host 'Installed WT fragment: %FRAGMENT_PATH%';" ^
        "Write-Host 'Restart Windows Terminal to see the profile in the dropdown menu.'"
)

:: -----------------------------------------------------------
:: Launch (always uses inline args so it works regardless of
:: whether WT has loaded the fragment yet)
:: -----------------------------------------------------------
start "" wt.exe -w new --title "%REPO_NAME%" --tabColor "%TAB_COLOR%" --suppressApplicationTitle -d "%REPO_DIR%" cmd.exe /k "title %REPO_NAME%"
