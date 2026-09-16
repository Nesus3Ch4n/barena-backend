# run-migrations.ps1 - aplica las migraciones de Alembic contra la DB
# Uso 1: .\run-migrations.ps1 -DbUrl "postgresql://postgres.PROYECTO:PASSWORD@pooler.supabase.com:6543/postgres"
# Uso 2: .\run-migrations.ps1  (usa DATABASE_URL_SYNC del archivo .env)
param(
    [string]$DbUrl = ""
)
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if (-not $DbUrl) {
    if (Test-Path .env) {
        $line = (Get-Content .env | Where-Object { $_ -match "^DATABASE_URL_SYNC=" }) | Select-Object -First 1
        if ($line) { $DbUrl = ($line -split "=", 2)[1].Trim().Trim('"') }
    }
}
if (-not $DbUrl) {
    Write-Host "Falta la URL. Usa -DbUrl o define DATABASE_URL_SYNC en .env" -ForegroundColor Red
    exit 1
}

if (-not (Test-Path .venv)) { py -m venv .venv }
$py = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $py)) { Write-Host "No se pudo crear el venv" -ForegroundColor Red; exit 1 }

& $py -m pip install --quiet -r requirements.txt
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

$env:DATABASE_URL_SYNC = $DbUrl
Write-Host "Estado actual de la DB:" -ForegroundColor Cyan
& $py -m alembic current
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "Aplicando migraciones..." -ForegroundColor Cyan
& $py -m alembic upgrade head
exit $LASTEXITCODE