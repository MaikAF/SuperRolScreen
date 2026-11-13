# SuperRolScreen

SuperRolScreen es un overlay de **1920 × 1080** para partidas de rol transmitidas con OBS. Combina un fondo de video en bucle con un HUD de tiradas y una escena para mostrar imágenes, GIFs y videos que se publican en Discord.

## Funciones

- Reproduce en bucle los videos guardados en `media/Gameplay/`.
- Muestra en el HUD el jugador, la reserva de dados y los éxitos de las tiradas detectadas en un canal de Discord.
- Proyecta adjuntos y medios compartidos en otro canal de Discord, incluidos enlaces compatibles con metadatos OpenGraph. Los medios se ponen en cola y aparecen con animaciones.
- Indica el estado de conexión con el backend mediante el LED del HUD.
- Permite probar eventos manuales desde el propio equipo sin publicar mensajes en Discord.

## Requisitos

- Windows y PowerShell (los comandos de esta guía usan esas herramientas).
- Python 3.12 y Node.js 22; son las versiones usadas para probar el proyecto.
- Un bot de Discord con **Message Content Intent** activado en el Developer Portal y permisos para ver los canales y leer su historial.
- OBS Studio con una fuente de navegador.
- Conexión a Internet para que el bot acceda a Discord y para descargar las tipografías externas del HUD. Sin acceso a los CDN de fuentes se utilizan fuentes de reserva.

## Configuración de Discord y archivos

1. Crea `server/.env` con el token del bot y los IDs de los canales:

   ```dotenv
   DISCORD_TOKEN=token_del_bot
   DICE_CHANNEL_ID=123456789012345678
   MEDIA_CHANNEL_ID=123456789012345679
   ```

   `DICE_CHANNEL_ID` es obligatorio. `MEDIA_CHANNEL_ID` es opcional; si no se configura, no se procesarán medios. Activa el modo desarrollador de Discord para copiar los IDs de los canales. No compartas ni subas el token; si se expone, regénéralo en Discord.

2. Coloca los videos de fondo en `media/Gameplay/`. Se admiten `.mp4`, `.webm`, `.m4v` y `.mov`; para OBS se recomienda MP4 con H.264.
3. Comprueba que exista el marco gráfico `media/HUD/Dados Hud.png`.

El bot lee `server/.env` independientemente de la carpeta desde la que se inicie. El directorio `media/cache/` se crea automáticamente y se usa para los medios descargados desde Discord.

## Instalación

Ejecuta estos comandos una vez desde PowerShell:

```powershell
cd server
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt

cd ..\client
npm ci
```

## Inicio rápido (un solo comando)

Desde la raíz del repositorio (o desde cualquier carpeta, indicando la ruta del script):

```powershell
.\run.ps1              # desarrollo: backend + overlay Vite + bot
.\run.ps1 obs          # compila el overlay y levanta backend + bot (OBS en /overlay/)
.\run.ps1 --no-bot     # sin bot de Discord, para pruebas con /api/events
.\run.ps1 --no-client  # solo backend + bot (sin Vite)
```

El orquestador (`scripts/run.py`) comprueba antes de arrancar que existan el venv, `client/node_modules` y `server/.env`, y que los puertos 8000 y 5173 estén libres. Arranca el backend, espera a que `/api/health` responda y después lanza Vite y el bot. Los registros de los tres procesos aparecen en la misma consola con los prefijos `[backend]`, `[client]` y `[bot]`. Pulsa **Ctrl+C** para detenerlo todo. Si el backend o Vite se cierran, se detiene todo; si se cae el bot, el overlay sigue activo.

Si PowerShell bloquea la ejecución de scripts, usa `powershell -ExecutionPolicy Bypass -File .\run.ps1` en lugar de cambiar la política global. También están disponibles `npm run dev`, `npm run dev:nobot` y `npm run obs` desde la raíz, y las tareas **SuperRol: …** de VS Code (*Terminal → Ejecutar tarea*).

## Iniciar en modo desarrollo (manual)

Si prefieres controlar cada proceso por separado, abre tres terminales PowerShell y ejecuta los comandos en el orden indicado:

**1. Backend** (desde `server/`):

```powershell
.\.venv\Scripts\python.exe -m uvicorn main:app --host 127.0.0.1 --port 8000
```

**2. Overlay web** (desde `client/`):

```powershell
npm run dev
```

**3. Bot de Discord** (desde `server/`):

```powershell
.\.venv\Scripts\python.exe discord_listener.py
```

Abre `http://localhost:5173` para ver el overlay. El LED del HUD muestra el estado del enlace con el backend: cian indica conectado, ámbar indica conexión en curso y rojo indica desconectado. El cliente intenta reconectarse al backend y el bot reintenta su conexión WebSocket.

## Usar con OBS

Para servir el overlay desde el backend, genera primero el build:

```powershell
cd client
npm run build
```

Con `client/dist/` disponible, inicia el backend y el bot como se indicó arriba. En OBS agrega una **fuente de navegador** con la URL `http://localhost:8000/overlay/` y dimensiones de **1920 × 1080**. La salida tiene fondo transparente. Si no quieres reproducir audio desde el navegador, desactiva el audio de esa fuente o configúrala según tu mezcla de OBS.

El backend de ejemplo escucha en `127.0.0.1`. Mantén ese enlace local y no expongas el puerto 8000 a redes externas.

## Prueba manual sin Discord

Con el backend iniciado, envía una tirada de prueba desde otra terminal:

```powershell
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/api/events -ContentType 'application/json' `
  -Body '{"type":"DICE_ROLL","user":"Tester","dice_count":6,"successes":2}'
```

También se pueden inyectar eventos `NEW_MEDIA` con una URL de imagen o video accesible desde el backend. La API de inyección solo acepta solicitudes desde localhost.

## Pruebas automatizadas

Desde `server/`, ejecuta:

```powershell
.\.venv\Scripts\python.exe tests\smoke_test.py
```

Las pruebas usan los puertos locales 8765 y 8766, y comprueban el procesamiento de medios, el backend, el WebSocket y las solicitudes HTTP Range. No necesitan iniciar sesión en Discord; asegúrate de que esos puertos estén libres.

## Ayuda

- **El LED está rojo:** confirma que Uvicorn está activo en el puerto 8000 y que el overlay se abrió en `http://localhost:5173` o en `/overlay/`.
- **No aparece el fondo:** revisa que haya videos con extensiones admitidas en `media/Gameplay/`.
- **No aparece el HUD:** comprueba `media/HUD/Dados Hud.png`, el canal configurado y los permisos del bot. El parser de tiradas depende del título del embed del bot de dados.
- **No aparecen medios de Discord:** confirma `MEDIA_CHANNEL_ID`, permisos del bot y los registros de la terminal del listener. Los archivos grandes, HEIC y formatos no reconocidos no se muestran.
- **La fuente de navegador no muestra nada:** genera `client/dist/`, verifica la URL `/overlay/` y confirma que backend y build correspondan a la misma versión.

Para entender los módulos, el contrato de eventos y la estructura del proyecto, consulta [ANALISIS_DE_SOFTWARE.md](./ANALISIS_DE_SOFTWARE.md).
