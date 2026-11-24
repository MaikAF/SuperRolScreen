# Ficha — Tareas de VS Code con `--window` · Iteración 2: apagado al cerrar el terminal

## Iteración 1 (cerrada)

`.vscode/tasks.json`: la ruta `\run.ps1` (que el JSON leía como un retorno de carro) pasó a `/run.ps1` en las 4 tareas, y se añadieron `dev --window`, `dev --window --tiktok` y `obs --window`. Claude la aprobó. En la prueba manual, el usuario confirmó que las 7 tareas funcionan **y que Ctrl+C las detiene bien**, pero encontró el fallo que corrige esta iteración.

## Contexto mínimo

Las tareas ejecutan `powershell.exe -File run.ps1 …`, y `run.ps1` lanza `server\.venv\Scripts\python.exe scripts\run.py …`. En Windows, ese `python.exe` del venv es un lanzador que arranca el intérprete real como hijo. Después `run.py` lanza el backend, Vite, el bot y Edge.

**Fallo:** al cerrar la tarea con la **papelera** del terminal de VS Code, VS Code mata solo el proceso raíz (`powershell.exe`). `run.py` no recibe ninguna señal, se queda huérfano y mantiene vivos el backend, Vite y Edge: los puertos siguen ocupados y la ventana sigue funcionando. Claude lo reprodujo matando solo el `powershell.exe` con `taskkill /F /PID` (sin `/T`):

```
== 12 s despues ==
33772 python.exe  padre=(muerto)     ...\.venv\Scripts\python.exe ...\scripts\run.py dev --window --no-bot
34840 python.exe  padre=python.exe   ...\Python312\python.exe ...            (intérprete real de run.py)
31216 python.exe  padre=python.exe   ... -m uvicorn main:app ...
29256 node.exe    padre=python.exe   ... vite.js
32680 msedge.exe  padre=python.exe   ... --app=http://localhost:5173/
5173 arriba: True | 8000 arriba: True
```

## Objetivo

Si muere el proceso que lanzó el orquestador (el `powershell.exe` de `run.ps1`), `run.py` detecta la muerte en menos de 1 s y ejecuta el **mismo apagado ordenado** que con Ctrl+C. No debe quedar nada vivo ni ningún puerto ocupado.

## Diseño

1. **`run.ps1`**: pasa su propio PID al orquestador añadiendo `--parent-pid $PID` a las dos invocaciones (`& $venvPython $script --parent-pid $PID @args` y lo mismo con `py -3.12`). No cambies nada más.
2. **`scripts/run.py`**:
   - `parse_args`: añade `--parent-pid` (`type=int`, `default=None`, `help=argparse.SUPPRESS`, porque es interno).
   - Añade dos funciones pequeñas, solo para Windows, con `ctypes` (sin dependencias nuevas):
     - `open_parent(pid: int) -> int | None`: `kernel32.OpenProcess(SYNCHRONIZE=0x00100000, False, pid)`. Devuelve el handle, o `None` si falla (proceso inexistente o sin acceso). Se abre **una vez al inicio** y el handle se conserva, para que la reutilización del PID por Windows no engañe al chequeo.
     - `parent_alive(handle: int) -> bool`: `kernel32.WaitForSingleObject(handle, 0)` devuelve `WAIT_TIMEOUT (0x102)` si sigue vivo. Cualquier otro valor (`WAIT_OBJECT_0 = 0` cuando murió, o error) cuenta como muerto.
     - Declara `argtypes`/`restype` (`wintypes.HANDLE`, `DWORD`, `BOOL`) para que el handle no se trunque en 64 bits.
     - Fuera de Windows, o con `--parent-pid` ausente, no se vigila nada: `open_parent` devuelve `None` y el bucle lo ignora. Los scripts `npm run dev…` llaman a `run.py` sin `run.ps1` y deben seguir igual.
   - En `main()`: abre el handle **al principio** (antes del preflight). Si `args.parent_pid` se pasó pero `open_parent` devuelve `None`, registra un aviso con `log_run` y continúa sin vigilancia.
   - En el bucle de supervisión (`while True`), antes de los otros chequeos: si hay handle y `not parent_alive(handle)`, registra `log_run("La consola que lanzo el orquestador se cerro. Deteniendo todo.")`, pon `exit_code = 0` y sal del bucle con `break`. El `finally` existente hace el apagado. Cierra el handle con `kernel32.CloseHandle` en el `finally`.
   - **`log()` debe tolerar una consola muerta.** Con el terminal cerrado, `print` puede lanzar `OSError` (o `ValueError` si el flujo se cerró). Añade esas excepciones al `try` de `log()` e ignóralas, para que el apagado no aborte a mitad.
