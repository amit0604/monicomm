# Run every check CI runs, on your own machine, before you push (Windows / PowerShell).
#   .\scripts\check.ps1            lint + tests + build
#   .\scripts\check.ps1 -Docker    also runs the full Docker smoke test
param([switch]$Docker)
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot

function Invoke-Step($name, [scriptblock]$cmd) {
    Write-Host "==> $name" -ForegroundColor Cyan
    & $cmd
    if ($LASTEXITCODE -ne 0) { Write-Host "FAILED: $name" -ForegroundColor Red; exit 1 }
}

Push-Location $root
try {
    Invoke-Step "Air-gap check" { python scripts/check_airgap.py }

    Push-Location api
    Invoke-Step "API: install" { uv sync --frozen }
    Invoke-Step "API: format check" { uv run ruff format --check . }
    Invoke-Step "API: lint" { uv run ruff check . }
    Invoke-Step "API: tests" { uv run pytest }
    Pop-Location

    Push-Location web
    Invoke-Step "Web: install" { npm ci }
    Invoke-Step "Web: format, lint, typecheck, tests, build" { npm run check }
    Pop-Location

    if ($Docker) { Invoke-Step "Docker smoke test" { bash scripts/smoke_test.sh } }
    Write-Host "All checks passed." -ForegroundColor Green
}
finally { Pop-Location }
