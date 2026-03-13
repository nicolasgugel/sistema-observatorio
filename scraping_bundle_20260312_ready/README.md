# Santander Scraper Bundle

Carpeta autocontenida con el codigo necesario para ejecutar el scraping fuera de este repo.

## Contenido

- `main.py`: orquestador principal
- `scrapers/`: scrapers de Boutique y competidores activos
- `models/`: modelos de datos
- `exporters/`: exportacion CSV y Excel
- `matching/`: utilidades de matching
- `requirements.txt`: dependencias Python
- `targets_example.json`: targets opcionales para correr competidores sin Boutique

## Instalacion

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

## Ejemplos de uso

Full run:

```bash
python main.py --scrapers boutique grover rentik amazon mediamarkt apple_store samsung_store movistar orange el_corte_ingles --output master_prices
```

Prueba rapida:

```bash
python main.py --scrapers boutique orange el_corte_ingles --test --output smoke_test
```

Competidores usando targets ya generados:

```bash
python main.py --targets-file targets_example.json --scrapers orange el_corte_ingles samsung_store --output competitors_only
```

## Notas

- Ejecuta los comandos desde esta carpeta.
- Los CSV y logs se generan en esta misma carpeta.
- `scrapling[fetchers]` y `camoufox[geoip]` son obligatorios para los scrapers con navegador.
- Esta carpeta no incluye `debug_*`, `__pycache__`, CSV historicos ni logs antiguos.
