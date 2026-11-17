# Ficha de tarea — HUD "Now playing" (detector de FlaviBot)

Fecha: 2026-11-16 · Iteración 1

## 1. Contexto mínimo

SuperRolScreen es un overlay 1920 × 1080 para OBS. Tiene tres piezas:

- `server/discord_listener.py`, el bot que lee Discord y emite eventos JSON por WebSocket.
- `server/main.py`, el backend FastAPI que valida (`validate_event`) y reenvía los eventos.
- `client/src/App.tsx`, el overlay React que valida otra vez (`parseEvent`) y los dibuja.

Hoy existen los eventos `DICE_ROLL`, `NEW_MEDIA` y `VOICE_STATE`. El canal de medios (`MEDIA_CHANNEL_ID`) ya funciona como modelo de "canal de Discord que produce algo visual". La configuración se carga en `server/config.py` desde `server/.env`. El usuario ya añadió `MUSIC_CHANNEL_ID` a `server/.env`. **No leas, imprimas ni modifiques `server/.env`.**

FlaviBot es un bot de música externo. En el canal de música publica un **embed** cuando empieza una canción. **No se conoce todavía la estructura exacta del embed** (si "Now Playing" va en el título, en el autor del embed o en un campo, ni si la canción va en la descripción o en el título). Por eso el parser debe ser tolerante y el inspector debe poder volcar ese canal.

## 2. Objetivo

Cuando FlaviBot publique en `MUSIC_CHANNEL_ID` el aviso de la canción que suena, el overlay muestra un panel `NOW PLAYING:` + `[canción]`. El panel entra deslizándose desde el borde izquierdo, a media altura, se queda unos 8 s y sale deslizándose hacia la izquierda. Mantiene la estética LED/CRT de los otros HUD y no usa ninguna imagen nueva.

## 3. Diseño

### 3.1 Contrato del evento nuevo

```json
{ "type": "NOW_PLAYING", "title": "Artista - Canción" }
```

- `title`: texto plano, sin markdown ni URLs, sin espacios al inicio o al final, de 1 a 120 caracteres.

### 3.2 Servidor

**`server/config.py`**: añadir `MUSIC_CHANNEL_ID: int = _int_env("MUSIC_CHANNEL_ID")` junto a los otros IDs.

**`server/music_detect.py` (nuevo, lógica pura, sin red ni token)**:

