# Análisis de software — SuperRolScreen

## 1. Propósito y alcance

SuperRolScreen es una aplicación local de overlay para streams de partidas de rol. Integra varias fuentes de información en una escena 1920 × 1080: videos de fondo almacenados localmente, eventos de tiradas del bot de dados de Discord, multimedia de un canal de Discord, la presencia en un canal de voz y los avisos de canción del bot de música. La primera fase prioriza la reproducción continua de la escena, una comunicación sencilla entre procesos y la descarga en caché de medios externos que pueden no ser reproducibles directamente desde OBS.

El sistema se divide en:

1. **Bot de Discord** (`server/discord_listener.py`): interpreta mensajes y produce eventos.
2. **Backend local** (`server/main.py`): sirve archivos y API, mantiene clientes WebSocket y distribuye eventos.
3. **Overlay web** (`client/src/`): consume eventos, reproduce los clips y presenta el HUD y la multimedia.

El bot y el backend se ejecutan como procesos independientes. El overlay se sirve desde Vite durante el desarrollo y desde el backend como build estático para OBS.

## 2. Arquitectura y flujo de datos

```text
Discord
  ├─ canal de dados ──> parser de embed ──> DICE_ROLL ──┐
  ├─ canal de medios ─> extracción/resolución/cache ──> NEW_MEDIA
  ├─ canal de música ─> music_detect (FlaviBot) ─────> NOW_PLAYING
  └─ canal de voz (/join) ─> voice-recv: miembros + habla ──> VOICE_STATE
                                                        │
                                                        v
                                            WebSocket del bot
                                                        │
                                                        v
Backend FastAPI :8000 ───── /ws: broadcast a overlays conectados
  ├─ /api/clips             lista clips de Gameplay
  ├─ /api/health            estado del proceso y cantidad de WS
  ├─ /api/events            inyección local de eventos
  ├─ /media/*               Gameplay, HUD y cache
  └─ /overlay/*             build de producción, si existe
                                                        │
                                                        v
Overlay React ──> GameplayLoop + DiceHud + VoiceHud + MediaStage + NowPlayingHud
```

### Tiradas de dados

`OverlayBot` escucha el canal definido por `DICE_CHANNEL_ID`. `parse_button_dice()` toma el primer embed y busca en el título una secuencia equivalente a `number of dice: X ⇒ Y successes`; acepta las variantes de flecha contempladas por su expresión regular. El nombre del jugador se toma, en orden, de los metadatos de interacción, del autor del embed, del pie del embed o del valor predeterminado `Jugador`. El evento se envía una sola vez por ID de mensaje, incluso si el bot de dados edita un mensaje existente.

El parser está acoplado al texto y al idioma del embed de un bot externo. Si su formato cambia, la detección de tiradas puede dejar de funcionar sin que necesariamente falle el resto del overlay. `inspect_bot.py` sirve para inspeccionar mensajes y ajustar el parser.

### Multimedia de Discord

`MediaProcessor` agrupa candidatos por adjunto o embed, preserva el orden de llegada y limita la emisión a cuatro medios por mensaje. Para cada enlace:

1. Considera adjuntos de imagen/video y sus URLs `url` y `proxy_url`; también recoge URLs de video, imagen, miniatura y página de los embeds.
2. Si el mensaje contiene enlaces sin embeds, vuelve a leerlo a los 2,5 y 7,5 segundos desde el inicio del procesamiento (esperas acumuladas de 2,5 y 5 segundos), ya que Discord puede generar sus embeds más tarde.
3. `MediaCache` intenta descargar el candidato, reconoce el contenido por magic bytes y guarda un archivo local. Si el candidato es HTML, examina metadatos OpenGraph y Twitter, con preferencia por video.
4. Emite `NEW_MEDIA` con URL local y tipo detectado. Si la descarga no puede resolverse, puede utilizar como último recurso una URL remota cuya extensión sea reconocible.

El caché limita el tamaño por archivo a 60 MiB y conserva hasta 200 archivos. Elimina descargas parciales abandonadas de más de una hora. Los archivos HEIC, los formatos desconocidos y los archivos mayores al límite no se aceptan. El tipo MIME informado por un servidor o la extensión original no se consideran suficientes para determinar el formato.

### Presencia de voz

`OverlayBot` registra los slash commands `/join` y `/leave` en un `app_commands.CommandTree` y los sincroniza por servidor en `on_ready` (una vez). `/join` conecta al canal de voz del invocador con `voice_recv.VoiceRecvClient` (`self_mute=True`, `self_deaf=False`; ensordecido no recibiría paquetes). Si el bot ya estaba en otro canal del mismo servidor, se mueve; si estaba en otro servidor, se desconecta de allí. El overlay muestra un solo canal.

