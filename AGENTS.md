# Contexto de trabajo - Sistema Observatorio

## Objetivo del proyecto
Construir un sistema que:
1. Haga scraping en vivo de productos Samsung en Santander Boutique.
2. Haga scraping en vivo de esos mismos productos en competidores.
3. Genere un HTML de comparativa de precios con grafico de barras.

## Reglas estables del dominio
- Archivo base visual: `price_comparison_v5_wow.html`.
- El entregable inicial debe mantenerse como HTML estatico.
- Competidores objetivo: Amazon, El Corte Ingles, Fnac, Grover, Media Markt, Movistar, Orange, PcComponentes, Qonexa, Rentik, Santander Boutique y Vodafone.
- Si el esfuerzo inicial es demasiado alto, se puede reducir temporalmente la cobertura a 7 competidores.
- Base de productos: entre 10 y 12 productos Samsung disponibles en Santander Boutique.
- En cada competidor solo se buscan esos productos base; no el catalogo completo.
- Claves obligatorias de comparacion: `modalidad`, `modelo`, `capacidad`.
- Modalidades obligatorias del dataset cuando existan de forma fiable en web: `renting_no_insurance`, `renting_with_insurance`, `financing`, `cash`.
- Regla de precio: capturar el primer precio visible por modalidad sin aplicar reglas extra de envio, descuentos ocultos o promociones inferidas.
- Clave temporal de matching: `marca + modelo + capacidad`.
- Stack inicial: Python + Playwright + parsing HTML segun necesidad.
- Prioridad tecnica: robustez de captura sobre complejidad arquitectonica.

## Workflow esperado
1. Activacion del sistema.
2. Scraping de informacion de productos.
3. Construccion del dataset normalizado.
4. Generacion del HTML de comparativa.

## Entregable inicial esperado
- Pipeline funcional de scraping en vivo para el universo Samsung de Santander Boutique.
- Dataset normalizado de precios por competidor.
- HTML estatico de comparativa con grafico de barras.

## Convenciones de trabajo
- Cerrar un competidor de principio a fin antes de pasar al siguiente.
- Para iteraciones rapidas, ejecutar solo el competidor objetivo salvo que el usuario pida regression checks mas amplios.
- Para trabajo de scraping por competidor, usar `skills/observatorio-competitor-scraping/SKILL.md`.
- El estado vivo del proyecto, la cola actual y las validaciones recientes viven en `docs/project_checkpoint.md`.
- Actualizar `docs/project_checkpoint.md` solo despues de una corrida validada que cambie cobertura, estado de cierre o limitaciones relevantes.
- No usar `AGENTS.md` como changelog operativo ni pegar aqui logs, checkpoints largos o resultados de corridas.
- Leer `docs/project_checkpoint.md` solo cuando la tarea dependa del estado actual del scraping.
- Para trabajo mas focalizado, preferir sesiones desde el subdirectorio afectado:
  - `codex --cd observatorio`
  - `codex --cd app_backend`
  - `codex --cd frontend`

## Referencias utiles
- Estado operativo y checkpoints: `docs/project_checkpoint.md`
- Skill de scraping por competidor: `skills/observatorio-competitor-scraping/SKILL.md`
- Criterios de cierre de competidores: `skills/observatorio-competitor-scraping/references/workflow.md`
- App local end-to-end: `README.md`
