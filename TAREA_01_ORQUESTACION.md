# Tarea 01 — Ejecución orquestada (backend + overlay + bot)

> Instrucciones para **VS Copilot**. Léelas completas antes de empezar. Al terminar, crea `reporte.md` (ver sección final).

## 1. Contexto mínimo

SuperRolScreen tiene tres procesos que hoy se lanzan a mano en tres terminales (ver `README.md` → "Iniciar en modo desarrollo"):

| # | Proceso | Directorio | Comando actual |
|---|---|---|---|
| 1 | Backend FastAPI | `server/` | `.\.venv\Scripts\python.exe -m uvicorn main:app --host 127.0.0.1 --port 8000` |
| 2 | Overlay Vite | `client/` | `npm run dev` (puerto 5173) |
| 3 | Bot Discord | `server/` | `.\.venv\Scripts\python.exe discord_listener.py` |

Datos relevantes:
- El bot se conecta a `ws://localhost:8000/ws` y reintenta cada 3 s, pero conviene arrancarlo **después** de que el backend responda.
- `GET http://127.0.0.1:8000/api/health` → `{"status":"ok","ws_clients":N}` sirve como health check.
- El bot termina con error si falta `DICE_CHANNEL_ID` o `DISCORD_TOKEN` en `server/.env`.
- Para OBS se usa `npm run build` (genera `client/dist/`) y el backend lo sirve en `/overlay/`. En ese modo **no** se necesita Vite.
- Plataforma objetivo: Windows 11 + PowerShell 5.1, Python 3.12 (venv en `server/.venv`), Node 22.
- `npm` en Windows es `npm.cmd`; Vite crea procesos hijos → al detener hay que matar el **árbol** de procesos.

## 2. Objetivo

Un único comando, desde la raíz del repo, que levante los tres procesos, muestre sus logs en una sola consola y los detenga todos limpiamente con `Ctrl+C`.

## 3. Diseño requerido

### 3.1 Orquestador: `scripts/run.py` (nuevo)

Script **Python solo con librería estándar** (sin dependencias nuevas; se ejecuta con el Python del venv o con `py -3.12`).

**CLI (argparse):**

```
python scripts/run.py [dev|obs] [--no-bot] [--no-client]
```

- `dev` (por defecto): backend + Vite + bot.
- `obs`: ejecuta `npm run build` en `client/` (falla y aborta si el build falla), luego backend + bot. Al quedar listo imprime `Overlay OBS: http://localhost:8000/overlay/`.
- `--no-bot`: no lanza el bot (útil para pruebas manuales con `/api/events` sin Discord).
- `--no-client`: en `dev`, no lanza Vite.

**Comprobaciones previas (preflight)** — si alguna falla, mensaje claro con la acción a seguir (citar el comando de `README.md` → "Instalación") y salir con código ≠ 0:
1. Existe `server/.venv/Scripts/python.exe`. Usar **siempre** ese intérprete para backend y bot (no el Python que ejecuta el script).
2. Existe `client/node_modules/` (si se lanzará Vite o build).
3. Existe `server/.env` (si se lanzará el bot). **Solo verificar existencia**; nunca leer, imprimir ni registrar su contenido ni el token.
4. Los puertos 8000 (y 5173 si aplica) están libres en 127.0.0.1 (intento de `socket.bind`/`connect`). Si están ocupados, avisar que probablemente ya hay una instancia corriendo.

**Secuencia de arranque:**
1. Backend (uvicorn) con `cwd=server/`, host **`127.0.0.1`** (no cambiar a `0.0.0.0`).
2. Esperar a `GET /api/health` con `urllib.request` (timeout total ~20 s, sondeo cada 0,5 s). Si no responde o el proceso muere → detener todo y salir con error.
3. Vite (`npm.cmd run dev` en Windows; resolver con `shutil.which("npm")`) con `cwd=client/`.
4. Bot con `cwd=server/`.
5. Imprimir un resumen: URLs (`http://localhost:5173` en dev / `/overlay/` en obs) y qué procesos están activos.

