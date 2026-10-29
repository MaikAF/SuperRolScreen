"""Descarga y cachea localmente imágenes / GIFs / videos cortos recibidos desde Discord.

¿Por qué descargar en vez de pasar la URL remota al overlay?
  * Las URLs de adjuntos de Discord (cdn.discordapp.com) están firmadas y caducan.
  * Los enlaces de Klipy / Tenor / Giphy suelen ser *páginas HTML*, no archivos:
    un <img> con esa URL se rompe. Aquí se resuelven vía metatags OpenGraph.
  * La extensión de la URL miente con frecuencia (".gif" que en realidad es MP4,
    ".png" que es WEBP...). Aquí el tipo real se detecta por *magic bytes*.
  * Algunos CDNs bloquean hotlinking. Servido desde localhost nunca falla.

El overlay recibe siempre una URL local (`/media/cache/<hash>.<ext>`) y un
`media_type` fiable ("image" | "video").
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import time
import uuid
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from typing import Iterable, Literal, Optional
from urllib.parse import urljoin, urlsplit, urlunsplit

import aiohttp

from config import (
    MEDIA_CACHE_MAX_FILES,
    MEDIA_DOWNLOAD_TIMEOUT_S,
    MEDIA_MAX_BYTES,
)

log = logging.getLogger("superrol.media")

MediaType = Literal["image", "video"]

BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
)

IMAGE_EXTS = {".gif", ".png", ".jpg", ".jpeg", ".webp", ".avif", ".apng"}
VIDEO_EXTS = {".mp4", ".webm", ".mov", ".m4v"}

# Hosts cuyas URLs llevan parámetros de firma que cambian en cada petición.
SIGNED_HOSTS = ("cdn.discordapp.com", "media.discordapp.net")

# Prioridad de metatags al resolver una página HTML (video primero: más liviano y fluido).
OG_PRIORITY = (
    "og:video:secure_url",
    "og:video:url",
    "og:video",
    "twitter:player:stream",
    "og:image:secure_url",
    "og:image:url",
    "og:image",
    "twitter:image",
    "twitter:image:src",
    "link:image_src",
)

HTML_MAX_BYTES = 2 * 1024 * 1024
CHUNK = 64 * 1024


@dataclass(frozen=True)
class ResolvedMedia:
    url: str  # URL a enviar al overlay (local "/media/cache/..." o remota como último recurso)
    media_type: MediaType


# ----------------------------------------------------------------------------
# Detección de tipo
# ----------------------------------------------------------------------------


def guess_type_from_url(url: str) -> Optional[MediaType]:
    ext = Path(urlsplit(url).path).suffix.lower()
    if ext in IMAGE_EXTS:
        return "image"
    if ext in VIDEO_EXTS:
        return "video"
    return None


def sniff(head: bytes) -> Optional[tuple[MediaType, str]]:
    """Detecta el formato real por magic bytes. Devuelve (tipo, extensión)."""
    if head[:6] in (b"GIF87a", b"GIF89a"):
        return "image", "gif"
    if head[:8] == b"\x89PNG\r\n\x1a\n":
        return "image", "png"  # también cubre APNG
    if head[:3] == b"\xff\xd8\xff":
        return "image", "jpg"
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "image", "webp"
    if head[4:8] == b"ftyp":
        brands = head[8:48]
        if b"avif" in brands or b"avis" in brands:
            return "image", "avif"
        if any(b in brands for b in (b"heic", b"heix", b"hevc", b"heim")):
            return None  # HEIC no lo reproduce Chromium / OBS
        if head[8:12] == b"qt  ":
            return "video", "mov"
        return "video", "mp4"
    if head[:4] == b"\x1a\x45\xdf\xa3":
        return "video", "webm"
    return None


def _looks_like_html(head: bytes, content_type: str) -> bool:
    if "html" in content_type:
        return True
    snippet = head[:512].lstrip().lower()
    return snippet.startswith((b"<!doctype html", b"<html", b"<head", b"<meta"))


class _MetaParser(HTMLParser):
    """Recoge metatags OpenGraph / Twitter y <link rel=image_src>."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.found: dict[str, str] = {}

    def handle_starttag(self, tag: str, attrs: list[tuple[str, Optional[str]]]) -> None:
        a = {k.lower(): (v or "") for k, v in attrs}
        if tag == "meta":
            key = (a.get("property") or a.get("name") or "").strip().lower()
            content = a.get("content", "").strip()
            if key in OG_PRIORITY and content and key not in self.found:
                self.found[key] = content
        elif tag == "link" and a.get("rel", "").lower() == "image_src" and a.get("href"):
            self.found.setdefault("link:image_src", a["href"].strip())


def extract_og_candidates(html: str, base_url: str) -> list[str]:
    parser = _MetaParser()
    try:
        parser.feed(html)
    except Exception:  # HTML roto: usamos lo que se haya podido leer
        pass
    return [urljoin(base_url, parser.found[k]) for k in OG_PRIORITY if k in parser.found]


def _cache_key(url: str) -> str:
    parts = urlsplit(url)
    if parts.hostname and parts.hostname.endswith(SIGNED_HOSTS):
        url = urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))
    return hashlib.sha1(url.encode("utf-8")).hexdigest()[:20]