`server/voice_presence.py` contiene la lógica pura, testeable sin token:

- `build_voice_state()`: arma el evento. Excluye bots, ordena por nombre, recorta a 32 caracteres y limita a 25 miembros.
- `has_humans()`: indica si queda alguna persona en el canal.
- `SpeakingSink`: un `AudioSink` con `wants_opus=True` que no decodifica audio. Sus eventos `on_voice_member_speaking_start/stop` llegan desde el hilo `SpeakingTimer` de voice-recv, según la llegada de paquetes (stop ≈ 200 ms tras el último), y se trasladan al event loop con `call_soon_threadsafe`.

voice-recv no implementa DAVE, el cifrado E2EE de voz de Discord. Por eso solo se detecta la llegada de paquetes por SSRC, sin descifrar ni decodificar el audio; se verificó que funciona con Discord real (2026-11-16). Los cambios de habla y de miembros se agrupan con un debounce de 100 ms. Mientras el bot está conectado, el estado completo se reenvía cada 5 s como latido, para que un overlay recién abierto lo reciba. `on_voice_state_update` actualiza los miembros y desconecta al bot cuando no quedan personas; al desconectarse se emite `channel: null`. Los logs INFO de voice-recv (RTCP, claves `seq` del gateway de voz) se silencian.

En el overlay, `parseEvent()` revalida `VOICE_STATE`: descarta los miembros mal formados (no el evento entero) y recorta los nombres a 32 code points. `VoiceHud` muestra el canal y los miembros, y vuelve a `STANDBY` con `channel: null`, cuando pasan `VOICE_STALE_MS` (15 s, tres latidos perdidos) sin eventos o cuando el WebSocket no está abierto.

### Avisos de canción (bot de música)

`OverlayBot` atiende `on_message` y `on_message_edit` en `MUSIC_CHANNEL_ID`, porque los bots de música suelen editar su aviso. `server/music_detect.py` contiene la lógica pura, testeable sin token:

- `is_music_bot()`: el autor debe ser bot y su `name` o `display_name` debe contener `MUSIC_BOT_NAME_HINT` (`"flavi"`).
- `extract_now_playing()`: busca la cabecera `HEADER_RE` ("now playing", "reproduciendo ahora", "ahora suena", "está sonando", "sonando ahora") y aplica estas reglas en orden:
  1. Título del embed `Now playing: X`.
  2. Título o autor del embed formados solo por la cabecera; la canción sale de la descripción, del título o del primer campo.
  3. Campo cuyo nombre contiene la cabecera.
  4. Descripción o `content` en texto plano `Now playing: X`.

  Si ningún texto tiene la cabecera, devuelve `None`, de modo que "Added to queue", "Paused", etc. se ignoran.
- `clean_title()`: deja una línea de texto plano, sin markdown ni URLs, y la recorta a 120 caracteres con `…`.

FlaviBot no usa embeds: publica un mensaje con **componentes V2** (flag `components_v2`). Es un `Container` con un `TextDisplay` `### [Now playing](https://flavibot.xyz/music-player)` y, dentro de un `SectionComponent`, otro `TextDisplay` con `**[Artista - Canción](url de Spotify)**`; además lleva botones y una imagen de progreso. `component_texts()` recorre los `children` de los componentes y junta sus textos; `_from_texts()` pasa cada línea a texto plano (enlaces convertidos en su texto, sin URLs ni encabezados `#`) y, si una línea es solo la cabecera, toma como canción la siguiente línea con texto. `clean_title()` elimina además las menciones `<@id>` y `<#id>`.

El evento se deduplica por `(id de mensaje, título)`, de modo que una edición que no cambia la canción no lo repite. La estructura de FlaviBot se tomó de un volcado real de `inspect_bot.py` (2026-11-16), que muestra el árbol de componentes y el JSON crudo del gateway.

En el overlay, `NowPlayingHud` muestra el panel a media altura, pegado al borde izquierdo: entra con `.np-in` (0,7 s), permanece `NOW_PLAYING_DISPLAY_MS` (8 s) y sale con `.np-out` (`NOW_PLAYING_EXIT_MS`, 600 ms). Un aviso nuevo reemplaza al actual y reinicia la entrada; no hay cola.

### Entrega y reproducción de eventos

El listener mantiene una única conexión WebSocket saliente a `ws://localhost:8000/ws`. `OverlayLink` usa una cola de hasta 200 eventos, reintenta cada tres segundos y descarta los eventos que tengan más de 60 segundos al momento de enviarlos. El backend reenvía cada evento a todos los WebSocket conectados excepto al emisor. Los errores de envío provocan la desconexión del cliente fallido.