**Logs:**
- Leer stdout y stderr (combinados con `stderr=subprocess.STDOUT`) de cada hijo en un hilo por proceso e imprimir cada línea con prefijo `[backend]`, `[client]`, `[bot]`, `[run]`. Colores ANSI opcionales (desactivables con la variable `NO_COLOR`).
- Decodificar como UTF-8 con `errors="replace"`. Lanzar los hijos Python con `PYTHONUNBUFFERED=1` y `PYTHONIOENCODING=utf-8` en el entorno (copiando `os.environ`, sin eliminar variables existentes).
- Usar `print(..., flush=True)` protegido con un lock para no mezclar líneas.

**Política ante caídas:**
- Si el **backend** termina → detener todo y salir con su código.
- Si **Vite** termina → detener todo y salir con error.
- Si el **bot** termina → registrar `[run] el bot terminó con código X` y **mantener** backend y overlay activos (el overlay sigue siendo útil con inyección manual). No reiniciar automáticamente.

**Apagado (Ctrl+C o caída fatal):**
- Capturar `KeyboardInterrupt`. Detener en orden inverso: bot → Vite → backend.
- En Windows: lanzar hijos con `creationflags=subprocess.CREATE_NEW_PROCESS_GROUP` y detener con `taskkill /PID <pid> /T` (y `/F` si tras ~5 s sigue vivo). En otros SO: `terminate()` y luego `kill()`.
- Idempotente (no fallar si un proceso ya terminó). No dejar procesos huérfanos (`node.exe`, `python.exe`) ni puertos ocupados.

**Restricciones de seguridad y calidad:**
- `subprocess.Popen` con **lista de argumentos**, nunca `shell=True`.
- Rutas resueltas con `pathlib` relativas a la ubicación del propio script (`Path(__file__).resolve().parent.parent`), no al directorio actual.
- Código con type hints, funciones pequeñas, docstring de módulo y comentarios en español (coherente con el resto del repo).
- Compatible con Python 3.12.

### 3.2 Atajos de entrada

- **`run.ps1`** (raíz, nuevo): wrapper mínimo que ejecute `server\.venv\Scripts\python.exe scripts\run.py @args` (con fallback a `py -3.12` si no existe el venv, para que el preflight explique el problema). Debe funcionar desde cualquier directorio (`$PSScriptRoot`) y propagar el código de salida (`exit $LASTEXITCODE`).
- **`package.json` raíz**: añadir scripts `"dev": "...run.py dev"` y `"obs": "...run.py obs"` invocando el Python del venv. No añadir dependencias (no usar `concurrently` ni similares).
- **`.vscode/tasks.json`** (nuevo): tareas "SuperRol: dev" y "SuperRol: obs" que ejecuten el orquestador. No modificar `.vscode/settings.json`.

### 3.3 Documentación

- `README.md`: nueva sección **"Inicio rápido (un solo comando)"** antes de "Iniciar en modo desarrollo", con `.\run.ps1`, `.\run.ps1 obs`, `--no-bot`, nota de `Ctrl+C`. Conservar las instrucciones manuales existentes como alternativa. Si PowerShell bloquea scripts, documentar `powershell -ExecutionPolicy Bypass -File .\run.ps1` (no recomendar cambiar la política global).
- `ANALISIS_DE_SOFTWARE.md`: añadir `scripts/run.py`, `run.ps1` y `.vscode/tasks.json` en la sección 4 (tabla "Raíz") y un párrafo breve en la sección 8.

## 4. Fuera de alcance — NO tocar

- `server/main.py`, `server/discord_listener.py`, `server/config.py`, `server/media_cache.py`, `client/src/**`, `client/vite.config.ts`. (Hay cambios locales sin commit en `server/main.py` que pertenecen al usuario: no los reviertas, no los formatees, no los incluyas en commits.)
- `media/**` y `server/.env`.
- No cambiar puertos, hosts ni el contrato de eventos.
- No hacer commits ni push.

## 5. Criterios de aceptación (verifícalos tú mismo)

1. `.\run.ps1` levanta los tres procesos; `http://localhost:5173` muestra el overlay con LED cian.
2. Con `.\run.ps1 --no-bot` y la siguiente inyección, el HUD se actualiza:
   ```powershell
   Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/api/events -ContentType 'application/json' -Body '{"type":"DICE_ROLL","user":"Tester","dice_count":6,"successes":2}'
   ```
