# Workflow de cierre por competidor

## Objetivo
Estandarizar el avance del scraping en `Sistema_Observatorio` para cerrar competidores uno a uno sin romper los ya validados.

## Entrada
- Base de productos Samsung desde Santander Boutique (idealmente 10-12, minimo el lote activo de la corrida).
- Competidores ya cerrados en `docs/project_checkpoint.md`.
- Competidor objetivo de la iteracion.

## Paso 1. Ejecutar corrida minima util
Comando recomendado:

```bash
python skills/observatorio-competitor-scraping/scripts/run_competitor.py --competitor "Media Markt"
```

Opcional en caso de anti-bot o cobertura parcial:

```bash
python skills/observatorio-competitor-scraping/scripts/run_competitor.py --competitor "Media Markt" --headed
```

## Paso 2. Validar cobertura y modalidades
Comando:

```bash
python skills/observatorio-competitor-scraping/scripts/summarize_prices.py --json output/latest_prices.json
```

Comprobar:
- Cobertura por `model + capacity` contra Santander Boutique.
- Modalidades segun competidor:
  - Santander Boutique: `cash`, `financing`, `renting` (con/sin seguro cuando aplique).
  - Amazon: normalmente `cash`.
  - Media Markt: `cash` y `financing_max_term` solo cuando cuota y plazo salen visibles/exactos del payload o del DOM.
- Regla de publicacion accuracy-first:
  - ninguna fila publicada puede venir de calculos sobre `cash`, division por plazo o TIN por defecto
  - si hay mismatch de capacidad/conectividad o match debil, la fila se descarta
  - `output/latest_*` es compatibilidad del snapshot publicado; el rastro de la corrida real vive en el raw CSV y en metadata

## Paso 3. Decidir cierre del competidor
Marcar como cerrado cuando:
- No hay regresion en competidores previamente cerrados.
- Cobertura de modelos/capacidades es aceptable para el lote base de esa ejecucion.
- Modalidades esperadas para el competidor quedan extraidas o se documenta claramente una limitacion externa (anti-bot o ausencia real en web).

Nota:
- Durante la iteracion normal, correr solo el competidor objetivo.
- Antes de declarar cierre, ejecutar la regresion minima necesaria sobre competidores ya cerrados si el cambio toca logica compartida.

## Paso 4. Actualizar contexto del proyecto
Actualizar `docs/project_checkpoint.md` con:
- Comando ejecutado.
- Cobertura por competidor/modalidad.
- Limitaciones detectadas.
- Siguiente competidor de la cola.

## Salida esperada
- `output/latest_prices.json`
- `output/latest_prices.csv`
- `output/price_comparison_live.html`
- Estado del cierre actualizado en `docs/project_checkpoint.md`.
- Runtime de publicacion: `scraping_bundle_20260312_ready`.
- Runtime legacy/diagnostico: `run_observatorio.py` + `observatorio/scraper.py`.
