"""SuperRolScreen — bot de Discord que alimenta el overlay.

* Canal DICE_CHANNEL_ID  -> parsea los embeds del bot de dados y emite DICE_ROLL.
* Canal MEDIA_CHANNEL_ID -> extrae imágenes / GIFs (adjuntos, GIFs nativos de
  Discord vía Klipy/Tenor, enlaces de Giphy, etc.), los descarga a media/cache
  con MediaCache y emite NEW_MEDIA con una URL local y el tipo real del archivo.
* Canal MUSIC_CHANNEL_ID -> detecta avisos Now Playing de FlaviBot y emite NOW_PLAYING.
* Comandos slash /join y /leave -> el bot entra/sale del canal de voz del
  invocador y emite eventos VOICE_STATE (miembros + quién habla) al overlay
  a través de OverlayLink.

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
from typing import Any, Dict, Iterable, Optional, Set

import discord
from discord import app_commands
from discord.ext import voice_recv
import websockets

from config import (
    CACHE_DIR,
    CACHE_URL_PREFIX,
    DICE_CHANNEL_ID,
    DISCORD_TOKEN,
    MEDIA_CHANNEL_ID,
    MUSIC_CHANNEL_ID,
)
from media_cache import MediaCache
from music_detect import extract_now_playing, is_music_bot
from voice_presence import (
    VOICE_DEBOUNCE_S,
    VOICE_HEARTBEAT_S,
    SpeakingSink,
    build_voice_state,
    has_humans,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
log = logging.getLogger("superrol.listener")
# voice-recv registra en INFO cada paquete RTCP (1/s) y cada mensaje del gateway
# de voz con claves nuevas ('seq'); y en WARNING paquetes perdidos al vaciar su
# búfer. Es ruido para este uso (solo detectar quién habla).
logging.getLogger("discord.ext.voice_recv").setLevel(logging.WARNING)
logging.getLogger("discord.ext.voice_recv.opus").setLevel(logging.ERROR)

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
if MUSIC_CHANNEL_ID == 0:
    log.warning("MUSIC_CHANNEL_ID no configurado: no se detectarán canciones")


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
                            # VOICE_STATE sale en cada cambio de habla y en el latido: solo en DEBUG.
                            level = logging.DEBUG if payload.get("type") == "VOICE_STATE" else logging.INFO
                            log.log(level, "[WS ENVIADO] %s", payload)
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
        self._music_seen: "OrderedDict[tuple[int, str], None]" = OrderedDict()
        self.tree = app_commands.CommandTree(self)
        # Los decoradores @app_commands.command en métodos de un Client NO se
        # registran solos (solo en Group/Cog): se añaden al árbol explícitamente.
        self.tree.add_command(
            app_commands.Command(
                name="join",
                description="El bot entra al canal de voz en el que estás",
                callback=self._cmd_join,
            )
        )
        self.tree.add_command(
            app_commands.Command(
                name="leave",
                description="El bot sale del canal de voz",
                callback=self._cmd_leave,
            )
        )

        # --- Estado de voz ---
        self._voice: Optional[voice_recv.VoiceRecvClient] = None
        self._voice_guild_id: Optional[int] = None
        self._speaking_ids: Set[int] = set()
        self._voice_emit_handle: Optional[asyncio.TimerHandle] = None
        self._heartbeat_task: Optional[asyncio.Task[None]] = None
        self._synced_guilds: bool = False

    async def setup_hook(self) -> None:
        await self.cache.start()
        self.link.start()

    async def close(self) -> None:
        await self._disconnect_voice(emit=self._voice is not None)
        await self.link.stop()
        await self.cache.close()
        await super().close()

    async def on_ready(self) -> None:
        log.info("=== Bot activo: %s ===", self.user)
        for label, cid in (("dados", DICE_CHANNEL_ID), ("media", MEDIA_CHANNEL_ID), ("música", MUSIC_CHANNEL_ID)):
            if not cid:
                continue
            channel = self.get_channel(cid)
            if channel is None:
                log.error("Canal de %s %s no visible para el bot (¿permisos / ID?)", label, cid)
            else:
                log.info("Escuchando %s en #%s (%s)", label, getattr(channel, "name", "?"), cid)

        if not self._synced_guilds:
            self._synced_guilds = True
            for guild in self.guilds:
                try:
                    self.tree.copy_global_to(guild=guild)
                    await self.tree.sync(guild=guild)
                    log.info("Comandos sincronizados en guild %s (%s)", guild.id, guild.name)
                except discord.HTTPException as exc:
                    log.warning("No se pudieron sincronizar comandos en guild %s: %s", guild.id, exc)

    # --- Voz -----------------------------------------------------------------

    def _current_voice_members(self) -> list[tuple[int, str, bool]]:
        if not self._voice or not self._voice.channel:
            return []
        return [(m.id, m.display_name, m.bot) for m in self._voice.channel.members]

    def _emit_voice_state(self) -> None:
        channel_name = self._voice.channel.name if (self._voice and self._voice.channel) else None
        snapshot = build_voice_state(channel_name, self._current_voice_members(), self._speaking_ids)
        self.link.send(snapshot)

    def _schedule_voice_emit(self) -> None:
        if self._voice_emit_handle is not None:
            return
        loop = asyncio.get_running_loop()

        def _fire() -> None:
            self._voice_emit_handle = None
            self._emit_voice_state()

        self._voice_emit_handle = loop.call_later(VOICE_DEBOUNCE_S, _fire)

    async def _voice_heartbeat(self) -> None:
        try:
            while self._voice and self._voice.is_connected():
                await asyncio.sleep(VOICE_HEARTBEAT_S)
                if self._voice and self._voice.is_connected():
                    self._emit_voice_state()
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("Error en heartbeat de voz")

    async def _start_voice_heartbeat(self) -> None:
        await self._stop_voice_heartbeat()
        self._heartbeat_task = asyncio.create_task(self._voice_heartbeat(), name="voice-heartbeat")

    async def _stop_voice_heartbeat(self) -> None:
        if self._heartbeat_task is not None:
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except asyncio.CancelledError:
                pass
            self._heartbeat_task = None

    def _on_speaking_change(self, member_id: int, speaking: bool) -> None:
        """Callback invocado desde el hilo del SpeakingTimer vía call_soon_threadsafe."""
        if speaking:
            self._speaking_ids.add(member_id)
        else:
            self._speaking_ids.discard(member_id)
        self._schedule_voice_emit()

    async def _connect_to_voice(self, channel: discord.abc.Connectable) -> voice_recv.VoiceRecvClient:
        """Conecta (o mueve) al bot al canal de voz indicado."""
        # Si ya hay conexión en otro guild, desconectar primero (un solo canal)
        if self._voice and self._voice.is_connected() and self._voice.channel and self._voice.channel.id != channel.id:
            if self._voice.guild and self._voice.guild.id != getattr(channel.guild, "id", None):
                await self._disconnect_voice(emit=False)

        if self._voice and self._voice.is_connected() and self._voice.channel.id == channel.id:
            return self._voice

        try:
            if self._voice and self._voice.is_connected() and self._voice.guild == channel.guild:
                await self._voice.move_to(channel)
                vc = self._voice
            else:
                vc = await channel.connect(cls=voice_recv.VoiceRecvClient, self_deaf=False, self_mute=True)
        except (asyncio.TimeoutError, discord.ClientException, discord.opus.OpusNotLoaded):
            log.exception("Error conectando al canal de voz %s", channel)
            raise

        self._voice = vc
        self._voice_guild_id = channel.guild.id if channel.guild else None
        self._speaking_ids.clear()
        sink = SpeakingSink(asyncio.get_running_loop(), self._on_speaking_change)
        vc.listen(sink)
        self._emit_voice_state()
        await self._start_voice_heartbeat()
        return vc

    async def _disconnect_voice(self, emit: bool = True) -> None:
        await self._stop_voice_heartbeat()
        # Soltar la referencia ANTES de esperar: durante el await llega el
        # on_voice_state_update del propio bot y, si _voice siguiera asignado,
        # emitiría un segundo estado vacío.
        vc, self._voice = self._voice, None
        self._voice_guild_id = None
        if vc and vc.is_connected():
            try:
                await vc.disconnect()
            except Exception:
                log.exception("Error desconectando voz")
        self._speaking_ids.clear()
        if self._voice_emit_handle:
            self._voice_emit_handle.cancel()
            self._voice_emit_handle = None
        if emit:
            self._emit_voice_state()

    # --- Slash commands -----------------------------------------------------

    async def _cmd_join(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True, thinking=True)
        if interaction.guild is None:
            await interaction.followup.send("Este comando solo funciona en un servidor.", ephemeral=True)
            return
        member = interaction.user
        if not isinstance(member, discord.Member) or member.voice is None or member.voice.channel is None:
            await interaction.followup.send("Entra primero a un canal de voz.", ephemeral=True)
            return
        try:
            await self._connect_to_voice(member.voice.channel)
            await interaction.followup.send(f"Conectado a **{member.voice.channel.name}**.", ephemeral=True)
        except Exception:  # noqa: BLE001
            log.exception("Error al unirme al canal de voz")
            await interaction.followup.send(
                "No pude unirme al canal de voz. Revisa mis permisos.",
                ephemeral=True,
            )

    async def _cmd_leave(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True, thinking=True)
        if self._voice and self._voice.is_connected():
            await self._disconnect_voice(emit=True)
            await interaction.followup.send("Desconectado del canal de voz.", ephemeral=True)
        else:
            await interaction.followup.send("No estaba conectado a ningún canal de voz.", ephemeral=True)

    # --- Eventos ------------------------------------------------------------

    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState) -> None:
        if self._voice is None or self._voice.channel is None:
            return
        bot_channel_id = self._voice.channel.id
        was_in = before.channel is not None and before.channel.id == bot_channel_id
        is_in = after.channel is not None and after.channel.id == bot_channel_id
        if not was_in and not is_in:
            return

        # ¿El propio bot fue desconectado?
        if self.user and member.id == self.user.id and after.channel is None:
            self._voice = None
            self._voice_guild_id = None
            self._speaking_ids.clear()
            await self._stop_voice_heartbeat()
            if self._voice_emit_handle:
                self._voice_emit_handle.cancel()
                self._voice_emit_handle = None
            self._emit_voice_state()
            return

        if not has_humans(self._current_voice_members()):
            await self._disconnect_voice(emit=True)
            return

        # Quitar del set de speaking a quien salió
        if was_in and not is_in:
            self._speaking_ids.discard(member.id)

        self._schedule_voice_emit()

    def _handle_dice(self, message: discord.Message) -> None:
        if message.id in self._dice_seen:
            return
        parsed = parse_button_dice(message)
        if parsed:
            self._dice_seen[message.id] = None
            while len(self._dice_seen) > 500:
                self._dice_seen.popitem(last=False)
            self.link.send(parsed)

    def _handle_music(self, message: discord.Message) -> None:
        if not is_music_bot(message.author):
            return
        title = extract_now_playing(message.content, message.embeds, message.components)
        if not title:
            return
        key = (message.id, title)
        if key in self._music_seen:
            return
        self._music_seen[key] = None
        while len(self._music_seen) > 200:
            self._music_seen.popitem(last=False)
        self.link.send({"type": "NOW_PLAYING", "title": title})
        log.info("Now playing: %s", title)

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
        elif MUSIC_CHANNEL_ID and message.channel.id == MUSIC_CHANNEL_ID:
            try:
                self._handle_music(message)
            except Exception:
                log.exception("Error procesando música del mensaje %s", message.id)

    async def on_message_edit(self, _before: discord.Message, after: discord.Message) -> None:
        # Algunos bots publican el embed de la tirada editando un mensaje previo.
        if after.channel.id == DICE_CHANNEL_ID:
            self._handle_dice(after)
        elif MUSIC_CHANNEL_ID and after.channel.id == MUSIC_CHANNEL_ID:
            try:
                self._handle_music(after)
            except Exception:
                log.exception("Error procesando música editada %s", after.id)


if __name__ == "__main__":
    OverlayBot().run(DISCORD_TOKEN, log_handler=None)