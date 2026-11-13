# Análisis de software — SuperRolScreen

## 1. Propósito y alcance

SuperRolScreen es una aplicación local de overlay para streams de partidas de rol. Integra tres fuentes de información en una escena 1920 × 1080: videos de fondo almacenados localmente, eventos de tiradas del bot de dados de Discord y multimedia de un canal de Discord. La primera fase prioriza la reproducción continua de la escena, una comunicación sencilla entre procesos y la descarga en caché de medios externos que pueden no ser reproducibles directamente desde OBS.

El sistema se divide en:

1. **Bot de Discord** (`server/discord_listener.py`): interpreta mensajes y produce eventos.
2. **Backend local** (`server/main.py`): sirve archivos y API, mantiene clientes WebSocket y distribuye eventos.
3. **Overlay web** (`client/src/`): consume eventos, reproduce los clips y presenta el HUD y la multimedia.

El bot y el backend se ejecutan como procesos independientes. El overlay se sirve desde Vite durante el desarrollo y desde el backend como build estático para OBS.

## 2. Arquitectura y flujo de datos

```text
Discord
  ├─ canal de dados ──> parser de embed ──> DICE_ROLL ──┐
  └─ canal de medios ─> extracción/resolución/cache ──> NEW_MEDIA
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
Overlay React ──> GameplayLoop + DiceHud + MediaStage
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

### Entrega y reproducción de eventos

El listener mantiene una única conexión WebSocket saliente a `ws://localhost:8000/ws`. `OverlayLink` usa una cola de hasta 200 eventos, reintenta cada tres segundos y descarta los eventos que tengan más de 60 segundos al momento de enviarlos. El backend reenvía cada evento a todos los WebSocket conectados excepto al emisor. Los errores de envío provocan la desconexión del cliente fallido.

El cliente React valida y normaliza los mensajes recibidos, actualiza el HUD o agrega medios a una cola de capacidad 10. Solo hay un medio visible a la vez. Si una imagen/video no carga, el cliente prueba el elemento alternativo una vez; si tampoco carga, la descarta. La fase de carga expira a los 10 segundos.

## 3. Tecnologías y dependencias

### Backend y bot

- **Python 3.12**: runtime usado para probar el proyecto.
- **FastAPI**: API HTTP y endpoint WebSocket.
- **Uvicorn**: servidor ASGI usado para ejecutar FastAPI.
- **discord.py 2.x**: cliente del bot, sus eventos y modelos de mensajes/embeds.
- **aiohttp**: cliente HTTP asíncrono para resolver y descargar medios.
- **websockets**: conexión WebSocket saliente persistente del bot.
- **python-dotenv**: carga de variables desde `server/.env`.
- **Starlette StaticFiles**, incorporado vía FastAPI/Starlette: distribución de archivos y build del cliente; soporta solicitudes Range para video.

Las versiones instalables se fijan en `server/requirements.txt`. `server/pyproject.toml` existe actualmente sin configuración declarada.

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
| `package.json` | Manifiesto de nivel raíz sin dependencias; scripts `dev`, `dev:nobot` y `obs` que invocan el orquestador. |
| `scripts/run.py` | Orquestador (solo librería estándar): preflight, arranque ordenado con health check, logs unificados con prefijo, política de caídas y apagado del árbol de procesos. |
| `run.ps1` | Atajo de PowerShell para `scripts/run.py` con el Python del venv; propaga el código de salida. |
| `.vscode/tasks.json` | Tareas de VS Code que ejecutan `run.ps1` en los modos `dev`, `obs`, `--no-bot` y `--no-client`. |
| `media/Gameplay/` | Clips de fondo enumerados por el backend. Admite MP4, WebM, M4V y MOV. |
| `media/HUD/` | Recursos del HUD; el cliente espera `Dados Hud.png`. |
| `media/cache/` | Caché local de archivos descargados desde Discord. |

### Backend (`server/`)

| Ruta | Responsabilidad |
|---|---|
| `server/main.py` | Crea la aplicación FastAPI, configura CORS, monta `/media` y opcionalmente `/overlay`, implementa HTTP, WebSocket y validación básica de eventos. |
| `server/config.py` | Carga `server/.env`, centraliza rutas, valores de Discord, extensiones y límites del caché. |
| `server/discord_listener.py` | Implementa `OverlayBot`, `OverlayLink`, el parser de tiradas, candidatos multimedia, reintentos y emisión de eventos. |
| `server/media_cache.py` | Detecta tipos por magic bytes, extrae candidatos OpenGraph/Twitter y descarga, deduplica y poda el caché. |
| `server/inspect_bot.py` | Herramienta manual que conecta a Discord e imprime datos y embeds del canal de dados. |
| `server/requirements.txt` | Lista de dependencias Python con versiones fijadas. |
| `server/pyproject.toml` | Archivo existente, vacío en la configuración actual. |
| `server/tests/smoke_test.py` | Pruebas de humo del caché y del backend con servidores/fixtures locales; no inicia un bot conectado a Discord. |
| `server/.env` | Configuración local no versionada que debe contener el token y los IDs de canales. |

### Cliente (`client/`)

| Ruta | Responsabilidad |
|---|---|
| `client/src/App.tsx` | Aplicación del overlay: tipos y parseo de eventos, reconexión WebSocket, bucle de clips, HUD, cola multimedia y componentes visuales. |
| `client/src/main.tsx` | Punto de entrada; crea el root React y carga `App` y los estilos. |
| `client/src/index.css` | Lienzo transparente 1920 × 1080, tipografías, estilo LED/CRT y animaciones de entrada/salida. |
| `client/index.html` | Documento HTML de entrada y elemento `#root`. |
| `client/package.json` | Scripts `dev`, `build`, `preview` y dependencias del cliente. |
| `client/tsconfig.json` | Opciones TypeScript estrictas para el código cliente. |
| `client/tsconfig.node.json` | Configuración de TypeScript para la configuración de Vite. |
| `client/vite.config.ts` | Plugin React y servidor de desarrollo en puerto 5173. |
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

