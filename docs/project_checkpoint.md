# Project checkpoint

Actualizar este archivo solo despues de una corrida validada que cambie estado de cierre, cobertura, matching o limitaciones relevantes.

## Runtime publicado actual
- Fuente de verdad de publicacion: `scraping_bundle_20260312_ready`.
- `data/current`, `data/history` y `output/latest_*` se generan desde el runtime publicado y aplican politica accuracy-first.
- `run_observatorio.py` y `observatorio/scraper.py` quedan en modo legacy/diagnostico y no deben usarse para declarar cobertura publicada ni cierre de competidores.
- `output/latest_*` es compatibilidad del snapshot publicado; la evidencia de la corrida real y su CSV crudo viven en metadata/runs del backend.
- Los checkpoints historicos de abajo contienen validaciones previas del pipeline legacy y requieren revalidacion en el runtime publicado antes de tomarse como estado de cierre vigente.

## Cola actual de trabajo
1. Amazon: cerrado.
2. Media Markt: cerrado para `cash` y financiacion visible.
3. Grover: en curso.
4. Continuar competidor por competidor hasta cubrir los 12 objetivos.

## Baseline actual
- Santander Boutique: extraccion en vivo operativa via API oficial + apoyo HTML para modalidades.
- Amazon: adaptador dedicado operativo; matching por `modelo + capacidad`; ASIN unico por producto base en cada corrida.
- Media Markt: adaptador dedicado operativo; retry automatico en `headed` si `headless` devuelve cobertura parcial; `cash` + `financing_max_term` con periodicidades desde `GetInstallmentCalculations`.
- PcComponentes: adaptador base creado, pero Cloudflare puede bloquear algunas corridas.
- Resto de competidores: pendientes de cierre con adaptador dedicado o flujo robusto.

## Ultimas validaciones integradas

### Runtime publicado Samsung + Media Markt
- Comando: `python -u scripts/run_published_runtime.py --brand Samsung --competitors "Media Markt" --output mediamarkt_run_20260325_fix2`
- Base Santander: 18 seeds Samsung, 18/18 cubiertos en Boutique.
- Media Markt: 65 registros, 16/18 en cobertura por `modelo + capacidad`.
- Modalidades publicadas en la corrida validada:
  - `cash`: 16
  - `financing_max_term`: 49
- Validacion live: `passed` en `output/mediamarkt_run_20260325_fix2_20260325_103655_validation.json`.
- Fixes relevantes validados:
  - seed pool Samsung ampliado y deduplicado por `modelo + capacidad`
  - descarte de match incorrecto `A17 5G -> A17 LTE`
  - `cash` de Media Markt extraido desde el precio visible principal de la PDP
  - financiacion visible priorizada cuando el modal no coincide con la cuota mostrada en la PDP
- Cobertura visible validada en la corrida:
  - `Samsung Galaxy A36 5G 128GB`: `cash 349 EUR` + `financing 38 EUR/mes x10`
  - `Samsung Galaxy A56 5G 128GB`: `cash 459 EUR` + financiacion visible y modal consistente
  - `Samsung Galaxy Z Fold 7 256GB`: `cash` + financiacion
- Faltantes actuales en Media Markt:
  - `Samsung Galaxy A17 5G 128GB`
  - `Samsung Galaxy Book5 Pro 14 512GB`

### Santander + Amazon
- Comando: `python run_observatorio.py --max-products 8 --competitors "Santander Boutique,Amazon"`
- Base Santander: 8 productos Samsung.
- Cobertura Amazon: 8/8 con precio capturado.
- Archivos generados:
  - `output/latest_prices.json`
  - `output/latest_prices.csv`
  - `output/price_comparison_live.html`

### Santander + Amazon + Media Markt
- Comando: `python run_observatorio.py --max-products 8 --competitors "Santander Boutique,Amazon,Media Markt"`
- Base Santander: 8 productos Samsung.
- Cobertura Amazon: 8/8.
- Cobertura Media Markt en modelos: 8/8.
- Cobertura Media Markt en `cash`: 8/8.
- Cobertura Media Markt en `financing_max_term`: 7/8. Un producto no mostro bloque de financiacion visible durante la extraccion.
- Total de registros: 157 = 78 Santander + 8 Amazon + 71 Media Markt.
- Nota tecnica: se corrigio el parseo de importes de 4 digitos y se incorporaron plazos de financiacion como 3, 6, 10, 12, 14, 18, 20, 24 y 30 meses cuando el endpoint los devuelve.

## Estado por competidor

### Grover
- Adaptador: `grover_adapter_live` en `observatorio/scraper.py`.
- Matching: estricto por `modelo + capacidad + URL Samsung`; sin fallback generico.
- Modalidades visibles actuales: `renting_with_insurance` (planes 6/12/18 meses cuando existen).
- No se observa precio fiable actual para `cash`, `financing_max_term` ni `renting_no_insurance`.
- Ultima validacion integrada:
  - Comando: `python run_observatorio.py --max-products 8 --competitors "Santander Boutique,Amazon,Media Markt,Grover" --headed`
  - Registros Grover: 9
  - Cobertura por `modelo + capacidad`: 3/8
  - Matches validos:
    - `Samsung Galaxy S25 Ultra 256GB`
    - `Samsung Galaxy Z Flip 7 256GB`
    - `Samsung Galaxy Z Fold 7 256GB`
  - Sin match valido actual:
    - `Samsung Galaxy A17 5G 128GB`
    - `Samsung Galaxy A36 5G 128GB`
    - `Samsung Galaxy A56 5G 128GB`
    - `Samsung Galaxy S25 256GB`
    - `Samsung Galaxy S25 FE 5G 128GB`

