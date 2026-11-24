# Ficha — Escalar el layout horizontal al viewport

## Contexto mínimo

El overlay (`client/src/App.tsx`) tiene tres layouts. `gameplay` (1920 × 1080) y `hud` (1080 × 656) ya se escalan al viewport con `useFitScale(w, h)`. Ese hook calcula `min(innerWidth / w, innerHeight / h)` y se recalcula en `resize`. El `<main>` aplica `transform: scale(...)` con `transformOrigin: 'top left'` (helper `fitStyle`). El layout **horizontal** (el de por defecto, sin `?layout=`) **no escala**: su `<main>` es fijo (`h-[1080px] w-[1920px]`). Si la ventana de Edge (`--window`) o la fuente de navegador tienen menos de 1080 px de alto, el HUD de dados y el de voz, anclados abajo, se cortan.

Pendiente de origen: `docs/pendientes.md`, entrada del 2026-11-15.

## Objetivo

El layout horizontal se escala entero al viewport igual que `gameplay`: si la ventana es más pequeña que 1920 × 1080, se ve completo y reducido, sin cortes. A 1920 × 1080 exactos (OBS), la escala es 1 y el resultado es idéntico al actual. Debe seguir **transparente**.

## Diseño

1. En `App()` (cerca de la línea 1028), `useFitScale` ya se llama de forma incondicional. Deja la llamada como está: para el horizontal ya recibe `GAMEPLAY_W × GAMEPLAY_H` (1920 × 1080). Actualiza el comentario «el layout horizontal no usa la escala», que dejará de ser cierto.
2. En el `return` final (layout horizontal), sustituye `className="relative h-[1080px] w-[1920px] overflow-hidden"` por `className="relative overflow-hidden"` con `style={fitStyle(GAMEPLAY_W, GAMEPLAY_H)}`. **No** añadas `bg-black` ni ningún otro fondo: el horizontal debe seguir transparente.
3. Si existe una constante con nombre más claro para 1920 × 1080 (p. ej. `LANDSCAPE_W/H`), úsala; si no, reutiliza `GAMEPLAY_W/H` y **no** crees constantes nuevas.
4. Actualiza el comentario de `useFitScale` o de la sección de layouts si dice que solo se aplica a TikTok.
5. **No** cambies `index.css`, `index.html` (el `bg-black` del `body` es otro pendiente), ni los componentes (`DiceHud`, `VoiceHud`, `MediaStage`, etc.), ni `scripts/run.py`.

## Archivos permitidos

- `client/src/App.tsx`

## Fuera de alcance

- `client/index.html` y su `bg-black` (pendiente del 2026-11-19).
- El solapamiento de `MediaStage` con el HUD de voz (pendiente del 2026-11-17).
- `docs/pendientes.md`, `README.md`, `ANALISIS_DE_SOFTWARE.md` (los actualiza Claude).
- Cualquier archivo de `server/` o `scripts/`.

## Criterios de aceptación

### (a) Los verifica Copilot

1. `cd client; npm run build` termina sin errores (incluye `tsc`). Pega las últimas líneas de la salida.
2. `git diff --stat` muestra solo `client/src/App.tsx`. Pega la salida **real**, copiada de la terminal.
3. `git diff client/src/App.tsx` muestra que el `<main>` horizontal usa `fitStyle(...)`, que no tiene clases de fondo (`bg-*`) y que se actualizaron los comentarios. Pega el diff.
4. `grep -n "h-\[1080px\] w-\[1920px\]" client/src/App.tsx` no devuelve nada.

### (b) Los verifican Claude y el usuario

1. En Edge headless con el overlay a 1920 × 1080, escala 1 y HUD completo.
2. En Edge headless a una ventana más pequeña (p. ej. 1600 × 800), el lienzo se ve entero, reducido desde la esquina superior izquierda, con los HUD de dados y de voz completos.
3. El `<main>` horizontal sigue transparente (sin clases ni estilos de fondo).
4. `?layout=gameplay` y `?layout=hud` siguen igual.
5. Usuario: `.\run.ps1 --window` con la ventana redimensionada a mano y en OBS a 1920 × 1080.

