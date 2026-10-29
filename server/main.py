"""SuperRolScreen — backend FastAPI.

* GET  /api/clips   -> lista de videos de media/Gameplay
* GET  /api/health  -> estado del servicio y overlays conectados
* POST /api/events  -> inyecta un evento manualmente (solo desde localhost, útil para pruebas)
* WS   /ws          -> bus de eventos: lo que envía un cliente (el bot) se reenvía al resto (overlays)
* /media/...        -> archivos estáticos (Gameplay, HUD y cache de Discord)
* /overlay/         -> build de producción del cliente (si existe client/dist)
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from config import (
    CACHE_DIR,
    CLIENT_DIST_DIR,
    GAMEPLAY_DIR,
    GAMEPLAY_EXTENSIONS,
    HUD_DIR,
    MEDIA_DIR,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
log = logging.getLogger("superrol.server")

ALLOWED_EVENT_TYPES = {"DICE_ROLL", "NEW_MEDIA"}

for directory in (GAMEPLAY_DIR, HUD_DIR, CACHE_DIR):
    directory.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="SuperRolScreen API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

# Starlette sirve con soporte de Range requests (necesario para <video>).
app.mount("/media", StaticFiles(directory=str(MEDIA_DIR)), name="media")

if CLIENT_DIST_DIR.is_dir():
    app.mount("/overlay", StaticFiles(directory=str(CLIENT_DIST_DIR), html=True), name="overlay")


class ConnectionManager:
    def __init__(self) -> None:
        self.active: set[WebSocket] = set()
        self._lock = asyncio.Lock()

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        async with self._lock:
            self.active.add(ws)
        log.info("Cliente WS conectado (%d activos)", len(self.active))

    async def disconnect(self, ws: WebSocket) -> None:
        async with self._lock:
            self.active.discard(ws)
        log.info("Cliente WS desconectado (%d activos)", len(self.active))

    async def broadcast(self, payload: dict[str, Any], exclude: WebSocket | None = None) -> int:
        async with self._lock:
            targets = [ws for ws in self.active if ws is not exclude]
        results = await asyncio.gather(
            *(asyncio.wait_for(ws.send_json(payload), timeout=5) for ws in targets),
            return_exceptions=True,
        )
        dead = [ws for ws, res in zip(targets, results) if isinstance(res, Exception)]
        for ws in dead:
            await self.disconnect(ws)
        return len(targets) - len(dead)


manager = ConnectionManager()


def validate_event(payload: Any) -> dict[str, Any] | None:
    if not isinstance(payload, dict) or payload.get("type") not in ALLOWED_EVENT_TYPES:
        return None
    if payload["type"] == "NEW_MEDIA" and not isinstance(payload.get("url"), str):
        return None
    return payload


@app.get("/api/clips")
async def get_clips() -> dict[str, list[str]]:
    clips = sorted(
        f.name
        for f in GAMEPLAY_DIR.iterdir()
        if f.is_file() and f.suffix.lower() in GAMEPLAY_EXTENSIONS
    )
    return {"clips": clips}


@app.get("/api/health")
async def health() -> dict[str, Any]:
    return {"status": "ok", "ws_clients": len(manager.active)}


@app.post("/api/events")
async def inject_event(request: Request) -> dict[str, Any]:
    if request.client is None or request.client.host not in {"127.0.0.1", "::1", "localhost"}:
        raise HTTPException(status_code=403, detail="Solo disponible desde localhost")
    event = validate_event(await request.json())
    if event is None:
        raise HTTPException(status_code=422, detail="Evento inválido")
    delivered = await manager.broadcast(event)
    return {"delivered": delivered}


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket) -> None:
    await manager.connect(ws)
    try:
        while True:
            raw = await ws.receive_text()
            try:
                event = validate_event(json.loads(raw))
            except json.JSONDecodeError:
                event = None
            if event is None:
                log.warning("Mensaje WS descartado: %.200s", raw)
                continue
            delivered = await manager.broadcast(event, exclude=ws)
            log.info("Evento %s reenviado a %d overlay(s)", event["type"], delivered)
    except WebSocketDisconnect:
        pass
    except Exception as exc:  # no tumbar el servidor por un cliente roto
        log.warning("Error en conexión WS: %s", exc)
    finally:
        await manager.disconnect(ws)