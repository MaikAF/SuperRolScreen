# run.ps1 - Atajo para el orquestador de SuperRolScreen (scripts/run.py).
# Funciona desde cualquier directorio.
# Uso: .\run.ps1 [dev|obs] [--no-bot] [--no-client] [--window]

$ErrorActionPreference = 'Stop'

$script = Join-Path $PSScriptRoot 'scripts\run.py'
$venvPython = Join-Path $PSScriptRoot 'server\.venv\Scripts\python.exe'

if (Test-Path $venvPython) {
    & $venvPython $script --parent-pid $PID @args
} else {
    # Sin venv: el preflight de run.py explica como crearlo.
    & py -3.12 $script --parent-pid $PID @args
}
exit $LASTEXITCODE