def _dedupe(urls: Iterable[Optional[str]]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for u in urls:
        if u and u.startswith(("http://", "https://")) and u not in seen:
            seen.add(u)
            out.append(u)
    return out


# ----------------------------------------------------------------------------
# Cache
# ----------------------------------------------------------------------------


class MediaCache:
    def __init__(self, cache_dir: Path, url_prefix: str) -> None:
        self.cache_dir = cache_dir
        self.url_prefix = url_prefix.rstrip("/")
        self._session: Optional[aiohttp.ClientSession] = None

    async def start(self) -> None:
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=MEDIA_DOWNLOAD_TIMEOUT_S, sock_connect=10),
            headers={"User-Agent": BROWSER_UA, "Accept": "*/*"},
        )
        await asyncio.to_thread(self._prune)

    async def close(self) -> None:
        if self._session:
            await self._session.close()
            self._session = None

    async def resolve(self, candidates: Iterable[Optional[str]]) -> Optional[ResolvedMedia]:
        """Prueba cada URL candidata en orden y devuelve la primera que se pueda mostrar."""
        urls = _dedupe(candidates)
        for url in urls:
            try:
                result = await self._resolve_one(url, depth=0)
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # red caída, timeout, SSL...
                log.warning("No se pudo descargar %s: %s", url, exc)
                result = None
            if result:
                return result

        # Último recurso: URL remota si su extensión es reconocible (el overlay
        # igualmente intentará <img> y luego <video> si falla).
        for url in urls:
            media_type = guess_type_from_url(url)
            if media_type:
                log.warning("Usando URL remota sin cachear: %s", url)
                return ResolvedMedia(url, media_type)
        return None

    async def _resolve_one(self, url: str, depth: int) -> Optional[ResolvedMedia]:
        if self._session is None:
            raise RuntimeError("MediaCache.start() no fue llamado")

        key = _cache_key(url)
        cached = next(
            (p for p in self.cache_dir.glob(f"{key}.*") if p.suffix != ".part"), None
        )
        if cached:
            kind = guess_type_from_url(cached.name)
            if kind:
                return ResolvedMedia(f"{self.url_prefix}/{cached.name}", kind)

        async with self._session.get(url, allow_redirects=True, max_redirects=6) as resp:
            if resp.status != 200:
                log.info("HTTP %s al descargar %s", resp.status, url)
                return None
            if resp.content_length and resp.content_length > MEDIA_MAX_BYTES:
                log.warning("Archivo demasiado grande (%s bytes): %s", resp.content_length, url)
                return None

            head = await self._read_head(resp.content)
            detected = sniff(head)

            if detected is None:
                if depth == 0 and _looks_like_html(head, resp.content_type or ""):
                    html = head + await resp.content.read(HTML_MAX_BYTES - len(head))
                    page_url = str(resp.url)
                    for candidate in extract_og_candidates(
                        html.decode(resp.charset or "utf-8", errors="replace"), page_url
                    ):
                        if candidate == url:
                            continue
                        try:
                            result = await self._resolve_one(candidate, depth=1)
                        except asyncio.CancelledError:
                            raise
                        except Exception as exc:
                            log.info("Candidato OG falló %s: %s", candidate, exc)
                            continue
                        if result:
                            return result
                log.info("Formato no soportado (%s) en %s", resp.content_type, url)
                return None

            media_type, ext = detected
            final_path = self.cache_dir / f"{key}.{ext}"
            tmp_path = self.cache_dir / f"{key}.{uuid.uuid4().hex[:8]}.part"
            written = len(head)
            try:
                with open(tmp_path, "wb") as fh:
                    fh.write(head)
                    async for chunk in resp.content.iter_chunked(CHUNK):
                        written += len(chunk)
                        if written > MEDIA_MAX_BYTES:
                            raise ValueError(f"supera {MEDIA_MAX_BYTES} bytes")
                        fh.write(chunk)
                os.replace(tmp_path, final_path)
            finally:
                if tmp_path.exists():
                    tmp_path.unlink(missing_ok=True)

        log.info("Media cacheada (%s, %.1f KB): %s", media_type, written / 1024, final_path.name)
        asyncio.get_running_loop().run_in_executor(None, self._prune)
        return ResolvedMedia(f"{self.url_prefix}/{final_path.name}", media_type)

    @staticmethod
    async def _read_head(stream: aiohttp.StreamReader, size: int = 4096) -> bytes:
        buf = b""
        while len(buf) < size:
            chunk = await stream.read(size - len(buf))
            if not chunk:
                break
            buf += chunk
        return buf

    def _prune(self) -> None:
        """Mantiene el cache acotado y elimina descargas a medias abandonadas."""
        try:
            now = time.time()
            files = []
            for p in self.cache_dir.iterdir():
                if not p.is_file():
                    continue
                if p.suffix == ".part":
                    if now - p.stat().st_mtime > 3600:
                        p.unlink(missing_ok=True)
                    continue
                files.append(p)
            files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
            for old in files[MEDIA_CACHE_MAX_FILES:]:
                old.unlink(missing_ok=True)
        except OSError as exc:
            log.warning("Error limpiando cache: %s", exc)
