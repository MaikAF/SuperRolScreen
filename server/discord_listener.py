"""SuperRolScreen — bot de Discord que alimenta el overlay.

* Canal DICE_CHANNEL_ID  -> parsea los embeds del bot de dados y emite DICE_ROLL.
* Canal MEDIA_CHANNEL_ID -> extrae imágenes / GIFs (adjuntos, GIFs nativos de
  Discord vía Klipy/Tenor, enlaces de Giphy, etc.), los descarga a media/cache
  con MediaCache y emite NEW_MEDIA con una URL local y el tipo real del archivo.

Los eventos se envían por una única conexión WebSocket persistente con
reconexión automática (OverlayLink).
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from collections import OrderedDict
from typing import Any, Dict, Iterable, Optional

import discord
import websockets

from config import (
    CACHE_DIR,
    CACHE_URL_PREFIX,
    DICE_CHANNEL_ID,
    DISCORD_TOKEN,
    MEDIA_CHANNEL_ID,
)
from media_cache import MediaCache

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
log = logging.getLogger("superrol.listener")

WS_URL = "ws://localhost:8000/ws"
WS_RECONNECT_S = 3
EVENT_MAX_AGE_S = 60  # eventos encolados más viejos que esto se descartan (overlay caído mucho rato)

MAX_MEDIA_PER_MESSAGE = 4
# Discord genera los embeds de enlaces (Klipy, Tenor, Giphy...) unos segundos
# DESPUÉS de crear el mensaje: se re-lee el mensaje tras esta espera.
EMBED_WAIT_S = (2.5, 5.0)

URL_RE = re.compile(r"https?://[^\s<>|]+", re.IGNORECASE)

if not DISCORD_TOKEN or DICE_CHANNEL_ID == 0:
    raise SystemExit("Verifica DISCORD_TOKEN y DICE_CHANNEL_ID en server/.env")
if MEDIA_CHANNEL_ID == 0:
    log.warning("MEDIA_CHANNEL_ID no configurado: no se procesarán imágenes/GIFs")


# ----------------------------------------------------------------------------
# Enlace WebSocket persistente hacia el backend
# ----------------------------------------------------------------------------


class OverlayLink:
    def __init__(self, url: str) -> None:
        self.url = url
        self.queue: asyncio.Queue[tuple[float, Dict[str, Any]]] = asyncio.Queue(maxsize=200)
        self._task: Optional[asyncio.Task[None]] = None

    def start(self) -> None:
        self._task = asyncio.create_task(self._run(), name="overlay-link")

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()

    def send(self, payload: Dict[str, Any]) -> None:
        try:
            self.queue.put_nowait((time.monotonic(), payload))
        except asyncio.QueueFull:
            log.warning("Cola WS llena, se descarta evento %s", payload.get("type"))

    async def _run(self) -> None:
        pending: Optional[tuple[float, Dict[str, Any]]] = None
        while True:
            try:
                async with websockets.connect(self.url, open_timeout=5, ping_interval=20) as ws:
                    log.info("Conectado al overlay en %s", self.url)
                    while True:
                        if pending is None:
                            pending = await self.queue.get()
                        created, payload = pending
                        if time.monotonic() - created > EVENT_MAX_AGE_S:
                            log.info("Evento caducado descartado: %s", payload.get("type"))
                        else:
                            await ws.send(json.dumps(payload, ensure_ascii=False))
                            log.info("[WS ENVIADO] %s", payload)
                        pending = None
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                log.warning("Sin conexión con %s (%s). Reintento en %ss", self.url, exc, WS_RECONNECT_S)
                await asyncio.sleep(WS_RECONNECT_S)


# ----------------------------------------------------------------------------
# Dados
# ----------------------------------------------------------------------------


def parse_button_dice(message: discord.Message) -> Optional[Dict[str, Any]]:
    if not message.embeds:
        return None

    embed = message.embeds[0]
    title = embed.title or ""

    # Extrae: "number of dice: X ⇒ Y successes"
    match = re.search(
        r"number of dice:\s*(\d+)\s*(?:⇒|=>|->|→)\s*(\d+)\s*success", title, re.IGNORECASE
    )
    if not match:
        return None

    dice_count = int(match.group(1))
    successes = int(match.group(2))

    # Identificar quién tiró el dado
    user_name = "Jugador"
    if message.interaction_metadata:
        user_name = message.interaction_metadata.user.display_name
    elif embed.author and embed.author.name:
        user_name = embed.author.name
    elif embed.footer and embed.footer.text:
        user_name = embed.footer.text

    return {
        "type": "DICE_ROLL",
        "user": user_name,
        "dice_count": dice_count,
        "successes": successes,
    }


# ----------------------------------------------------------------------------
# Multimedia
# ----------------------------------------------------------------------------


def attachment_candidates(message: discord.Message) -> list[list[str]]:
    """Un grupo de URLs candidatas por adjunto de imagen/video."""
    groups: list[list[str]] = []
    for att in message.attachments:
        ctype = (att.content_type or "").lower()
        name = att.filename.lower()
        is_media = ctype.startswith(("image/", "video/")) or name.endswith(
            (".gif", ".png", ".jpg", ".jpeg", ".webp", ".avif", ".mp4", ".webm", ".mov")
        )
        if is_media:
            groups.append([att.url, att.proxy_url])
    return groups


def embed_candidates(embed: discord.Embed) -> list[str]:
    """URLs de un embed, de mejor a peor.

    Los GIFs del selector de Discord (Klipy / Tenor) llegan como embed de tipo
    "gifv": `video.url` es un MP4 en bucle y `thumbnail` solo el primer frame,
    por eso el video va primero. `embed.url` (la página) queda como último
    recurso: MediaCache la resuelve vía metatags OpenGraph.
    """
    urls: list[Optional[str]] = [
        embed.video.url,
        embed.video.proxy_url,
        embed.image.url,
        embed.image.proxy_url,
        embed.thumbnail.url,
        embed.thumbnail.proxy_url,
        embed.url,
    ]
    return [u for u in urls if u]


def content_urls(message: discord.Message) -> list[str]:
    return [u.rstrip(").,>") for u in URL_RE.findall(message.content or "")]


class MediaProcessor:
    """Extrae, descarga y emite los medios de un mensaje sin duplicados."""

    def __init__(self, cache: MediaCache, link: OverlayLink) -> None:
        self.cache = cache
        self.link = link
        self._sent: "OrderedDict[int, set[str]]" = OrderedDict()  # message_id -> URLs locales emitidas
        self._lock = asyncio.Lock()  # serializa la emisión para respetar el orden de llegada

    def _seen(self, message_id: int) -> set[str]:
        seen = self._sent.setdefault(message_id, set())
        self._sent.move_to_end(message_id)
        while len(self._sent) > 500:
            self._sent.popitem(last=False)
        return seen

    async def _emit_groups(self, message: discord.Message, groups: Iterable[list[str]]) -> int:
        emitted = 0
        seen = self._seen(message.id)
        for group in groups:
            if len(seen) >= MAX_MEDIA_PER_MESSAGE:
                break
            resolved = await self.cache.resolve(group)
            if resolved is None:
                log.warning("No se pudo resolver media de %s: %s", message.author, group[:2])
                continue
            if resolved.url in seen:
                continue
            seen.add(resolved.url)
            self.link.send(
                {
                    "type": "NEW_MEDIA",
                    "user": message.author.display_name,
                    "url": resolved.url,
                    "media_type": resolved.media_type,
                }
            )
            emitted += 1
        return emitted

    async def handle(self, message: discord.Message) -> None:
        async with self._lock:
            groups = attachment_candidates(message)
            groups += [embed_candidates(e) for e in message.embeds]
            await self._emit_groups(message, [g for g in groups if g])

        urls = content_urls(message)
        if not urls or message.embeds:
            return

        # Hay enlaces pero Discord aún no generó los embeds: esperar y re-leer.
        for delay in EMBED_WAIT_S:
            await asyncio.sleep(delay)
            try:
                message = await message.channel.fetch_message(message.id)
            except discord.NotFound:
                return  # mensaje borrado
            except discord.HTTPException as exc:
                log.warning("No se pudo re-leer el mensaje %s: %s", message.id, exc)
                break
            if message.embeds:
                async with self._lock:
                    await self._emit_groups(message, [embed_candidates(e) for e in message.embeds])
                return

        # Sin embeds: resolver los enlaces del texto directamente (OpenGraph / archivo directo).
        async with self._lock:
            await self._emit_groups(message, [[u] for u in urls])


# ----------------------------------------------------------------------------
# Cliente de Discord
# ----------------------------------------------------------------------------


class OverlayBot(discord.Client):
    def __init__(self) -> None:
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(intents=intents)
        self.link = OverlayLink(WS_URL)
        self.cache = MediaCache(CACHE_DIR, CACHE_URL_PREFIX)
        self.media = MediaProcessor(self.cache, self.link)
        self._dice_seen: "OrderedDict[int, None]" = OrderedDict()

    async def setup_hook(self) -> None:
        await self.cache.start()
        self.link.start()

    async def close(self) -> None:
        await self.link.stop()
        await self.cache.close()
        await super().close()

    async def on_ready(self) -> None:
        log.info("=== Bot activo: %s ===", self.user)
        for label, cid in (("dados", DICE_CHANNEL_ID), ("media", MEDIA_CHANNEL_ID)):
            if not cid:
                continue
            channel = self.get_channel(cid)
            if channel is None:
                log.error("Canal de %s %s no visible para el bot (¿permisos / ID?)", label, cid)
            else:
                log.info("Escuchando %s en #%s (%s)", label, getattr(channel, "name", "?"), cid)

    def _handle_dice(self, message: discord.Message) -> None:
        if message.id in self._dice_seen:
            return
        parsed = parse_button_dice(message)
        if parsed:
            self._dice_seen[message.id] = None
            while len(self._dice_seen) > 500:
                self._dice_seen.popitem(last=False)
            self.link.send(parsed)

    async def on_message(self, message: discord.Message) -> None:
        if self.user and message.author.id == self.user.id:
            return
        if message.channel.id == DICE_CHANNEL_ID:
            self._handle_dice(message)
        elif MEDIA_CHANNEL_ID and message.channel.id == MEDIA_CHANNEL_ID:
            try:
                await self.media.handle(message)
            except Exception:
                log.exception("Error procesando media del mensaje %s", message.id)

    async def on_message_edit(self, _before: discord.Message, after: discord.Message) -> None:
        # Algunos bots publican el embed de la tirada editando un mensaje previo.
        if after.channel.id == DICE_CHANNEL_ID:
            self._handle_dice(after)


if __name__ == "__main__":
    OverlayBot().run(DISCORD_TOKEN, log_handler=None)