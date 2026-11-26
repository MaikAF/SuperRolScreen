# Ficha — Cerrar las ventanas de Edge sin esperar 5 s cada una

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
> En las dos fichas anteriores (11-26) cumpliste todas las filas. Sigue así. Detalle menor de la última: no importes nombres que luego no usas.

## Contexto mínimo

Con `--window`, `scripts/run.py` abre Edge en modo app (`start_window()`), y al apagar `stop_window()` lo cierra así en Windows:

```python
for force in (False, True):
    cmd = ["taskkill", "/PID", str(proc.pid), "/T"] + (["/F"] if force else [])
    subprocess.run(cmd, ...)
    try:
        proc.wait(timeout=5); return
    except subprocess.TimeoutExpired:
        continue
```

Es decir, primero `taskkill /T` sin `/F` (`WM_CLOSE`), espera 5 s y después `/F`. Claude lo midió en el flujo real (`dev --no-bot --window --tiktok`, dos ventanas), parcheando `run.py` en memoria:

| Variante | Cada `stop_window` | Apagado total |
|---|---|---|
| Actual | 5,2 s | 12,8 s |
| Actual + `--disable-background-mode` en Edge | 5,2 s | 12,9 s |
| `taskkill /T /F` directo | 0,12 s | 2,8 s |

El `WM_CLOSE` **nunca** cierra Edge: las ventanas acaban siempre en el `/F`. Pasar a `/F` directamente no cambia cómo termina Edge; solo elimina 5 s de espera por ventana. El perfil es propio de la app (`%LOCALAPPDATA%\SuperRolScreen\edge-profile*`), así que no hay estado del usuario que perder.

Pendiente de origen: `docs/pendientes.md`, entrada del 2026-11-24 («Cada ventana de Edge tarda unos 5 s en cerrarse al apagar»).

## Objetivo

Que `stop_window()` cierre Edge en Windows con un único `taskkill /T /F`, sin la espera previa de 5 s.

## Diseño

1. En `scripts/run.py`, en `stop_window()`, sustituye **solo la rama de Windows** (el bucle `for force in (False, True)` y el `log_run` final) por:
   ```python
   # WM_CLOSE (taskkill sin /F) nunca cerraba Edge: siempre se acababa en /F
   # tras 5 s de espera. El perfil es propio de la app; no hay nada que perder.
   subprocess.run(
       ["taskkill", "/PID", str(proc.pid), "/T", "/F"],
       stdout=subprocess.DEVNULL,
       stderr=subprocess.DEVNULL,
   )
   try:
       proc.wait(timeout=5)
   except subprocess.TimeoutExpired:
       log_run(f"No se pudo cerrar Edge (PID {proc.pid}).")
   ```
2. Actualiza el docstring de `stop_window()`: quita «taskkill sin /F envia WM_CLOSE (cierre normal); /F solo si no basta» y pon que se cierra con `taskkill /T /F` porque `WM_CLOSE` no lo cerraba. Mantén la explicación de por qué no usa `stop_process()`/`CTRL_BREAK`.
3. **No** cambies la rama no-Windows, `stop_process()`, `shutdown()`, `start_window()` ni `build_window_args()`.
4. En `scripts/test_run.py`, añade dos tests, al estilo de los existentes (`unittest.mock.patch`):
   - `test_stop_window_forces_once_on_windows`: con `patch.object(run, "IS_WINDOWS", True)` y `patch("scripts.run.subprocess.run")`, un `MagicMock` como `proc` con `poll.return_value = None` y `pid = 1234`. Tras `run.stop_window(proc)`: `subprocess.run` se llamó **una sola vez**, con primer argumento `["taskkill", "/PID", "1234", "/T", "/F"]`, y `proc.wait` se llamó con `timeout=5`.
   - `test_stop_window_skips_finished_process`: con `proc.poll.return_value = 0` (y también con `proc=None`), `subprocess.run` no se llama.
   Importa solo lo que uses.

## Archivos permitidos

- `scripts/run.py`: puntos 1 y 2.
- `scripts/test_run.py`: punto 4.
- `docs/copilot_report.md`: el Reporte (sobrescribe el anterior).

## Fuera de alcance

- `run.ps1`, `server/`, `client/`, `.vscode/tasks.json`.
- `docs/pendientes.md`, `docs/README.md`, `docs/ANALISIS_DE_SOFTWARE.md` (los actualiza Claude) y **esta ficha**.
- Arrancar `run.ps1`, `run.py`, Edge, uvicorn o Vite. Hacer commits o stage.

