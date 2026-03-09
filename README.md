# Santander Price Intelligence (Local App)

Aplicacion local end-to-end para analitica de precios Santander vs competidores, con backend FastAPI y frontend React.

## Alcance implementado

Se incluyen 5 modulos funcionales:
1. Comparador de precios con competidores
2. Actualizacion diaria automatica
3. Visualizador de precios (tabla avanzada)
4. Dashboard analitico
5. Agente de consultas en lenguaje natural (modo local deterministico)

## Stack

- Backend: `FastAPI` + `uvicorn`
- Frontend: `React + TypeScript + Vite`
- Estado frontend: `Zustand`
- Graficas: `Recharts`
- Scraping: `scraper_clean/` como motor principal local

Justificacion estado (`Zustand`): el estado principal en esta app es UI-centric (filtros globales, paginacion, modulo activo, parametros de auto-refresh). `Zustand` reduce boilerplate y permite un store unico simple sin acoplarlo a un cache server-state complejo.

## Estructura

- Backend API: `app_backend/`
- Frontend app: `frontend/`
- Dataset canonico activo: `data/current/master_prices.csv`
- Historicos publicados: `data/history/{snapshot_id}/`
- Indice persistente de runs y snapshots: `data/state.sqlite`
- Logs persistidos por run: `data/logs/{run_id}.log`
- Artefactos derivados actuales: `data/current/latest_prices.json`, `data/current/latest_prices.csv`
- Compatibilidad legacy: `master_prices.csv` y `output/latest_*`
- Fallback demo local (si faltan datos reales): se activa automaticamente desde `app_backend/intelligence.py`

## Instalacion

### 1) Python deps

```bash
python -m pip install -r requirements.full.txt
python -m playwright install chromium
```

### 2) Frontend deps

```bash
cd frontend
cmd /c "set npm_config_cache=%CD%\\..\\.npm-cache&& npm install"
```

## Arranque

### Backend

```bash
python -m uvicorn app_backend.main:app --host 127.0.0.1 --port 8000
```

### Frontend

```bash
cd frontend
cmd /c npm run dev -- --host 127.0.0.1 --port 5173
```

### Variables utiles para despliegue

- Worker/API persistente:
  - `OBSERVATORIO_EDITOR_TOKEN=...`
- Frontend/Vercel:
  - `VITE_API_BASE_URL=https://tu-worker/api`

## Despliegue recomendado

### Worker persistente en Render

El repo ya incluye:
- [render.yaml](c:\Users\juan.gugel.gonzalez\OneDrive - Accenture\ACCENTURE\NewCo\Sistema_Observatorio\render.yaml)
- [Dockerfile.worker](c:\Users\juan.gugel.gonzalez\OneDrive - Accenture\ACCENTURE\NewCo\Sistema_Observatorio\Dockerfile.worker)
- [scripts/run_worker.py](c:\Users\juan.gugel.gonzalez\OneDrive - Accenture\ACCENTURE\NewCo\Sistema_Observatorio\scripts\run_worker.py)

Config esperada del worker:
- runtime Docker
- disco persistente montado en `/var/data/observatorio`
- `OBSERVATORIO_DATA_DIR=/var/data/observatorio`
- `OBSERVATORIO_EDITOR_TOKEN=<token elegido por ti>`
- `OBSERVATORIO_ALLOWED_ORIGINS=https://sistema-observatorio.vercel.app`

La URL final del worker sera algo como:
- `https://tu-worker.onrender.com/api`

### Frontend en Vercel

