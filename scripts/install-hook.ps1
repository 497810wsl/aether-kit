<#
.SYNOPSIS
    Install aether-kit global Cursor hook · Windows.

.DESCRIPTION
    Copies aether-dispatch.py + aether.mdc to ~/.cursor/ and merges the
    sessionStart hook entry into ~/.cursor/hooks.json (preserves any
    existing user hooks · never overwrites unrelated entries).

    After install, restart Cursor. Open ANY workspace · if it contains
    an `aether/bin/aether_hook.py` file the session auto-handshakes.
    Non-Aether workspaces are unaffected.

.PARAMETER Force
    Overwrite existing aether-dispatch.py and aether.mdc without asking.
    Useful for upgrading from an older version.

.PARAMETER DryRun
    Print what would be done · do not touch the filesystem.

.EXAMPLE
    .\scripts\install-hook.ps1
    Standard install.

.EXAMPLE
    .\scripts\install-hook.ps1 -Force
    Upgrade · overwrite existing Aether files.

.NOTES
    Requires Python 3.6+ in PATH(aether-dispatch.py is a Python script).
    Safe to run multiple times · merge-based · no duplication.
#>
[CmdletBinding()]
param(
    [switch]$Force,
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"

# ----- locate ourselves · repo root = parent of scripts/ -----
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot  = Split-Path -Parent $scriptDir
$srcHooks  = Join-Path $repoRoot "kit\.cursor-global\hooks"
$srcRules  = Join-Path $repoRoot "kit\.cursor-global\rules"
$srcHooksJson = Join-Path $repoRoot "kit\.cursor-global\hooks.json"

# ----- target location · ~/.cursor/ -----
$cursorDir = Join-Path $env:USERPROFILE ".cursor"
$targetHooks = Join-Path $cursorDir "hooks"
$targetRules = Join-Path $cursorDir "rules"
$targetHooksJson = Join-Path $cursorDir "hooks.json"

Write-Host ""
Write-Host "═══════════════════════════════════════════════════════════" -ForegroundColor Magenta
Write-Host "  Aether Kit · install global Cursor hook" -ForegroundColor Magenta
Write-Host "═══════════════════════════════════════════════════════════" -ForegroundColor Magenta
Write-Host ""
Write-Host "  source   : $repoRoot" -ForegroundColor Gray
Write-Host "  target   : $cursorDir" -ForegroundColor Gray
if ($DryRun) { Write-Host "  MODE     : DRY RUN (no filesystem writes)" -ForegroundColor Yellow }
if ($Force) { Write-Host "  MODE     : FORCE (overwrite existing Aether files)" -ForegroundColor Yellow }
Write-Host ""

# ----- precheck · Python available? -----
$py = Get-Command python -ErrorAction SilentlyContinue
if (-not $py) {
    Write-Host "✗ python not found in PATH" -ForegroundColor Red
    Write-Host "  aether-dispatch.py requires Python 3.6+" -ForegroundColor Red
    Write-Host "  install from https://python.org · ensure 'Add to PATH' is checked" -ForegroundColor Red
    exit 1
}
$pyver = (python --version 2>&1).ToString().Trim()
Write-Host "✓ Python: $pyver" -ForegroundColor Green

# ----- precheck · source files exist -----
$srcDispatcher = Join-Path $srcHooks "aether-dispatch.py"
$srcAetherMdc  = Join-Path $srcRules "aether.mdc"
foreach ($f in @($srcDispatcher, $srcAetherMdc, $srcHooksJson)) {
    if (-not (Test-Path $f)) {
        Write-Host "✗ missing source file: $f" -ForegroundColor Red
        Write-Host "  is this a valid aether-kit checkout?" -ForegroundColor Red
        exit 1
    }
}
Write-Host "✓ all source files present" -ForegroundColor Green

# ----- step 1 · ensure ~/.cursor/{hooks,rules}/ exist -----
Write-Host ""
Write-Host "▶ step 1 · prepare target dirs" -ForegroundColor Cyan
foreach ($d in @($cursorDir, $targetHooks, $targetRules)) {
    if (-not (Test-Path $d)) {
        Write-Host "  creating $d" -ForegroundColor Gray
        if (-not $DryRun) { New-Item -ItemType Directory -Path $d -Force | Out-Null }
    } else {
        Write-Host "  exists   $d" -ForegroundColor Gray
    }
}

# ----- step 2 · copy aether-dispatch.py -----
Write-Host ""
Write-Host "▶ step 2 · install dispatcher" -ForegroundColor Cyan
$tgtDispatcher = Join-Path $targetHooks "aether-dispatch.py"
if ((Test-Path $tgtDispatcher) -and -not $Force) {
    # Compare · only overwrite if different
    $srcHash = (Get-FileHash $srcDispatcher -Algorithm SHA256).Hash
    $tgtHash = (Get-FileHash $tgtDispatcher -Algorithm SHA256).Hash
    if ($srcHash -eq $tgtHash) {
        Write-Host "  ✓ up to date · $tgtDispatcher" -ForegroundColor Green
    } else {
        Write-Host "  ✗ $tgtDispatcher exists and differs" -ForegroundColor Yellow
        Write-Host "    re-run with -Force to upgrade" -ForegroundColor Yellow
        exit 1
    }
} else {
    Write-Host "  installing $tgtDispatcher" -ForegroundColor Gray
    if (-not $DryRun) { Copy-Item -Path $srcDispatcher -Destination $tgtDispatcher -Force }
}

# ----- step 3 · copy aether.mdc -----
Write-Host ""
Write-Host "▶ step 3 · install rule" -ForegroundColor Cyan
$tgtAetherMdc = Join-Path $targetRules "aether.mdc"
if ((Test-Path $tgtAetherMdc) -and -not $Force) {
    $srcHash = (Get-FileHash $srcAetherMdc -Algorithm SHA256).Hash
    $tgtHash = (Get-FileHash $tgtAetherMdc -Algorithm SHA256).Hash
    if ($srcHash -eq $tgtHash) {
        Write-Host "  ✓ up to date · $tgtAetherMdc" -ForegroundColor Green
    } else {
        Write-Host "  ✗ $tgtAetherMdc exists and differs" -ForegroundColor Yellow
        Write-Host "    re-run with -Force to upgrade" -ForegroundColor Yellow
        exit 1
    }
} else {
    Write-Host "  installing $tgtAetherMdc" -ForegroundColor Gray
    if (-not $DryRun) { Copy-Item -Path $srcAetherMdc -Destination $tgtAetherMdc -Force }
}

# ----- step 4 · merge hooks.json -----
Write-Host ""
Write-Host "▶ step 4 · merge hooks.json" -ForegroundColor Cyan

# The command line we want · expand ~ so the user's actual home is baked in.
$dispatchCmd = "python `"$tgtDispatcher`""
$aetherHook  = [ordered]@{
    command = $dispatchCmd
    timeout = 30
}

if (Test-Path $targetHooksJson) {
    Write-Host "  found existing $targetHooksJson · merging" -ForegroundColor Gray
    try {
        $existing = Get-Content $targetHooksJson -Raw | ConvertFrom-Json -ErrorAction Stop
    } catch {
        Write-Host "  ✗ existing hooks.json is not valid JSON" -ForegroundColor Red
        Write-Host "    fix it manually or re-run with -Force to replace" -ForegroundColor Red
        if (-not $Force) { exit 1 }
        $existing = $null
    }
    if (-not $existing) {
        $existing = [PSCustomObject]@{ version = 1; hooks = [PSCustomObject]@{} }
    }
    if (-not $existing.hooks) {
        $existing | Add-Member -MemberType NoteProperty -Name hooks -Value ([PSCustomObject]@{}) -Force
    }
    # Get or create sessionStart array
    $ss = $existing.hooks.sessionStart
    if (-not $ss) { $ss = @() }
    # Check if Aether hook already registered
    $already = $ss | Where-Object { $_.command -match "aether-dispatch\.py" }
    if ($already) {
        Write-Host "  ✓ aether-dispatch already registered · leaving unchanged" -ForegroundColor Green
    } else {
        $ss = @($ss) + [PSCustomObject]$aetherHook
        $existing.hooks | Add-Member -MemberType NoteProperty -Name sessionStart -Value $ss -Force
        if (-not $DryRun) {
            $existing | ConvertTo-Json -Depth 10 | Out-File -FilePath $targetHooksJson -Encoding utf8
        }
        Write-Host "  ✓ appended aether-dispatch to sessionStart" -ForegroundColor Green
    }
} else {
    Write-Host "  creating $targetHooksJson" -ForegroundColor Gray
    if (-not $DryRun) {
        # Build hooks.json as an object · let ConvertTo-Json handle quote
        # escaping · string interpolation was producing invalid JSON when
        # the dispatcher path contained characters needing escape.
        $newHooks = [ordered]@{
            version = 1
            "_comment" = "Aether Kit · user-level hooks · installed by aether-kit/scripts/install-hook.ps1 · remove with uninstall-hook.ps1 or delete this file"
            hooks = [ordered]@{
                sessionStart = @(
                    [ordered]@{
                        command = $dispatchCmd
                        timeout = 30
                    }
                )
            }
        }
        $newHooks | ConvertTo-Json -Depth 10 | Out-File -FilePath $targetHooksJson -Encoding utf8
    }
}

# ----- done -----
Write-Host ""
Write-Host "═══════════════════════════════════════════════════════════" -ForegroundColor Green
Write-Host "  ✓ Aether Kit global hook installed" -ForegroundColor Green
Write-Host "═══════════════════════════════════════════════════════════" -ForegroundColor Green
Write-Host ""
Write-Host "  Next steps:" -ForegroundColor White
Write-Host "    1. Restart Cursor" -ForegroundColor White
Write-Host "    2. Open any workspace" -ForegroundColor White
Write-Host "       - if it has aether/bin/aether_hook.py · session auto-handshakes" -ForegroundColor Gray
Write-Host "       - if not · nothing changes · you won't notice it's installed" -ForegroundColor Gray
Write-Host ""
Write-Host "  To uninstall:" -ForegroundColor White
Write-Host "    .\scripts\uninstall-hook.ps1" -ForegroundColor Gray
Write-Host ""
