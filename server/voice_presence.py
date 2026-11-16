"""Lógica pura de presencia de voz: build_voice_state, has_humans, SpeakingSink.

Este módulo no importa config ni discord_listener para ser testeable sin token.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Callable, Iterable

import discord
from discord.ext import voice_recv

log = logging.getLogger("superrol.voice")

VOICE_MAX_MEMBERS = 25
VOICE_NAME_MAX = 32
VOICE_HEARTBEAT_S = 5.0
VOICE_DEBOUNCE_S = 0.1


def build_voice_state(
    channel_name: str | None,
    members: Iterable[tuple[int, str, bool]],
    speaking: set[int],
) -> dict:
    """Construye el payload VOICE_STATE según contrato.

    Args:
        channel_name: Nombre del canal o None si desconectado.
        members: Iterable de tuplas (id, display_name, is_bot).
        speaking: Set de IDs que están hablando.

    Returns:
        dict con keys: type, channel, members (lista ordenada alfabéticamente por name).
    """
    if channel_name is None:
        return {"type": "VOICE_STATE", "channel": None, "members": []}

    human_members = []
    for member_id, display_name, is_bot in members:
        if is_bot:
            continue
        name = display_name[:VOICE_NAME_MAX]
        human_members.append((member_id, name, member_id in speaking))

    # Ordenar alfabéticamente por name sin distinguir mayúsculas
    human_members.sort(key=lambda x: x[1].lower())

    # Limitar a VOICE_MAX_MEMBERS
    human_members = human_members[:VOICE_MAX_MEMBERS]

    return {
        "type": "VOICE_STATE",
        "channel": channel_name[:100] if channel_name else None,
        "members": [
            {"id": str(member_id), "name": name, "speaking": speaking_flag}
            for member_id, name, speaking_flag in human_members
        ],
    }


def has_humans(members: Iterable[tuple[int, str, bool]]) -> bool:
    """Verifica si hay al menos un miembro humano (no bot) en el iterable."""
    return any(not is_bot for _, _, is_bot in members)


class SpeakingSink(voice_recv.AudioSink):
    """Sink que solo detecta quién está hablando (start/stop) vía eventos del SpeakingTimer.

    No decodifica audio: quiere Opus y descarta los datos en write().
    Los listeners se ejecutan en el hilo del SpeakingTimer, por lo que usan
    loop.call_soon_threadsafe para invocar el callback en el event loop.
    """

    def __init__(
        self,
        loop: asyncio.AbstractEventLoop,
        on_change: Callable[[int, bool], None],
    ) -> None:
        super().__init__()
        self._loop = loop
        self._on_change = on_change

    def wants_opus(self) -> bool:
        return True

    def write(self, user: discord.Member | None, data: voice_recv.VoiceData) -> None:
        # No hacemos nada con los datos de audio; solo nos interesa la detección de habla
        pass

    def cleanup(self) -> None:
        pass

    def _notify(self, member_id: int, speaking: bool) -> None:
        try:
            self._loop.call_soon_threadsafe(self._on_change, member_id, speaking)
        except RuntimeError:
            # El loop ya se cerró (apagado del bot): el evento ya no importa.
            pass

    @voice_recv.AudioSink.listener()
    def on_voice_member_speaking_start(self, member: discord.Member) -> None:
        """Se dispara cuando el SpeakingTimer detecta inicio de habla (llegada de paquetes)."""
        log.debug("Speaking start: %s (%s)", member.display_name, member.id)
        self._notify(member.id, True)

    @voice_recv.AudioSink.listener()
    def on_voice_member_speaking_stop(self, member: discord.Member) -> None:
        """Se dispara ~200 ms después del último paquete de ese miembro."""
        log.debug("Speaking stop: %s (%s)", member.display_name, member.id)
        self._notify(member.id, False)