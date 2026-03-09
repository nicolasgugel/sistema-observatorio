$ErrorActionPreference = "Stop"

$root = Resolve-Path (Join-Path $PSScriptRoot "..")
$outputDir = Join-Path $root "output"
$dataDir = Join-Path $root "data"
$pidFile = Join-Path $root ".observatorio_worker_pids.json"
$workerLogOut = Join-Path $outputDir "public_worker.out.log"
$workerLogErr = Join-Path $outputDir "public_worker.err.log"
$tunnelLogOut = Join-Path $outputDir "public_tunnel.out.log"
$tunnelLogErr = Join-Path $outputDir "public_tunnel.err.log"
$tokenFile = Join-Path $dataDir "editor_token.txt"
$urlFile = Join-Path $dataDir "public_worker_url.txt"
$pythonExe = (Get-Command python).Source

New-Item -ItemType Directory -Force -Path $outputDir | Out-Null
New-Item -ItemType Directory -Force -Path $dataDir | Out-Null

if (Test-Path $pidFile) {
  throw "Ya existe un worker publico arrancado. Para reiniciarlo usa scripts/stop_public_worker.ps1"
}

if (-not (Test-Path $tokenFile)) {
  $generatedToken = python -c "import secrets; print(secrets.token_urlsafe(32))"
  $generatedToken.Trim() | Set-Content -Path $tokenFile -Encoding UTF8
}

$editorToken = (Get-Content $tokenFile -Raw).Trim()
if (-not $editorToken) {
  throw "No se pudo leer el token de edicion."
}

$workerCommand = '$env:OBSERVATORIO_EDITOR_TOKEN=''' + $editorToken + '''; ' +
  '$env:OBSERVATORIO_ALLOWED_ORIGINS=''https://sistema-observatorio.vercel.app,http://127.0.0.1:5173,http://localhost:5173''; ' +
  '$env:PORT=''8010''; ' +
  'python scripts/run_worker.py'

$worker = Start-Process -FilePath "powershell.exe" `
  -ArgumentList "-NoProfile", "-Command", $workerCommand `
  -WorkingDirectory $root `
  -RedirectStandardOutput $workerLogOut `
  -RedirectStandardError $workerLogErr `
  -PassThru

Start-Sleep -Seconds 4

$health = $null
for ($i = 0; $i -lt 20; $i++) {
  try {
    $health = Invoke-WebRequest -UseBasicParsing http://127.0.0.1:8010/api/health -TimeoutSec 3
    if ($health.StatusCode -eq 200) {
      break
    }
  } catch {
    Start-Sleep -Seconds 1
  }
}

if (-not $health -or $health.StatusCode -ne 200) {
  Stop-Process -Id $worker.Id -Force -ErrorAction SilentlyContinue
  throw "El worker publico no arranco correctamente en el puerto 8010."
}

$tunnel = Start-Process -FilePath "cmd.exe" `
  -ArgumentList "/c", "npx localtunnel --port 8010" `
  -WorkingDirectory $root `
  -RedirectStandardOutput $tunnelLogOut `
  -RedirectStandardError $tunnelLogErr `
  -PassThru

$publicUrl = $null
for ($i = 0; $i -lt 60; $i++) {
  if (Test-Path $tunnelLogOut) {
    $content = Get-Content $tunnelLogOut -Raw
    if ($content -match 'https://[^\s"]+') {
      $publicUrl = $Matches[0]
      break
    }
  }
  Start-Sleep -Seconds 2
}

if (-not $publicUrl) {
  Stop-Process -Id $tunnel.Id -Force -ErrorAction SilentlyContinue
  Stop-Process -Id $worker.Id -Force -ErrorAction SilentlyContinue
  throw "No se pudo obtener la URL publica del tunel."
}

$publicUrl.Trim() | Set-Content -Path $urlFile -Encoding UTF8

$payload = @{
  worker_pid = $worker.Id
  tunnel_pid = $tunnel.Id
  editor_token_file = $tokenFile
  public_url_file = $urlFile
  started_at = (Get-Date).ToString("o")
}

$payload | ConvertTo-Json | Set-Content -Path $pidFile -Encoding UTF8

Write-Output "Worker PID: $($worker.Id)"
Write-Output "Tunnel PID: $($tunnel.Id)"
Write-Output "Worker URL: $publicUrl"
Write-Output "Worker API: $publicUrl/api"
Write-Output "Editor token: $tokenFile"
