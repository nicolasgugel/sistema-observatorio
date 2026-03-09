$ErrorActionPreference = "Stop"

$root = Resolve-Path (Join-Path $PSScriptRoot "..")
$frontendDir = Join-Path $root "frontend"
$pidFile = Join-Path $root ".observatorio_app_pids.json"
$frontendLogOut = Join-Path $root "output\frontend_app.out.log"
$frontendLogErr = Join-Path $root "output\frontend_app.err.log"
$pythonExe = (Get-Command python).Source

if (-not (Test-Path $frontendDir)) {
  throw "No se encontro carpeta frontend en: $frontendDir"
}

$backend = Start-Process -FilePath $pythonExe `
  -ArgumentList "-m", "uvicorn", "app_backend.main:app", "--host", "127.0.0.1", "--port", "8000" `
  -WorkingDirectory $root `
  -PassThru

$frontend = Start-Process -FilePath "cmd.exe" `
  -ArgumentList "/c set npm_config_cache=%CD%\.npm-cache&& npm run dev -- --host 127.0.0.1 --port 5173" `
  -WorkingDirectory $frontendDir `
  -RedirectStandardOutput $frontendLogOut `
  -RedirectStandardError $frontendLogErr `
  -PassThru

$payload = @{
  backend_pid = $backend.Id
  frontend_pid = $frontend.Id
  started_at = (Get-Date).ToString("o")
}

$payload | ConvertTo-Json | Set-Content -Path $pidFile -Encoding UTF8

Write-Output "Backend PID: $($backend.Id)"
Write-Output "Frontend PID: $($frontend.Id)"
Write-Output "Health API: http://127.0.0.1:8000/api/health"
Write-Output "App URL:    http://127.0.0.1:5173"
Write-Output "Frontend logs: $frontendLogOut | $frontendLogErr"