El cliente React valida y normaliza los mensajes recibidos, actualiza el HUD o agrega medios a una cola de capacidad 10. Solo hay un medio visible a la vez. Si una imagen/video no carga, el cliente prueba el elemento alternativo una vez; si tampoco carga, la descarta. La fase de carga expira a los 10 segundos.

## 3. Tecnologías y dependencias

### Backend y bot

- **Python 3.12**: runtime usado para probar el proyecto.
- **FastAPI**: API HTTP y endpoint WebSocket.
- **Uvicorn**: servidor ASGI usado para ejecutar FastAPI.
- **discord.py 2.x** con el extra `[voice]` (PyNaCl, davey): cliente del bot, slash commands, conexión de voz y modelos de mensajes/embeds.
- **discord-ext-voice-recv** (fijado a un commit por URL de archivo): recepción de voz; aquí solo se usa para detectar quién habla.
- **aiohttp**: cliente HTTP asíncrono para resolver y descargar medios.
- **websockets**: conexión WebSocket saliente persistente del bot.
- **python-dotenv**: carga de variables desde `server/.env`.
- **Starlette StaticFiles**, incorporado vía FastAPI/Starlette: distribución de archivos y build del cliente; soporta solicitudes Range para video.

Las versiones instalables se fijan en `server/requirements.txt`, el único archivo de dependencias Python del repo. `.gitignore` ignora un `/requirements.txt` en la raíz, para que un `pip freeze >` accidental no se cuele en un commit. `server/pyproject.toml` existe actualmente sin configuración declarada.

### Cliente

- **React 18** y **React DOM**: componentes y renderizado de la escena.
- **TypeScript 5.6**: tipos del contrato de eventos y validación estática estricta.
- **Vite 5** y `@vitejs/plugin-react`: servidor de desarrollo y build.
- **Tailwind CSS 3**, **PostCSS** y **Autoprefixer**: utilidades de estilo y procesamiento CSS.

El manifiesto del cliente es `client/package.json`; `npm ci` instala las versiones registradas en el lockfile del cliente. El paquete `package.json` de la raíz está vacío en dependencias; los comandos y dependencias de interfaz corresponden al directorio `client/`.

### Recursos remotos

`client/src/index.css` carga Orbitron y Share Tech Mono desde Google Fonts, y DSEG7 Classic desde jsDelivr. Si esos recursos no están disponibles, se utilizan fuentes alternativas definidas en CSS. La escena no descarga imágenes del repositorio desde un servicio externo; el backend sirve los archivos de `media/`.

## 4. Estructura del proyecto

### Raíz

| Ruta | Responsabilidad |
|---|---|
| `README.md` | Guía para instalar, configurar, arrancar y utilizar el proyecto con OBS. |
| `ANALISIS_DE_SOFTWARE.md` | Documento técnico para entender la arquitectura y orientar cambios futuros. |
| `package.json` | Manifiesto de nivel raíz sin dependencias; scripts `dev`, `dev:nobot`, `dev:window`, `dev:tiktok` y `obs` que invocan el orquestador. |
| `scripts/test_run.py` | Tests unitarios (`unittest`) de la CLI del orquestador (incluido `--tiktok`), de `with_layout`, de `window_specs`, de `start_client` (lanzamiento de Vite con node), de `--parent-pid` y de `open_parent`/`parent_alive` con un proceso real, del orden de `shutdown` y de la construcción del lanzamiento de Edge. |
| `scripts/run.py` | Orquestador (solo librería estándar): preflight, arranque ordenado con health check, logs unificados con prefijo, política de caídas y apagado del árbol de procesos. |
| `run.ps1` | Atajo de PowerShell para `scripts/run.py` con el Python del venv; propaga el código de salida. |
| `.vscode/tasks.json` | Tareas de VS Code que ejecutan `${workspaceFolder}/run.ps1` en los modos `dev`, `obs`, `dev --no-bot`, `dev --no-client`, `dev --window`, `dev --window --tiktok` y `obs --window`. La ruta usa `/`: con `
` el JSON lo interpretaría como un retorno de carro. |
| `media/Gameplay/` | Clips de fondo enumerados por el backend. Admite MP4, WebM, M4V y MOV. |
| `media/HUD/` | Recursos del HUD; el cliente espera `Dados Hud.png` (dados), `voice.png` (voz, 276 × 539, con esquinas transparentes) y `background.jpg` (fondo de la ventana HUD de TikTok, 1200 × 630). |
| `media/cache/` | Caché local de archivos descargados desde Discord. |

