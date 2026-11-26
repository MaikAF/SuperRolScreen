# Ficha — `MediaStage` no debe solaparse con el HUD de voz

> ## 📌 PROCEDIMIENTO: el Reporte va en otro archivo
>
> **Este archivo (`docs/copilot_instructions.md`) es de solo lectura para ti.** El Reporte va en **`docs/copilot_report.md`** (créalo con la plantilla del final). No modifiques, restaures ni reescribas esta ficha.

> ## ⚠️ PROBLEMAS DE COMPORTAMIENTO QUE DEBES CORREGIR
>
> Son patrones que se repiten en las fichas anteriores (detalle en `docs/pendientes.md`). Cada uno invalida la entrega por sí solo.
>
> | # | Problema | Veces | Última vez | Qué se espera |
> |---|---|---|---|---|
> | 1 | **Editar `docs/pendientes.md` o tachar el pendiente** | 4 | CORS (11-24): lo tachó y escribió «Resuelto» | No tocarlo nunca. Lo cierra Claude. |
> | 2 | **Borrar o sobrescribir la ficha** | 2 seguidas | CORS (11-24): reporte escrito sobre la ficha anterior | Esta ficha es de solo lectura; el reporte va en `docs/copilot_report.md`. |
> | 3 | **No ejecutar los comandos de verificación** | 4 | CORS (11-24): ningún test, «el shell no permite ejecutar Python» | Los comandos funcionan. Si uno falla, pega el error **exacto**. |
> | 4 | **Afirmar que algo está bien sin probarlo** | 3 | CORS (11-24): «correcto según el diff» con un `SyntaxError` en `main.py` | Solo afirma lo que respalda una salida pegada. |
> | 5 | **Salidas incompletas o inventadas** | 3 | CORS (11-24): `git diff --stat` sin 2 archivos que sí había tocado | Copia la salida de la terminal sin recortar ni reescribir. |
> | 6 | **Reporte vacío** | 5 | Escalado horizontal (11-24) | Todos los campos de la plantilla, rellenos. |
> | 7 | **Diseño a medias o tests que no pueden pasar** | 3 | CORS (11-24): API de `websockets` inexistente | Ejecuta lo que escribes. Un test que no ejecutaste no cuenta. |
> | 8 | **Salir del alcance** | 4 | Editar docs fuera de «Archivos permitidos» | Solo los archivos listados abajo, más `docs/copilot_report.md`. |

## Contexto mínimo

El overlay es un lienzo fijo de **1920 × 1080** (`client/src/App.tsx`, layout horizontal, el de por defecto). Posiciones actuales, en px del lienzo:

| Elemento | Origen en el código | Caja (x, y) | z |
|---|---|---|---|
| `MediaStage` | `placement` por defecto: `right-[120px] top-[110px] h-[640px] w-[900px]` (`App.tsx:895`) | x 900–1800, y 110–750 | 20 |
| `VoiceHud` | `bottom-[16px] right-[40px]`, ancho `VOICE_HUD_WIDTH` 240 → alto ≈ 469 | x 1640–1880, y 595–1064 | 30 |
| `DiceHud` | `bottom-[16px] left-[40px]`, ancho `HUD_WIDTH` 420 → alto ≈ 396 | x 40–460, y 668–1064 | 30 |
| `NowPlayingHud` | `left-0 top-1/2`, `.np-panel` `max-width: 640px` | x 0–640 como máximo, centro y 540 | 40 |

El medio (`MEDIA_ELEMENT_CLASS`: hasta 860 × 560, más 6 px de padding del marco y el pie `SENT BY`) se centra dentro de la caja de `MediaStage`. Un medio ancho o alto invade la zona del HUD de voz (x 1640–1800, y 595–750) y queda parcialmente tapado por él.

Pendiente de origen: `docs/pendientes.md`, entrada del 2026-11-17 («En el layout horizontal, `MediaStage` se solapa con el HUD de voz»).

