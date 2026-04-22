# Auditoria de diferencias >30%

- Fichero auditado: `C:\Users\juan.gugel.gonzalez\OneDrive - Accenture\ACCENTURE\NewCo\Sistema_Observatorio\output\santander_vs_competidores_diff_gt_30.csv`
- Fecha auditoria: 2026-03-02
- Filas revisadas: **51**

## Resumen por estado
- MISMATCH_CAPACITY_URL: 14
- OK: 12
- GENERIC_BUY_PAGE_VARIANT_UNCLEAR: 9
- PARTIAL_OK: 5
- MISMATCH_CONNECTIVITY_URL: 5
- UNVERIFIED_BLOCKED_CAPTCHA: 3
- WRONG_PRODUCT_ACCESSORY: 1
- PRICE_MISMATCH_LIVE: 1
- MODEL_GENERATION_MISMATCH: 1

## Hallazgos criticos (modelo/capacidad/plazo)
- Row 1: Amazon | Apple MacBook Air 13 M4 512GB | WRONG_PRODUCT_ACCESSORY | ASIN apunta a accesorio, no al dispositivo | sin marcador expl?cito de segunda mano en t?tulo | title=360° Privacy Filter for MacBook Air 13.6 inch M4 2025 / M3 2024 / M2 2022, Anti-Spy Filter Screen Protection Privacy Screen for Mac Laptop Model - A3240 : Amazon.es: Computers
- Row 4: Movistar | Samsung Galaxy S25 256GB | PRICE_MISMATCH_LIVE | precio_csv=12.0 vs cuota_pagina=11.5 | plazo_csv=24 vs plazo_pagina=48
- Row 5: Amazon | Apple Mac Studio M4 Max 512GB | MODEL_GENERATION_MISMATCH | faltan tokens de generaci?n en t?tulo: ['m4'] | sin marcador expl?cito de segunda mano en t?tulo | title=Hard Drives Brand Apple Model Apple Mac Studio 27 M2 MAX Chip with 12Core CPU + 30Core GPU 32GB 512SSD : Amazon.es: Computers
- Row 16: Movistar | Samsung Galaxy S25 Ultra 256GB | MISMATCH_CAPACITY_URL | cap_csv=256GB vs cap_url/title=[512]GB | cuota_pagina=22.5 coincide con csv | plazo_csv=24 vs plazo_pagina=48
- Row 22: Media Markt | Samsung Galaxy S25 Ultra 256GB | MISMATCH_CAPACITY_URL | cap_csv=256GB vs cap_url=[512]GB
- Row 26: Media Markt | Samsung Galaxy S25 Ultra 256GB | MISMATCH_CAPACITY_URL | cap_csv=256GB vs cap_url=[512]GB
- Row 28: Media Markt | Samsung Galaxy Z Flip 7 256GB | MISMATCH_CAPACITY_URL | cap_csv=256GB vs cap_url=[512]GB
- Row 31: Media Markt | Samsung Galaxy S25 Ultra 256GB | MISMATCH_CAPACITY_URL | cap_csv=256GB vs cap_url=[512]GB
- Row 32: Media Markt | Samsung Galaxy S25 Ultra 256GB | MISMATCH_CAPACITY_URL | cap_csv=256GB vs cap_url=[512]GB
- Row 33: Media Markt | Samsung Galaxy Z Flip 7 256GB | MISMATCH_CAPACITY_URL | cap_csv=256GB vs cap_url=[512]GB
- Row 35: Media Markt | Samsung Galaxy Z Flip 7 256GB | MISMATCH_CAPACITY_URL | cap_csv=256GB vs cap_url=[512]GB
- Row 36: Media Markt | Samsung Galaxy Z Flip 7 256GB | MISMATCH_CAPACITY_URL | cap_csv=256GB vs cap_url=[512]GB
- Row 39: Media Markt | Samsung Galaxy S25 Ultra 256GB | MISMATCH_CAPACITY_URL | cap_csv=256GB vs cap_url=[512]GB
- Row 40: Media Markt | Apple iPad Air M3 11 WiFi 128GB | MISMATCH_CONNECTIVITY_URL | modelo_csv=WiFi pero URL indica WiFi+Cellular
- Row 41: Media Markt | Apple iPad Air M3 11 WiFi 128GB | MISMATCH_CONNECTIVITY_URL | modelo_csv=WiFi pero URL indica WiFi+Cellular
- Row 43: Media Markt | Samsung Galaxy S25 Ultra 256GB | MISMATCH_CAPACITY_URL | cap_csv=256GB vs cap_url=[512]GB
- Row 44: Media Markt | Samsung Galaxy Z Flip 7 256GB | MISMATCH_CAPACITY_URL | cap_csv=256GB vs cap_url=[512]GB
- Row 45: Media Markt | Apple iPad Air M3 11 WiFi 128GB | MISMATCH_CONNECTIVITY_URL | modelo_csv=WiFi pero URL indica WiFi+Cellular
- Row 47: Media Markt | Samsung Galaxy Z Flip 7 256GB | MISMATCH_CAPACITY_URL | cap_csv=256GB vs cap_url=[512]GB
- Row 49: Media Markt | Apple iPad Air M3 11 WiFi 128GB | MISMATCH_CONNECTIVITY_URL | modelo_csv=WiFi pero URL indica WiFi+Cellular
- Row 50: Media Markt | Samsung Galaxy S25 Ultra 256GB | MISMATCH_CAPACITY_URL | cap_csv=256GB vs cap_url=[512]GB
- Row 51: Media Markt | Apple iPad Pro M5 13 WiFi 256GB | MISMATCH_CONNECTIVITY_URL | modelo_csv=WiFi pero URL indica WiFi+Cellular

## Notas de verificacion
- Movistar: verificacion en vivo de cuota /mes por extraccion textual + validacion manual de dos casos (rows 21 y 23).
- Amazon: validacion por titulo de ASIN y comprobacion de posible segunda mano en titulo.
- MediaMarkt: bloqueo CAPTCHA/403 en acceso automatizado; validacion por URL cuando fue posible.
- Apple/Samsung Oficial: paginas de compra genericas con selector, no siempre cerradas por variante.