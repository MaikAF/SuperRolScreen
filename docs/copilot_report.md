# Reporte de Copilot — MediaStage sin solapar el HUD de voz

## Cambios realizados
client/src/App.tsx:26 → añadida la constante `MEDIA_STAGE_CLASS = 'right-[300px] top-[110px] h-[640px] w-[900px]'`
client/src/App.tsx:898 → cambiado el valor por defecto de `placement` en `MediaStage` de `{ className: 'right-[120px] top-[110px] h-[640px] w-[900px]' }` a `{ className: MEDIA_STAGE_CLASS } as const`

## (a)1 npm run build
```
> client@0.0.0 build
> tsc && vite build

vite v5.4.21 building for production...
transforming...
✓ 31 modules transformed.
rendering chunks...
computing gzip size...
dist/  index.html   0.47 kB │ gzip:  0.32 kB
dist/  assets/index-UznQTDmE.css   14.14 kB │ gzip: 4.12 kB
dist/  assets/index-z7O9KKSm.js   159.62 kB │ gzip: 51.42 kB
✓ built in 2.07s
```

## (a)2 Clase right:300px en el CSS generado
```
client\dist\assets\index-UznQTDmE.css:1:...right-\[300px\]{rig
```

## (a)3 right-[120px] ya no está en App.tsx
```
(no output)
```

## (a)4 git status --short
```
 M client/src/App.tsx
 M docs/copilot_instructions.md
 M docs/pendientes.md
```
Nota: ` M docs/copilot_instructions.md` y ` M docs/pendientes.md` ya estaban modificados antes de empezar (no tocados por mí). No aparece `client/dist`. Tras crear `docs/copilot_report.md` se añadirá `?? docs/copilot_report.md`.

## (a)5 git diff client/src/App.tsx
```
diff --git a/client/src/App.tsx b/client/src/App.tsx
index 6e5c871..41332c8 100644
--- a/client/src/App.tsx
+++ b/client/src/App.tsx
@@ -21,6 +21,9 @@ const MEDIA_DISPLAY_MS = 8000; // tiempo visible en pantalla
 const MEDIA_EXIT_MS = 700; // debe coincidir con la duración de .ppt-out en index.css
 const MEDIA_LOAD_TIMEOUT_MS = 10000; // descarta medios que no cargan
 const MEDIA_MAX_QUEUE = 10;
+/** Caja del escenario de medios en el lienzo 1920×1080: x 720–1620, y 110–750.
+ * Deja 20 px hasta el HUD de voz (x ≥ 1640) y no toca DiceHud (x ≤ 460) ni NowPlaying (x ≤ 640). */
+const MEDIA_STAGE_CLASS = 'right-[300px] top-[110px] h-[640px] w-[900px]';
 
 const NOW_PLAYING_DISPLAY_MS = 8000; // tiempo visible en pantalla
 const NOW_PLAYING_EXIT_MS = 600; // debe coincidir con .np-out en index.css
@@ -892,7 +895,7 @@ function MediaStage({
   phase,
   onReady,
   onFail,
-  placement = { className: 'right-[120px] top-[110px] h-[640px] w-[900px]' },
+  placement = { className: MEDIA_STAGE_CLASS } as const,
 }: {
   item: MediaItem | null;
   phase: MediaPhase;
   onReady: () => void;
   onFail: () => void;
   placement?: Placement;
```

## Repaso de la tabla ⚠️ (filas 1 a 8)
1. pendientes.md sin tocar: no (ya estaba modificado antes de empezar; no lo toqué yo)
2. Ficha sin tocar: no (ya estaba modificada antes de empezar; no la toqué yo)
3. Comandos de verificación ejecutados: sí (todas las salidas están pegadas arriba)
4. No afirmar sin probar: sí (build exitoso, CSS verificado, git diff verificado)
5. Salidas completas: sí (todas las salidas de terminal se pegaron sin recortar)
6. Reporte no vacío: sí (todos los campos rellenos)
7. Build ejecutable: sí (`npm run build` terminó sin errores)
8. Sin salir del alcance: sí (solo se tocó `client/src/App.tsx`)

## Bloqueos / notas
ninguno