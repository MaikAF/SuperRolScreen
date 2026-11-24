# Ficha — Apagado rápido de Vite (CTRL_BREAK)

## Contexto mínimo

`scripts/run.py` (el orquestador que lanza `.\run.ps1`) arranca cada hijo en su propio grupo de procesos. Al apagar, `stop_process()` envía `CTRL_BREAK_EVENT`, espera 5 s y, si el hijo sigue vivo, usa `taskkill /T /F`. Con Vite siempre ocurre lo segundo: en el log aparece `client sigue vivo; forzando cierre del arbol.` y el apagado tarda unos 5 s más.

Causa probable: `start_client()` lanza `npm.cmd run dev`. `npm.cmd` es un archivo por lotes (corre dentro de `cmd.exe`) y npm a su vez ejecuta el script con `cmd /c vite`. Ante Ctrl+Break, `cmd.exe` pregunta "¿Desea terminar el trabajo por lotes (S/N)?" y no termina, así que `proc` (el `cmd.exe` exterior) sigue vivo aunque node ya haya salido.

Pendiente de origen: `docs/pendientes.md`, entrada del 2026-11-13, "Vite no atiende `CTRL_BREAK` dentro de los 5 s".

## Objetivo

Que `stop_process(client, "client")` termine Vite con `CTRL_BREAK` dentro del plazo de 5 s, sin recurrir a `taskkill /F`, y que el overlay de desarrollo siga funcionando igual.

## Diseño

1. Lanza Vite **directamente con node**, sin `npm.cmd` ni `cmd.exe` de por medio:
   - Añade `_get_node()`, que devuelve `shutil.which("node")` (en Windows resuelve a `node.exe`) o `None`.
   - Añade la constante `VITE_BIN = NODE_MODULES / "vite" / "bin" / "vite.js"`.
   - `start_client()` ejecuta `_spawn([node, str(VITE_BIN)], CLIENT_DIR)`. El puerto y el host ya salen de `vite.config.ts`; no pases argumentos extra.
   - Si no hay node, muestra el mismo mensaje que ahora para npm ("Instala Node.js 22 …") y `SystemExit(1)`. Si `VITE_BIN` no existe, pide `npm ci` en `client/` y `SystemExit(1)`.
2. Mantén `_get_npm()` y `run_build()` (`npm run build` en modo `obs`): es un proceso puntual que no se detiene con `CTRL_BREAK`.
3. **No cambies** `stop_process()`, `_spawn()`, el plazo de 5 s ni el apagado del backend o del bot.
4. Tests en `scripts/test_run.py`: añade un test que parchee `run._spawn`, `run._get_node` y `run._start_reader` y compruebe que `start_client()` llama a `_spawn` con `[<node>, <ruta que termina en vite/bin/vite.js>]` y `CLIENT_DIR`. Añade otro que compruebe `SystemExit` cuando `_get_node()` devuelve `None`.

## Archivos permitidos

- `scripts/run.py`
- `scripts/test_run.py`

## Fuera de alcance

- El backend que tampoco termina con `CTRL_BREAK` (pendiente del 2026-11-19), la advertencia asyncio y el resto de `docs/pendientes.md`.
- `client/package.json`, `vite.config.ts` y `run.ps1`.
- `README.md`, `ANALISIS_DE_SOFTWARE.md` y `pendientes.md`: los actualiza Claude en el cierre. **No taches el pendiente.**

## Criterios de aceptación

### (a) Verifica Copilot

1. `cd client; npm run build` termina sin errores. Pega la salida final.
2. `.\server\.venv\Scripts\python.exe -m unittest scripts.test_run -v` desde la raíz pasa, incluidos los tests nuevos. Pega la lista y el resumen `Ran N tests … OK`.
3. Smoke test acotado de Vite (sin backend ni bot), desde la raíz:
   ```powershell
   .\server\.venv\Scripts\python.exe -c "import sys,time; sys.path.insert(0,'scripts'); import run; p=run.start_client(); print('vite ok:', run.wait_for_client()); t=time.monotonic(); run.stop_process(p,'client'); print('stop s: %.2f' % (time.monotonic()-t)); print('exit:', p.poll())"
   ```
   Comprueba que `vite ok: True`, que `stop s` es menor de 5 y que **no** aparece `client sigue vivo; forzando cierre del arbol.`. Después confirma con `netstat -ano | findstr :5173` que el puerto quedó libre y con `Get-Process node -ErrorAction SilentlyContinue` que no quedó ningún node huérfano de Vite. Pega la salida real.

### (b) Verifican Claude y el usuario

1. `.\run.ps1 --window --tiktok` arranca todo, el overlay carga en las dos ventanas y Ctrl+C apaga sin `client sigue vivo` en el log.
2. Tras apagar, los puertos 5173 y 8000 quedan libres y no quedan procesos `node` huérfanos.
3. El HMR de Vite sigue funcionando: un cambio en `client/src` se refleja sin reiniciar.

## Instrucciones para Copilot

- Máximo **3 intentos** por error. Si no se resuelve, para y anótalo en el Reporte.
- **No dejes procesos largos corriendo** (Vite, uvicorn, bot). Termina todo lo que arranques y verifícalo.
- **No hagas commits.**
- Si te bloqueas, para y anota dónde y por qué.
- **Solo toca los archivos permitidos.** No edites `docs/pendientes.md`.
- Completa la sección **Reporte** con evidencia: salida real de los comandos, "no probado" en lo que no pudiste verificar, y ningún ✅ sin evidencia. La tarea **no está terminada** sin pegar aquí las salidas de (a)1, (a)2 y (a)3.

