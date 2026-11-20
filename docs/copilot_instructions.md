# Ficha de tarea — TikTok en dos ventanas (gameplay + HUD)

Fecha: 2026-11-19 · Iteración 1 · Rama `tiktok`

> Fichas anteriores en el historial de git: layout TikTok (`282ace0`) y marco `voice.png` (`ecb2f57`).

## 1. Contexto mínimo

- El overlay (`client/src/App.tsx`) elige layout una sola vez con `readLayout()` a partir de `?layout=`. Hoy hay dos: `landscape` (1920 × 1080, transparente, para OBS) y `tiktok` (lienzo único de 1080 × 1920: banda superior, gameplay y banda inferior con los HUD). `index.css` dimensiona `html`/`body`/`#root` con `html[data-layout='tiktok']`.
- `scripts/run.py --window --tiktok` abre **una** ventana de Edge en modo app de 1080 × 1920 con `?layout=tiktok`. En una pantalla de 1080 px de alto, Windows la recorta y el lienzo (fijo, sin escalar) no se ve entero. Este es el problema que motiva la tarea.
- Todas las ventanas reciben los mismos eventos: el backend hace broadcast por `/ws` a todos los clientes. Cada ventana abre su propio WebSocket y no hace falta tocar el servidor.

## 2. Objetivo

Con `--tiktok`, el orquestador abre **dos ventanas** que el usuario compone en TikTok Live Studio:

| Ventana | URL | Lienzo | Contenido |
|---|---|---|---|
| **Gameplay** | `?layout=gameplay` | 1920 × 1080 | `GameplayLoop` + `MediaStage` + `NowPlayingHud`, con las mismas posiciones que el layout horizontal. **Sin** HUD de dados ni de voz. |
| **HUD** | `?layout=hud` | 1080 × 656 | `background.jpg` en *cover* en todo el lienzo, con `DiceHud` a la izquierda y `VoiceHud` a la derecha, centrados en vertical. |

En el estudio, el usuario pone el gameplay en el centro (escalado a 1080 × 608), el HUD arriba y una imagen propia abajo (esto último no es parte de la tarea). El layout de lienzo único `?layout=tiktok` **se elimina**.

## 3. Diseño

### 3.1 Cliente — `client/src/App.tsx`

1. `type Layout = 'landscape' | 'gameplay' | 'hud'`. `readLayout()`: el literal `gameplay` da `'gameplay'`, el literal `hud` da `'hud'` y cualquier otro valor (incluido `tiktok`) da `'landscape'`.
2. Antes del primer render, además de `dataset.layout`, fija `document.title`: `SuperRolScreen · Gameplay` para `gameplay`, `SuperRolScreen · HUD` para `hud` y sin cambios para `landscape`. Así se distinguen las ventanas en la captura de ventana del estudio.
3. **Escalado al viewport (solo `gameplay` y `hud`).** Crea un hook `useFitScale(w, h): number` que devuelva `Math.min(innerWidth / w, innerHeight / h)` y se recalcule en `resize`, limpiando el listener al desmontar. Aplícalo al `<main>` con `transform: scale(s)` y `transformOrigin: 'top left'`. Así, si Windows recorta la ventana (barra de título, barra de tareas), el lienzo se reduce entero en vez de cortarse. El layout `landscape` **no** se escala (OBS usa el tamaño exacto).
4. Render de **`gameplay`**: `<main>` de 1920 × 1080 con fondo negro (`bg-black`) que contiene `GameplayLoop`, `MediaStage` (placement por defecto) y `NowPlayingHud` (sin `top`, a media altura, como en horizontal). No renderiza `DiceHud` ni `VoiceHud`.
5. Render de **`hud`**: `<main>` de `HUD_W = 1080` × `HUD_H = 656` con un único fondo `background.jpg` (`cover`, `center`) en todo el lienzo, y encima `DiceHud` y `VoiceHud`.
   - Se conservan `TIKTOK_DICE_SCALE` (1,15) y `TIKTOK_VOICE_SCALE` (1,3), renombradas a `HUD_DICE_SCALE` y `HUD_VOICE_SCALE`, y `TIKTOK_SIDE_MARGIN` (24) como `HUD_SIDE_MARGIN`.
   - `lowerBandTop()` pasa a ser `centeredTop(width, ratio, scale) = (HUD_H - width * ratio * scale) / 2`. La voz mide unos 609 px de alto, de modo que queda centrada con unos 23 px de margen arriba y abajo.
   - El `transformOrigin` de cada HUD se mantiene: `top left` para dados y `top right` para voz.