### Backend (`server/`)

| Ruta | Responsabilidad |
|---|---|
| `server/main.py` | Crea la aplicación FastAPI, configura CORS, monta `/media` y opcionalmente `/overlay`, implementa HTTP, WebSocket y validación básica de eventos. En Windows, su `lifespan` instala `_ignore_proactor_reset` como handler de excepciones del bucle: descarta el `ConnectionResetError`/`ConnectionAbortedError` de `_ProactorBasePipeTransport._call_connection_lost` (fallo de CPython al cerrarse un socket ya reseteado) y deja pasar cualquier otra excepción. |
| `server/config.py` | Carga `server/.env`, centraliza rutas, valores de Discord, extensiones y límites del caché. |
| `server/discord_listener.py` | Implementa `OverlayBot`, `OverlayLink`, el parser de tiradas, candidatos multimedia, reintentos y emisión de eventos. |
| `server/music_detect.py` | Lógica pura de detección de avisos "now playing" del bot de música: `is_music_bot`, `extract_now_playing` y `clean_title`. |
| `server/voice_presence.py` | Lógica pura de presencia de voz: construcción de `VOICE_STATE`, detección de humanos y `SpeakingSink` (detección de habla sin decodificar audio). |
| `server/media_cache.py` | Detecta tipos por magic bytes, extrae candidatos OpenGraph/Twitter y descarga, deduplica y poda el caché. |
| `server/inspect_bot.py` | Herramienta manual que conecta a Discord e imprime datos y embeds de los canales de dados, medios y música (incluidas las ediciones en música, con el resultado de `music_detect`). |
| `server/requirements.txt` | Lista de dependencias Python con versiones fijadas. |
| `server/pyproject.toml` | Archivo existente, vacío en la configuración actual. |
| `server/tests/smoke_test.py` | Pruebas de humo del caché y del backend con servidores/fixtures locales (incluidos CORS y el rechazo de `Origin` ajenos en `/api/events` y `/ws`); no inicia un bot conectado a Discord. |
| `server/tests/test_origin.py` | Tests unitarios de `origin_allowed` (orígenes aceptados y rechazados). |
| `server/tests/test_loop_handler.py` | Tests unitarios de `_ignore_proactor_reset` (qué excepciones del bucle se silencian y cuáles no). |
| `server/tests/test_music_detect.py` | Tests unitarios de `music_detect` y de la validación de `NOW_PLAYING` en `main.validate_event`. |
| `server/tests/test_voice_presence.py` | Tests unitarios de `voice_presence` y de la validación de `VOICE_STATE` en `main.validate_event`. |
| `server/.env` | Configuración local no versionada que debe contener el token y los IDs de canales. |

### Cliente (`client/`)

| Ruta | Responsabilidad |
|---|---|
| `client/src/App.tsx` | Aplicación del overlay: tipos y parseo de eventos, reconexión WebSocket, bucle de clips, HUD, cola multimedia y componentes visuales. |
| `client/src/main.tsx` | Punto de entrada; crea el root React y carga `App` y los estilos. |
| `client/src/index.css` | Lienzo transparente 1920 × 1080 (1080 × 656 con `html[data-layout='hud']`; fondo negro en `hud` y `gameplay`), tipografías, estilo LED/CRT y animaciones de entrada/salida. |
| `client/index.html` | Documento HTML de entrada y elemento `#root`. |
| `client/package.json` | Scripts `dev`, `build`, `preview` y dependencias del cliente. |
| `client/tsconfig.json` | Opciones TypeScript estrictas para el código cliente. |
| `client/tsconfig.node.json` | Configuración de TypeScript para la configuración de Vite. |
| `client/vite.config.ts` | Plugin React y servidor de desarrollo en `127.0.0.1:5173` (`strictPort`: falla si el puerto está ocupado, no busca otro). |
| `client/tailwind.config.js` | Rutas de contenido que Tailwind inspecciona para generar clases. |
| `client/postcss.config.js` | Plugins PostCSS: Tailwind CSS y Autoprefixer. |
| `client/dist/` | Salida generada por `npm run build`; FastAPI la sirve bajo `/overlay/` cuando existe. |

## 5. Configuración central

`server/config.py` resuelve `PROJECT_ROOT` a partir de la ubicación del propio archivo, por lo que las rutas de medios no dependen del directorio actual del proceso. Siempre carga `server/.env`.

