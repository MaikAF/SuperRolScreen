# Ficha de tarea — Nuevo marco del HUD de voz (`voice.png`)

Fecha: 2026-11-17 · Iteración 1 · Rama `tiktok`

> La ficha anterior (layout TikTok) está en el historial de git (commit `282ace0`).

## 1. Contexto mínimo

`VoiceHud` (en `client/src/App.tsx`) dibuja una imagen de marco y encima, posicionada en %, una "pantalla" LED (`.hud-screen`) con el canal y los miembros. Se usa en los dos layouts: horizontal (240 px de ancho, abajo a la derecha) y TikTok (`?layout=tiktok`, mismo componente con `transform: scale(TIKTOK_VOICE_SCALE = 1.3)`).

El usuario sustituyó el marco:

| | Antes | Ahora |
|---|---|---|
| Archivo | `media/HUD/Voice.jpg` (borrado) | `media/HUD/voice.png` (minúsculas) |
| Tamaño | 736 × 1439 | **276 × 539** (RGBA, esquinas exteriores transparentes) |
| Proporción alto/ancho | 1,9552 | 1,9529 |

Hoy el cliente sigue pidiendo `/media/HUD/Voice.jpg` → **404, el HUD de voz sale sin marco**.

Medición de la pantalla negra de `voice.png` (Claude, decodificando el PNG; píxeles con RGB < 20 y alfa > 200, recorrido contiguo desde el centro):

- x: 25 … 248 (224 px) · y: 138 … 437 (300 px).
- Esquinas redondeadas: la fila 138 empieza en x = 34 y la 437 en x = 33 → radio ≈ 9 px nativos ≈ **8 px** a 240 px de ancho.

## 2. Objetivo

Que el HUD de voz use `voice.png` y que la pantalla LED coincida con la pantalla negra del nuevo marco, sin sobresalir ni dejar huecos visibles, en ambos layouts.

## 3. Diseño

Todo en el bloque de constantes al inicio de `client/src/App.tsx`, más un estilo en `VoiceHud`:

1. `VOICE_FRAME_URL` → `` `${API_BASE}/media/HUD/voice.png` `` (minúsculas exactas, igual que el archivo).
2. `VOICE_HUD_SCREEN` → `{ left: 9.06, top: 25.6, width: 81.16, height: 55.66 }` (25/276, 138/539, 224/276, 300/539). Actualiza el comentario: «Pantalla negra de voice.png (276 × 539), en %. Recalibrar si cambia el PNG.»
3. Nueva constante `VOICE_HUD_SCREEN_RADIUS_PX = 8` y aplícala **solo** en el `div.hud-screen` de `VoiceHud` como `borderRadius` inline. No cambies `.hud-screen` en `index.css` (la comparte el HUD de dados).
4. `VOICE_FRAME_RATIO` → `539 / 276`, y actualiza el comentario de la línea ~70 (`voice.png 276x539`).
5. Actualiza el comentario de `VOICE_HUD_WIDTH` (`≈ 240 × 469 px`, se mantiene).
6. **No cambies** `VOICE_HUD_WIDTH` (240), `TIKTOK_VOICE_SCALE` (1.3) ni tamaños de texto: la proporción del marco es prácticamente la misma, así que la geometría de ambos layouts no cambia (240 × 469 y ≈ 312 × 609).

Nota: a 1.3× el PNG (276 px) se muestra a 312 px, un 13 % ampliado. Es aceptable; no intentes compensarlo.

## 4. Archivos

- **Permitido:** `client/src/App.tsx` (solo las constantes de voz indicadas y el `style` del `div.hud-screen` dentro de `VoiceHud`).
- **Fuera de alcance:** `client/src/index.css`, `media/` (no renombrar ni convertir imágenes), `server/`, `scripts/`, el HUD de dados, `client/dist/` (no hace falta recompilarlo para la entrega), la documentación (la actualiza Claude).

## 5. Criterios de aceptación

### (a) Los verifica Copilot

1. `grep -rn "Voice.jpg\|1439\|736" client/src` no devuelve nada.
2. `grep -n "voice.png" client/src/App.tsx` muestra la URL y los comentarios actualizados.
3. `cd client; npx tsc --noEmit` termina sin errores.
4. `cd client; npm run build` termina sin errores (verifica que compila; no incluyas `client/dist` en el reporte como cambio intencional).
5. Con el backend levantado brevemente, `Invoke-WebRequest http://127.0.0.1:8000/media/HUD/voice.png -Method Head` devuelve 200 y `Content-Type: image/png`. Detén el backend al terminar. Si no puedes levantarlo, escribe «no probado».

### (b) Los verifican Claude o el usuario

