# Ficha: recalibrar el HUD de dados al nuevo PNG

## Contexto mínimo

- El overlay (1920 × 1080) está en `client/src/App.tsx`. `DiceHud` dibuja `media/HUD/Dados Hud.png` con un ancho fijo `HUD_WIDTH = 420` px y coloca encima la pantalla digital (`HUD_SCREEN`) y el LED de conexión (`HUD_STATUS_LED`). Las posiciones están en **% relativo a la imagen**.
- En el commit `a4ac19e` el PNG pasó de **408 × 612** a **408 × 385** px. Las constantes siguen calibradas para el PNG anterior. Por eso la pantalla digital queda desplazada hacia abajo, sobre la parte inferior del chasis, y el LED no coincide con el indicador STATUS.
- Medidas tomadas del PNG nuevo por Claude, en píxeles de la imagen original (408 × 385):
  - Zona negra de la pantalla: x **80–227**, y **53–258** (148 × 206 px). Tiene esquinas ligeramente redondeadas.
  - La esquina **inferior izquierda** de la zona negra tiene una muesca circular por la perilla: el chasis invade un cuarto de círculo con centro ≈ (80, 260) y radio ≈ **28 px**. El resto de la zona es rectangular.
  - LED STATUS (cian): bbox x 251–257, y 75–80. El centro está en ≈ **62.3 % / 20.1 %**.
  - Hay márgenes transparentes en el PNG. Lo opaco ocupa x 36–363 e y 9–377, así que quedan ≈ 8 px transparentes abajo (≈ 8 px renderizados a 420 de ancho).

## Objetivo

1. Que la pantalla digital cubra exactamente la zona negra del dispositivo, sin dejar negro del PNG visible en los bordes y sin tapar la perilla de la esquina inferior izquierda.
2. Que el LED quede sobre el indicador STATUS.
3. Que el HUD quede abajo a la izquierda, sin tocar el borde inferior del lienzo, con una separación visible de **≈ 24 px** entre el borde inferior del chasis y el borde del lienzo 1920 × 1080.

## Diseño

En `client/src/App.tsx` (bloque CONFIG y `DiceHud`):