| Variable | Obligatoria | Uso |
|---|---:|---|
| `DISCORD_TOKEN` | Sí para iniciar el bot | Token de autenticación del bot. |
| `DICE_CHANNEL_ID` | Sí para iniciar el listener | Canal que contiene las tiradas. El listener finaliza si falta o no es un entero distinto de cero. |
| `MEDIA_CHANNEL_ID` | No | Canal de medios. Si es cero o falta, se registra una advertencia y no se procesan medios. |
| `MUSIC_CHANNEL_ID` | No | Canal donde publica el bot de música. Si es cero o falta, se registra una advertencia y no se detectan canciones. |

Límites definidos en `server/config.py`: 60 MiB por descarga, 200 archivos de caché, 25 segundos por descarga y las extensiones admitidas para clips de fondo.

## 6. Interfaces HTTP y WebSocket

El backend de desarrollo se ejecuta en `127.0.0.1:8000` y el servidor de Vite en `127.0.0.1:5173`; ninguno es accesible desde la LAN. Los orígenes CORS permitidos para la interfaz web son `http://localhost:5173` y `http://127.0.0.1:5173` (solo GET/POST, sin credenciales). Como CORS no frena los WebSocket ni los POST «simples» (`text/plain`, sin preflight), `origin_allowed()` revisa además la cabecera `Origin` en `POST /api/events` y en `/ws`: se acepta si falta (bot, PowerShell, curl) o si coincide exactamente con `ALLOWED_ORIGINS` (los dos de Vite más `http://localhost:8000` y `http://127.0.0.1:8000`, el del overlay de producción); cualquier otro valor se rechaza. Así, una web ajena abierta en el navegador del equipo no puede inyectar eventos en el overlay.

| Método/ruta | Uso y respuesta |
|---|---|
| `GET /api/health` | Devuelve `{"status":"ok","ws_clients":N}`. Comprueba el proceso y cantidad de conexiones, no la conexión de Discord. |
| `GET /api/clips` | Devuelve `{"clips":["archivo.mp4", ...]}` ordenados alfabéticamente. Solo incluye archivos de extensiones admitidas en `media/Gameplay/`. |
| `POST /api/events` | Valida y distribuye un evento. Solo permite clientes localhost sin `Origin` ajeno; responde `403` para otro cliente o un origen no permitido, y `422` para evento inválido. |
| `WS /ws` | Recibe eventos JSON del cliente emisor y los reenvía a los demás clientes conectados. Mensajes inválidos se descartan. Un handshake con `Origin` no permitido se rechaza con `403` antes de aceptarlo (`Conexion WS rechazada` en el log). |
| `/media/{ruta}` | Sirve los archivos de `media/`, incluidos Gameplay, HUD y caché. |
| `/overlay/` | Sirve `client/dist/` si ese directorio existía al iniciar el backend. |

### Contrato de eventos

Tirada:

```json
{
  "type": "DICE_ROLL",
  "user": "Jugador",
  "dice_count": 5,
  "successes": 3
}
```

Medio:

```json
{
  "type": "NEW_MEDIA",
  "user": "Jugador",
  "url": "/media/cache/ab12.mp4",
  "media_type": "video"
}
```

Presencia de voz:

```json
{
  "type": "VOICE_STATE",
  "channel": "Mesa 1",
  "members": [
    { "id": "873352537313538108", "name": "Maik", "speaking": true }
  ]
}
```

Canción en reproducción:

```json
{ "type": "NOW_PLAYING", "title": "Artista - Canción" }
```

El backend exige que `title` sea un string con 1 a 120 caracteres tras aplicar `strip()` y reenvía un objeto reconstruido solo con `type` y `title`. El cliente vuelve a validarlo y lo recorta a 120 code points.

`channel` es `null` (con `members: []`) cuando el bot no está en voz. Los `id` son strings, porque JavaScript pierde precisión con snowflakes de 64 bits. A diferencia de los otros eventos, el backend valida `VOICE_STATE` estrictamente: `channel` es un string de hasta 100 caracteres o `null`; `members` es una lista de hasta 25 elementos con `id` numérico de hasta 20 dígitos, `name` de 1 a 32 caracteres y `speaking` estrictamente `bool`. El backend reenvía un objeto reconstruido solo con las claves conocidas.

El backend admite únicamente los tipos `DICE_ROLL`, `NEW_MEDIA`, `VOICE_STATE` y `NOW_PLAYING`. Para `NEW_MEDIA`, exige `url` de tipo string. La validación detallada de `dice_count`, `successes`, y del tipo multimedia ocurre en el cliente. `media_type` es opcional; el cliente lo infiere de la extensión cuando falta. La URL del medio puede ser relativa al backend o absoluta.