## Objetivo

Que la caja de `MediaStage` no se cruce con ningún HUD en el layout horizontal, **sin reducir** el tamaño máximo del medio.

## Diseño

1. En `client/src/App.tsx`, en la sección de constantes del principio (junto a `MEDIA_MAX_QUEUE`), añade:
   ```ts
   /** Caja del escenario de medios en el lienzo 1920×1080: x 720–1620, y 110–750.
    * Deja 20 px hasta el HUD de voz (x ≥ 1640) y no toca DiceHud (x ≤ 460) ni NowPlaying (x ≤ 640). */
   const MEDIA_STAGE_CLASS = 'right-[300px] top-[110px] h-[640px] w-[900px]';
   ```
2. En `MediaStage`, cambia el valor por defecto de `placement` a `{ className: MEDIA_STAGE_CLASS }`.
   - La constante debe ser un **literal de string completo** en el código fuente: Tailwind solo genera las clases que encuentra escritas tal cual. No la construyas con plantillas ni concatenación.
3. **No** cambies nada más: ni `MEDIA_ELEMENT_CLASS`, ni los HUD, ni `index.css`. El layout `gameplay` sigue usando el mismo valor por defecto (mismas posiciones que el horizontal, como dice ANALISIS); es intencional.

## Archivos permitidos

- `client/src/App.tsx`: solo los puntos 1 y 2.
- `docs/copilot_report.md` (nuevo): el Reporte.

## Fuera de alcance

- `client/src/index.css`, `client/index.html` (el `bg-black` del `body` es otro pendiente).
- `docs/pendientes.md`, `docs/README.md`, `docs/ANALISIS_DE_SOFTWARE.md` y **esta ficha**.
- Hacer commits o stage.

## Criterios de aceptación

### (a) Los verifica Copilot

Ejecuta en PowerShell y pega cada salida **completa**:

1. Desde `client/`: `npm run build` → termina sin errores de `tsc` ni de Vite. Pega la salida entera.
2. Desde la raíz: `Select-String -Path client\dist\assets\*.css -Pattern 'right:300px'` → al menos una coincidencia (prueba de que Tailwind generó la clase). Pega la salida.
3. Desde la raíz: `Select-String -Path client\src\App.tsx -Pattern "right-\[120px\]"` → **sin salida**.
4. Desde la raíz: `git status --short` → exactamente ` M client/src/App.tsx` y `?? docs/copilot_report.md` (más ` M docs/pendientes.md`, que ya estaba modificado antes de empezar y **no** debes tocar). Ninguna otra línea. Si `client/dist` aparece, dilo.
5. Desde la raíz: `git diff client/src/App.tsx` → solo la constante nueva y el cambio del valor por defecto.

### (b) Los verifican Claude y el usuario

1. Claude: con `.\run.ps1 dev --no-bot`, inyectar un `NEW_MEDIA` ancho (p. ej. 1600 × 900) y otro alto (p. ej. 600 × 1200) y un `VOICE_STATE`, y comprobar en Edge headless a 1920 × 1080 (captura + `getBoundingClientRect`) que el medio no se cruza con el HUD de voz ni con el de dados.
2. Claude: con `NOW_PLAYING` inyectado a la vez, comprobar que tampoco se solapa con el medio.
3. Usuario: verlo en OBS con un medio real de Discord.

## Instrucciones para Copilot

- Máximo **3 intentos** por error. Si no lo resuelves, para y anótalo en el Reporte con el error **exacto**.
- No dejes procesos corriendo (no lances `npm run dev` ni `run.ps1`). **No hagas commits ni stage.**
- **No edites esta ficha** ni `docs/pendientes.md`, `README.md` o `ANALISIS_DE_SOFTWARE.md`.
- El Reporte va en **`docs/copilot_report.md`**, con la plantilla de abajo. Pega la salida **real** de cada comando, sin recortar. Escribe «no probado» y el motivo si no pudiste verificar algo. Sin ✅ sin evidencia.
- Antes de entregar, repasa la tabla ⚠️ fila por fila y confírmalo en el Reporte.

