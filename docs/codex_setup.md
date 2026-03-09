# Codex setup para sesiones con poco desgaste de contexto

## Objetivo
- Mantener pequeno el contexto que entra en cada sesion.
- Separar instrucciones estables del estado operativo cambiante.
- Compactar antes y evitar retener logs o salidas gigantes cuando no aportan.

## Reparto de archivos
- `AGENTS.md`: solo reglas estables del repositorio.
- `docs/project_checkpoint.md`: estado vivo del scraping, validaciones recientes y cola actual.
- `observatorio/AGENTS.md`: reglas especificas del scraper cuando la sesion arranca en `observatorio/`.
- `frontend/AGENTS.md`: reglas especificas del frontend cuando la sesion arranca en `frontend/`.
- `app_backend/AGENTS.md`: reglas especificas del backend cuando la sesion arranca en `app_backend/`.
- `.codex/config.toml`: configuracion de proyecto para leer menos instrucciones base, retener menos payload de herramientas y compactar antes.

## Uso recomendado
- Arrancar Codex desde el subdirectorio real del trabajo cuando la tarea sea focalizada:
  - `codex --cd observatorio`
  - `codex --cd app_backend`
  - `codex --cd frontend`
- Para scraping por competidor, invocar la skill por nombre o por ruta; no pegar el contenido completo de `SKILL.md` en el chat.
- Cuando necesites el estado actual del proyecto, referenciar `docs/project_checkpoint.md` en vez de pegar su contenido en la conversacion.
- Actualizar el checkpoint solo despues de una corrida validada, no tras cada experimento.
- Mantener `AGENTS.md` corto y estable. Si vuelve a crecer con checkpoints, el problema reaparecera.

## Por que ayuda
- `AGENTS.md` se carga al arrancar cada sesion y por eso debe ser pequeno.
- `docs/project_checkpoint.md` solo se lee cuando de verdad hace falta.
- Los `AGENTS.md` anidados solo cargan en sesiones arrancadas en su subdirectorio.
- `.codex/config.toml` reduce el peso retenido por outputs de herramientas y activa compaction antes de que la sesion se degrade.

## Nota operativa
- Reinicia Codex despues de cambiar `.codex/config.toml` para que la configuracion de proyecto se vuelva a cargar.
