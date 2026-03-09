# Scope: scraping core

Usa este directorio para adaptadores, matching, normalizacion y generacion del HTML comparativo.

## Reglas
- Lee `../docs/project_checkpoint.md` solo cuando la tarea dependa del estado actual de competidores, cobertura o validaciones recientes.
- Usa `../skills/observatorio-competitor-scraping/SKILL.md` para el workflow de cierre competidor por competidor.
- Para iteraciones rapidas, prefiere:
  - `python ../skills/observatorio-competitor-scraping/scripts/run_competitor.py --competitor "..."`
  - `python ../skills/observatorio-competitor-scraping/scripts/summarize_prices.py --json ../output/latest_prices.json`
- No des por bueno un precio, modalidad o URL si proviene de un fallback generico que pueda inventar datos.
- Valida siempre por `marca + modelo + capacidad` y por modalidad antes de marcar un competidor como cerrado.
- Actualiza `../docs/project_checkpoint.md` despues de cambios validados que afecten cobertura, cierre o limitaciones externas.
