param(
  [switch]$NoBrowser
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

Write-Host "ARGUS FloodOps — competition launcher" -ForegroundColor Cyan

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
  Write-Host "Docker is not installed or not in PATH. Install/start Docker Desktop, then run this file again." -ForegroundColor Red
  exit 1
}

try {
  docker info *> $null
} catch {
  Write-Host "Docker Desktop is not running. Start Docker Desktop, wait until it is ready, then run again." -ForegroundColor Red
  exit 1
}

if (-not (Test-Path ".env")) {
  Copy-Item ".env.example" ".env"
  Write-Host "Created .env from .env.example"
}

# Competition mode must never silently fall back to the synthetic demo when a real-data pack is missing.
$env:ARGUS_DATA_PROFILE = "historical"
$env:ARGUS_INSTALL_REALDATA = "true"
$env:ARGUS_OPEN_METEO_ENABLED = "true"

Write-Host "Starting PostGIS + ARGUS API + console..." -ForegroundColor Cyan
docker compose up -d --build
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

$deadline = (Get-Date).AddMinutes(10)
$healthy = $false
while ((Get-Date) -lt $deadline) {
  try {
    $h = Invoke-RestMethod -Uri "http://localhost:8000/api/system/health" -TimeoutSec 3
    if ($h.status -eq "ok" -and $h.database -eq "ok") {
      $healthy = $true
      break
    }
  } catch {}
  Start-Sleep -Seconds 3
}

if (-not $healthy) {
  Write-Host "ARGUS did not become healthy in time. Recent backend logs:" -ForegroundColor Red
  docker compose logs --tail=120 backend
  exit 1
}

# The frontend can take a few seconds longer than the API.
$front = $false
for ($i=0; $i -lt 60; $i++) {
  try {
    $r = Invoke-WebRequest -Uri "http://localhost:3000/login" -TimeoutSec 3 -UseBasicParsing
    if ($r.StatusCode -eq 200) { $front = $true; break }
  } catch {}
  Start-Sleep -Seconds 2
}
if (-not $front) {
  Write-Host "Backend is healthy, but the console is not responding. Recent frontend logs:" -ForegroundColor Red
  docker compose logs --tail=120 frontend
  exit 1
}

Write-Host ""
Write-Host "ARGUS IS READY" -ForegroundColor Green
Write-Host "Open: http://localhost:3000"
Write-Host "Competition account: planner / argus2026"
Write-Host "Commander approval: commander / argus2026"
Write-Host ""
Write-Host "Real-data packs are cached in Docker volumes and will NOT be downloaded again on normal restarts."

if (-not $NoBrowser) {
  Start-Process "http://localhost:3000"
}
