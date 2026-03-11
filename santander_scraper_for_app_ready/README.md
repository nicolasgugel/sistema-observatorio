# Santander Scraper Runtime For App

Esta carpeta contiene el runtime limpio que debe integrarse en el proyecto principal para usar el scraper validado.

## Contenido incluido

- `main.py`: orquestador del scrape completo.
- `config.py`: configuración central.
- `requirements.txt`: dependencias Python del runtime.
- `scrapers/`: scrapers activos usados por el orquestador.
- `models/`: esquema de salida `PriceRow` y modelos auxiliares.
- `matching/`: lógica de matching.
- `exporters/csv_exporter.py`: exportación a CSV.

## Cambios funcionales ya incluidos

- Amazon con mejor fallback y matching de variantes.
- Rentik resolviendo disponibilidad real de capacidad/color.
- Samsung Store revalidando PDP y capacidad real antes de aceptar el precio.
- Movistar clasificado como `renting_no_insurance` cuando aplica.
- MediaMarkt con matching más estricto para Apple Silicon.

## Qué copiar al proyecto principal

Copiar esta carpeta completa o integrar su estructura equivalente dentro del backend principal.

Si el proyecto principal ya tiene un módulo de scraping, la forma más segura es:

1. Copiar esta carpeta como un módulo nuevo.
2. Ejecutar `pip install -r requirements.txt` en el entorno del backend.
3. Invocar `python main.py --scrapers boutique grover rentik amazon mediamarkt apple_store samsung_store movistar`.
4. Consumir el CSV generado o importar directamente `main_async`.

## Notas de integración

- El runtime genera logs `scraping_YYYYMMDD_HHMM.log` en el directorio de ejecución.
- El scrape completo tarda del orden de 20 minutos, así que conviene lanzarlo como job de backend y no dentro de una request síncrona.
- El esquema de salida está definido en `models/price_row.py`.
- `offer_type` puede ser: `cash`, `financing_max_term`, `renting_no_insurance`, `renting_with_insurance`.

## Baseline validada

La validación más estable en este workspace corresponde a:

- `master_prices_v10_20260311_0918.csv`
- `price_outlier_flags_v10_20260311_0918.csv`

Esos ficheros no forman parte de esta carpeta porque son solo referencia de validación.
