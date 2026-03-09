$ErrorActionPreference = "SilentlyContinue"

$root = Resolve-Path (Join-Path $PSScriptRoot "..")
$pidFile = Join-Path $root ".observatorio_worker_pids.json"

if (-not (Test-Path $pidFile)) {
  Write-Output "No hay worker publico levantado."
  exit 0
}

$data = Get-Content -Path $pidFile -Raw | ConvertFrom-Json

if ($data.worker_pid) {
  Stop-Process -Id ([int]$data.worker_pid) -Force
  Write-Output "Worker detenido: $($data.worker_pid)"
}

if ($data.tunnel_pid) {
  Stop-Process -Id ([int]$data.tunnel_pid) -Force
  Write-Output "Tunel detenido: $($data.tunnel_pid)"
}

Remove-Item -Path $pidFile -Force
Write-Output "PIDs del worker publico limpiados."
