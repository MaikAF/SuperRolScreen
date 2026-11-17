"""Detección de avisos "Now playing" del bot de música (FlaviBot).

Lógica pura, sin dependencias de discord.py: acepta objetos discord.Embed /
discord.Member o SimpleNamespace (todo se lee con getattr), para poder
testearla sin token.
"""

from __future__ import annotations

import re
from typing import Any, Iterable, Optional

NOW_PLAYING_TITLE_MAX = 120
MUSIC_BOT_NAME_HINT = "flavi"

HEADER_RE = re.compile(
    r"now\s*playing|reproduciendo\s*ahora|ahora\s*suena|est[aá]\s*sonando|sonando\s*ahora",
    re.IGNORECASE,
)
# Lo que puede rodear a una cabecera "sola" o separarla de la canción:
# espacios, puntuación y emojis/símbolos (cualquier cosa que no sea letra o dígito).
_NON_WORD_RE = re.compile(r"^[\W_]*$")
_SEPARATOR_RE = re.compile(r"^[\s:\-–—|·•>»]+")
_MD_LINK_RE = re.compile(r"\[([^\]]+)\]\((?:[^)\s]+)\)")
_URL_RE = re.compile(r"https?://\S+", re.IGNORECASE)
_MENTION_RE = re.compile(r"<(?:@[!&]?|#|a?:\w+:)\d+>")  # <@id>, <#id>, emojis custom
_MD_MARK_RE = re.compile(r"\*\*|__|~~|\|\||`|\*")


def is_music_bot(author: Any) -> bool:
    """True si el autor es un bot y su nombre contiene MUSIC_BOT_NAME_HINT."""
    if author is None or not getattr(author, "bot", False):
        return False
    hint = MUSIC_BOT_NAME_HINT.lower()
    for attr in ("name", "display_name"):
        value = getattr(author, attr, None)
        if isinstance(value, str) and hint in value.lower():
            return True
    return False


def clean_title(text: Optional[str]) -> Optional[str]:
    """Texto plano de una línea: sin markdown ni URLs, recortado a NOW_PLAYING_TITLE_MAX."""
    if not isinstance(text, str):
        return None
    for raw_line in text.splitlines():
        line = _MD_LINK_RE.sub(r"\1", raw_line)
        line = _URL_RE.sub("", line)
        line = _MENTION_RE.sub("", line)
        line = _MD_MARK_RE.sub("", line)
        line = re.sub(r"\s+", " ", line).strip()
        if line and not _NON_WORD_RE.match(line):
            if len(line) > NOW_PLAYING_TITLE_MAX:
                line = line[: NOW_PLAYING_TITLE_MAX - 1].rstrip() + "…"
            return line
    return None


def _is_header_only(text: Optional[str]) -> bool:
    """True si el texto es solo la cabecera (con emojis/signos alrededor)."""
    if not isinstance(text, str):
        return False
    text = _plain_line(text)
    m = HEADER_RE.search(text)
    if not m:
        return False
    rest = (text[: m.start()] + text[m.end() :]).replace("*", "")
    return bool(_NON_WORD_RE.match(rest))


def _after_header(text: Optional[str]) -> Optional[str]:
    """Si el texto es "<cabecera><sep><canción>", devuelve la canción limpia."""
    if not isinstance(text, str):
        return None
    m = HEADER_RE.search(text)
    if not m:
        return None
    after = text[m.end() :]
    # Quita el cierre de un posible markdown alrededor de la cabecera ("**Now playing:** X").
    after = re.sub(r"^\s*[*_~]+", "", after)
    after = _SEPARATOR_RE.sub("", after)
    return clean_title(after)


def _field_parts(embed: Any) -> list[tuple[Optional[str], Optional[str]]]:
    parts = []
    for f in getattr(embed, "fields", None) or []:
        name, value = getattr(f, "name", None), getattr(f, "value", None)
        parts.append((name if isinstance(name, str) else None, value if isinstance(value, str) else None))
    return parts


