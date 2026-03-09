$ErrorActionPreference = "SilentlyContinue"

$root = Resolve-Path (Join-Path $PSScriptRoot "..")
$pidFile = Join-Path $root ".observatorio_app_pids.json"

if (-not (Test-Path $pidFile)) {
  Write-Output "No hay archivo de PIDs: $pidFile"
  exit 0
}

$data = Get-Content -Path $pidFile -Raw | ConvertFrom-Json

if ($data.backend_pid) {
  Stop-Process -Id ([int]$data.backend_pid) -Force
  Write-Output "Backend detenido: $($data.backend_pid)"
}

if ($data.frontend_pid) {
  Stop-Process -Id ([int]$data.frontend_pid) -Force
  Write-Output "Frontend detenido: $($data.frontend_pid)"
}

Remove-Item -Path $pidFile -Force
Write-Output "PIDs limpiados."

