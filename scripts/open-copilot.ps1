#Requires -Version 5.1

# Launch from File Explorer with "Run with PowerShell", or run:
#   pwsh -File .\scripts\open-copilot.ps1
#   powershell.exe -File .\scripts\open-copilot.ps1
# The effective PowerShell execution policy must permit local scripts.

$ErrorActionPreference = 'Stop'

# Deploy-provided default. A repository-local exact TAB_COLOR=#RRGGBB line
# in .copilot-launcher.env may override it; the last matching line wins.
$TabColor = '#963885'
$CopilotCommand = 'copilot --yolo --experimental --max-autopilot-continues 22'

$ScriptDirectory = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoDirectory = [System.IO.Path]::GetFullPath(
    (Join-Path -Path $ScriptDirectory -ChildPath '..')
)
$RepoName = Split-Path -Leaf $RepoDirectory

$LauncherEnv = Join-Path -Path $RepoDirectory -ChildPath '.copilot-launcher.env'
if (Test-Path -LiteralPath $LauncherEnv -PathType Leaf) {
    foreach ($Line in Get-Content -LiteralPath $LauncherEnv) {
        if ($Line -cmatch '^TAB_COLOR=#[0-9A-Fa-f]{6}$') {
            $TabColor = $Line.Substring('TAB_COLOR='.Length)
        }
    }
}

if ([string]::IsNullOrWhiteSpace($env:LOCALAPPDATA)) {
    throw 'LOCALAPPDATA is not set; cannot install the Windows Terminal fragment.'
}

$WtCommand = Get-Command -Name 'wt.exe' -CommandType Application `
    -ErrorAction SilentlyContinue
if ($null -eq $WtCommand) {
    throw 'wt.exe was not found on PATH. Install Windows Terminal before using this launcher.'
}

$ShellCommand = Get-Command -Name 'pwsh.exe' -CommandType Application `
    -ErrorAction SilentlyContinue
if ($null -eq $ShellCommand) {
    $ShellCommand = Get-Command -Name 'powershell.exe' -CommandType Application `
        -ErrorAction SilentlyContinue
}
if ($null -eq $ShellCommand) {
    throw 'Neither pwsh.exe nor powershell.exe was found on PATH.'
}

$FragmentDirectory = Join-Path -Path $env:LOCALAPPDATA `
    -ChildPath 'Microsoft\Windows Terminal\Fragments\MyTerminals'
$FragmentPath = Join-Path -Path $FragmentDirectory `
    -ChildPath "$RepoName-copilot-powershell.json"

if (Test-Path -LiteralPath $FragmentDirectory -PathType Leaf) {
    throw "Windows Terminal fragment directory path is a file: $FragmentDirectory"
}
if ((Test-Path -LiteralPath $FragmentPath) -and
    -not (Test-Path -LiteralPath $FragmentPath -PathType Leaf)) {
    throw "Windows Terminal fragment path is not a file: $FragmentPath"
}

if (-not (Test-Path -LiteralPath $FragmentPath)) {
    New-Item -ItemType Directory -Force -Path $FragmentDirectory | Out-Null

    $QuotedShellPath = '"{0}"' -f $ShellCommand.Source
    $Fragment = @{
        profiles = @(
            @{
                name = "$RepoName (PowerShell)"
                commandline = (
                    "$QuotedShellPath -NoExit -Command " +
                    "`"$CopilotCommand`""
                )
                startingDirectory = $RepoDirectory
                tabTitle = $RepoName
                tabColor = $TabColor
                suppressApplicationTitle = $true
            }
        )
    }
    $Fragment | ConvertTo-Json -Depth 10 |
        Set-Content -LiteralPath $FragmentPath -Encoding utf8
    Write-Host "Installed WT fragment: $FragmentPath"
    Write-Host 'Restart Windows Terminal to see the profile in the dropdown menu.'
}

& $WtCommand.Source -w new --title $RepoName --tabColor $TabColor `
    --suppressApplicationTitle -d $RepoDirectory $ShellCommand.Source `
    -NoExit -Command $CopilotCommand
if ($LASTEXITCODE -ne 0) {
    throw "wt.exe failed with exit code $LASTEXITCODE."
}
