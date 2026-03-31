param(
    [string]$EnvName = "spinelab-0-2"
)

$ErrorActionPreference = "Stop"

$condaExe = $env:CONDA_EXE
if (-not $condaExe) {
    $condaCommand = Get-Command conda.exe -ErrorAction SilentlyContinue
    if ($null -ne $condaCommand) {
        $condaExe = $condaCommand.Source
    }
}

if (-not $condaExe) {
    throw "Unable to locate conda.exe. Activate the app environment or set CONDA_EXE."
}

$repoRoot = Split-Path -Parent $PSScriptRoot
Push-Location $repoRoot
try {
    Write-Host "Using conda env '$EnvName' via $condaExe" -ForegroundColor Cyan

    & $condaExe run -n $EnvName python tools/check_theme_usage.py
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

    & $condaExe run -n $EnvName python -m ruff check .
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

    & $condaExe run -n $EnvName python -m mypy src
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

    & $condaExe run -n $EnvName python -m pytest -q
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
finally {
    Pop-Location
}
