<#
.SYNOPSIS
    Remove aether-kit global Cursor hook · Windows.

.DESCRIPTION
    Reverses install-hook.ps1:
    - Removes ~/.cursor/hooks/aether-dispatch.py
    - Removes ~/.cursor/rules/aether.mdc
    - Strips the aether-dispatch entry from ~/.cursor/hooks.json
      (preserves any other user hooks unchanged)

    Safe to run even if hook was never installed.
#>
[CmdletBinding()]
param([switch]$DryRun)

$ErrorActionPreference = "Continue"

$cursorDir = Join-Path $env:USERPROFILE ".cursor"
$targetDispatcher = Join-Path $cursorDir "hooks\aether-dispatch.py"
$targetMdc = Join-Path $cursorDir "rules\aether.mdc"
$targetHooksJson = Join-Path $cursorDir "hooks.json"

Write-Host ""
Write-Host "═══════════════════════════════════════════════════════════" -ForegroundColor Magenta
Write-Host "  Aether Kit · uninstall global Cursor hook" -ForegroundColor Magenta
Write-Host "═══════════════════════════════════════════════════════════" -ForegroundColor Magenta
Write-Host ""

foreach ($f in @($targetDispatcher, $targetMdc)) {
    if (Test-Path $f) {
        Write-Host "  removing $f" -ForegroundColor Gray
        if (-not $DryRun) { Remove-Item $f -Force }
    } else {
        Write-Host "  not present $f" -ForegroundColor DarkGray
    }
}

# Strip aether-dispatch from hooks.json
if (Test-Path $targetHooksJson) {
    try {
        $existing = Get-Content $targetHooksJson -Raw | ConvertFrom-Json -ErrorAction Stop
        if ($existing.hooks -and $existing.hooks.sessionStart) {
            $kept = $existing.hooks.sessionStart | Where-Object { $_.command -notmatch "aether-dispatch\.py" }
            if (-not $kept -or $kept.Count -eq 0) {
                # Remove sessionStart key entirely if empty
                $existing.hooks.PSObject.Properties.Remove("sessionStart")
            } else {
                $existing.hooks | Add-Member -MemberType NoteProperty -Name sessionStart -Value @($kept) -Force
            }
            # If hooks is now empty and this looks like a file we created (no non-trivial other hooks)
            $otherHooks = $existing.hooks.PSObject.Properties | Where-Object { $_.Name -notlike "_*" }
            if (-not $otherHooks) {
                Write-Host "  removing now-empty $targetHooksJson" -ForegroundColor Gray
                if (-not $DryRun) { Remove-Item $targetHooksJson -Force }
            } else {
                Write-Host "  updated $targetHooksJson (kept user's other hooks)" -ForegroundColor Gray
                if (-not $DryRun) {
                    $existing | ConvertTo-Json -Depth 10 | Out-File -FilePath $targetHooksJson -Encoding utf8
                }
            }
        } else {
            Write-Host "  hooks.json has no sessionStart · nothing to strip" -ForegroundColor DarkGray
        }
    } catch {
        Write-Host "  ✗ existing hooks.json is not valid JSON · left untouched" -ForegroundColor Yellow
    }
} else {
    Write-Host "  not present $targetHooksJson" -ForegroundColor DarkGray
}

Write-Host ""
Write-Host "═══════════════════════════════════════════════════════════" -ForegroundColor Green
Write-Host "  ✓ Aether Kit global hook removed" -ForegroundColor Green
Write-Host "═══════════════════════════════════════════════════════════" -ForegroundColor Green
Write-Host ""
Write-Host "  Restart Cursor to apply." -ForegroundColor White
Write-Host ""
