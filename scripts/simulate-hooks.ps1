# Copilot Command Ring — simulate hook events (Windows)
# Sends a test sequence through the host bridge for firmware validation.

$ErrorActionPreference = 'Stop'

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$HostDir = Join-Path $RepoRoot 'host'
$env:PYTHONPATH = $HostDir

# Find Python
$Python = $null
$PyArgs = @()
if (Get-Command 'py' -ErrorAction SilentlyContinue) {
    $Python = 'py'
    $PyArgs = @('-3')
} elseif (Get-Command 'python' -ErrorAction SilentlyContinue) {
    $Python = 'python'
}

if (-not $Python) {
    Write-Error "Python not found"
    exit 1
}

Write-Host "Running Copilot Command Ring simulation..."
& $Python @PyArgs -m copilot_command_ring.simulate --dry-run @args