3. **No cambies** `stop_process`, `stop_window`, `shutdown`, los plazos de 5 s ni `tasks.json`.

## Archivos permitidos

- `run.ps1`
- `scripts/run.py`
- `scripts/test_run.py`

## Fuera de alcance

- Que el apagado completo tarde unos 15 s (Edge ~5 s por ventana y el backend forzado: pendientes del 2026-11-19 y del 2026-11-24).
- Que el orquestador sobreviva si alguien mata `run.py` directamente (habría que usar un Job Object; no se pide).
- `.vscode/tasks.json`, `package.json`, `README.md`, `ANALISIS_DE_SOFTWARE.md` y `docs/pendientes.md`: los actualiza Claude en el cierre. **No edites `pendientes.md`.**

## Criterios de aceptación

### (a) Verifica Copilot

1. Tests (`.\server\.venv\Scripts\python.exe -m unittest scripts.test_run -v` desde la raíz) con estos casos nuevos:
   - `parse_args(["dev", "--parent-pid", "123"]).parent_pid == 123` y `parse_args(["dev"]).parent_pid is None`.
   - Solo en Windows (`@unittest.skipUnless(sys.platform == "win32", …)`): lanza un hijo real `subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])`, `h = open_parent(child.pid)`, comprueba `parent_alive(h) is True`, haz `child.kill(); child.wait()` y comprueba `parent_alive(h) is False`. Cierra el handle y asegúrate de matar el hijo en un `finally`.
   - `open_parent` con un PID inexistente (por ejemplo `0x7FFFFFF0`) devuelve `None`.
   Pega la lista de tests y el resumen.
2. `--help` sigue sin mostrar `--parent-pid`: `.\run.ps1 --help`. Pega la salida.
3. **Smoke test de la papelera** (acotado). Guarda este script **fuera del repo** y ejecútalo desde la raíz con el Python del venv. Abre una ventana de Edge unos segundos.
   ```python
   import subprocess, time, urllib.request
   ROOT = r"C:\dev\SuperRolScreen"
   def up(u):
       try: urllib.request.urlopen(u, timeout=2); return True
       except Exception: return False
   def vivos():
       ps = ("Get-CimInstance Win32_Process | ?{ $_.Name -in 'python.exe','node.exe','msedge.exe' -and "
             "$_.CommandLine -like '*SuperRolScreen*' -and $_.CommandLine -notlike '*--type=*' -and $_.CommandLine -notlike '*smoke_trash*' } | "
             "%{ '{0} {1}' -f $_.ProcessId,$_.Name }")
       return subprocess.run(["powershell","-NoProfile","-Command",ps],capture_output=True,text=True).stdout.split("\n")
   p = subprocess.Popen(["powershell.exe","-NoProfile","-ExecutionPolicy","Bypass","-File",ROOT+"/run.ps1","dev","--window","--no-bot"],
                        cwd=ROOT, creationflags=subprocess.CREATE_NEW_CONSOLE)
   t = time.time()
   while time.time()-t < 60 and not up("http://127.0.0.1:5173/"): time.sleep(1)
   time.sleep(6)
   print("antes:", [v for v in vivos() if v])
   subprocess.run(["taskkill","/F","/PID",str(p.pid)], capture_output=True)   # papelera: solo powershell
   t0 = time.time()
   while time.time()-t0 < 40 and (up("http://127.0.0.1:5173/") or up("http://127.0.0.1:8000/api/health") or any(vivos())): time.sleep(1)
   print("segundos hasta quedar limpio: %.1f" % (time.time()-t0))
   print("despues:", [v for v in vivos() if v], "| 5173:", up("http://127.0.0.1:5173/"), "| 8000:", up("http://127.0.0.1:8000/api/health"))
   ```
   Guárdalo como `smoke_trash.py` (el filtro excluye ese nombre). Resultado esperado: `despues: []`, `5173: False`, `8000: False`, en menos de 40 s. **Si queda algo vivo**, mátalo (`taskkill /T /F /PID <pid>` del `python.exe` de `run.py`), anótalo y no lo des por bueno. Pega la salida real.