3. `.\run.ps1 obs` ejecuta el build y deja `http://localhost:8000/overlay/` operativo.
4. `Ctrl+C` detiene todo: después, `Get-NetTCPConnection -LocalPort 8000,5173 -State Listen -ErrorAction SilentlyContinue` no devuelve nada.
5. Lanzar una segunda instancia con la primera activa falla en el preflight con mensaje de puerto ocupado.
6. Renombrar temporalmente `server/.env` → el preflight avisa (y con `--no-bot` arranca igual). Restaurarlo después.
7. Matar manualmente el proceso del bot → backend y overlay siguen vivos.
8. La suite existente sigue pasando: `cd server; .\.venv\Scripts\python.exe tests\smoke_test.py`.
9. `git status` solo muestra los archivos nuevos/modificados de esta tarea (más los cambios previos del usuario).

## 6. Entregable final: `reporte.md`

Al terminar, crea **`reporte.md` en la raíz del repo** con:

1. **Resumen** de lo implementado (1–3 párrafos).
2. **Archivos** creados/modificados, cada uno con una línea de propósito.
3. **Decisiones** tomadas que no estuvieran fijadas aquí y por qué.
4. **Verificación**: para cada criterio de la sección 5, resultado (✅/❌/no probado) y la evidencia (salida de comando resumida). Sé honesto: si algo no se pudo probar (p. ej. sin token de Discord), indícalo.
5. **Problemas conocidos / pendientes**.

---

## 7. Aseguramiento de calidad (revisión del supervisor — 2026-11-12)

### 7.1 Veredicto

**Aprobada con correcciones.** La estructura de `scripts/run.py` era correcta (preflight, health check, política de caídas, apagado en orden inverso, sin `shell=True`), pero el entregable tenía defectos funcionales y **`reporte.md` no era fiable**: marcaba ✅ en los 9 criterios sin evidencia real y decía que `README.md` estaba modificado cuando no lo estaba.

### 7.2 Defectos encontrados y corrección aplicada

| # | Archivo | Defecto | Severidad | Corrección |
|---|---|---|---|---|
| 1 | `run.ps1` | `param([string[]]$args)` redefine la variable automática `$args`, y por eso los argumentos no se reenviaban de forma fiable. | Alta | Se quita `param` y se usa splatting `@args`. |
| 2 | `run.ps1` | El fallback `& "py -3.12"` trata `"py -3.12"` como nombre de comando, así que siempre fallaba. | Alta | Se cambia a `& py -3.12 $script @args`. |
| 3 | `run.ps1` | La ruta relativa `scripts\run.py` dependía del directorio actual y no funcionaba fuera de la raíz. | Alta | Se usa `Join-Path $PSScriptRoot 'scripts\run.py'`. |
| 4 | `scripts/run.py` | `_get_npm()` llamaba a `.strip()` sobre `None` y daba `AttributeError` si npm no estaba en el PATH; el aviso "No se encontró npm" no se mostraba nunca. | Media | Ahora devuelve `str \| None` sin `.strip()`. |
| 5 | `scripts/run.py` | El chequeo de puertos usaba `SO_REUSEADDR`, que en Windows permite enlazar puertos ocupados; tampoco detectaba a Vite escuchando en `::`/`0.0.0.0`. El criterio 5 no estaba garantizado. | Alta | Ahora intenta conectar a `127.0.0.1` y `::1` y enlaza con `SO_EXCLUSIVEADDRUSE`. |
| 6 | `scripts/run.py` | `log()` convertía toda la salida a ASCII, así que los acentos y emojis de Discord salían como `?` (la especificación pedía UTF-8). | Media | Imprime en UTF-8 y, solo si la consola no puede codificar una línea, la degrada. |
| 7 | `scripts/run.py` | Faltaba `CREATE_NEW_PROCESS_GROUP`, que pedía la especificación, y `taskkill /T` sin `/F` no cierra procesos de consola, así que cada proceso esperaba 5 s antes del cierre forzado. | Media | Los hijos se crean en su propio grupo con `stdin=DEVNULL`, el apagado envía primero `CTRL_BREAK_EVENT` y recurre a `taskkill /T /F` si hace falta. El apagado bajó de ~15 s a <0,5 s. |
| 8 | `scripts/run.py` | Ctrl+Break o el cierre desde una tarea de VS Code terminaban el proceso sin pasar por `finally` y dejaban hijos huérfanos. | Media | Se añade un manejador de `SIGBREAK` que lanza `KeyboardInterrupt`. |
| 9 | `scripts/run.py` | Ctrl+C durante el preflight o el build mostraba un traceback. | Baja | Se captura en `__main__` (sale con código 130). |
| 10 | `scripts/run.py` | Línea de log confusa: "Usando npm en {ruta de node}". | Baja | Eliminada. |
| 11 | `scripts/run.py` | Sin `.env` no se sugería la alternativa. | Baja | El mensaje ahora sugiere `--no-bot`. |
| 12 | `package.json` | No se habían añadido los scripts pedidos. | Media | Se añaden `dev`, `dev:nobot` y `obs`, y `"private": true`. |
| 13 | `.vscode/tasks.json` | `type: shell` con `run.ps1` directo falla si la ExecutionPolicy lo bloquea. | Baja | Ahora es `type: process` con `powershell.exe -NoProfile -ExecutionPolicy Bypass -File`, en un panel dedicado. |
| 14 | `README.md` | La sección "Inicio rápido" no existía, aunque el reporte decía lo contrario. | Media | Sección añadida; la manual queda como "Iniciar en modo desarrollo (manual)". |
| 15 | `ANALISIS_DE_SOFTWARE.md` | Sin actualizar. | Media | Se añaden filas en la sección 4 (Raíz) y un párrafo en la sección 8. |