6. Elimina lo que solo servía al lienzo único: `TIKTOK_W`, `TIKTOK_H`, `TIKTOK_GAMEPLAY_H`, `TIKTOK_BAND_H`, `TIKTOK_LOWER_TOP`, `TIKTOK_GAMEPLAY_BOX`, `TIKTOK_MEDIA_SCALE`, `TiktokBackdrop`, `BAND_STYLE` con dos bandas y el render `LAYOUT === 'tiktok'`.
   - Si el prop `scale` de `MediaStage` y el `top` de `NowPlayingHud` quedan sin uso, elimínalos también. No dejes props muertos.
   - Actualiza los comentarios de cabecera de la sección (`LAYOUT TIKTOK` pasa a `LAYOUTS GAMEPLAY / HUD`).
7. No cambies el layout `landscape` ni los componentes internos de los HUD (`HUD_SCREEN`, `VOICE_HUD_SCREEN`, textos, etc.).

### 3.2 Cliente — `client/src/index.css`

Sustituye la regla `html[data-layout='tiktok']` (1080 × 1920) por `html[data-layout='hud']` con 1080 × 656. `gameplay` usa la regla base de 1920 × 1080 y no necesita una propia. Añade `background: #000` a `html`/`body`/`#root` **solo** para `gameplay` y `hud`, porque el layout horizontal debe seguir transparente para OBS. Así, si el lienzo escalado no llena la ventana, el sobrante se ve negro y no blanco.

### 3.3 Orquestador — `scripts/run.py`

1. Sustituye `with_layout(url, tiktok: bool)` por `with_layout(url: str, layout: str | None) -> str`. Con `None` devuelve la URL tal cual; con un valor devuelve `f"{url}?layout={layout}"`.
2. Constantes nuevas, que sustituyen a `TIKTOK_WINDOW_SIZE`:
   ```python
   GAMEPLAY_WINDOW_SIZE = (1920, 1080)
   HUD_WINDOW_SIZE = (1080, 656)
   ```
   Además, una función pura y testeable:
   ```python
   def window_specs(tiktok: bool) -> list[tuple[str, str | None, tuple[int, int]]]:
       """(nombre, layout, tamaño) de cada ventana a abrir."""
       # tiktok=False -> [("overlay", None, LANDSCAPE_WINDOW_SIZE)]
       # tiktok=True  -> [("gameplay", "gameplay", GAMEPLAY_WINDOW_SIZE),
       #                  ("hud", "hud", HUD_WINDOW_SIZE)]
   ```
3. `start_window(url, name, layout, size)` abre una ventana. **Cada ventana usa su propio perfil**: `edge-profile` para `overlay` (la ruta actual no cambia) y `edge-profile-<name>` para las demás.
   - **Por qué:** si dos `msedge --app` comparten `--user-data-dir`, el segundo proceso le pasa la URL al primero y termina enseguida. Su `Popen` queda muerto y `stop_window` no podría cerrar esa ventana.
   - El log indica qué ventana se abrió y su URL, por ejemplo `Ventana Edge 'hud' abierta en …`.
