param(
  [string]$PythonExe = "python"
)

$ErrorActionPreference = "Stop"

$root = Resolve-Path (Join-Path $PSScriptRoot "..")
$outputDir = Join-Path $root "output"
$logDir = Join-Path $outputDir "scheduler"
$timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$logFile = Join-Path $logDir "daily_refresh_$timestamp.log"

New-Item -ItemType Directory -Force -Path $logDir | Out-Null

function Write-Log {
  param([string]$Message)
  $line = "[{0}] {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $Message
  $line | Tee-Object -FilePath $logFile -Append
}

try {
  Write-Log "Inicio del refresh diario programado."
  Push-Location $root

  Write-Log "Ejecutando scripts/run_daily_refresh.py"
  & $PythonExe "scripts/run_daily_refresh.py" 2>&1 | Tee-Object -FilePath $logFile -Append
  if ($LASTEXITCODE -ne 0) {
    throw "run_daily_refresh.py devolvio codigo $LASTEXITCODE"
  }

  Write-Log "Publicando nueva version en Vercel"
  powershell -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot "deploy_vercel_frontend.ps1") -SkipEnvUpdate 2>&1 |
    Tee-Object -FilePath $logFile -Append
  if ($LASTEXITCODE -ne 0) {
    throw "deploy_vercel_frontend.ps1 devolvio codigo $LASTEXITCODE"
  }

  Write-Log "Refresh diario completado correctamente."
}
catch {
  Write-Log ("ERROR: " + $_.Exception.Message)
  throw
}
finally {
  Pop-Location
}