`/api/events` y `/ws` comparten la misma función de validación del backend. La ruta HTTP restringe el emisor a localhost; el WebSocket no implementa autenticación. No se debe exponer el servicio a una red no confiable.

## 7. Modelo de la interfaz

Todo el overlay está implementado en `client/src/App.tsx`:

- **`useOverlaySocket`** administra estados `connecting`, `open` y `closed`, parsea mensajes y reintenta cada tres segundos.
- **`GameplayLoop`** consulta `/api/clips`, reintenta si backend o clips no están disponibles y alterna dos elementos `<video>`. Mientras uno se reproduce, el otro precarga el clip siguiente para reducir pantallas negras. Con un solo clip activa el loop nativo. Los clips se arrancan con `play()` explícito (sin atributo `autoplay`) y la recarga tras el swap usa `setTimeout` (`SWAP_RELOAD_DELAY_MS`), no `requestAnimationFrame`, que se detiene cuando la página está oculta. Un vigilante (`visibilitychange`, evento `pause` del slot activo y un intervalo de `PLAYBACK_WATCHDOG_MS`) reanuda el video si el navegador lo pausa y fuerza el avance si `ended` no llegó a dispararse. `advancingRef` evita avances concurrentes.
- **`DiceHud`** superpone texto y valores segmentados sobre `Dados Hud.png`. Distingue la tirada con cero éxitos y refleja el estado del WebSocket.
- **`VoiceHud`** superpone sobre `voice.png` (abajo a la derecha, 240 px) el canal de voz y la lista de miembros con estética LED: `🔈` atenuado si el miembro calla y `🔊·` resaltado si habla, usando la variante de texto U+FE0E para que el icono tome el color LED. Muestra hasta `VOICE_MAX_ROWS` (10) filas, con quienes hablan primero, y `+N MORE` para el resto. Sin canal muestra `NO VOICE` / `STANDBY`.
- **`NowPlayingHud`** muestra el panel `NOW PLAYING:` + título (estética LED/CRT, `.np-panel` con `hud-screen` y `hud-scanlines`, sin imagen de chasis) a media altura, en el borde izquierdo, durante 8 s. La fase de salida va ligada al id del aviso, para que uno nuevo no arranque saliendo.
- **`useMediaQueue`** encola eventos de medios hasta una capacidad de 10 y coordina las fases `loading`, `in` y `out`.
- **`MediaElement`** presenta el medio como `<video>` o `<img>` y, ante un error, intenta el otro elemento una vez.
- **`MediaStage`** posiciona el medio y aplica una animación de entrada aleatoria. Su caja (`MEDIA_STAGE_CLASS`, 900 × 640 en x 720–1620, y 110–750) se eligió para no cruzarse con el HUD de voz (x ≥ 1640), el de dados (x ≤ 460) ni `NOW PLAYING` (x ≤ 640); si cambia el tamaño de alguno, hay que revisarla. El archivo permanece visible 8 segundos y sale con una animación de 700 ms; un medio que no carga en 10 segundos se descarta.
- **`App`** conecta el socket con el estado de tiradas y la cola de multimedia, y elige el layout.

### Layouts

`readLayout()` lee una sola vez, al cargar el módulo, el parámetro `?layout=`. Solo los literales `gameplay` y `hud` activan las ventanas de TikTok; cualquier otro valor da el horizontal. Antes del primer render fija `document.documentElement.dataset.layout`, que `index.css` usa para dimensionar `html`, `body` y `#root`, y `document.title` (`SuperRolScreen · Gameplay` o `SuperRolScreen · HUD`), para distinguir las ventanas al capturarlas. Los tres layouts comparten el mismo estado, socket y `handleEvent`; cada ventana abre su propio WebSocket y recibe todos los eventos, pero solo muestra los componentes de su layout.

- **Horizontal (por defecto, 1920 × 1080, transparente):** como se describe arriba. Los componentes reciben su posición por el prop `placement` (`className` + `style`), cuyo valor por defecto es el de este layout.
- **Gameplay (`?layout=gameplay`, 1920 × 1080):** `GameplayLoop`, `MediaStage` y `NowPlayingHud` en las mismas posiciones que en el horizontal, sin `DiceHud` ni `VoiceHud` y con fondo negro.
- **HUD (`?layout=hud`, 1080 × 656, el alto de la banda superior del lienzo vertical de TikTok):** `background.jpg` en cover sobre todo el lienzo (`HUD_BACKGROUND_STYLE`). `DiceHud` y `VoiceHud` se agrandan con `transform: scale()` (`HUD_DICE_SCALE` 1,15 y `HUD_VOICE_SCALE` 1,3), sin cambiar `HUD_WIDTH` ni `VOICE_HUD_WIDTH`, cuyos textos están calibrados en px. `centeredTop()` los centra en vertical según el alto real del marco (`DICE_FRAME_RATIO`, `VOICE_FRAME_RATIO`), a `HUD_SIDE_MARGIN` (24 px) de cada lado.
- En los tres layouts, `useFitScale(w, h)` escala el `<main>` con `transform: scale(min(1, innerWidth/w, innerHeight/h))` desde la esquina superior izquierda y se recalcula en `resize`. Así, si Windows recorta la ventana (barra de título o de tareas), el lienzo se reduce entero y no se corta. Nunca se amplía: `html`, `body` y `#root` miden lo mismo que el lienzo con `overflow: hidden` y recortarían un lienzo ampliado.