4. En `main()`, `edge` pasa a ser `edges: list[subprocess.Popen[str]]`. Se abre una ventana por cada `window_specs(args.tiktok)` y se omiten las que devuelvan `None`.
   - Sin `--window`, el log muestra **todas** las URLs: con `--tiktok`, `Overlay gameplay: …?layout=gameplay` y `Overlay HUD: …?layout=hud`, tanto en `dev` (puerto 5173) como en `obs` (`/overlay/`).
5. **Corrige el bug de apagado:** `shutdown()` está declarada como `(bot, client, backend, edge)`, pero se llama con `shutdown(bot, edge, client, backend)`. Hoy detiene Edge como si fuera «client» y el backend con `stop_window`. La nueva firma es `shutdown(bot, edges, client, backend)`, con argumentos por nombre en la llamada, y cierra cada ventana con `stop_window` en orden bot → ventanas → Vite → backend.
6. Actualiza el `help` de `--tiktok`: `Dos ventanas para TikTok Live: gameplay 1920x1080 (?layout=gameplay) y HUD 1080x656 (?layout=hud)`.

### 3.4 Tests — `scripts/test_run.py`

- Adapta `test_with_layout` a la nueva firma (`None`, `"gameplay"`, `"hud"`, con la URL de Vite y la de `/overlay/`).
- `test_window_specs`: con `False` devuelve una sola ventana de 1920 × 1080 sin layout; con `True` devuelve las dos especificaciones exactas de §3.3.2.
- `test_build_window_args_hud`: comprueba que `--window-size=1080,656` está presente (sustituye al test de 1080 × 1920).
- Un test de que `shutdown` llama a `stop_window` por cada ventana y a `stop_process` con `"client"` y `"backend"` para los procesos correctos. Usa `unittest.mock.patch` sobre `scripts.run.stop_window` y `scripts.run.stop_process`.

## 4. Archivos

- **Permitidos:** `client/src/App.tsx`, `client/src/index.css`, `scripts/run.py`, `scripts/test_run.py`.
- **Fuera de alcance:** `server/`, `media/` (no tocar ni convertir imágenes), `package.json` (`dev:tiktok` ya pasa `--window --tiktok`), `.vscode/`, `run.ps1`, `client/dist/` (no se versiona) y la documentación (README, ANALISIS y pendientes los actualiza Claude). Tampoco cambies el layout `landscape`, la calibración de los HUD ni el escalado del lienzo horizontal.

## 5. Criterios de aceptación

### (a) Los verifica Copilot (pega la salida real)

1. `grep -rn "tiktok\|TIKTOK" client/src` solo puede devolver comentarios que expliquen el uso en TikTok, nunca código. En particular, no debe aparecer ni `'tiktok'` ni `data-layout='tiktok'`.
2. `cd client; npx tsc --noEmit` termina con exit 0.
3. `cd client; npm run build` termina sin errores.
4. `server\.venv\Scripts\python.exe -m unittest scripts.test_run -v`, ejecutado desde la raíz, pasa entero e incluye los tests nuevos de §3.4.
5. `server\.venv\Scripts\python.exe scripts/run.py --help` muestra el nuevo texto de `--tiktok`.
6. **Smoke test sin ventanas:** `server\.venv\Scripts\python.exe scripts/run.py dev --no-bot --tiktok`, dejado correr unos 15 s y detenido con Ctrl+C. Pega las líneas `Overlay gameplay:` y `Overlay HUD:` del log y las de apagado. Si no puedes detenerlo limpiamente, mata el árbol y escribe «no probado».

### (b) Los verifican Claude o el usuario

