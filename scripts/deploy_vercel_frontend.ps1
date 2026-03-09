param(
  [string]$ApiBaseUrl,
  [string]$TokenPath = "hola.txt",
  [switch]$SkipEnvUpdate
)

$ErrorActionPreference = "Stop"

$root = Resolve-Path (Join-Path $PSScriptRoot "..")
$tokenFile = Join-Path $root $TokenPath

if (-not (Test-Path $tokenFile)) {
  throw "No se encontro el token de Vercel en: $tokenFile"
}

$token = (Get-Content $tokenFile -Raw).Trim()
if (-not $token) {
  throw "El token de Vercel esta vacio."
}

if (-not $SkipEnvUpdate) {
  if (-not $ApiBaseUrl) {
    throw "Pasa -ApiBaseUrl https://tu-worker/api o usa -SkipEnvUpdate si solo quieres desplegar."
  }

  foreach ($environment in @("production")) {
    $existing = cmd /c "npx vercel env ls --token $token" 2>&1
    if ($LASTEXITCODE -ne 0) {
      throw "No se pudo leer la configuracion de Vercel."
    }

    if ($existing -match "VITE_API_BASE_URL") {
      cmd /c "echo y | npx vercel env rm VITE_API_BASE_URL $environment --token $token"
      if ($LASTEXITCODE -ne 0) {
        throw "No se pudo eliminar VITE_API_BASE_URL para $environment."
      }
    }

    cmd /c "echo $ApiBaseUrl | npx vercel env add VITE_API_BASE_URL $environment --token $token"
    if ($LASTEXITCODE -ne 0) {
      throw "No se pudo guardar VITE_API_BASE_URL para $environment."
    }
  }
}

Push-Location $root
try {
  cmd /c "npx vercel --prod --token $token"
  if ($LASTEXITCODE -ne 0) {
    throw "Fallo el despliegue a Vercel."
  }
}
finally {
  Pop-Location
}