Con el worker ya publicado, puedes desplegar Vercel con el script:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/deploy_vercel_frontend.ps1 -ApiBaseUrl https://tu-worker.onrender.com/api
```

El script:
- lee tu token de Vercel desde `hola.txt`
- actualiza `VITE_API_BASE_URL` en `production`
- lanza `vercel --prod`

### Refresh diario en GitHub Actions

El repo incluye [`.github/workflows/daily_refresh.yml`](c:\Users\juan.gugel.gonzalez\OneDrive - Accenture\ACCENTURE\NewCo\Sistema_Observatorio\.github\workflows\daily_refresh.yml), que:
- corre cada dia a las `09:00` hora peninsular espanola (`Europe/Madrid`), ajustando CET/CEST
- ejecuta `scraper_clean`
- publica `data/current/` y `data/history/`
- regenera `output/latest_*` y `master_prices.csv`
- hace commit de los datos nuevos en `main`
- despliega la app de produccion en Vercel desde GitHub Actions usando `VERCEL_TOKEN`

Script de publicacion usado por el workflow:
- [scripts/run_daily_refresh.py](c:\Users\juan.gugel.gonzalez\OneDrive - Accenture\ACCENTURE\NewCo\Sistema_Observatorio\scripts\run_daily_refresh.py)

El repo incluye tambien [`.github/workflows/deploy_vercel.yml`](c:\Users\juan.gugel.gonzalez\OneDrive - Accenture\ACCENTURE\NewCo\Sistema_Observatorio\.github\workflows\deploy_vercel.yml), que despliega Vercel en cada `push` a `main` y permite disparo manual con `workflow_dispatch`.

### URLs

- App: `http://127.0.0.1:5173`
- API health: `http://127.0.0.1:8000/api/health`

## Endpoints principales (nueva app)

### Datos / filtros
- `GET /api/intelligence/filters`
- `GET /api/intelligence/records`
- `GET /api/intelligence/comparator`
- `GET /api/intelligence/dashboard`
- `GET /api/intelligence/export?fmt=csv|json&snapshot_id=current|{id}`
- `GET /api/table/rows?snapshot_id=current|{id}`
- `GET /api/table/meta?snapshot_id=current|{id}`
- `GET /api/table/snapshots`
- `GET /api/table/snapshots/{snapshot_id}`

### Agente local
- `POST /api/intelligence/agent/query`

### Publicacion / historico
- `GET /api/table/publish-info`

## Integracion con scraping

La app publica datos en modo read-only. El scraping queda automatizado en un workflow diario.

Flujo actual:
- Cada refresh diario exitoso genera un snapshot en `data/history/{snapshot_id}/`.
- Solo despues de un refresh diario exitoso se actualiza `data/current/master_prices.csv`.
- Si el refresh diario falla, el dataset vigente anterior se conserva intacto.
- La pestaña `Actualizacion diaria` muestra ultima publicacion y acceso al historico.

Para compatibilidad con la app y los artefactos existentes, tras cada corrida se regeneran:
- `output/latest_prices.json`
- `output/latest_prices.csv`
- `output/unified_last_scrapes_with_book.csv`
- `output/price_comparison_live.html`

Notas:
- El flujo manual de updater/scraping local sigue existiendo en `app_backend.main`, pero no se expone en la app publica.
- La pestaña `Visualizador` permite elegir snapshot historico y descargar el CSV exacto de esa version.
- Los snapshots timestamped `master_prices_*.csv` se conservan como salida del scraper, pero la app consume `data/current/master_prices.csv`.
- El frontend publico puede funcionar sin worker persistente si consumes directamente los snapshots versionados del repo.

## Comando helper de arranque simultaneo

Tambien puedes usar:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/start_observatorio_app.ps1
```

Y parar con:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/stop_observatorio_app.ps1
```

## Checklist de validacion funcional

- [x] Backend responde `GET /api/health` con `{"status":"ok"}`
- [x] Frontend compila y abre sin cambios de contrato
- [x] Comparador y dashboard siguen leyendo el dataset vigente
- [x] Actualizacion diaria muestra ultima publicacion y snapshots historicos
- [x] GitHub Actions programa un refresh diario y publica snapshots versionados
- [x] `GET /api/table/publish-info` expone la publicacion vigente
- [x] Visualizador lista snapshots, abre historicos y descarga el CSV exacto por `snapshot_id`
- [x] `GET /api/table/meta`, `GET /api/table/rows` y `GET /api/intelligence/export` leen snapshots historicos
- [x] Dashboard muestra KPIs + graficas
- [x] Agente responde consultas sin API key (modo local)

## Notas

- `data/current/master_prices.csv` es la fuente de verdad vigente para dashboard, comparador y visualizador.
- Si `output/latest_prices.json` no existe o viene vacio, se sirve dataset demo local para que la app no quede bloqueada.

## Codex workflow

- Instrucciones estables del repo: `AGENTS.md`
- Estado vivo del scraping: `docs/project_checkpoint.md`
- Setup para sesiones con menos desgaste de contexto: `docs/codex_setup.md`