def _from_embed(embed: Any) -> Optional[str]:
    title = getattr(embed, "title", None)
    description = getattr(embed, "description", None)
    author = getattr(embed, "author", None)
    author_name = getattr(author, "name", None) if author is not None else None
    fields = _field_parts(embed)

    # 1. Título "Now playing: X".
    if not _is_header_only(title):
        song = _after_header(title)
        if song:
            return song

    # 2. Título o autor son solo la cabecera.
    title_hdr = _is_header_only(title)
    author_hdr = _is_header_only(author_name)
    if title_hdr or author_hdr:
        candidates = [description]
        if author_hdr and not title_hdr:
            candidates.append(title)
        if fields:
            candidates.append(fields[0][1])
        for c in candidates:
            song = clean_title(c)
            if song:
                return song

    # 3. Campo cuyo nombre contiene la cabecera.
    for name, value in fields:
        if name and HEADER_RE.search(name):
            song = clean_title(value) if _is_header_only(name) else (_after_header(name) or clean_title(value))
            if song:
                return song

    # Variante: la descripción empieza por "Now playing: X".
    return _after_header(description)


_COMPONENT_MAX_DEPTH = 6


def _plain_line(line: str) -> str:
    """Línea de markdown -> texto: sin encabezado (#, >, -), enlaces ni URLs."""
    line = _MD_LINK_RE.sub(r"\1", line)
    line = _URL_RE.sub("", line)
    line = re.sub(r"^\s*(?:#{1,3}|>{1,3}|-#)\s+", "", line)
    return line.strip()


def component_texts(components: Optional[Iterable[Any]], _depth: int = 0) -> list[str]:
    """Textos de los componentes V2 (TextDisplay), en orden, recorriendo
    Container / Section / ActionRow por `children`. Ignora botones y medios."""
    texts: list[str] = []
    if _depth > _COMPONENT_MAX_DEPTH:
        return texts
    for comp in components or []:
        if comp is None:
            continue
        content = getattr(comp, "content", None)
        if isinstance(content, str) and content.strip():
            texts.append(content)
        children = getattr(comp, "children", None)
        if children:
            texts.extend(component_texts(children, _depth + 1))
    return texts


def _from_texts(texts: list[str]) -> Optional[str]:
    """Aplica las reglas a una secuencia de bloques de texto (componentes V2).

    Cada bloque puede tener varias líneas: "## Now Playing\\n**Canción**".
    - Una línea "Now playing: X" -> X.
    - Una línea que es solo la cabecera -> la siguiente línea con texto.
    """
    # Enlaces -> su texto y sin URLs antes de buscar la cabecera: FlaviBot
    # publica "### [Now playing](https://flavibot.xyz/music-player)".
    lines = [_plain_line(ln) for t in texts for ln in t.splitlines()]
    lines = [ln for ln in lines if ln]
    for i, line in enumerate(lines):
        if not HEADER_RE.search(line):
            continue
        if _is_header_only(line):
            for nxt in lines[i + 1 :]:
                song = clean_title(nxt)
                if song:
                    return song
        else:
            song = _after_header(line)
            if song:
                return song
    return None


def extract_now_playing(
    content: Optional[str],
    embeds: Optional[Iterable[Any]],
    components: Optional[Iterable[Any]] = None,
) -> Optional[str]:
    """Canción que anuncia el mensaje, o None si no es un aviso de "now playing".

    Solo devuelve algo si algún texto contiene la cabecera, de modo que
    "Added to queue", "Paused", etc. se ignoran.
    """
    for embed in embeds or []:
        if embed is None:
            continue
        song = _from_embed(embed)
        if song:
            return song
    # Componentes V2 (mensajes sin content ni embeds, con TextDisplay).
    song = _from_texts(component_texts(components))
    if song:
        return song
    # 4. Último recurso: texto plano "Now playing: X".
    return _from_texts([content]) if isinstance(content, str) else None
