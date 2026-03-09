$ErrorActionPreference = "Stop"

$root = Resolve-Path (Join-Path $PSScriptRoot "..")
$urlFile = Join-Path $root "data\public_worker_url.txt"

if (-not (Test-Path $urlFile)) {
  throw "No existe data/public_worker_url.txt. Primero ejecuta scripts/start_public_worker.ps1"
}

$publicUrl = (Get-Content $urlFile -Raw).Trim()
if (-not $publicUrl) {
  throw "La URL publica del worker esta vacia."
}

$apiBaseUrl = "$publicUrl/api"

powershell -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot "deploy_vercel_frontend.ps1") -ApiBaseUrl $apiBaseUrl