### Movistar
- Adaptador: `movistar_adapter_live`.
- Descubrimiento: busqueda en `https://www.movistar.es/moviles/?sort=relevance&query=...` con matching estricto y fallback por familia de modelo.
- Fix relevante: `fe` ya se detecta por tokens y no por subcadenas como `ofertas`.
- Modalidades capturadas: `financing_max_term` y `cash`.
- Renting no es fiable en la ficha actual.
- Validacion:
  - Comando: `python run_observatorio.py --max-products 12 --competitors "Movistar"`
  - Registros Movistar: 16
  - Cobertura por `modelo + capacidad`: 8/8
  - Nota: la semilla Santander `A56 128GB` encontro variante `A56 5G 256GB` en Movistar.
  - Sin faltantes en la corrida validada.

### Fnac
- Adaptador: `fnac_adapter_live`.
- Flujo: busqueda en Fnac + matching por modelo/variantes + extraccion de `cash` y `financing_max_term`.
- Robustez anti-bloqueo: deteccion DataDome/CAPTCHA, retry `headed` y espera manual de desbloqueo hasta 60s.
- Validaciones:
  - `python run_observatorio.py --max-products 12 --competitors "Fnac"`
  - `python run_observatorio.py --max-products 12 --competitors "Fnac" --headed`
- Resultado actual: 0 registros por challenge DataDome (`Slide right to secure your access`).
- Estado: adaptador listo, pendiente de una ejecucion sin challenge.

### Rentik
- Adaptador: `rentik_adapter_live`.
- Flujo: catalogo Samsung -> matching estricto por `modelo + capacidad` -> extraccion visible en ficha.
- Sin fallback generico para evitar capturas espurias.
- Modalidades del adaptador: `renting_with_insurance` y `renting_no_insurance` cuando se muestra explicitamente.
- Validacion:
  - Comando: `python skills/observatorio-competitor-scraping/scripts/run_competitor.py --competitor "Rentik" --closed-base "Santander Boutique" --max-products 8`
  - Registros Rentik: 6
  - Cobertura por `modelo + capacidad`: 6/8
  - Modalidad detectada en la corrida validada: `renting_with_insurance`
  - Matches validos:
    - `Samsung Galaxy S25 256GB`
    - `Samsung Galaxy S25 Ultra 256GB`
    - `Samsung Galaxy A56 5G 128GB`
    - `Samsung Galaxy A36 5G 128GB`
    - `Samsung Galaxy Z Flip 7 256GB`
    - `Samsung Galaxy Z Fold 7 256GB`
  - Sin match valido actual:
    - `Samsung Galaxy A17 5G 128GB`
    - `Samsung Galaxy S25 FE 5G 128GB`
  - Notas:
    - `Samsung Galaxy S25 Ultra 256GB` validado a `63,9 EUR/mes`, distinto de `512GB = 67,9 EUR/mes`.
    - `Samsung Galaxy A17 5G` solo mostraba `256GB` en Rentik durante la validacion.
    - `Samsung Galaxy S25 FE 5G 128GB` no aparecia en catalogo ni en busqueda.

## Nota de seed laptop: Samsung Book5 en Amazon
- Objetivo: cerrar el hueco de `Samsung Galaxy Book5 Pro 14 512GB` con matching exacto por capacidad.
- Cambios en `observatorio/scraper.py`:
  - parseo de capacidad reforzado para `GB` y `TB`
  - queries enriquecidas con `product_code` Santander
  - matcher laptop con soporte de `product_code`
  - matcher Amazon acepta identidad por `product_code`
  - filtros anti-accesorios ampliados
- Validacion dirigida:
  - corrida ad-hoc contra `_scrape_amazon_prices` con 1 seed laptop
  - resultado exacto: Amazon, `Samsung Galaxy Book5 Pro 14`, `512GB`, `cash`, `1489.0`, `https://www.amazon.es/dp/B0F2W3VRK1`
- Validacion integrada ligera:
  - Comando: `python run_observatorio.py --max-products 3 --competitors "Santander Boutique,Amazon"`
  - Base: 3 productos (movil + tablet + laptop)
  - Amazon: 3/3 cubiertos
  - Laptop exacto `512GB`: 1/1
- Nota de estabilidad: corridas amplias de Amazon todavia pueden caer por timeouts intermitentes en algunas semillas.

## Regla operativa para iteraciones rapidas
- Ejecutar solo el competidor objetivo en pruebas iterativas.
- Helpers actuales:
  - `python skills/observatorio-competitor-scraping/scripts/run_competitor.py --competitor "Movistar"`
  - `python skills/observatorio-competitor-scraping/scripts/run_competitor.py --competitor "Fnac"`
- `run_competitor.py` usa base vacia por defecto y ejecuta solo el competidor solicitado.