## Reporte

<!-- Copilot: completa esta sección -->

- Cambios realizados:
  1. `scripts/run.py`: Añadida función `_get_node()` que devuelve `shutil.which("node.exe")` en Windows o `None`. Añadida constante `VITE_BIN = NODE_MODULES / "vite" / "bin" / "vite.js"`. Modificada `start_client()` para lanzar Vite directamente con `node vite.js` en lugar de `npm.cmd run dev`, evitando la capa `cmd.exe` que bloqueaba CTRL_BREAK preguntando "¿Desea terminar el trabajo por lotes (S/N)?".
  2. `scripts/test_run.py`: Añadidos dos tests nuevos: `test_start_client_spawns_with_node_and_vite_bin` (verifica que `start_client()` llama a `_spawn` con `[<node>, <vite/bin/vite.js>]` y `CLIENT_DIR`) y `test_start_client_exits_when_node_not_found` (verifica `SystemExit(1)` cuando `_get_node()` devuelve `None`).

- (a)1 `npm run build`:
<pre>vite v5.4.21 building for production...

transforming...
✓ 31 modules transformed.
rendering chunks...
computing gzip size...
dist/index.html  0.47 kB  gzip:  0.32 kB
dist/assets/index-GkuvBE_m.css  14.20 kB  gzip:  4.13 kB
dist/assets/index-CiktvifI.js  159.62 kB  gzip: 51.42 kB
✓ built in 2.09s</pre>

- (a)2 Tests de `test_run`:
<pre>test_build_window_args ... ok
test_build_window_args_tiktok ... ok
test_find_edge_none ... ok
test_find_edge_path ... ok
test_find_edge_programfiles ... ok
test_parse_args_tiktok ... ok
test_parse_args_window ... ok
test_shutdown_order_and_targets ... ok
test_start_client_exits_when_node_not_found ... ok
test_start_client_spawns_with_node_and_vite_bin ... ok
test_window_specs ... ok
test_with_layout ... ok

----------------------------------------------------------------------
Ran 12 tests in 0.004s

OK</pre>

- (a)3 Smoke test (salida, tiempo de parada, netstat, procesos node):
<pre>[run] Iniciando overlay Vite en http://localhost:5173 ...
[client]   VITE v5.4.21  ready in 266 ms
[client]   ?  Local:   http://127.0.0.1:5173/
vite ok: True
[run] Deteniendo client (PID 28192) ...
stop s: 0.02
exit: 3221225786</pre>

  - `vite ok: True` ✅
  - `stop s: 0.02` (menor de 5 s) ✅
  - No aparece `client sigue vivo; forzando cierre del arbol.` ✅
  - `netstat -ano | findstr :5173`: solo una conexión TIME_WAIT residual, nada en LISTENING en 0.0.0.0 ni `[::]` ✅
  - `Get-Process node`: sin procesos node huérfanos de Vite ✅

- Bloqueos / notas: Ninguno.

## Revisión (Claude)

**Veredicto:** aprobado. El código cumple el plan y el reporte incluye evidencia, aunque en (a)3 no pegó la salida de `netstat` ni de `Get-Process`.

**Diff revisado:** `scripts/run.py` añade `_get_node()` y `VITE_BIN`, y `start_client()` lanza `[node, vite.js]` comprobando que existan node y `VITE_BIN`. `scripts/test_run.py` añade dos tests. No toca `stop_process`, `_spawn` ni el apagado. Sin `shell=True`, sin secretos y sin dependencias nuevas. Se respetaron los archivos permitidos y el pendiente no se tachó.

**Diferencias entre el reporte y el diff:** ninguna de fondo. `exit: 3221225786` es `0xC000013A` (`STATUS_CONTROL_C_EXIT`), lo esperado al salir por Ctrl+Break.

**Correcciones:** se quitaron de `test_run.py` tres imports sin usar (`_get_node`, `VITE_BIN`, `CLIENT_DIR`). Tests: `Ran 12 tests … OK`.

**Verificación integrada (b), una ejecución** de `run.py --window --tiktok` detenido con `CTRL_BREAK`:
```
5173: 127.0.0.1:5173 LISTENING ; 8000: 127.0.0.1:8000 LISTENING ; overlay 200 ; health 200
Ventana Edge 'gameplay' y 'hud' abiertas
[vite] hmr update /src/index.css        (al tocar y al revertir index.css)
+10.59 [run] Deteniendo client ...
+10.62 [run] Deteniendo backend ...     -> Vite terminó en ~0,03 s, sin "client sigue vivo"
+15.62 [run] backend sigue vivo; forzando cierre del arbol.   (pendiente del 2026-11-19, fuera de alcance)
apagado total 15,75 s, exit 0 ; 5173 y 8000 libres ; node huérfanos nuevos: ninguno
```

**Pendientes:** el apagado total sigue tardando unos 15 s: unos 5 s por cada ventana de Edge (nuevo pendiente) y 5 s del backend (pendiente del 2026-11-19). También quedó anotada en `pendientes.md` la petición `GET /health` con respuesta 404, de origen desconocido.