1. `.\run.ps1 --window --tiktok` abre **dos** ventanas de Edge, tituladas `SuperRolScreen · Gameplay` y `SuperRolScreen · HUD`, ambas con el LED/socket conectado.
2. **Gameplay:** se ve el video. Un `NEW_MEDIA` y un `NOW_PLAYING` inyectados aparecen en esta ventana y no en la del HUD. No hay HUD de dados ni de voz.
3. **HUD:** fondo `background.jpg` en todo el lienzo. Un `DICE_ROLL` y un `VOICE_STATE` de 12 miembros inyectados se ven completos, centrados, sin solaparse y sin salirse del lienzo.
4. Si se reduce una ventana, el lienzo se escala entero (no se recorta) y el sobrante se ve negro.
5. Ctrl+C cierra **las dos** ventanas y todos los procesos, sin dejar `msedge` huérfanos de los perfiles `edge-profile-gameplay` ni `edge-profile-hud`.
6. El layout horizontal (`http://localhost:5173` y `.\run.ps1 --window`) se ve igual que antes y sigue siendo transparente.
7. La prueba en TikTok Live Studio la hace el usuario.

## 6. Instrucciones para Copilot

- Máximo 3 intentos por error; si al tercero sigue fallando, para y anótalo.
- No dejes procesos largos corriendo (backend, Vite, Edge): arráncalos solo para la comprobación y ciérralos.
- No hagas commits.
- Si te bloqueas, para y anótalo en «Desviaciones / bloqueos».
- Completa la sección «Reporte» con evidencia: salida real de los comandos, «no probado» si no pudiste verificar algo, y ningún ✅ sin evidencia. **La tarea no está terminada si el reporte está vacío** (ha pasado en las dos fichas anteriores).

## Reporte (Copilot)

### Archivos tocados

### Evidencia de criterios (a)

### Desviaciones del diseño / bloqueos

### Notas para la revisión

## Revisión (Claude)

Fecha: 2026-11-19 · **Veredicto: APROBADO CON CORRECCIONES.** La estructura cumple el diseño, pero había un error de React, un log que anunciaba una URL inexistente, props muertos y un test borrado o ausente. Claude lo corrigió todo.

### Diferencias entre el reporte y el diff

- La sección «Reporte (Copilot)» quedó **vacía por tercera ficha consecutiva**: sin archivos, evidencia ni desviaciones. Claude ejecutó todos los criterios (a).
- `git diff --stat` en código: `App.tsx`, `index.css`, `run.py` y `test_run.py`, todos dentro del alcance. `docs/claude.md` lo cambió el usuario (es la tarea).
- **Desviaciones respecto al diseño:**
  - `useFitScale` se llamaba dentro de los `if (LAYOUT === …)`, lo que viola las reglas de hooks de React (§3.1.3).
  - Los props `scale` de `MediaStage` y `top` de `NowPlayingHud` quedaron sin uso, con el envoltorio de escalado incluido (§3.1.6).
  - Se añadió `get_layout()`, que devolvía `'tiktok'`. Sin `--window`, el log mostraba `?layout=tiktok`, un layout eliminado, en vez de las dos URLs (§3.3.4).
  - Se añadían a `edges` las ventanas `None` (§3.3.4).
  - `shutdown()` aceptaba una lista o un proceso suelto y se llamaba con argumentos posicionales (§3.3.5).
  - Faltaba el test de `shutdown` (§3.4).
  - Se borró el bloque `if __name__ == "__main__": unittest.main()` de `test_run.py`.

### Seguridad y buenas prácticas

Sin observaciones de seguridad: no hay secretos, `shell=True`, cambios de host/CORS ni dependencias nuevas. Las URLs y los perfiles de Edge se forman con constantes internas, no con entradas del usuario. Los perfiles separados (`edge-profile-gameplay`, `edge-profile-hud`) quedan en `%LOCALAPPDATA%\SuperRolScreen`, igual que el existente.

### Correcciones de Claude

1. `App.tsx`: una sola llamada incondicional a `useFitScale` y un helper `fitStyle`. Se extrajo `HUD_BACKGROUND_STYLE` y se eliminaron `scale` de `MediaStage` y `top` de `NowPlayingHud`, con su envoltorio y su comentario.
2. `run.py`: una sola `url` por modo. Las ventanas se abren con `window_specs()` y solo se añaden si `start_window` devuelve un proceso. El log enumera todas las URLs con `window_specs()` (`Overlay web gameplay: …?layout=gameplay` y `Overlay web hud: …?layout=hud`; sin `--tiktok`, `Overlay web: …`). Se eliminó `get_layout()`. `shutdown(bot, edges: list, client, backend)` se llama con argumentos por nombre.
3. `test_run.py`: se añadió `test_shutdown_order_and_targets`, que comprueba el orden y que cada proceso va a su función, y se restauró `unittest.main()`.