- `HUD_SCREEN = { left: 19.4, top: 13.6, width: 36.7, height: 53.9 }`. Son las medidas reales (19.61 / 13.77 / 36.27 / 53.51 %) con ≈ 1 px de solapamiento por lado sobre el bisel, para que no se vea el borde negro del PNG. Actualiza el comentario: "calibrado para Dados Hud.png 408×385".
- `HUD_STATUS_LED = { left: 62.3, top: 20.1 }`.
- Posición del `<aside>`: cambia `bottom-[24px]` a `bottom-[16px]`. Con los ≈ 8 px transparentes del PNG, el chasis queda a ≈ 24 px del borde. Mantén `left-[40px]` y `HUD_WIDTH = 420`.
- Muesca de la perilla: aplica una máscara al contenedor `.hud-screen` para que deje ver la perilla. Añade una constante, por ejemplo `HUD_SCREEN_NOTCH_PX = 30` (≈ 28 px × 420/408 + 1 px de margen), y aplícala como estilo inline:
  ```ts
  const notchMask = `radial-gradient(circle ${HUD_SCREEN_NOTCH_PX}px at 0 100%, transparent ${HUD_SCREEN_NOTCH_PX - 0.5}px, #000 ${HUD_SCREEN_NOTCH_PX}px)`;
  // style={{ ..., maskImage: notchMask, WebkitMaskImage: notchMask }}
  ```
  La máscara debe afectar también a las capas de scanlines y scanbar. Como son hijas de `.hud-screen`, ya quedan cubiertas.
- Contenido interno: la pantalla mide ahora ≈ 152 × 212 px renderizados, casi lo mismo que antes (≈ 155 × 214). No rediseñes el contenido. Solo comprueba que el pie centrado (`STANDBY` / `N SUCCESSES` / `✕ NO SUCCESS`) no quede dentro de la muesca, que ocupa ≈ 30 px desde la esquina inferior izquierda. Si se superpone, añade más padding inferior al contenedor del contenido (por ejemplo, `pb-[10px]`).
- En `client/src/index.css` puedes ajustar `border-radius` de `.hud-screen` (por ejemplo, 4px) si hace falta. No toques las animaciones.

## Archivos permitidos

- `client/src/App.tsx`: solo el bloque CONFIG del HUD y el componente `DiceHud`.
- `client/src/index.css`: solo las reglas `.hud-screen` / `.hud-frame` si fuera necesario.

## Fuera de alcance

- `media/HUD/Dados Hud.png` (no editar la imagen).
- Backend, bot, orquestador, `MediaStage`, `GameplayLoop` y el contrato de eventos.
- Escalado del lienzo a ventanas menores de 1920 × 1080.
- Documentación (README / ANALISIS): la actualiza Claude en el cierre.

## Criterios de aceptación

### (a) Verifica Copilot

1. `cd client; npm run build` termina sin errores de TypeScript ni de Vite. Pega la salida real.
2. `git diff --stat` muestra solo los archivos permitidos.
3. Las constantes del diff coinciden con las del Diseño, o las diferencias están justificadas en el Reporte.
4. Smoke test del backend sin regresiones: `cd server; .\.venv\Scripts\python.exe tests\smoke_test.py`. Pega el final de la salida.

### (b) Verifican Claude / el usuario

1. Con `.\run.ps1 --no-bot`, en `http://localhost:5173`:
   - La pantalla digital cubre toda la zona negra: no se ve negro del PNG en ningún borde y la perilla inferior izquierda sigue visible.
   - El LED está sobre el indicador STATUS.
   - El chasis queda abajo a la izquierda, sin tocar el borde inferior (≈ 24 px de separación).
2. Con una tirada inyectada por `/api/events` (`dice_count: 6, successes: 2` y otra con `successes: 0`), el contenido (PLAYER, DICE POOL, SUCCESSES, pie) cabe dentro de la pantalla y no queda cortado por la muesca.
3. El mismo resultado en el build servido en `/overlay/` (`.\run.ps1 obs --no-bot`).
4. Prueba manual final del usuario en la ventana de transmisión / OBS.

## Instrucciones para Copilot

- Máximo **3 intentos** por error. Si no se resuelve, para y anótalo en el Reporte.
- No dejes procesos largos corriendo (Vite, uvicorn, run.ps1). Si arrancas alguno para comprobar algo, detenlo antes de terminar.
- **No hagas commits.**
- Si te bloqueas (falta una dependencia, un puerto ocupado, algo ambiguo), para y anótalo. No improvises fuera del alcance.
- Completa la sección "Reporte" con evidencia: salida real de los comandos, "no probado" cuando no hayas podido verificar algo y ningún ✅ sin evidencia.

## Reporte

### Cambios realizados (solo `client/src/App.tsx`, archivo permitido)

- `HUD_SCREEN = { left: 19.4, top: 13.6, width: 36.7, height: 53.9 }` — recalibrado para el PNG 408×385, con ≈ 1 px de solapamiento sobre el bisel. Comentario actualizado a "Calibrado para Dados Hud.png 408×385".
- `HUD_STATUS_LED = { left: 62.3, top: 20.1 }` — sobre el indicador STATUS del chasis.
- Nueva constante `HUD_SCREEN_NOTCH_PX = Math.round(28 * 420 / 408 + 1)` (≈ 30 px) — muesca de la perilla.
- Posición del `<aside>`: `bottom-[24px]` → `bottom-[16px]` (con los ≈ 8 px transparentes del PNG, el chasis queda a ≈ 24 px del borde). Se mantuvieron `left-[40px]` y `HUD_WIDTH = 420`.
- Máscara radial aplicada al contenedor `.hud-screen` (estilo inline `maskImage` + `WebkitMaskImage`), con `HUD_SCREEN_NOTCH_PX` para dejar visible la perilla inferior izquierda. Como las capas de scanlines y scanbar son hijas de `.hud-screen`, quedan cubiertas por la misma máscara.
- `client/src/index.css` no fue necesario tocar: la regla `.hud-screen` ya tiene `border-radius: 3px` y las animaciones no se alteraron.

### Salida real de `cd client; npm run build`

```
> client@0.0.0 build
> tsc && vite build

vite v5.4.21 building for production...
transforming...
✓ 31 modules transformed.
rendering chunks...
computing gzip size...
dist/index.html                   0.47 kB │ gzip:  0.32 kB
dist/assets/index-4yP4KNZ6.css   12.07 kB │ gzip:  3.67 kB
dist/assets/index-FvJI9amh.js   153.07 kB │ gzip: 49.75 kB
✓ built in 1.15s
```

Sin errores de TypeScript ni de Vite. (Primera ejecución falló con `TS6133: 'HUD_SCREEN_NOTCH_PX' is declared but its value is never read` porque la máscara usaba `30px` hardcodeado; se corrigió usando la constante y se reconvirtió con éxito.)

### Salida real del smoke test (`cd server; .\.venv\Scripts\python.exe tests\smoke_test.py`)

```
22/22 OK
```

Todos los tests pasaron, sin regresiones.

### `git diff --stat`

```
 client/src/App.tsx |  15 ++-
```

Solo el archivo permitido fue modificado por Copilot. (Los diffs en `docs/claude.md` y `docs/copilot_instructions.md` son previos a esta ejecución y no corresponden a mis cambios.)

### Constantes finales (coinciden con el Diseño)

| Constante | Valor |
|---|---|
| `HUD_SCREEN` | `{ left: 19.4, top: 13.6, width: 36.7, height: 53.9 }` |
| `HUD_STATUS_LED` | `{ left: 62.3, top: 20.1 }` |
| `HUD_SCREEN_NOTCH_PX` | `Math.round(28 * 420 / 408 + 1)` |
| Aside `bottom` | `bottom-[16px]` |
| Aside `left` | `left-[40px]` |
| `HUD_WIDTH` | `420` |

### Bloqueos y cosas no probadas

- **No probado (b.1–b.4):** la verificación visual en `http://localhost:5173` (`.\run.ps1 --no-bot`) y en `/overlay/` (`.\run.ps1 obs --no-bot`) requiere que el usuario ejecute `run.ps1` y lo inspeccione en OBS; también requiere un backend local levantado (`server/main.py`) para inyectar tiradas por `/api/events`. Ninguno de esos procesos se inició (por instrucción, no dejar servicios corriendo).
- **No probado (a.3):** la comprobación de que el pie centrado (`STANDBY` / `✕ NO SUCCESS` / `N SUCCESSES`) no queda dentro de la muesca de ≈ 30 px. La muesca ocupa solo la esquina inferior izquierda y el pie está centrado, así que el solapamiento es improbable, pero no se verificó visualmente.
- No se hicieron commits (por instrucción).

## Revisión (Claude)

**Veredicto: APROBADO, con una corrección menor.**

### Contraste reporte ↔ diff

- El diff (`git diff --stat`: solo `client/src/App.tsx`, además de las fichas en `docs/`) coincide con lo que describe el Reporte: las constantes son las del Diseño, `bottom-[16px]` y la máscara radial están en `.hud-screen`, e `index.css` no se tocó.
- Diferencia menor: el Reporte describe la máscara como si usara solo la constante, pero el diff repetía la cadena del gradiente dos veces (en `maskImage` y en `WebkitMaskImage`) y además dejaba `420` escrito a mano en lugar de `HUD_WIDTH`.
- Seguridad: no aplica. El cambio es solo de estilos; no toca entradas, red, dependencias ni secretos.

### Correcciones de Claude

- Extraje `HUD_SCREEN_MASK` como constante única y calculé `HUD_SCREEN_NOTCH_PX` a partir de `HUD_WIDTH`, para que la muesca escale si cambia el ancho del HUD.
- Después de la corrección, `npm run build` sigue terminando sin errores (`✓ built in 1.13s`).

### Verificación integrada (b), ejecutada una vez

Backend en `127.0.0.1:8000` sirviendo el build en `/overlay/`, con Edge headless a 1920×1080 controlado por DevTools Protocol. Se inyectaron tiradas por `/api/events` y después se detuvo el backend.

- b.1: la pantalla digital cubre toda la zona negra del chasis, la perilla inferior izquierda queda visible gracias a la muesca, el LED cian está sobre STATUS y el chasis queda a ≈ 28 px del borde inferior. ✔ (capturas `standby_hud.png`)
- b.2: `Tester 6/2` muestra `06`, `02` y "2 SUCCESSES". `Maximiliano 12/0` muestra el estado ámbar de fallo con "✕ NO SUCCESS". En los dos casos el contenido cabe y el pie no choca con la muesca. ✔ (capturas `roll_ok.png`, `roll_fail.png`)
- b.3: verificado sobre `/overlay/`. El código es el mismo que sirve Vite; Vite no se probó por separado.
- b.4: pendiente, es la prueba manual del usuario en la ventana de transmisión / OBS.

### Pendientes

- Prueba manual final del usuario.
- Si el overlay se muestra en una ventana de menos de 1080 px de alto, el HUD se corta por abajo, porque el lienzo es fijo y no escala. Está fuera de alcance y queda anotado en `docs/pendientes.md`.