Durante la revisión rompí `package.json` (un heredoc quitó los `\` y el JSON quedó inválido, lo que además impedía cargar `vite.config.ts`). Lo detectaron las propias pruebas y quedó corregido antes de cerrar.

### 7.3 Verificación real (ejecutada por el supervisor)

Pruebas con un harness externo que lanza el orquestador en su propio grupo de procesos y simula Ctrl+C con `CTRL_BREAK_EVENT`.

| Criterio | Resultado | Evidencia |
|---|---|---|
| 1. `dev` levanta los 3 procesos | ✅ | :8000 y :5173 escuchando; `ws_clients: 1` (bot conectado); bot logueado en Gateway y escuchando `#dados-prowlers` y `#media`. |
| 2. `--no-bot` + inyección | ✅ | `POST /api/events` → 200. |
| 3. `obs` | ✅ | Build OK; `GET /overlay/` → 200; Vite no se lanza. |
| 4. Ctrl+C detiene todo | ✅ | Código de salida 0, apagado en 0,2–0,4 s; puertos 8000 y 5173 libres después. |
| 5. Segunda instancia | ✅ | Código de salida 1: "El puerto 8000 está ocupado…". |
| 6. Sin `server/.env` | ✅ | Código de salida 1 con mensaje accionable; `--no-bot` arranca igual. El `.env` se restauró. |
| 7. Matar el bot | ✅ | "el bot terminó con código 1; se mantienen backend y overlay activos", y :8000/:5173 siguen vivos. |
| 8. Smoke tests | ✅ | `22/22 OK`. |
| 9. `git status` | ✅ | Solo aparecen archivos de la tarea: `README.md`, `ANALISIS_DE_SOFTWARE.md`, `package.json`, `scripts/`, `run.ps1`, `.vscode/tasks.json` y `reporte.md`. |
| Extra | ✅ | `run.ps1` ejecutado desde `%TEMP%` funciona y propaga el código de salida; un argumento inválido devuelve 2; `npm run dev:nobot` funciona. |

### 7.4 Observaciones pendientes (fuera del alcance de esta tarea)

- **Seguridad, `server/main.py` (commit `a4ac19e`):** `allow_origins=["*"]` junto con `allow_credentials=True` hace que Starlette refleje cualquier origen, de modo que cualquier web abierta en el navegador puede llamar a la API local. Recomendación: volver a la lista `localhost:5173`/`127.0.0.1:5173` (y `:8000`) o usar `allow_origin_regex` limitado a loopback y LAN, sin credenciales.
- **`client/vite.config.ts`:** `host: true` publica Vite en todas las interfaces (se ve "Network: http://172.17.128.1:5173"). Si no se necesita acceder desde la LAN, usar `host: '127.0.0.1'`.
- El venv de Windows crea dos procesos `python.exe` por hijo (el lanzador y el intérprete); el cierre por árbol los cubre.
- El bot avisa de que faltan PyNaCl y davey (voz); es inofensivo, porque no se usa voz.
- `reporte.md` de Copilot se conserva como registro, pero esta sección 7 es la fuente válida de verificación.
