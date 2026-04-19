# Copilot Command Ring — hook wrapper for Windows (PowerShell)
# Invoked by Copilot CLI hooks. Passes the event name and stdin payload to
# the Python host bridge. stdout MUST remain empty.

param(
    [Parameter(Mandatory=$true, Position=0)]
    [string]$EventName
)

$ErrorActionPreference = 'SilentlyContinue'

# Resolve repo root relative to this script (.github/hooks/ -> repo root)
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$HostDir = Join-Path $RepoRoot 'host'

# Set PYTHONPATH so copilot_command_ring is importable
$env:PYTHONPATH = $HostDir

# Find Python: prefer py -3 (Windows launcher), fallback to python
$Python = $null
if (Get-Command 'py' -ErrorAction SilentlyContinue) {
    $Python = 'py'
    $PythonArgs = @('-3', '-m', 'copilot_command_ring.hook_main', $EventName)
} elseif (Get-Command 'python' -ErrorAction SilentlyContinue) {
    $Python = 'python'
    $PythonArgs = @('-m', 'copilot_command_ring.hook_main', $EventName)
}

if (-not $Python) {
    # No Python found — fail silently, don't block Copilot
    exit 0
}

# Pipe stdin through to the Python process; forward stderr, keep stdout clean
$input | & $Python @PythonArgs 2>&1 | Where-Object { $_ -is [System.Management.Automation.ErrorRecord] } | ForEach-Object { [Console]::Error.WriteLine($_.Exception.Message) }

exit 0