El tamaño y las posiciones del HUD (`HUD_WIDTH`, `HUD_SCREEN`, `HUD_STATUS_LED`, y `HUD_SCREEN_NOTCH_PX`, la muesca circular que deja visible la perilla en la esquina inferior izquierda de la pantalla; calibrados en % sobre `Dados Hud.png` de 408 × 385 px, por lo que deben recalibrarse si cambia el PNG), los del HUD de voz (`VOICE_HUD_WIDTH`, `VOICE_HUD_SCREEN` y `VOICE_HUD_SCREEN_RADIUS_PX`, el redondeo de la pantalla; calibrados sobre `voice.png` de 276 × 539 px, por lo que deben recalibrarse si cambia el PNG), los tiempos de reproducción y otras constantes de escena se configuran al inicio de `App.tsx`. Las animaciones asociadas están en `index.css`; `MEDIA_EXIT_MS` y la duración de `.ppt-out` deben permanecer sincronizadas, igual que `NOW_PLAYING_EXIT_MS` y la de `.np-out`.

## 8. Ejecución y validación

Las instrucciones de preparación y ejecución están en [README.md](./README.md). En resumen, se ejecutan backend, cliente Vite y listener como procesos separados en desarrollo; para OBS se compila el cliente y se sirve el build desde FastAPI.

`scripts/run.py` (vía `run.ps1`) orquesta esos procesos. En el modo `dev` lanza backend, Vite y bot (Vite se lanza con `node node_modules/vite/bin/vite.js`, no con `npm run dev`: `npm.cmd` corre dentro de `cmd.exe`, que ante `CTRL_BREAK` se queda preguntando «¿Terminar el trabajo por lotes?» y obligaba a forzar el cierre); en el modo `obs` ejecuta `npm run build` y lanza backend y bot. El bot y Vite solo arrancan cuando `/api/health` responde. En Windows cada hijo se crea en su propio grupo de procesos, y el apagado envía `CTRL_BREAK` y recurre a `taskkill /T /F` si el proceso no termina en 5 s. El backend se lanza con `--timeout-graceful-shutdown` (`BACKEND_GRACEFUL_SHUTDOWN_S`, 2 s): sin ese flag, uvicorn espera sin límite a las respuestas en curso, y las de video con Range (`206`) que el navegador deja a medias lo mantenían vivo hasta el `taskkill /F`. Al vencer el plazo escribe `ERROR: Cancel N running task(s), timeout graceful shutdown exceeded`, que es esperado. Si el backend o Vite terminan, se detiene todo; si termina el bot, no se reinicia y el resto sigue activo. `run.ps1` pasa su PID con `--parent-pid` (opción interna, oculta en `--help`). `run.py` abre al arrancar un handle `SYNCHRONIZE` a ese proceso (`open_parent`, con `ctypes`) y, si muere, aplica el mismo apagado que con Ctrl+C. Así cubre el cierre de una tarea de VS Code con la papelera, que mata solo `powershell.exe`. `log()` ignora los errores de escritura en una consola cerrada para no cortar el apagado. Los scripts `npm run …` llaman a `run.py` sin `run.ps1` y no tienen esta vigilancia. `window_specs(tiktok)` define las ventanas: sin `--tiktok`, una (`overlay`, 1920 × 1080, sin layout); con `--tiktok`, dos (`gameplay`, 1920 × 1080, `?layout=gameplay`, y `hud`, 1080 × 656, `?layout=hud`). `with_layout()` añade el parámetro. Sin `--window`, solo se muestran en el log esas URLs. Cada ventana usa su propio perfil de Edge (`edge-profile` para `overlay`, `edge-profile-<nombre>` para las demás), porque dos `msedge --app` con el mismo `--user-data-dir` se fusionan en un solo proceso y el segundo `Popen` termina enseguida, de modo que no se podría cerrar su ventana. `shutdown()` cierra todas las ventanas entre el bot y Vite. Con `--window`, una vez disponible el overlay (en `dev` espera a que Vite responda) abre Microsoft Edge en modo app, con perfil propio en `%LOCALAPPDATA%\SuperRolScreen\edge-profile` y flags que desactivan el throttling de ventanas ocultas u ocluidas (`--disable-backgrounding-occluded-windows`, `--disable-renderer-backgrounding`, `--disable-background-timer-throttling`, `--disable-features=CalculateNativeWinOcclusion,IntensiveWakeUpThrottling`). La ventana no es crítica y se cierra con `taskkill /T` (sin `CTRL_BREAK`, porque no tiene grupo de consola propio). El chequeo de puertos no usa `SO_REUSEADDR`, porque en Windows esa opción permite enlazar puertos ocupados.