## Plantilla de `docs/copilot_report.md`

````markdown
# Reporte de Copilot — MediaStage sin solapar el HUD de voz

## Cambios realizados
<archivo:línea → qué>

## (a)1 npm run build
```
<salida>
```
## (a)2 Clase right:300px en el CSS generado
```
<salida>
```
## (a)3 right-[120px] ya no está en App.tsx
```
<salida>
```
## (a)4 git status --short
```
<salida>
```
## (a)5 git diff client/src/App.tsx
```
<salida>
```

## Repaso de la tabla ⚠️ (filas 1 a 8)
1. pendientes.md sin tocar: <sí/no>
2. Ficha sin tocar: <sí/no>
3. …

## Bloqueos / notas
<texto o «ninguno»>
````

## Revisión (Claude)

**Veredicto:** aceptado. El código cumple el diseño y la verificación integrada pasa. Es la primera entrega de Copilot en mucho tiempo con el Reporte completo y sin tocar `pendientes.md` ni la ficha.

**Diferencias entre el reporte y el diff:**
- El diff coincide con lo que dice el reporte. El único añadido fuera del diseño es un `as const` en el valor por defecto de `placement`, que el reporte sí declara, pero que no aporta nada (el tipo ya es `Placement`).
- (a)1: la salida pegada tiene el color ANSI quitado y el tiempo distinto (2,07 s frente a 1,07 s en mi ejecución), pero los hashes `index-UznQTDmE.css` e `index-z7O9KKSm.js` coinciden con mi build. Es creíble.
- (a)2: la salida está recortada (`...right-\[300px\]{rig`), pero es una sola línea minificada; comprobé que `right:300px` está en el CSS.
- (a)4: lo ejecutó antes de crear el reporte, así que falta `?? docs/copilot_report.md`. Lo advierte en una nota; no es un problema.
- Tabla ⚠️, filas 1 y 2: respondió «no» a «sin tocar», pero el diff muestra que no los tocó: `pendientes.md` solo tiene los cambios previos del usuario y la ficha sigue igual que la escribí (126 líneas). Leyó mal la pregunta.

**Correcciones de Claude:** quité el `as const` (`App.tsx:898`). `npm run build` da los mismos hashes.

**Seguridad:** no hay nada relevante. Solo cambian clases CSS, sin entradas, red ni dependencias.

**Verificación integrada (b), una ejecución** (`.\run.ps1 dev --no-bot` + Edge headless a 1920 × 1080 por CDP; eventos `VOICE_STATE` con 10 miembros, `DICE_ROLL`, `NOW_PLAYING` y `NEW_MEDIA` con SVG de prueba):
```
ancho 1600×900  stage [720,110,1620,750]  figure [733,154,1607,706]
alto  600×1200  stage [720,110,1620,750]  figure [1023,116,1317,745]
DiceHud [40,668,460,1064]   VoiceHud [1640,595,1880,1064]   NowPlaying [0,493,640,587]
figure vs DiceHud / VoiceHud / NowPlaying -> ok en los dos casos
RESULTADO: OK
```
Captura revisada: el medio ancho queda entre `NOW PLAYING` y el HUD de voz, sin tocar ninguno. Al detener, los puertos 8000 y 5173 quedaron libres.

**Pendientes:**
- (b)3, para el usuario: verlo en OBS con un medio real de Discord.
- En la ventana `gameplay` (TikTok) el medio también se desplaza 180 px a la izquierda, porque comparte el valor por defecto. Es intencional (ANALISIS: mismas posiciones que el horizontal).
- Nuevo dato sobre el pendiente de `GET /health` 404: apareció **al arrancar** y **a mitad de la sesión**, no solo al apagar, y sin que se cerrara ningún Edge. Lo anoto en `pendientes.md`.
