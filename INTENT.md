# Observatorio de Precios Samsung — Intención del proyecto

## Qué queremos construir

Un sistema automatizado que, dado un catálogo de referencia de productos Samsung vendidos en **Santander Boutique**, scrapeé en vivo esos mismos productos en los principales competidores y genere un **HTML estático de comparativa de precios** con gráfico de barras.

## Por qué

Santander Boutique comercializa productos Samsung bajo distintas modalidades de pago (renting, financiación, contado). Necesitamos saber de forma rápida si esos precios son competitivos respecto al mercado. El sistema debe poder relanzarse en cualquier momento y generar siempre un snapshot actualizado.

## Universo de productos

- **Fuente de referencia:** Santander Boutique (entre 10 y 12 productos Samsung activos).
- **En cada competidor** solo se buscan esos productos base — no el catálogo completo.
- **Clave de matching:** `marca + modelo + capacidad`.

## Competidores objetivo (12)

Amazon, El Corte Inglés, Fnac, Grover, Media Markt, Movistar, Orange, PcComponentes, Qonexa, Rentik, Santander Boutique, Vodafone.

## Modalidades de precio a capturar

| Código interno | Descripción |
|---|---|
| `renting_no_insurance` | Renting sin seguro |
| `renting_with_insurance` | Renting con seguro |
| `financing_max_term` | Financiación (plazo máximo disponible) |
| `cash` | Al contado |

Regla: se captura el **primer precio visible** en la web para cada modalidad detectada. Sin ajustes por envío, descuentos ocultos, etc.

## Estructura de dato por registro

```
timestamp_extraccion · competidor · url_producto
marca · modelo · capacidad
modalidad · precio_texto · precio_valor · moneda · disponibilidad
```

## Stack técnico elegido (solución actual)

- **Python + Playwright** (Chromium) para scraping en vivo.
- Adaptadores dedicados por competidor cuando el sitio tiene anti-bot o estructura compleja.
- Salida: `JSON` + `CSV` + `HTML estático` de comparativa.

## Problema recurrente que motiva buscar otra solución

El enfoque actual (Playwright headless/headed, adaptador por competidor) es funcional pero costoso de mantener:

- Varios sitios bloquean con CAPTCHA / Cloudflare / DataDome (Fnac bloqueado, PcComponentes intermitente).
- Cada competidor requiere un adaptador a medida con lógica de retry, matching y parseo propio.
- La cobertura depende del entorno de ejecución (timeouts, IP, fingerprint del navegador).

## Lo que sí funciona bien hoy

| Competidor | Estado | Modalidades cubiertas |
|---|---|---|
| Santander Boutique | Operativo (API + HTML) | renting x2, financing, cash |
| Amazon | Operativo | cash |
| Media Markt | Operativo | cash, financing |
| Movistar | Operativo (8/8 modelos) | cash, financing |
| Rentik | Operativo (6/8 modelos) | renting_with_insurance |
| Grover | Parcial (3/8 modelos) | renting_with_insurance |
| Fnac | Adaptador listo, bloqueado por CAPTCHA | — |
| Resto | Pendientes de adaptador dedicado | — |

## Entregable esperado (independiente de la solución técnica)

1. Dataset normalizado con todos los registros de precio por competidor.
2. HTML estático de comparativa con gráfico de barras por producto y modalidad.
