# Ficha — El backend debe terminar con `CTRL_BREAK` sin que haya que forzarlo

> ## 📌 PROCEDIMIENTO: el Reporte va en otro archivo
>
> **Este archivo (`docs/copilot_instructions.md`) es de solo lectura para ti.** El Reporte va en **`docs/copilot_report.md`**: **sobrescribe** el que hay (es de la ficha anterior) con la plantilla del final. No modifiques, restaures ni reescribas esta ficha.

> ## ⚠️ PROBLEMAS DE COMPORTAMIENTO QUE DEBES CORREGIR
>
> Son patrones que se repiten en las fichas anteriores (detalle en `docs/pendientes.md`). Cada uno invalida la entrega por sí solo.
>
> | # | Problema | Veces | Última vez | Qué se espera |
> |---|---|---|---|---|
> | 1 | **Editar `docs/pendientes.md` o tachar el pendiente** | 4 | CORS (11-24) | No tocarlo nunca. Lo cierra Claude. |
> | 2 | **Borrar o sobrescribir la ficha** | 2 seguidas | CORS (11-24) | Esta ficha es de solo lectura; el reporte va en `docs/copilot_report.md`. |
> | 3 | **No ejecutar los comandos de verificación** | 4 | CORS (11-24) | Los comandos funcionan. Si uno falla, pega el error **exacto**. |
> | 4 | **Afirmar que algo está bien sin probarlo** | 3 | CORS (11-24) | Solo afirma lo que respalda una salida pegada. |
> | 5 | **Salidas incompletas o inventadas** | 3 | CORS (11-24) | Copia la salida de la terminal sin recortar ni reescribir. |
> | 6 | **Reporte vacío** | 5 | Escalado horizontal (11-24) | Todos los campos de la plantilla, rellenos. |
> | 7 | **Diseño a medias o tests que no pueden pasar** | 3 | CORS (11-24) | Ejecuta lo que escribes. Un test que no ejecutaste no cuenta. |
> | 8 | **Salir del alcance** | 4 | Editar docs fuera de «Archivos permitidos» | Solo los archivos listados abajo, más `docs/copilot_report.md`. |
>
> En la ficha anterior (`MediaStage`, 2026-11-26) cumpliste todas las filas. Sigue así.

## Contexto mínimo

`scripts/run.py` lanza el backend con `python -m uvicorn main:app --host 127.0.0.1 --port 8000` (`start_backend()`) y, al apagar, `stop_process()` le envía `CTRL_BREAK` y espera 5 s. Si no ha salido, lo fuerza con `taskkill /T /F` y escribe en el log «backend sigue vivo; forzando cierre del arbol».

Claude lo reprodujo y aisló la causa: al apagarse, uvicorn espera **sin límite** a que terminen las respuestas en curso. El overlay descarga los videos de `media/Gameplay/` con peticiones Range (`206`), y un navegador que no ha consumido toda la respuesta la deja abierta. Mediciones con uvicorn solo y un cliente que pide un `.mp4` con `Range: bytes=0-` y lee 64 KB:

| uvicorn | cliente abierto | cliente cerrado con RST |
|---|---|---|
| sin flag (como ahora) | **sigue vivo a los 15 s** | sale en 0,2 s |
| `--timeout-graceful-shutdown 2` | sale en 2,2 s | sale en 0,3 s |

Sin navegador, el backend ya sale en menos de 1 s.

Pendiente de origen: `docs/pendientes.md`, entrada del 2026-11-19 («El backend no termina con `CTRL_BREAK` en 5 s»).

## Objetivo

Que el backend lanzado por `run.py` termine solo con `CTRL_BREAK` aunque haya descargas de video a medias, sin llegar al `taskkill /F`.

## Diseño

1. En `scripts/run.py`, junto a las demás constantes del backend (`BACKEND_HOST`, `BACKEND_PORT`), añade:
   ```python
   # uvicorn espera sin limite a las respuestas en curso al apagarse; los videos
   # (Range/206) que el navegador deja a medias lo bloqueaban hasta el taskkill /F.
   # Debe ser menor que la espera de stop_process() (5 s).
   BACKEND_GRACEFUL_SHUTDOWN_S = 2
   ```
2. En `start_backend()`, añade al final de la lista de argumentos de uvicorn: `"--timeout-graceful-shutdown", str(BACKEND_GRACEFUL_SHUTDOWN_S)`.
3. En `scripts/test_run.py`, añade un test `test_start_backend_args`, con el mismo estilo que `test_start_client_spawns_with_node_and_vite_bin` (mock de `scripts.run._spawn` y `scripts.run._start_reader`). Debe comprobar que:
   - los argumentos contienen `"--timeout-graceful-shutdown"` seguido de `str(run.BACKEND_GRACEFUL_SHUTDOWN_S)`;
   - siguen estando `"main:app"`, `"--host", run.BACKEND_HOST` y `"--port", str(run.BACKEND_PORT)`;
   - `cwd` es `run.SERVER_DIR`;
   - `run.BACKEND_GRACEFUL_SHUTDOWN_S < 5`.
4. **No** cambies `stop_process()`, el plazo de 5 s ni nada del apagado de Vite o Edge (son otros pendientes).

## Archivos permitidos

- `scripts/run.py`: puntos 1 y 2.
- `scripts/test_run.py`: punto 3.
- `docs/copilot_report.md`: el Reporte (sobrescribe el anterior).

## Fuera de alcance

- `server/main.py`, `run.ps1`, `.vscode/tasks.json`.
- `docs/pendientes.md`, `docs/README.md` (el comando manual de uvicorn lo actualiza Claude), `docs/ANALISIS_DE_SOFTWARE.md` y **esta ficha**.
- Arrancar `run.ps1`, `run.py` o Edge. Hacer commits o stage.

