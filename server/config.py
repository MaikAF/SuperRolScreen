"""Configuración central del servidor (rutas y variables de entorno)."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

SERVER_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SERVER_DIR.parent

# Carga siempre server/.env, sin importar desde qué carpeta se lance el proceso.
load_dotenv(SERVER_DIR / ".env")


def _int_env(name: str) -> int:
    raw = (os.getenv(name) or "").strip().strip('"').strip("'")
    try:
        return int(raw)
    except ValueError:
        return 0


# --- Discord -----------------------------------------------------------------
DISCORD_TOKEN: str = (os.getenv("DISCORD_TOKEN") or "").strip().strip('"').strip("'")
DICE_CHANNEL_ID: int = _int_env("DICE_CHANNEL_ID")
MEDIA_CHANNEL_ID: int = _int_env("MEDIA_CHANNEL_ID")

# --- Rutas -------------------------------------------------------------------
MEDIA_DIR = PROJECT_ROOT / "media"
GAMEPLAY_DIR = MEDIA_DIR / "Gameplay"
HUD_DIR = MEDIA_DIR / "HUD"
CACHE_DIR = MEDIA_DIR / "cache"  # GIFs/imágenes descargados desde Discord
CLIENT_DIST_DIR = PROJECT_ROOT / "client" / "dist"

# URL pública (relativa al servidor) bajo la que se sirve CACHE_DIR.
CACHE_URL_PREFIX = "/media/cache"

# --- Límites -----------------------------------------------------------------
GAMEPLAY_EXTENSIONS = {".mp4", ".webm", ".m4v", ".mov"}
MEDIA_MAX_BYTES = 60 * 1024 * 1024  # 60 MB por archivo
MEDIA_CACHE_MAX_FILES = 200  # se borran los más antiguos al superar este número
MEDIA_DOWNLOAD_TIMEOUT_S = 25