### Evidencia (a), ejecutada por Claude tras las correcciones

1. `grep -rn "tiktok\|TIKTOK" client/src` → solo `App.tsx:74`, el comentario «Cualquier otro valor (incluido `tiktok`) da `landscape`».
2. `npx tsc --noEmit` → exit 0.
3. `npm run build` → `✓ built in 3.87s`.
4. `python -m unittest scripts.test_run -v` → `Ran 10 tests … OK`, incluidos `test_window_specs` y `test_shutdown_order_and_targets`.
5. `run.py --help` → `--tiktok  Dos ventanas para TikTok Live: gameplay 1920x1080 (?layout=gameplay) y HUD 1080x656 (?layout=hud)`.
6. El smoke test sin ventanas queda cubierto por la ejecución de (b), cuyo log incluye las líneas `Overlay web gameplay:` y `Overlay web hud:`.

### Verificación integrada (b), ejecutada una vez

- **Orquestador real:** `run.py dev --no-bot --window --tiktok`.
  - Abrió las dos ventanas: `21412 | SuperRolScreen · Gameplay` y `37308 | SuperRolScreen · HUD`, con perfiles separados (`edge-profile-gameplay`: 11 procesos; `edge-profile-hud`: 10). El backend registró 2 clientes WS.
  - Ctrl+Break → `Cerrando ventana Edge (PID 21412)`, `(PID 37308)`, client, backend → `Todo detenido`, exit 0, y **0** procesos `msedge` de SuperRolScreen restantes. **Criterios 1 y 5: OK.**
- **Contenido** (Edge headless por CDP sobre `/overlay/`, con `VOICE_STATE` de 12 miembros, `DICE_ROLL`, `NOW_PLAYING` y `NEW_MEDIA` inyectados):
  - **Gameplay** (1920 × 1080): título correcto, `NOW PLAYING` y medio visibles, sin HUD de dados ni de voz. **Criterio 2: OK.**
  - **HUD** (1080 × 656): `background.jpg` en todo el lienzo; dados a la izquierda y voz a la derecha, centrados y sin solaparse; 9 filas, `+3 MORE` y `12 IN VOICE · 2 TALKING` dentro de la pantalla; sin medios ni `NOW PLAYING`. **Criterio 3: OK.**
  - **HUD a 800 × 400:** `main` escalado a 659 × 400 entero, con el sobrante a la derecha en negro. **Criterio 4: OK.**
  - **Horizontal:** sin cambios visuales, con los HUD, el medio y `NOW PLAYING` en su sitio. **Criterio 6: OK en contenido.** Pero el `body` no es transparente: `client/index.html` tiene `class="bg-black"` desde el primer commit. Es un problema anterior y queda anotado en pendientes.
- **Sin probar:**
  - En la captura de escritorio de la ejecución real solo se vio el video del gameplay a pantalla completa, sin el panel `NOW PLAYING` ni el medio inyectados 3 s antes. No se pudo confirmar qué ventana quedaba delante ni si los eventos llegaron a esa ventana. El contenido se verificó en headless (donde el video H.264 no se decodifica).
  - Prueba manual del usuario en TikTok Live Studio (criterio 7).

### Pendientes

- Prueba manual del usuario: comprobar en las dos ventanas reales que `NOW PLAYING` y los medios aparecen sobre el gameplay, y componer la escena en TikTok Live Studio.
- Hallazgos nuevos en `pendientes.md`: `body` con `bg-black` en el layout horizontal, el backend forzado con `taskkill` al apagar y el reporte de Copilot vacío por tercera vez.