Límites definidos en `server/config.py`: 60 MiB por descarga, 200 archivos de caché, 25 segundos por descarga y las extensiones admitidas para clips de fondo.

## 6. Interfaces HTTP y WebSocket

El backend de desarrollo se ejecuta en `127.0.0.1:8000`. Los orígenes CORS permitidos para la interfaz web son `http://localhost:5173` y `http://127.0.0.1:5173`.

| Método/ruta | Uso y respuesta |
|---|---|
| `GET /api/health` | Devuelve `{"status":"ok","ws_clients":N}`. Comprueba el proceso y cantidad de conexiones, no la conexión de Discord. |
| `GET /api/clips` | Devuelve `{"clips":["archivo.mp4", ...]}` ordenados alfabéticamente. Solo incluye archivos de extensiones admitidas en `media/Gameplay/`. |
| `POST /api/events` | Valida y distribuye un evento. Solo permite clientes localhost; responde `403` para otro cliente y `422` para evento inválido. |
| `WS /ws` | Recibe eventos JSON del cliente emisor y los reenvía a los demás clientes conectados. Mensajes inválidos se descartan. |
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

El backend admite únicamente los tipos `DICE_ROLL` y `NEW_MEDIA`. Para `NEW_MEDIA`, exige `url` de tipo string. La validación detallada de `dice_count`, `successes`, y del tipo multimedia ocurre en el cliente. `media_type` es opcional; el cliente lo infiere de la extensión cuando falta. La URL del medio puede ser relativa al backend o absoluta.

`/api/events` y `/ws` comparten la misma función de validación del backend. La ruta HTTP restringe el emisor a localhost; el WebSocket no implementa autenticación. No se debe exponer el servicio a una red no confiable.

## 7. Modelo de la interfaz

Todo el overlay está implementado en `client/src/App.tsx`:

- **`useOverlaySocket`** administra estados `connecting`, `open` y `closed`, parsea mensajes y reintenta cada tres segundos.
- **`GameplayLoop`** consulta `/api/clips`, reintenta si backend o clips no están disponibles y alterna dos elementos `<video>`. Mientras uno se reproduce, el otro precarga el clip siguiente para reducir pantallas negras. Con un solo clip activa el loop nativo.
- **`DiceHud`** superpone texto y valores segmentados sobre `Dados Hud.png`. Distingue la tirada con cero éxitos y refleja el estado del WebSocket.
- **`useMediaQueue`** encola eventos de medios hasta una capacidad de 10 y coordina las fases `loading`, `in` y `out`.
- **`MediaElement`** presenta el medio como `<video>` o `<img>` y, ante un error, intenta el otro elemento una vez.
- **`MediaStage`** posiciona el medio y aplica una animación de entrada aleatoria. El archivo permanece visible 8 segundos y sale con una animación de 700 ms; un medio que no carga en 10 segundos se descarta.
- **`App`** conecta el socket con el estado de tiradas y la cola de multimedia.

El tamaño y las posiciones del HUD (`HUD_WIDTH`, `HUD_SCREEN`, `HUD_STATUS_LED`), los tiempos de reproducción y otras constantes de escena se configuran al inicio de `App.tsx`. Las animaciones asociadas están en `index.css`; `MEDIA_EXIT_MS` y la duración de `.ppt-out` deben permanecer sincronizadas.

## 8. Ejecución y validación

Las instrucciones de preparación y ejecución están en [README.md](./README.md). En resumen, se ejecutan backend, cliente Vite y listener como procesos separados en desarrollo; para OBS se compila el cliente y se sirve el build desde FastAPI.

`scripts/run.py` (vía `run.ps1`) orquesta esos procesos. En el modo `dev` lanza backend, Vite y bot; en el modo `obs` ejecuta `npm run build` y lanza backend y bot. El bot y Vite solo arrancan cuando `/api/health` responde. En Windows cada hijo se crea en su propio grupo de procesos, y el apagado envía `CTRL_BREAK` y recurre a `taskkill /T /F` si el proceso no termina en 5 s. Si el backend o Vite terminan, se detiene todo; si termina el bot, no se reinicia y el resto sigue activo. El chequeo de puertos no usa `SO_REUSEADDR`, porque en Windows esa opción permite enlazar puertos ocupados.

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
6. **Exposición fuera de localhost:** requiere diseñar autenticación/autorización para HTTP y WebSocket, configuración de orígenes y manejo de secretos antes de cambiar el host de escucha. CORS por sí solo no autentica clientes WebSocket.

## 10. Límites y validaciones pendientes

- La interpretación de tiradas depende de un embed externo con texto en inglés y estructura concreta.
- Los permisos y la configuración de intents deben estar correctamente habilitados en Discord.
- La reproducción automática y transición de los clips debe verificarse en el entorno real de OBS, junto con la calibración visual de `HUD_SCREEN`.
- Algunos formatos o enlaces remotos pueden ser incompatibles con Chromium/OBS; el resolver tiene límites explícitos y no representa un navegador completo.
- Las fuentes del HUD dependen de CDNs externos y tienen fallbacks.
- El backend y el WebSocket están pensados para uso local; no incluyen autenticación.
- El contenido y los archivos de Discord son externos al repositorio y deben validarse manualmente en la integración real.