## Criterios de aceptación

### (a) Los verifica Copilot

Ejecuta desde la raíz del repo, en PowerShell, y pega cada salida **completa**:

1. `.\server\.venv\Scripts\python.exe -m unittest scripts.test_run -v` → todos `ok`, incluido `test_start_backend_args`. Pega la salida entera, con el número de tests.
2. `.\server\.venv\Scripts\python.exe -m uvicorn --help | Select-String 'timeout-graceful-shutdown'` → la opción existe en la versión instalada.
3. `git status --short` → ` M scripts/run.py`, ` M scripts/test_run.py` y ` M docs/copilot_report.md`. También aparecen ` M client/src/App.tsx`, ` M docs/ANALISIS_DE_SOFTWARE.md`, ` M docs/copilot_instructions.md` y ` M docs/pendientes.md`, que son de Claude y del usuario; no los toques. Ninguna otra línea.
4. `git diff scripts/run.py scripts/test_run.py` → solo lo del diseño.

### (b) Los verifican Claude y el usuario

1. Claude: repetir la reproducción. `.\run.ps1 dev --no-bot` con un Edge que reproduce los videos; después se cierra Edge y se mata el `powershell.exe` padre. El log no debe decir «backend sigue vivo; forzando cierre del arbol», y el backend debe terminar en unos 2 s o menos.
2. Claude: la reproducción con uvicorn solo y un `.mp4` a medio leer sale en unos 2 s.
3. Usuario: cerrar `.\run.ps1 --window` con Ctrl+C tras un rato de uso y ver que el backend no se fuerza (las ventanas de Edge todavía tardan; es otro pendiente).

## Instrucciones para Copilot

- Máximo **3 intentos** por error. Si no lo resuelves, para y anótalo en el Reporte con el error **exacto**.
- No dejes procesos corriendo. **No hagas commits ni stage.**
- **No edites esta ficha** ni `docs/pendientes.md`, `README.md` o `ANALISIS_DE_SOFTWARE.md`.
- El Reporte va en **`docs/copilot_report.md`**, con la plantilla de abajo. Pega la salida **real** de cada comando, sin recortar. Escribe «no probado» y el motivo si no pudiste verificar algo. Sin ✅ sin evidencia.
- En el repaso de la tabla ⚠️, contesta si **tú** tocaste cada archivo, no si `git status` lo muestra modificado.

## Plantilla de `docs/copilot_report.md`

````markdown
# Reporte de Copilot — Apagado del backend sin forzar

## Cambios realizados
<archivo:línea → qué>

## (a)1 unittest scripts.test_run -v
```
<salida>
```
## (a)2 uvicorn --help
```
<salida>
```
## (a)3 git status --short
```
<salida>
```
## (a)4 git diff scripts/run.py scripts/test_run.py
```
<salida>
```

## Repaso de la tabla ⚠️ (filas 1 a 8)
1. Toqué pendientes.md: <sí/no>
2. Toqué la ficha: <sí/no>
3. …

## Bloqueos / notas
<texto o «ninguno»>
````

## Revisión (Claude)

**Veredicto:** aceptado. Lo ejecutó OpenCode como worker de Orca (`task_69d5fdaa9f4c`). El código cumple el diseño, el reporte coincide con el diff y no tocó ningún archivo fuera del alcance.

**Diferencias entre el reporte y el diff:** ninguna de fondo.
- (a)3 se ejecutó antes de escribir el reporte, por eso falta ` M docs/copilot_report.md`; lo explica en una nota.
- La tabla ⚠️ esta vez está bien contestada («no toqué» en las filas 1 y 2).

**Correcciones de Claude:** quité de `scripts/test_run.py` cinco imports sin usar (`BACKEND_GRACEFUL_SHUTDOWN_S`, `BACKEND_HOST`, `BACKEND_PORT`, `SERVER_DIR` y `start_backend`), porque el test usa `run.*`. Siguen pasando los 16 tests.

**Seguridad:** nada relevante. Solo se añade un flag de uvicorn; no cambian host, puertos, CORS ni dependencias.

**Verificación integrada (b), una ejecución:**
```
(b)1 .\run.ps1 dev --no-bot + Edge headless que reproduce los videos (6 peticiones 206); se mata Edge y luego el powershell padre
     [backend] INFO:     Shutting down
     [backend] ERROR:    Cancel 0 running task(s), timeout graceful shutdown exceeded
     [backend] INFO:     Finished server process [13792]
     [run] Todo detenido.          -> 2,5 s, sin «backend sigue vivo; forzando cierre del arbol»
     Antes del cambio, el mismo escenario acababa en «backend sigue vivo; forzando cierre del arbol».
(b)2 uvicorn solo + un .mp4 a medio leer: sin el flag sigue vivo a los 15 s; con --timeout-graceful-shutdown 2 sale en 2,2 s (medido en el diagnóstico)
```
Al final no quedó ningún proceso (`msedge`, uvicorn ni `run.py`) ni ningún `vite.config.ts.timestamp-*.mjs`.

**Cierre:** el README añade el flag al comando manual de uvicorn y explica para qué sirve. ANALISIS (§orquestación) documenta `BACKEND_GRACEFUL_SHUTDOWN_S` y que la línea `ERROR: … timeout graceful shutdown exceeded` es esperada.

**Pendientes:**
- (b)3, para el usuario: cerrar `.\run.ps1 --window` con Ctrl+C tras un rato de uso. Las ventanas de Edge todavía tardan unos 5 s cada una (es otro pendiente).
- El `GET /health` con 404 volvió a aparecer a mitad de la sesión, ya anotado en `pendientes.md`.
