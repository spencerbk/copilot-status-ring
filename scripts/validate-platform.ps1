# Copilot Command Ring — cross-platform validation (Windows)
# Checks that the host environment is correctly configured.
#
# Usage: .\scripts\validate-platform.ps1
#
# Exit codes:
#   0 — all checks passed
#   1 — one or more checks failed

$ErrorActionPreference = 'Continue'

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$HostDir = Join-Path $RepoRoot 'host'

$Pass = 0
$Fail = 0
$Warn = 0

function Pass($msg) { $script:Pass++; Write-Host "  ✅ $msg" }
function Fail($msg) { $script:Fail++; Write-Host "  ❌ $msg" }
function Warn($msg) { $script:Warn++; Write-Host "  ⚠️  $msg" }
function Section($msg) { Write-Host "`n── $msg ──" }

# --------------------------------------------------------------------------
Section "Python"

$Python = $null
$PyArgs = @()
if (Get-Command 'py' -ErrorAction SilentlyContinue) {
    $Python = 'py'
    $PyArgs = @('-3')
} elseif (Get-Command 'python' -ErrorAction SilentlyContinue) {
    $Python = 'python'
}

if ($Python) {
    $PyVer = & $Python @PyArgs --version 2>&1
    Pass "Python found: $Python ($PyVer)"
} else {
    Fail "Python 3 not found (tried py -3, python)"
}

# --------------------------------------------------------------------------
Section "Dependencies"

if ($Python) {
    $importCheck = & $Python @PyArgs -c "import serial; print(serial.VERSION)" 2>&1
    if ($LASTEXITCODE -eq 0) {
        Pass "pyserial importable (version $importCheck)"
    } else {
        Fail "pyserial not installed — run: py -3 -m pip install pyserial"
    }
} else {
    Fail "Skipped (no Python)"
}

# --------------------------------------------------------------------------
Section "Hook wrapper"

$HookScript = Join-Path $RepoRoot '.github\hooks\run-hook.ps1'
if (Test-Path $HookScript) {
    Pass "run-hook.ps1 exists"
    # Check for syntax errors
    try {
        $null = [System.Management.Automation.PSParser]::Tokenize((Get-Content $HookScript -Raw), [ref]$null)
        Pass "run-hook.ps1 has valid syntax"
    } catch {
        Fail "run-hook.ps1 has syntax errors"
    }
} else {
    Fail "run-hook.ps1 not found at $HookScript"
}

$HookJson = Join-Path $RepoRoot '.github\hooks\copilot-command-ring.json'
if (Test-Path $HookJson) {
    Pass "copilot-command-ring.json exists"
    try {
        $null = Get-Content $HookJson -Raw | ConvertFrom-Json
        Pass "copilot-command-ring.json is valid JSON"
    } catch {
        Fail "copilot-command-ring.json is not valid JSON"
    }
} else {
    Fail "copilot-command-ring.json not found"
}

# --------------------------------------------------------------------------
Section "Host bridge dry-run"

if ($Python) {
    $env:PYTHONPATH = $HostDir
    $env:COPILOT_RING_DRY_RUN = '1'

    $events = @(
        'sessionStart', 'sessionEnd', 'userPromptSubmitted',
        'preToolUse', 'postToolUse', 'postToolUseFailure',
        'permissionRequest', 'subagentStart', 'subagentStop',
        'agentStop', 'preCompact', 'errorOccurred', 'notification'
    )

    $allOk = $true
    foreach ($evt in $events) {
        $result = '{}' | & $Python @PyArgs -m copilot_command_ring.hook_main $evt 2>&1
        if ($LASTEXITCODE -ne 0) {
            Fail "hook_main $evt exited with code $LASTEXITCODE"
            $allOk = $false
        }
    }
    if ($allOk) {
        Pass "All $($events.Count) events exit cleanly in dry-run mode"
    }

    # Verify stdout stays empty for preToolUse
    $stdoutCheck = '{"toolName":"bash"}' | & $Python @PyArgs -m copilot_command_ring.hook_main preToolUse 2>$null
    if ([string]::IsNullOrEmpty($stdoutCheck)) {
        Pass "preToolUse produces no stdout output"
    } else {
        Fail "preToolUse wrote to stdout (would interfere with Copilot CLI)"
    }

    Remove-Item Env:\COPILOT_RING_DRY_RUN -ErrorAction SilentlyContinue
}

# --------------------------------------------------------------------------
Section "Serial port detection"

if ($Python) {
    $detectResult = & $Python @PyArgs -c @"
import sys
sys.path.insert(0, r'$HostDir')
from copilot_command_ring.detect_ports import detect_port
result = detect_port()
print(result if result else '(none detected)')
"@ 2>&1
    if ($LASTEXITCODE -eq 0) {
        Pass "Port detection runs without error"
    } else {
        Warn "Port detection raised an error (may be normal without a connected device)"
    }
}

# --------------------------------------------------------------------------
Section "Tests"

if ($Python) {
    $pytestCheck = & $Python @PyArgs -m pytest --version 2>&1
    if ($LASTEXITCODE -eq 0) {
        Pass "pytest is available"
        $testOutput = & $Python @PyArgs -m pytest "$RepoRoot\tests" -q --tb=line 2>&1
        $lastLine = ($testOutput | Select-Object -Last 1)
        if ($lastLine -match 'passed') {
            Pass "Tests: $lastLine"
        } else {
            Fail "Tests: $lastLine"
        }
    } else {
        Warn "pytest not installed — skipping test run"
    }
}

# --------------------------------------------------------------------------
Section "Firmware files"

foreach ($f in @('boot.py', 'code.py')) {
    $fPath = Join-Path $RepoRoot "firmware\circuitpython\$f"
    if (Test-Path $fPath) {
        Pass "firmware/circuitpython/$f exists"
    } else {
        Fail "firmware/circuitpython/$f missing"
    }
}

$inoPath = Join-Path $RepoRoot 'firmware\arduino\copilot_command_ring\copilot_command_ring.ino'
if (Test-Path $inoPath) {
    Pass "firmware/arduino/copilot_command_ring.ino exists"
} else {
    Fail "firmware/arduino/copilot_command_ring.ino missing"
}

# --------------------------------------------------------------------------
Write-Host "`n── Summary ──"
Write-Host "  Passed: $Pass  |  Failed: $Fail  |  Warnings: $Warn`n"

if ($Fail -gt 0) {
    Write-Host "Some checks failed. See above for details."
    exit 1
} else {
    Write-Host "All checks passed! Your environment is ready."
    exit 0
}
