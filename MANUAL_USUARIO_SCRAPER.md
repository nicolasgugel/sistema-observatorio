# Manual de Usuario - Scraper Observatorio (Daily)

## 1) Objetivo
Este manual explica como:
- montar el scraper en una maquina nueva,
- ejecutarlo en modo diario,
- generar historico CSV/JSON/HTML con timestamp,
- validar rapidamente si la corrida salio bien,
- mejorarlo sin romper lo que ya esta estable.

El flujo recomendado hoy es:
- script principal diario: `run_observatorio_focus_fast.py`
- scope fijo: `iPhone 17*` + `iPhone Air` + `Galaxy S25*` (mobile)
- salida automatica: CSV, JSON y HTML (latest + historico)

## 2) Requisitos
- Python 3.12+
- Windows/macOS/Linux con acceso a internet
- Dependencias Python del repo
- Playwright + Chromium instalado

Instalacion:

```bash
python -m pip install -r requirements.txt
python -m playwright install chromium
```

## 3) Estructura minima que debes compartir
Para que otra persona lo ejecute, comparte el repo completo. Minimo:
- `run_observatorio_focus_fast.py`
- carpeta `observatorio/`
- `requirements.txt`
- `price_comparison_v10_dual_brand.html`

## 4) Script diario recomendado
Comando base:

```bash
python run_observatorio_focus_fast.py
```

Por defecto ejecuta:
- marcas: `Samsung` + `Apple`
- competidores:
  - `Santander Boutique`
  - `Amazon`
  - `Media Markt`
  - `Grover`
  - `Movistar`
  - `Rentik`
  - `Samsung Oficial`
  - `Apple Oficial`

## 5) Parametros utiles del runner rapido
Ver ayuda:

```bash
python run_observatorio_focus_fast.py --help
```

Parametros principales:
- `--brand {all,Samsung,Apple}`
- `--max-products <int>`
- `--competitors "Santander Boutique,Amazon,Media Markt,..."`
- `--headed` (abre navegador visible para debug)
- `--template <ruta_html_template>`
- `--output-dir <carpeta_salida>`
- `--html-out <ruta_html_latest>`

Ejemplos:

```bash
python run_observatorio_focus_fast.py --brand Samsung
python run_observatorio_focus_fast.py --brand Apple --competitors "Santander Boutique,Amazon,Apple Oficial"
python run_observatorio_focus_fast.py --headed
```

## 6) Archivos de salida por corrida
En cada ejecucion se generan:

- latest (se sobreescribe):
  - `output/latest_prices.json`
  - `output/latest_prices.csv`
  - `output/price_comparison_live.html`

- historico (nuevo en cada corrida):
  - `output/prices_YYYYMMDD_HHMMSS.json`
  - `output/prices_YYYYMMDD_HHMMSS.csv`
  - `output/price_comparison_live_YYYYMMDD_HHMMSS.html`

- snapshot unificado (se sobreescribe):
  - `output/unified_last_scrapes_with_book.csv`

## 7) Checklist de validacion rapida (post-run)
Despues de cada corrida, revisa:

1. En consola:
- `[OK] Registros de precio: ...`
- `[OK] HTML historico: ...`
- `[OK] HTML comparativa: ...`

2. En `output/latest_prices.csv`:
- que solo existan modelos del scope objetivo,
- que haya datos de `Santander Boutique`,
- que `Samsung Oficial` tenga registros para Samsung (S25/S25 Ultra).

3. En HTML:
- abre `output/price_comparison_live.html`
- valida que los productos mostrados coinciden con esa tirada.

## 8) Ejecucion diaria automatica (Windows)
### Opcion A: Task Scheduler
1. Crear tarea basica en Programador de tareas.
2. Trigger diario (hora deseada).
3. Action:
- Program/script: `python`
- Add arguments: `run_observatorio_focus_fast.py`
- Start in: ruta del repo

### Opcion B: `.bat` manual o task scheduler
Crear `run_daily_focus_fast.bat`:

```bat
@echo off
cd /d C:\RUTA\AL\REPO
python run_observatorio_focus_fast.py
```

## 9) Troubleshooting comun
### Error Playwright / navegador no arranca
Reinstalar chromium:

```bash
python -m playwright install chromium
```

### Corrida lenta o muy larga
- Lanza solo una marca:
  - `--brand Samsung` o `--brand Apple`
- Reduce temporalmente competidores:
  - `--competitors "Santander Boutique,Amazon,Media Markt"`
- Mantener `headless` (no usar `--headed` salvo debug).

### Competidor con 0 registros
Puede ser anti-bot o cambio DOM.
Prueba:
- `--headed` para inspeccion visual.
- corrida focalizada por competidor:
  - `python run_observatorio_focus_fast.py --competitors "Santander Boutique,<competidor>"`

### Warning de PowerShell profile
Si aparece warning de `ExecutionPolicy` al final pero la corrida termina con `[OK]`, normalmente no afecta al resultado del scraper.

## 10) Como mejorar el scraper sin romper lo estable
Regla principal:
- no tocar el flujo diario estable sin una validacion focalizada.

Orden recomendado para cambios:
1. Probar cambio en corrida minima.
2. Probar marca unica.
3. Probar subset de competidores.
4. Probar corrida completa.

Comandos de validacion sugeridos:

```bash
python run_observatorio_focus_fast.py --brand Samsung --competitors "Santander Boutique,Samsung Oficial"
python run_observatorio_focus_fast.py --brand Apple --competitors "Santander Boutique,Apple Oficial,Amazon"
python run_observatorio_focus_fast.py
```

## 11) Guia para anadir o mejorar un competidor
Pasos tecnicos:
1. Crear/adaptar extractor dedicado en `observatorio/scraper.py`.
2. Conectar el extractor en `scrape_prices_for_competitor(...)`.
3. Si aplica, actualizar slugs/urls en `observatorio/config.py`.
4. Validar cobertura por `model + capacity`.
5. Verificar que no rompe competidores ya cerrados.

## 12) Guia para mejorar rendimiento
Acciones de mayor impacto:
- mantener seeds compactadas por `modelo + capacidad` (ya activo en runner fast),
- evitar correr competidores no necesarios en iteracion,
- reducir `--headed` a casos de debug,
- separar validaciones por marca cuando se toca un adaptador concreto.

## 13) Modo full catalog (fallback)
Si necesitas volver al pipeline amplio:

```bash
python run_observatorio.py --scope full_catalog --max-products 12
```

## 14) Resumen operativo
Para el dia a dia, usa:

```bash
python run_observatorio_focus_fast.py
```

Ese comando ya deja:
- historico CSV/JSON con timestamp,
- HTML latest y HTML historico por tirada,
- comparativa solo con los productos scrapeados en esa ejecucion.
