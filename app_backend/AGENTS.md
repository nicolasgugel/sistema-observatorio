# Scope: backend local app

Usa este directorio para la API FastAPI y la orquestacion de la app local.

## Reglas
- Mantener estables `/api/health` y `/api/intelligence/*` salvo que la tarea pida un cambio de contrato.
- Reutilizar `output/latest_prices.json` y `output/latest_prices.csv` como fuente principal de datos.
- Preservar el fallback demo local cuando falten datos reales para que la app no quede bloqueada.
- No mover scraping largo a request handlers salvo que la tarea lo requiera de forma explicita; preferir el flujo del updater y los scripts existentes.
