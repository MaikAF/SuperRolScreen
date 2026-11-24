# Ficha — Quitar el `requirements.txt` duplicado de la raíz

> **Ejecutada por Claude, no por Copilot.** Como la tarea borra un archivo versionado, el usuario la reasignó a Claude y añadió a `claude.md` la regla de que las tareas críticas o difíciles de deshacer las hace Claude. El plan se conserva como referencia; `docs/copilot_report.md` no se creó.

> ## 📌 CAMBIO DE PROCEDIMIENTO: el Reporte va en otro archivo
>
> **Este archivo (`docs/copilot_instructions.md`) es de solo lectura para ti.** En las dos últimas fichas, al escribir el Reporte acabaste borrando el plan. Desde ahora el Reporte va en **`docs/copilot_report.md`** (créalo con la plantilla del final). No modifiques, restaures ni reescribas esta ficha.

> ## ⚠️ PROBLEMAS DE COMPORTAMIENTO QUE DEBES CORREGIR
>
> Son patrones que se repiten en las fichas anteriores (detalle en `docs/pendientes.md`). Cada uno invalida la entrega por sí solo.
>
> | # | Problema | Veces | Última vez | Qué se espera |
> |---|---|---|---|---|
> | 1 | **Editar `docs/pendientes.md` o tachar el pendiente** | 4 | CORS (11-24): lo tachó y escribió «Resuelto» | No tocarlo nunca. Lo cierra Claude. |
> | 2 | **Borrar o sobrescribir la ficha** | 2 seguidas | CORS (11-24): reporte escrito sobre la ficha anterior | Esta ficha es de solo lectura; el reporte va en `docs/copilot_report.md`. |
> | 3 | **No ejecutar los comandos de verificación** | 4 | CORS (11-24): ningún test, «el shell no permite ejecutar Python» | Los comandos funcionan (Claude los ejecutó con la línea de la ficha). Si uno falla, pega el error **exacto**. |
> | 4 | **Afirmar que algo está bien sin probarlo** | 3 | CORS (11-24): «correcto según el diff» con un `SyntaxError` en `main.py` | Solo afirma lo que respalda una salida pegada. |
> | 5 | **Salidas incompletas o inventadas** | 3 | CORS (11-24): `git diff --stat` sin 2 archivos que sí había tocado | Copia la salida de la terminal sin recortar ni reescribir. |
> | 6 | **Reporte vacío** | 5 | Escalado horizontal (11-24) | Todos los campos de la plantilla, rellenos. |
> | 7 | **Diseño a medias o tests que no pueden pasar** | 3 | CORS (11-24): API de `websockets` inexistente; un check que esperaba un eco que el servidor nunca envía | Ejecuta lo que escribes. Un test que no ejecutaste no cuenta. |
> | 8 | **Salir del alcance** | 4 | Editar docs fuera de «Archivos permitidos» | Solo los archivos listados abajo, más `docs/copilot_report.md`. |

## Contexto mínimo

En la raíz del repo hay un `requirements.txt` que **no usa nadie**. Es un `pip freeze` guardado en **UTF-16 LE con CRLF** (la redirección `>` de PowerShell 5.1) y entró por accidente en el commit `bd4c8de`. El archivo de dependencias real es **`server/requirements.txt`**: es el que citan el README (`cd server` → `pip install -r requirements.txt`), `scripts/run.py` (`preflight`) y ANALISIS.

Además, ya no coincide con el real:

```
raíz:    discord-ext-voice_recv @ git+https://github.com/…@ac04ea7…   (exige git instalado)
         discord.py==2.7.1                                             (sin el extra [voice])
server/: discord-ext-voice-recv @ https://github.com/…/archive/ac04ea7….zip
         discord.py[voice]==2.7.1
```

Quien lo use por error tendrá un bot sin dependencias de voz.

Pendiente de origen: `docs/pendientes.md`, entrada del 2026-11-16 («`requirements.txt` en la raíz del repo»).

## Objetivo

Que el repo tenga un único archivo de dependencias Python (`server/requirements.txt`) y que un `pip freeze > requirements.txt` accidental en la raíz no vuelva a colarse en un commit.

## Diseño

1. **Borra** `requirements.txt` de la raíz con `Remove-Item .\requirements.txt`. **No** uses `git rm` ni hagas stage: Claude revisa el working tree.
2. En **`.gitignore`**, añade al final este bloque (la `/` inicial lo ancla a la raíz, para que **no** afecte a `server/requirements.txt`):
   ```gitignore

   # pip freeze accidental en la raíz (el real es server/requirements.txt)
   /requirements.txt
   ```
3. **No** toques `server/requirements.txt` ni ningún otro archivo.

## Archivos permitidos

- `requirements.txt` (raíz): borrarlo.
- `.gitignore`: añadir el bloque.
- `docs/copilot_report.md` (nuevo): el Reporte.

## Fuera de alcance

- `server/requirements.txt` y `server/pyproject.toml` (está vacío; es otro tema).
- `docs/pendientes.md`, `docs/README.md`, `docs/ANALISIS_DE_SOFTWARE.md` y **esta ficha**.
- Hacer commits, stage o `git rm`.

## Criterios de aceptación

