"""SuperRolScreen — backend FastAPI.

* GET  /api/clips   -> lista de videos de media/Gameplay
* GET  /api/health  -> estado del servicio y overlays conectados
* POST /api/events  -> inyecta un evento manualmente (solo desde localhost, útil para pruebas);
                       403 si trae un Origin de navegador no permitido
* WS   /ws          -> bus de eventos: lo que envía un cliente (el bot) se reenvía al resto (overlays);
                       rechaza el handshake (403) si trae un Origin no permitido
* /media/...        -> archivos estáticos (Gameplay, HUD y cache de Discord)
* /overlay/         -> build de producción del cliente (si existe client/dist)

Orígenes de navegador permitidos: `ALLOWED_ORIGINS` (ver `origin_allowed`).
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import sys
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

ALLOWED_EVENT_TYPES = {"DICE_ROLL", "NEW_MEDIA", "VOICE_STATE", "NOW_PLAYING"}

NOW_PLAYING_TITLE_MAX = 120  # igual que music_detect y el cliente

# Orígenes permitidos para CORS y WebSocket
DEV_ORIGINS = ("http://localhost:5173", "http://127.0.0.1:5173")
ALLOWED_ORIGINS = frozenset(DEV_ORIGINS + ("http://localhost:8000", "http://127.0.0.1:8000"))


def origin_allowed(origin: str | None) -> bool:
    """True si la petición no trae Origin (bot, PowerShell, curl) o si el Origin está en
    ALLOWED_ORIGINS (comparación exacta). Cualquier otro valor ('', 'null', otro puerto,
    https, barra final, IP de LAN) se rechaza: así una web ajena abierta en el navegador
    no puede abrir /ws ni inyectar en /api/events (CORS no protege ninguno de los dos)."""
    if origin is None:
        return True
    return origin in ALLOWED_ORIGINS


# --- Validación de VOICE_STATE -------------------------------------------
VOICE_MAX_MEMBERS = 25
VOICE_NAME_MAX = 32
VOICE_ID_MAX = 20
VOICE_CHANNEL_MAX = 100


def _validate_voice_state(payload: dict[str, Any]) -> dict[str, Any] | None:
    channel = payload.get("channel")
    if channel is not None and not isinstance(channel, str):
        return None
    if isinstance(channel, str) and (len(channel) < 1 or len(channel) > VOICE_CHANNEL_MAX):
        return None

    members = payload.get("members")
    if not isinstance(members, list) or len(members) > VOICE_MAX_MEMBERS:
        return None

    clean_members: list[dict[str, Any]] = []
    for m in members:
        if not isinstance(m, dict):
            return None
        mid = m.get("id")
        if not isinstance(mid, str) or not mid.isdigit() or len(mid) > VOICE_ID_MAX:
            return None
        name = m.get("name")
        if not isinstance(name, str) or len(name) < 1 or len(name) > VOICE_NAME_MAX:
            return None
        speaking = m.get("speaking")
        if not isinstance(speaking, bool):
            return None
        clean_members.append({"id": mid, "name": name, "speaking": speaking})

    return {"type": "VOICE_STATE", "channel": channel, "members": clean_members}


def _validate_now_playing(payload: dict[str, Any]) -> dict[str, Any] | None:
    title = payload.get("title")
    if not isinstance(title, str):
        return None
    t = title.strip()
    if len(t) < 1 or len(t) > NOW_PLAYING_TITLE_MAX:
        return None
    return {"type": "NOW_PLAYING", "title": t}


for directory in (GAMEPLAY_DIR, HUD_DIR, CACHE_DIR):
    directory.mkdir(parents=True, exist_ok=True)


def _ignore_proactor_reset(loop: asyncio.AbstractEventLoop, context: dict[str, Any]) -> None:
    """Suprime la traza `ConnectionResetError` de _call_connection_lost en Windows.

    Es un fallo conocido de CPython/asyncio en Windows (ProactorEventLoop): al
    cerrarse un socket bruscamente (WebSocket, recarga de overlay), el transporte
    intenta `shutdown()` sobre un socket ya reseteado por el host remoto. La
    desconexión ya se gestiona en `websocket_endpoint`, así que esta traza es ruido
    inofensivo. Cualquier otra excepción se pasa al handler por defecto.
    """
    exception = context.get("exception")
    if isinstance(exception, (ConnectionResetError, ConnectionAbortedError)):
        handle = context.get("handle")
        message = context.get("message", "")
        if handle is not None and "_call_connection_lost" in repr(handle):
            log.debug("Ignorando ConnectionResetError de ProactorEventLoop en %s", repr(handle))
            return
        if "_call_connection_lost" in message:
            log.debug("Ignorando ConnectionResetError de ProactorEventLoop (%s)", message)
            return
    loop.default_exception_handler(context)


@contextlib.asynccontextmanager
async def _lifespan(_app: FastAPI):
    if sys.platform == "win32":
        asyncio.get_running_loop().set_exception_handler(_ignore_proactor_reset)
    yield


app = FastAPI(title="SuperRolScreen API", lifespan=_lifespan)

# CORS solo para orígenes de desarrollo (overlay Vite en localhost:5173)
# El origen 8000 no necesita CORS (es el mismo origen que el overlay).
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(DEV_ORIGINS),
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
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
    if payload["type"] == "VOICE_STATE":
        return _validate_voice_state(payload)
    if payload["type"] == "NOW_PLAYING":
        return _validate_now_playing(payload)
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
    if not origin_allowed(request.headers.get("origin")):
        raise HTTPException(status_code=403, detail="Origen no permitido")
    event = validate_event(await request.json())
    if event is None:
        raise HTTPException(status_code=422, detail="Evento inválido")
    delivered = await manager.broadcast(event)
    return {"delivered": delivered}


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket) -> None:
    origin = ws.headers.get("origin")
    if not origin_allowed(origin):
        log.warning("Conexion WS rechazada: origen %.100s", origin)
        await ws.close(code=1008)
        return
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