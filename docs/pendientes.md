# Pendientes (hallazgos fuera de alcance)

- **2026-11-13 — Vite escucha en todas las interfaces.** `client/vite.config.ts` tiene `server.host: true`, y al arrancar se ve el overlay en IPs de red (192.168.x, 172.x). Contradice la política de mantener todo en localhost (README → "Usar con OBS"). El backend sigue en `127.0.0.1`, pero el overlay de desarrollo queda accesible desde la LAN. Sugerencia: `host: '127.0.0.1'`.
- **2026-11-13 — Vite no atiende `CTRL_BREAK` dentro de los 5 s** al detener `run.py` y siempre termina con `taskkill /F` ("client sigue vivo; forzando cierre del arbol."). Funciona, pero el apagado tarda unos 5 s más.
- **2026-11-13 — Advertencia asyncio del backend en Windows** (`_ProactorBasePipeTransport._call_connection_lost` → `socket.shutdown`) cuando un WebSocket se cierra bruscamente al recargar el overlay. Es ruido en los logs; no se observó impacto funcional.
- **2026-11-13 — `.vscode/tasks.json`** no tiene tarea para `--window`.
- **2026-11-15 — El lienzo del overlay es fijo a 1920 × 1080 y no escala.** Si la ventana de Edge (`--window`) o la fuente del navegador tienen menos alto, el HUD (anclado abajo) se corta o parece pegado al borde. Sugerencia: escalar `<main>` con `transform: scale()` según el viewport.