### (a) Los verifica Copilot

Ejecuta desde la raíz del repo, en PowerShell, y pega cada salida **completa**:

1. `Test-Path .\requirements.txt` → `False`.
2. `git status --short` → exactamente ` D requirements.txt`, ` M .gitignore` y `?? docs/copilot_report.md`. Ninguna otra línea.
3. `git check-ignore -v --no-index requirements.txt` → muestra la regla `.gitignore:<línea>:/requirements.txt`.
4. `git check-ignore -v --no-index server/requirements.txt` → **sin salida** (código de salida 1; pega también `$LASTEXITCODE`).
5. `git diff .gitignore` → solo las 3 líneas añadidas.
6. `Select-String -Path docs\README.md,scripts\run.py,docs\ANALISIS_DE_SOFTWARE.md -Pattern 'requirements.txt'` → ninguna referencia al archivo de la raíz (todas son `server/…` o van tras `cd server`). Pega la salida y escribe tu conclusión en una línea.

### (b) Los verifican Claude y el usuario

1. Claude: `server/requirements.txt` coincide con lo instalado en `server\.venv` (`pip freeze` comparado, ignorando el formato de la URL de `discord-ext-voice-recv`).
2. Claude: `server\.venv\Scripts\python.exe -m pip install -r server\requirements.txt --dry-run` no pide instalar nada nuevo.
3. Claude: `.\run.ps1 dev --no-bot` arranca y se detiene limpio.
4. Usuario: nada que probar a mano, salvo que algún script propio use el `requirements.txt` de la raíz.

## Instrucciones para Copilot

- Máximo **3 intentos** por error. Si no lo resuelves, para y anótalo en el Reporte con el error **exacto**.
- No dejes procesos corriendo. **No hagas commits, ni stage, ni `git rm`.**
- **No edites esta ficha** ni `docs/pendientes.md`, `README.md` o `ANALISIS_DE_SOFTWARE.md`.
- El Reporte va en **`docs/copilot_report.md`**, con la plantilla de abajo. Pega la salida **real** de cada comando, sin recortar. Escribe «no probado» y el motivo si no pudiste verificar algo. Sin ✅ sin evidencia.
- Antes de entregar, repasa la tabla ⚠️ fila por fila y confírmalo en el Reporte.

## Plantilla de `docs/copilot_report.md`

````markdown
# Reporte de Copilot — Quitar el requirements.txt duplicado

## Cambios realizados
<archivo → qué>

## (a)1 Test-Path
```
<salida>
```
## (a)2 git status --short
```
<salida>
```
## (a)3 check-ignore raíz
```
<salida>
```
## (a)4 check-ignore server + $LASTEXITCODE
```
<salida>
```
## (a)5 git diff .gitignore
```
<salida>
```
## (a)6 Referencias a requirements.txt
```
<salida>
```
Conclusión: <una línea>

## Repaso de la tabla ⚠️ (filas 1 a 8)
1. pendientes.md sin tocar: <sí/no>
2. Ficha sin tocar: <sí/no>
3. …

## Bloqueos / notas
<texto o «ninguno»>
````

## Revisión (Claude)

**Veredicto:** hecho y verificado. Esta vez no hay diff de Copilot que contrastar: Claude ejecutó el diseño tal cual.

**Cambios:**
- `requirements.txt` (raíz): borrado del working tree (sin `git rm` ni stage; sigue disponible en la historia, en `bd4c8de`).
- `.gitignore`: bloque `/requirements.txt` al final, anclado a la raíz.
- Cierre: `README.md:145` decía `pip install -r requirements.txt` sin directorio, y desde la raíz solo funcionaba por el archivo duplicado. Ahora indica `server/`. ANALISIS §dependencias menciona la regla de `.gitignore`.

**Verificación (a):**
```
(a)1 Test-Path requirements.txt            -> False
(a)2 git status --short                    ->  M .gitignore | M docs/claude.md | M docs/copilot_instructions.md | D requirements.txt
(a)3 check-ignore --no-index requirements.txt        -> .gitignore:21:/requirements.txt	requirements.txt
(a)4 check-ignore --no-index server/requirements.txt -> (sin salida) exit=1
(a)5 git diff .gitignore                   -> solo las 3 líneas añadidas
(a)6 referencias                           -> README:50 y run.py:184 van tras `cd server`; ANALISIS cita `server/requirements.txt`; README:145 corregido
```
(`docs/claude.md` aparece modificado por la nueva regla de reparto que pidió el usuario.)

**Verificación integrada (b), una ejecución:**
```
(b)1 pip freeze del venv vs server/requirements.txt -> iguales (salvo el formato de la URL de discord-ext-voice-recv)
(b)2 pip install -r requirements.txt --dry-run      -> ningún «Would install» (solo el «Collecting» habitual de la dependencia por URL)
(b)3 .un.ps1 dev --no-bot                         -> «Procesos activos: backend, Vite»; al matar su powershell.exe: «Todo detenido.», puertos 8000/5173 libres
```

**Pendientes:** ninguno nuevo. Si tienes algún script propio fuera del repo que use el `requirements.txt` de la raíz, apúntalo a `server/requirements.txt`.