## Instrucciones para Copilot

- Máximo **3 intentos** por error. Si no lo resuelves, para y anótalo en el Reporte.
- No dejes procesos largos corriendo (Vite, backend, `run.ps1`). `npm run build` termina solo y sí puedes ejecutarlo.
- **No hagas commits.** No edites `docs/pendientes.md` ni ningún archivo fuera de «Archivos permitidos», salvo la sección «Reporte» de esta ficha.
- Si te bloqueas, para y anótalo.
- Completa la sección «Reporte» con evidencia: la salida **real** de los comandos, copiada y sin editar. Escribe «no probado» si no pudiste verificar algo. No pongas ✅ sin evidencia. No inventes salidas ni líneas de log.
- La tarea no está terminada si `npm run build` no se ejecutó y su salida no está pegada.

## Reporte

*(Vacío. Copilot no lo completó: al entregar, esta ficha había sido sustituida por la versión de HEAD, la de la tarea anterior, sin reporte nuevo. Claude la reconstruyó.)*

## Revisión (Claude)

**Veredicto:** aprobado tras una corrección de Claude. El cambio de Copilot en el código era correcto y mínimo, pero el proceso volvió a incumplir la ficha.

**Diferencias entre el reporte y el diff:**
- No hay reporte. `docs/copilot_instructions.md` quedó idéntico a HEAD (`git diff --quiet HEAD` sin cambios), así que la ficha se perdió.
- `git diff --stat`: `client/src/App.tsx | 4 ++--` y `docs/pendientes.md | 2 +-`. Copilot **tachó el pendiente** en `pendientes.md`, que estaba prohibido.
- `App.tsx`: el `<main>` horizontal pasó a `className="relative overflow-hidden" style={fitStyle(GAMEPLAY_W, GAMEPLAY_H)}`, sin fondo, y se actualizó el comentario del hook incondicional. Cumple los puntos 1, 2 y 3 del diseño.

**Verificación de Claude:**
- `npm run build`: `✓ built in 1.08s`, sin errores de `tsc`.
- `grep "h-\[1080px\] w-\[1920px\]"`: sin resultados.

**Corrección de Claude:** `useFitScale` ampliaba el lienzo si el viewport era mayor (escala 1,029 con una ventana headless de 2000 × 1250). Como `html`, `body` y `#root` miden lo mismo que el lienzo con `overflow: hidden`, el lienzo ampliado se recortaba por la derecha y por abajo. En la captura a 2200 × 1400, el HUD de voz quedó cortado casi entero. Era un fallo previo de `gameplay` y `hud` que este cambio extendía al horizontal. Ahora la escala es `Math.min(1, innerWidth / w, innerHeight / h)`: solo reduce, como ya decía el README («si la ventana es más pequeña que su lienzo»).

**Verificación integrada (b), una ejecución** (backend en `127.0.0.1:8000` con `client/dist`, Edge headless, `<main>` leído con `--dump-dom`; el viewport headless es unos 92 px más bajo que `--window-size`):
```
2200,1400 horizontal: transform: scale(1)          -> lienzo entero arriba a la izquierda, HUD completos
1600,800  horizontal: transform: scale(0.655556)   -> lienzo entero reducido, HUD de dados y de voz completos
1600,800  gameplay:   transform: scale(0.655556)   (bg-black, igual que antes)
800,600   hud:        transform: scale(0.718519)   -> HUD completo
1300,900  hud:        transform: scale(1)
```
El `<main>` horizontal no tiene clases ni estilos de fondo (`class="relative overflow-hidden"`). El negro visible en headless viene del `bg-black` de `<body>` (pendiente del 2026-11-19).

**Pendientes:** el usuario prueba `.\run.ps1 --window` cambiando el tamaño de la ventana a mano y la fuente de OBS a 1920 × 1080 (escala 1, sin cambios visibles). Con un viewport mayor que el lienzo, el overlay queda arriba a la izquierda y no se centra (decisión deliberada).