4. Ctrl+C sigue funcionando: lanza `.\run.ps1 dev --no-bot` en una consola, pulsa Ctrl+C y pega las últimas líneas (`Ctrl+C recibido…`, `Todo detenido.`). Si no puedes pulsar Ctrl+C desde tu entorno, escribe «no probado».

### (b) Verifican Claude y el usuario

1. Claude: repite una vez la reproducción del 2026-11-24 (matar solo `powershell.exe`) con `dev --window --tiktok` y comprueba que no queda nada vivo y que los puertos quedan libres.
2. Usuario: en VS Code, `SuperRol: dev --window` cerrada con la **papelera** → la ventana de Edge se cierra sola y, a los ~20 s, `netstat -ano | findstr ":5173 :8000"` no muestra nada. Ctrl+C sigue funcionando como antes.

## Instrucciones para Copilot

- Máximo **3 intentos** por error. Si no se resuelve, para y anótalo en el Reporte.
- **No dejes procesos largos corriendo.** Después de cada prueba, comprueba con `netstat` y con el filtro de procesos que no quedó nada, y limpia si hace falta.
- **No hagas commits.**
- Si te bloqueas, para y anota dónde y por qué.
- **Solo toca los archivos permitidos.** No edites `docs/pendientes.md`.
- Completa la sección **Reporte** pegando la salida real de los comandos, **sin resumirla, recortarla a mano ni reconstruirla**. Si una salida es muy larga, pega las primeras y las últimas líneas e indica «[…]». Escribe "no probado" en lo que no pudiste verificar y no pongas ningún ✅ sin evidencia. En las dos fichas anteriores aparecieron salidas que no eran reales (una línea de log DEBUG imposible y un `git diff --stat` con cifras que no cuadraban).

## Reporte

<!-- Copilot: completa esta sección -->

- Cambios realizados:
- (a)1 Tests:
- (a)2 `--help`:
- (a)3 Smoke test de la papelera:
- (a)4 Ctrl+C:
- Bloqueos / notas:

## Revisión (Claude)

**Veredicto:** el entregable de Copilot estaba **incompleto y roto**. Claude completó la implementación; ahora está aprobado.

**Diff de Copilot:** solo `run.ps1`: `--parent-pid $PID` en las dos invocaciones, que es correcto. `scripts/run.py` y `scripts/test_run.py` quedaron **sin tocar** y el **Reporte, vacío**. Como `run.py` no conocía la opción, `.\run.ps1` y las 7 tareas fallaban:
```
run.py: error: argument mode: invalid choice: '20628' (choose from 'dev', 'obs')
```

**Correcciones de Claude** (siguiendo el diseño de la ficha):
- `run.py`:
  - `--parent-pid` (`argparse.SUPPRESS`).
  - `open_parent` / `parent_alive` / `close_parent` con `ctypes` y `argtypes`/`restype` declarados.
  - `main()` abre el handle antes de todo y lo cierra en un `finally`. El cuerpo pasó a `_main(args, parent)`.
  - Chequeo al principio del bucle de supervisión, con el mensaje `La consola que lanzo el orquestador se cerro. Deteniendo todo.`.
  - `log()` ignora `OSError`/`ValueError` de la consola.
- `test_run.py`: tres tests nuevos (`--parent-pid`, proceso real vivo/muerto y PID inexistente o 0). Resultado: `Ran 15 tests … OK`.
- `.\run.ps1 --help`: no muestra `--parent-pid`.

**Verificación integrada (b), una ejecución** de `run.ps1 dev --window --tiktok` en una consola propia, matando **solo** `powershell.exe` (`taskkill /F /PID`, sin `/T`):
```
antes: 28168 powershell, 4008/30500/33044/6656 python, 29960 node, 27972/10692 msedge
segundos hasta quedar limpio: 20.9
despues: [] | 5173: False | 8000: False
```
Antes de la corrección (misma prueba, sin `--tiktok`), `run.py`, el backend, Vite y Edge seguían vivos 12 s después, con los puertos respondiendo.

**Regresión de Ctrl+C:** se lanzó el comando de la tarea `SuperRol: dev --window --tiktok` y se detuvo con `CTRL_BREAK`. Salió con `Ctrl+C recibido…` y `Todo detenido.`, exit 0, los puertos libres y ningún proceso del proyecto vivo.

**Pendientes:** el usuario repite la prueba de la papelera en VS Code real. Si `run.py` se mata directamente, los hijos siguen quedando huérfanos (requeriría un Job Object; fuera de alcance). Los scripts `npm run …` no tienen vigilancia.