Prueba de humo desde `server/`:

```powershell
.\.venv\Scripts\python.exe tests\smoke_test.py
```

La suite levanta una aplicación de fixtures HTTP en el puerto 8766 y un backend de prueba en 8765. Comprueba los formatos reconocidos, metadatos OpenGraph, candidatos fallidos, rechazo de HEIC, deduplicación, fan-out del WebSocket, descarte de mensajes inválidos, inyección HTTP y solicitudes Range. Requiere que ambos puertos estén libres. No sustituye una prueba con Discord real ni con OBS.

## 9. Puntos de extensión para futuras iteraciones

1. **Cambios de formato de tirada:** ajustar `parse_button_dice()` y añadir fixtures o casos de prueba para títulos observados con `inspect_bot.py`. No modificar el contrato `DICE_ROLL` a menos que también se actualicen la API, el cliente y sus pruebas.
2. **Nuevos formatos de eventos:** actualizar `ALLOWED_EVENT_TYPES` y `validate_event()` en `server/main.py`, añadir tipo y validación en `parseEvent()` de `App.tsx`, y decidir cómo la escena procesa el nuevo evento.
3. **Nuevas fuentes o formatos multimedia:** ampliar la extracción en `discord_listener.py`, la detección/resolución en `media_cache.py` y el fallback del cliente. Añadir pruebas que representen respuestas HTTP y bytes de contenido reales.
4. **Cambios de escena/HUD:** ajustar componentes y constantes en `App.tsx`, actualizar las reglas vinculadas en `index.css` y probar tanto Vite como el build servido bajo `/overlay/`.
5. **Más canales o eventos concurrentes:** mantener el orden y la deduplicación del procesador, revisar límites de cola y caducidad, y decidir explícitamente el comportamiento cuando backend o overlay no están disponibles.
6. **Exposición fuera de localhost:** requiere diseñar autenticación/autorización para HTTP y WebSocket, configuración de orígenes y manejo de secretos antes de cambiar el host de escucha. La comprobación de `Origin` solo protege frente a páginas del navegador; no autentica procesos locales ni clientes de la red.

## 10. Límites y validaciones pendientes

- La interpretación de tiradas depende de un embed externo con texto en inglés y estructura concreta.
- La detección de canciones depende del nombre del bot (`"flavi"`) y del texto de su embed; el parser se ajustó con un volcado real de FlaviBot (componentes V2); falta ver el panel con el bot real y en OBS.
- Los permisos y la configuración de intents deben estar correctamente habilitados en Discord. La función de voz requiere además el scope `applications.commands` y el permiso Connect.
- La detección de habla depende de voice-recv, una extensión no oficial que no implementa DAVE y está fijada a un commit concreto. Si Discord cambia el protocolo de voz, la detección puede dejar de funcionar aunque `/join` conecte.
- El HUD de voz se verificó en Edge (Vite y `/overlay/`) con eventos inyectados; falta validarlo con Discord real y en OBS, incluido que los iconos salgan monocromos en el navegador de OBS.
- La reproducción automática y transición de los clips debe verificarse en el entorno real de OBS, junto con la calibración visual de `HUD_SCREEN`.
- Algunos formatos o enlaces remotos pueden ser incompatibles con Chromium/OBS; el resolver tiene límites explícitos y no representa un navegador completo.
- Las fuentes del HUD dependen de CDNs externos y tienen fallbacks.
- Las ventanas de TikTok (`?layout=gameplay` y `?layout=hud`) se verificaron con el orquestador real (dos ventanas, títulos, perfiles y cierre) y su contenido en Edge headless con eventos inyectados; falta componerlas en TikTok Live Studio.
- El backend y el WebSocket están pensados para uso local; no incluyen autenticación.
- El contenido y los archivos de Discord son externos al repositorio y deben validarse manualmente en la integración real.