1. Overlay horizontal (`http://localhost:5173`): el marco se ve, la pantalla LED cae dentro de la pantalla negra sin bordes negros visibles ni desborde sobre el metal, con esquinas que siguen el redondeo.
2. Overlay TikTok (`?layout=tiktok`): igual, y el HUD de voz sigue dentro de la banda inferior sin solaparse con el de dados.
3. Con un `VOICE_STATE` inyectado de 12 miembros: 9 filas + `+3 MORE` y el pie caben dentro de la pantalla.
4. En `STANDBY` se ve `NO VOICE_` y `STANDBY` dentro de la pantalla.

## 6. Instrucciones para Copilot

- Máximo 3 intentos por error; si al tercero sigue fallando, para y anótalo.
- No dejes procesos largos corriendo (backend, Vite): arráncalos solo para la comprobación y ciérralos.
- No hagas commits.
- Si te bloqueas, para y anótalo en «Desviaciones / bloqueos».
- Completa la sección «Reporte» con evidencia: salida real de los comandos, «no probado» si no pudiste verificar algo, y ningún ✅ sin evidencia.

## Reporte (Copilot)

### Archivos tocados

### Valores finales

### Evidencia de criterios (a)

### Desviaciones del diseño / bloqueos

### Notas para la revisión

## Revisión (Claude)

Fecha: 2026-11-17 · **Veredicto: APROBADO.** El código cumple el diseño y no hizo falta corregir nada. El reporte de Copilot está vacío.

### Diferencias entre el reporte y el diff

- La sección «Reporte (Copilot)» quedó sin rellenar: no hay archivos, valores ni evidencia. Por eso Claude ejecutó todos los criterios (a).
- `git diff --stat` en código: solo `client/src/App.tsx` (+8 / −6). Dentro del alcance. `docs/claude.md` lo cambió el usuario (tarea nueva). `Voice.jpg` borrado y `voice.png` sin rastrear son los cambios de imagen del usuario.
- El diff aplica exactamente los puntos 1–5 del diseño: URL `voice.png`, `VOICE_HUD_SCREEN = {9.06, 25.6, 81.16, 55.66}`, `VOICE_HUD_SCREEN_RADIUS_PX = 8` inline solo en la pantalla de voz, `VOICE_FRAME_RATIO = 539 / 276` y los comentarios. No se tocaron `VOICE_HUD_WIDTH`, `TIKTOK_VOICE_SCALE` ni `index.css`.

### Seguridad y buenas prácticas

Sin observaciones: el cambio son constantes y un estilo inline. No añade secretos, entradas, dependencias ni cambios de red o CORS.

### Correcciones de Claude

Ninguna en el código. Se recompiló `client/dist/` (está ignorado por git) para que `/overlay/` sirva la versión nueva.

### Evidencia (a), ejecutada por Claude

1. `grep -rn "Voice.jpg\|1439\|736" client/src` → sin coincidencias (exit 1).
2. `grep -n "voice.png" client/src/App.tsx` → líneas 12, 44, 46 y 71.
3. `npx tsc --noEmit` → exit 0.
4. `npm run build` → `✓ built in 1.10s`, exit 0.
5. `curl -sI http://127.0.0.1:8000/media/HUD/voice.png` → `HTTP/1.1 200 OK`, `content-type: image/png`. El backend se detuvo después.

### Verificación integrada (b), ejecutada una vez

Backend real y Edge headless por CDP sobre `/overlay/`. Los `VOICE_STATE` se inyectaron con `POST /api/events`. Se capturaron 4 vistas más dos ampliaciones del HUD de voz a 2×.

1. **Horizontal:** HUD de voz en x 1640, y 595, 240 × 469, y la imagen carga (`naturalWidth` 276). La pantalla LED queda dentro de la pantalla negra, sin borde negro visible ni desborde sobre el metal, y las esquinas siguen el redondeo. **OK.**
2. **TikTok:** voz en x 744–1056, y 1287–1896, 312 × 609, dentro de la banda inferior (1264–1920). Dados en x 24–507, sin solape. **OK.**
3. **12 miembros:** canal, 9 filas (los 2 que hablan primero), `+3 MORE` y el pie `12 IN VOICE · 2 TALKING` caben en la pantalla en los dos layouts. **OK.**
4. **STANDBY:** `NO VOICE_` y `STANDBY` dentro de la pantalla. **OK.**

### Pendientes

- Prueba manual del usuario en OBS y TikTok Live Studio.
- El marco sigue llevando la marca de terceros (logo y rótulos). Es un pendiente que ya existía y se actualizó en `pendientes.md`.
- `voice.png` se amplía un 13 % en el layout TikTok, así que se ve algo blanda (anotado en `pendientes.md`).
- Copilot volvió a entregar sin reporte (anotado en `pendientes.md`).