## Criterios de aceptación

### (a) Los verifica Copilot

Ejecuta desde la raíz del repo, en PowerShell, y pega cada salida **completa**:

1. `.\server\.venv\Scripts\python.exe -m unittest scripts.test_run -v` → todos `ok` (deberían ser 18), incluidos los dos nuevos.
2. `Select-String -Path scripts\run.py -Pattern 'for force in'` → **sin salida**.
3. `git status --short` → exactamente ` M scripts/run.py`, ` M scripts/test_run.py`, ` M docs/copilot_report.md` y ` M docs/copilot_instructions.md` (esta ficha, escrita por Claude; tú no la tocas). Ninguna otra línea.
4. `git diff scripts/run.py scripts/test_run.py` → solo lo del diseño.

### (b) Los verifican Claude y el usuario

1. Claude: `run.py dev --no-bot --window --tiktok` real; tras matar el `powershell.exe` padre, el apagado completo tarda unos 3 s (antes 12,8 s), y no queda ningún `msedge` con perfil `edge-profile*` de SuperRolScreen.
2. Claude: al relanzar `--window`, la ventana abre normal (sin bloqueo de perfil). Como hoy ya terminaba siempre en `/F`, no debería cambiar nada.
3. Usuario: Ctrl+C en `.\run.ps1 --window --tiktok` cierra las dos ventanas al instante.

## Instrucciones para Copilot

- Máximo **3 intentos** por error. Si no lo resuelves, para y anótalo en el Reporte con el error **exacto**.
- No dejes procesos corriendo. **No hagas commits ni stage.**
- **No edites esta ficha** ni `docs/pendientes.md`, `README.md` o `ANALISIS_DE_SOFTWARE.md`.
- El Reporte va en **`docs/copilot_report.md`**, con la plantilla de abajo. Pega la salida **real** de cada comando, sin recortar. Escribe «no probado» y el motivo si no pudiste verificar algo. Sin ✅ sin evidencia.
- En el repaso de la tabla ⚠️, contesta si **tú** tocaste cada archivo, no si `git status` lo muestra modificado.

## Plantilla de `docs/copilot_report.md`

````markdown
# Reporte de Copilot — Cierre de Edge sin espera

## Cambios realizados
<archivo:línea → qué>

## (a)1 unittest scripts.test_run -v
```
<salida>
```
## (a)2 'for force in' ya no está
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

**Veredicto:** aceptado sin correcciones. Lo ejecutó OpenCode como worker de Orca (`task_629caae9fe83`). El diff es exactamente el del diseño, el reporte coincide con él y no tocó nada fuera del alcance.

**Diferencias entre el reporte y el diff:** ninguna de fondo. «Cambios realizados» dice que añadió el import de `patch`, pero ya estaba; solo añadió `MagicMock` e `import scripts.run as run`. Los dos se usan.

**Correcciones de Claude:** ninguna. `unittest scripts.test_run`: 18 tests OK.

**Seguridad:** nada relevante. Solo cambia cómo se termina un proceso hijo propio (el PID que devolvió `Popen`, con `/T` sobre su árbol); no hay entradas externas ni `shell=True`.

**Verificación integrada (b), una ejecución:**
```
(b)1 run.py dev --no-bot --window --tiktok (código del repo; un envoltorio solo cronometra stop_window)
     [run] Cerrando ventana Edge (PID 29508) ...   stop_window 0,14 s
     [run] Cerrando ventana Edge (PID 7484) ...    stop_window 0,17 s
     'Todo detenido' a los 2,7 s   (antes: 12,8 s, con 5,2 s por ventana)
     msedge con perfil de SuperRolScreen después: 0
(b)2 relanzar --window: ventana 'overlay' abierta, conecta por WS y pide /api/clips; apagado en 3,1 s, 0 msedge restantes.
     Las ventanas de (b)1 también se abrieron con normalidad tras perfiles cerrados con /F en las pruebas anteriores.
```
No quedó ningún proceso (uvicorn, Vite, `run.py`) ni ningún `vite.config.ts.timestamp-*.mjs`.

**Cierre:** ANALISIS (§orquestación) documenta el cierre con `/F` y su motivo. El README solo dice que «Ctrl+C cierra las dos» y sigue siendo correcto.

**Pendientes:** (b)3, para el usuario: Ctrl+C en `.\run.ps1 --window --tiktok` debe cerrar las dos ventanas al instante.