- Constantes: `NOW_PLAYING_TITLE_MAX = 120` y `MUSIC_BOT_NAME_HINT = "flavi"`.
- `is_music_bot(author) -> bool`: verdadero si `author.bot` es verdadero y `MUSIC_BOT_NAME_HINT` aparece, sin distinguir mayúsculas, en `author.name` o en `author.display_name`. Debe aceptar objetos tipo `SimpleNamespace`, para poder testearlo sin discord.py.
- `clean_title(text) -> str | None`: convierte `[texto](url)` en `texto`; quita `**`, `__`, `*`, `` ` ``, `~~` y `||`; elimina las URLs sueltas; colapsa los espacios; se queda con la primera línea no vacía; recorta a `NOW_PLAYING_TITLE_MAX` (con `…` si recorta). Devuelve `None` si queda vacío.
- `extract_now_playing(content: str, embeds: list) -> str | None`: los embeds se reciben como objetos con `title`, `description`, `author.name` y `fields[].name/.value`; cualquiera puede ser `None`. Usa el patrón de cabecera `HEADER_RE` (sin distinguir mayúsculas): `now\s*playing|reproduciendo\s*ahora|ahora\s*suena|est[aá]\s*sonando|sonando\s*ahora`. Aplica estas reglas, en orden, a cada embed, y devuelve la primera que dé un título limpio:
  1. El título del embed contiene la cabecera **seguida de texto**, por ejemplo `Now Playing: X`, `🎶 Now playing - X` o `Now playing **X**`: la canción es lo que viene después de la cabecera y del separador (`:`, `-`, `–`, `|`, espacios o emojis).
  2. El título o el `author.name` del embed son **solo** la cabecera (admitiendo emojis o signos alrededor): la canción sale de la descripción y, si no hay descripción, del título cuando la cabecera estaba en el autor, o del primer campo.
  3. Un campo cuyo `name` contiene la cabecera: la canción sale de su `value`.
  4. Como último recurso, `content` en texto plano con la cabecera seguida de texto, igual que en la regla 1.
  - Si ningún texto del mensaje contiene la cabecera, devuelve `None`. Así se ignoran `Added to queue`, `Queue`, `Paused`, `Stopped`, etc.
- Admite indistintamente objetos `discord.Embed` y `SimpleNamespace` (usa `getattr(..., None)`).

**`server/discord_listener.py`**:

- Importar `MUSIC_CHANNEL_ID`. Si es 0, registrar la advertencia `MUSIC_CHANNEL_ID no configurado: no se detectarán canciones` (igual que con media). Incluir `("música", MUSIC_CHANNEL_ID)` en la comprobación de visibilidad de `on_ready`.
- Nuevo método `_handle_music(message)`: si `is_music_bot(message.author)` y `extract_now_playing(message.content, message.embeds)` devuelven una canción, emite `{"type": "NOW_PLAYING", "title": ...}` con `self.link.send`. Deduplica por la tupla `(message.id, title)` con un `OrderedDict` limitado a 200 entradas, como en `_dice_seen`. Así no se repite la misma canción cuando el bot edita su mensaje, pero sí se emite si la edición cambia la canción.
- Llamarlo desde `on_message` y desde `on_message_edit` cuando `channel.id == MUSIC_CHANNEL_ID` y el ID no es 0. Los bots de música suelen editar el mensaje de "Now playing". Envuelve la llamada en `try/except` con `log.exception`, como en media. Cuando emita, deja un `log.info("Now playing: %s", title)`.
- Actualizar el docstring del módulo.

**`server/main.py`**:

- Añadir `"NOW_PLAYING"` a `ALLOWED_EVENT_TYPES`.
- Crear `_validate_now_playing(payload)`: `title` debe ser `str`; se le aplica `strip()`; tras el strip debe tener entre 1 y 120 caracteres. Devuelve un objeto reconstruido `{"type": "NOW_PLAYING", "title": title}`, sin claves extra (igual criterio que en `VOICE_STATE`). Si no es válido, devuelve `None`.

**`server/inspect_bot.py`**:

- Leer también `MUSIC_CHANNEL_ID` (opcional) e inspeccionar mensajes de los dos canales, indicando el canal en cada volcado.
- Volcar además `embed.author.name`, `embed.footer.text` y `author.display_name`.
- Inspeccionar también `on_message_edit` en el canal de música, para saber si FlaviBot edita su mensaje.
- Con esto el usuario o Claude podrán ver el embed real y ajustar `music_detect.py`.

### 3.3 Cliente

**`client/src/App.tsx`**:

- Constantes al inicio: `NOW_PLAYING_DISPLAY_MS = 8000`, `NOW_PLAYING_EXIT_MS = 600` (debe coincidir con `.np-out` en el CSS), `NOW_PLAYING_TITLE_MAX = 120`.
- Tipo `NowPlayingEvent = { type: 'NOW_PLAYING'; title: string }`, añadido a `OverlayEvent`.
- En `parseEvent`, `title` debe ser string; se le aplica `trim`, se recorta a 120 *code points* (`Array.from`) y se descarta si queda vacío.
- Componente `NowPlayingHud({ item })`, donde `item` es `{ id: number; title: string } | null`:
  - Posición: `absolute`, `left: 0`, `top: 50%`, `-translate-y-1/2`, `z-40` (por encima de `MediaStage`), `pointer-events-none`, `select-none`, `max-width` de unos 640 px.
  - Panel: reutiliza las clases `.hud-screen` (fondo CRT), `.hud-scanlines` y las esquinas `.media-corner` derecha (tr/br), o un borde LED `1px solid rgb(77 243 255 / 0.45)` sin borde izquierdo, pegado al borde de pantalla. Usa el color `var(--led)` y la fuente `font-led` / Share Tech Mono que ya usan los otros HUD.
  - Contenido: una etiqueta `NOW PLAYING:` pequeña, en mayúsculas, con `letter-spacing` y `text-shadow` como `.media-caption`. Debajo o al lado, el título más grande, en una sola línea, con `overflow: hidden; text-overflow: ellipsis; white-space: nowrap`. Puede llevar un icono `♪` en variante de texto (U+FE0E) para que tome el color LED.
  - Fases: `in` (clase `.np-in`) → espera `NOW_PLAYING_DISPLAY_MS` → `out` (clase `.np-out`) → espera `NOW_PLAYING_EXIT_MS` → desmontado.
  - Si llega una canción nueva mientras hay otra en pantalla, la reemplaza y reinicia la entrada (usar `key={item.id}`), sin cola. Limpiar los timers al desmontar y al cambiar.
- En `App`, guardar el estado `nowPlaying` con un contador de id incremental, manejar el `case 'NOW_PLAYING'` en `handleEvent` y renderizar `<NowPlayingHud …/>` dentro de `<main>`.

**`client/src/index.css`**: nueva sección `Now Playing HUD` con:

- `.np-in`: keyframes de `transform: translateX(-105%)` y `opacity: 0` a `translateX(0)` y `opacity: 1`, 0,7 s, `cubic-bezier(0.22, 1, 0.36, 1)`, `both`.
- `.np-out`: keyframes inversos hacia `translateX(-105%)`, 0,6 s, `ease-in`, `forwards`.
- Estilos del panel y del texto que hagan falta (`.np-panel`, `.np-label`, `.np-title`). No modificar las reglas existentes.

## 4. Archivos

**Permitidos** (son 9 en total; si te pasas de presupuesto, termina primero la Parte A y anótalo):

- Parte A, servidor: `server/config.py`, `server/music_detect.py` (nuevo), `server/discord_listener.py`, `server/main.py`, `server/inspect_bot.py` y `server/tests/test_music_detect.py` (nuevo).
- Parte B, cliente: `client/src/App.tsx` y `client/src/index.css`.
- Esta ficha, solo la sección "Reporte".

**Fuera de alcance (no tocar)**:

- `server/.env`, `README.md`, `ANALISIS_DE_SOFTWARE.md` y `docs/pendientes.md`. Los documenta Claude.
- `scripts/`, `run.ps1`, `requirements.txt` (no añadir dependencias), `media/`, `voice_presence.py` y `media_cache.py`.
- El CORS de `main.py`, que ya está anotado como pendiente.
- La lógica de dados, medios y voz, salvo los puntos de enganche indicados en el diseño.

## 5. Criterios de aceptación

### (a) Los verifica Copilot

1. `server/tests/test_music_detect.py` (con `unittest` y `SimpleNamespace`, estilo `test_voice_presence.py`) pasa con: `.\.venv\Scripts\python.exe tests\test_music_detect.py` (desde `server/`). Mínimo:
   - título `Now Playing: Artista - Canción` → `Artista - Canción`
   - título `🎶 Now Playing` + descripción `[Canción](https://youtu.be/x) - 3:45` → `Canción - 3:45` (o el texto sin URL que dé `clean_title`; documentar el resultado real)
   - `author.name = "Now playing"` + `title = "Canción"` → `Canción`
   - campo `name="Now Playing"`, `value="**Canción**"` → `Canción`
   - `content` plano `Now playing: Canción` sin embeds → `Canción`
   - título `Added to queue` + descripción `Canción` → `None`
   - embed sin ningún texto (todo `None`) → `None` sin excepción
   - título de 300 caracteres → recortado a ≤ 120 con `…`
   - `is_music_bot`: FlaviBot con `bot=True` → `True`; usuario humano llamado "Flavio" con `bot=False` → `False`; otro bot → `False`
   - `validate_event`: `NOW_PLAYING` válido (con claves extra eliminadas); `title` vacío, solo espacios, de 121 caracteres o no string → `None`
2. Los tests existentes siguen pasando: `tests\test_voice_presence.py` y `tests\smoke_test.py` (con los puertos 8765/8766 libres).
3. `python -m py_compile` de cada `.py` tocado sin errores.
4. Cliente: `npm run build` en `client/` termina sin errores de TypeScript (`tsc` estricto) ni de Vite.
5. Revisión estática: sin `shell=True`, sin `eval`/`dangerouslySetInnerHTML` (el título se renderiza como texto React), sin imprimir el token, sin dependencias nuevas.

### (b) Los verifican Claude o el usuario

1. Con `.\run.ps1 --no-bot` y Edge en `http://localhost:5173`, inyectar `{"type":"NOW_PLAYING","title":"Prueba - Canción"}` por `/api/events`. El panel entra desde el centro izquierda, se queda unos 8 s y sale. Un segundo evento durante la visualización reemplaza al primero sin solapes. Un título largo se corta con elipsis.
2. Al inyectar `title` inválido, la API responde 422 y el overlay no cambia.
3. Estética coherente con el HUD de dados y el de voz, sin tapar el HUD de dados (abajo a la izquierda).
4. El build servido en `/overlay/` se comporta igual.
5. Con Discord real: `inspect_bot.py` vuelca el embed de FlaviBot; con `.\run.ps1`, al reproducir una canción aparece el panel con el nombre correcto, una sola vez por canción (incluidas las ediciones). Los mensajes de cola o pausa no lo disparan.
6. Prueba manual final del usuario en OBS.

## 6. Instrucciones para Copilot

- Máximo **3 intentos por error**. Si el tercero falla, para y anótalo en el Reporte con la salida real.
- No dejes procesos largos corriendo (Vite, uvicorn, bot). Si levantas algo para el smoke test, ciérralo. No ejecutes `discord_listener.py` ni `inspect_bot.py`, porque necesitan el token real.
- **No hagas commits** ni cambies de rama.
- Si te bloqueas (por ejemplo, porque una decisión de diseño no encaja con el código), para y anótalo en el Reporte en lugar de improvisar fuera de alcance.
- Completa la sección **Reporte** con evidencia: la salida real de cada comando (recortada a lo relevante) y "no probado" cuando no hayas podido verificar algo. No marques ✅ sin evidencia.
- Comandos de Python siempre con el venv: `server\.venv\Scripts\python.exe`.

## Reporte (Copilot)

_Pendiente._

### Archivos tocados

### Evidencia de criterios (a)

### Desviaciones del diseño / bloqueos

### Notas para la revisión

## Revisión (Claude)

Fecha: 2026-11-16

**Veredicto: aprobado tras correcciones.** La entrega de Copilot no compilaba ni pasaba sus propios tests. Claude rehízo el parser, los tests y el componente del cliente. Con eso se cumplen los criterios (a) y los (b) que se pueden comprobar sin Discord.

### Diferencias entre el reporte y el diff

- **Reporte:** la sección "Reporte (Copilot)" quedó vacía (`_Pendiente._`). No había ninguna evidencia que contrastar.
- **`index.css`:** no se tocó. Faltaban `.np-in`, `.np-out` y los estilos del panel.
- **`App.tsx`:**
  - Constantes `NOW_PLAYING_*` declaradas dos veces (error TS2451).
  - Asignación a una constante de estado (`++nowPlayingId`, error TS2588).
  - El componente `NowPlayingHud` no existía (error TS2552).
  - Resultado: `tsc` daba 11 errores.
- **`inspect_bot.py`:** `SyntaxError`, por un `\n` literal tras el `print` de cierre de `on_message_edit`.
- **`tests/test_music_detect.py`:**
  - No se podía importar: `ModuleNotFoundError: music_detect`, porque faltaba `sys.path`.
  - No probaba `validate_event`.
  - Fijaba comportamientos erróneos: con el autor "Now playing", esperaba `"Now playing"` como canción.
- **`music_detect.py`:**
  - Las reglas 2 y 3 solo se evaluaban si el **título** contenía la cabecera. Por eso un embed con la cabecera en el autor o en un campo y un título distinto devolvía `None`.
  - `clean_title` colapsaba los saltos de línea antes de quedarse con la primera línea, así que mezclaba las líneas de la descripción.
  - Borraba todos los `_` y `|`, lo que rompía títulos como `my_song`.

### Correcciones de Claude

- `music_detect.py` reescrito:
  - Reglas 1 a 4 independientes entre sí.
  - `_is_header_only` admite emojis y signos alrededor de la cabecera.
  - `clean_title` va línea a línea y descarta las líneas que solo tienen símbolos.
  - El markdown se quita por marcadores (`**`, `__`, `~~`, `||`, `` ` ``, `*`), no por caracteres sueltos.
- `tests/test_music_detect.py` reescrito: 29 tests, incluidos `validate_event` (claves extra eliminadas, límite de 120 caracteres, tipos inválidos).
- `discord_listener.py`: el import de `music_detect` pasa al inicio del módulo; se quita un `try` redundante.
- `main.py`: constante `NOW_PLAYING_TITLE_MAX` en lugar del literal 120.
- `inspect_bot.py`:
  - Se corrige la sintaxis.
  - Una única `dump_message()` sirve para los mensajes nuevos y para las ediciones de música.
  - Muestra `repr` del autor, el pie y los campos del embed, y el resultado de `is_music_bot` y `extract_now_playing`, para ajustar el parser con el embed real.
- `App.tsx`:
  - Constantes únicas.
  - Contador con `useRef`.
  - Componente `NowPlayingHud`: la fase de salida va ligada al id del aviso (`leavingId`), para que uno nuevo no arranque en `np-out`. Los timers se limpian al reemplazar o desmontar.
- `index.css`: sección "Now Playing HUD" con `.np-panel`, `.np-icon`, `.np-label`, `.np-title`, `.np-in` (0,7 s) y `.np-out` (0,6 s, igual que `NOW_PLAYING_EXIT_MS`).

### Evidencia (a) — ejecutada por Claude

- `py_compile` de `music_detect`, `inspect_bot`, `discord_listener`, `main`, `config` y del test: OK.
- `tests\test_music_detect.py`: `Ran 29 tests … OK`.
- `tests\test_voice_presence.py`: `Ran 23 tests … OK`.
- `tests\smoke_test.py`: `26/26 OK`.
- `npx tsc --noEmit`: sin errores. `npm run build`: `✓ built in 1.27s`.
- Búsqueda de `shell=True`, `dangerouslySetInnerHTML` y `eval(` en `server/*.py` y `client/src/`: sin resultados. No hay dependencias nuevas. El título se muestra como texto React.

### Verificación integrada (b) — ejecutada una vez

Montaje: backend propio en `:8000` con el build en `/overlay/`, Edge headless controlado por CDP y eventos inyectados con `POST /api/events`.

- **Entrada:** el panel se ve a t=0,15 s en `x=-129` (deslizando) y a t=1,35 s en `x=0`, `y=493` (centro-izquierda). Línea de tiempo medida en la página: `np-in` a 3 ms, `np-out` a 8003 ms, desmontado a 8604 ms.
- **Reemplazo:** un segundo aviso durante la visualización reemplaza al primero (`count panels 1`). Un título largo se recorta con elipsis a 640 px de ancho.
- **Inválidos:** `title` con solo espacios o de 121 caracteres → 422, y el overlay no cambia. La clave extra `extra` se descarta.
- **Convivencia:** con dados, voz y el aviso a la vez no hay solapes. El panel queda por encima del HUD de dados y lejos del escenario de medios.
- **No probado:**
  - Vite `:5173`. Solo se probó `/overlay/`; el código es el mismo.
  - Discord real con FlaviBot: no se conoce el embed real.
  - OBS.

### Pendientes

1. **Usuario:** ejecutar `.\.venv\Scripts\python.exe inspect_bot.py` desde `server/`, poner una canción con FlaviBot y comprobar en la consola la línea `[music_detect] is_music_bot=True now_playing='…'`. Si sale `None` o un texto incorrecto, pegar el volcado para ajustar `music_detect.py`. Si el usuario del bot no contiene "flavi", cambiar `MUSIC_BOT_NAME_HINT`.
2. Prueba manual final con `.\run.ps1` y en OBS. Comprobar también que la nota `♪` sale monocroma en el navegador de OBS.

### Ajuste con el volcado real de FlaviBot (Claude)

- **Primer volcado:** `content=''` y sin embeds. FlaviBot usa **componentes V2** (`flags=36864`, `components_v2=True`).
- **Inspector:** ahora muestra los flags, los adjuntos, el árbol de componentes y el JSON crudo del gateway del canal de música (`enable_debug_events` + `on_socket_raw_receive`).
- **Detector:**
  - `component_texts()` y `_from_texts()` leen los `TextDisplay`; el listener pasa `message.components`.
  - La cabecera real es un enlace, `### [Now playing](https://flavibot.xyz/music-player)`. Por eso las líneas se pasan a texto plano antes de buscarla, también en `_is_header_only` para los embeds.
  - Se eliminan las menciones `<@id>` y `<#id>`.
- **Tests:** 38 OK. Uno replica el mensaje real y da `Black Eyed Peas - I Gotta Feeling`. Con objetos reales de discord.py (`_component_factory` sobre el JSON equivalente) también se obtiene `Black Eyed Peas - I Gotta Feeling`.
- **Pendiente:** prueba de punta a punta con `.\run.ps1` y OBS.
