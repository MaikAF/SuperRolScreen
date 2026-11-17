import json
import os
import discord
from dotenv import load_dotenv

from music_detect import extract_now_playing, is_music_bot

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")
# Convertimos el ID a entero (int) para poder compararlo con message.channel.id
DICE_CHANNEL_ID = int(os.getenv("DICE_CHANNEL_ID", "0"))
MEDIA_CHANNEL_ID = int(os.getenv("MEDIA_CHANNEL_ID", "0"))
MUSIC_CHANNEL_ID = int(os.getenv("MUSIC_CHANNEL_ID", "0"))

if not TOKEN or DICE_CHANNEL_ID == 0:
    raise ValueError("Debes configurar DISCORD_TOKEN y DICE_CHANNEL_ID en tu archivo .env")

# Configuramos los intents requeridos para leer mensajes
intents = discord.Intents.default()
intents.message_content = True

# enable_debug_events: habilita on_socket_raw_receive (volcado crudo del canal de música).
client = discord.Client(intents=intents, enable_debug_events=True)


@client.event
async def on_ready():
    print(f"=== Bot conectado como {client.user} ===")
    print(f"Escuchando mensajes en el canal ID: {DICE_CHANNEL_ID}...\n")
    if MEDIA_CHANNEL_ID:
        print(f"También inspeccionando canal MEDIA {MEDIA_CHANNEL_ID}")
    if MUSIC_CHANNEL_ID:
        print(f"También inspeccionando canal MÚSICA {MUSIC_CHANNEL_ID}")


def dump_message(message: discord.Message, label: str) -> None:
    cid = message.channel.id
    print(f"\n------------------ {label} ------------------")
    print(f"Canal: {cid}  Autor: {message.author.name} (Bot: {message.author.bot}, display_name: {getattr(message.author, 'display_name', '')})")
    print(f"Contenido plano (content):\n{repr(message.content)}")

    if message.embeds:
        print(f"\nTiene {len(message.embeds)} embed(s):")
        for i, embed in enumerate(message.embeds):
            print(f"--- Embed {i + 1} ---")
            print(f"Title: {embed.title!r}")
            print(f"Description: {embed.description!r}")
            print(f"Embed author name: {embed.author.name!r}")
            print(f"Embed footer text: {embed.footer.text!r}")
            if embed.fields:
                print("Fields:")
                for f in embed.fields:
                    print(f"  - {f.name!r}: {f.value!r}")
    print(f"Flags: {message.flags.value} (components_v2={getattr(message.flags, 'components_v2', '?')})")
    if message.attachments:
        print("Adjuntos:")
        for a in message.attachments:
            print(f"  - {a.filename!r} ({a.content_type}, {a.size} B)")
    if message.components:
        print("Componentes:")
        dump_components(message.components, 1)
    if MUSIC_CHANNEL_ID and cid == MUSIC_CHANNEL_ID:
        print(f"\n[music_detect] is_music_bot={is_music_bot(message.author)} "
              f"now_playing={extract_now_playing(message.content, message.embeds, message.components)!r}")
    print("-------------------------------------------\n")


def dump_components(components, depth: int) -> None:
    pad = "  " * depth
    for c in components:
        kind = type(c).__name__
        extra = []
        for attr in ("content", "label", "placeholder", "custom_id"):
            value = getattr(c, attr, None)
            if value:
                extra.append(f"{attr}={value!r}")
        media = getattr(c, "media", None)
        if media is not None and getattr(media, "url", None):
            extra.append(f"media={media.url!r}")
        print(f"{pad}- {kind} {' '.join(extra)}")
        accessory = getattr(c, "accessory", None)
        if accessory is not None:
            dump_components([accessory], depth + 1)
        children = getattr(c, "children", None) or getattr(c, "items", None)
        if children and not isinstance(children, str):
            dump_components(children, depth + 1)


@client.event
async def on_socket_raw_receive(raw):
    # JSON crudo del gateway para el canal de música: muestra la forma exacta
    # del mensaje aunque discord.py no la interprete.
    if not MUSIC_CHANNEL_ID or not isinstance(raw, str):
        return
    try:
        msg = json.loads(raw)
    except ValueError:
        return
    if msg.get("t") not in ("MESSAGE_CREATE", "MESSAGE_UPDATE"):
        return
    data = msg.get("d") or {}
    if str(data.get("channel_id")) != str(MUSIC_CHANNEL_ID):
        return
    text = json.dumps(
        {k: data.get(k) for k in ("content", "flags", "embeds", "components", "attachments") if k in data},
        ensure_ascii=False,
        indent=1,
    )
    print(f"\n[RAW {msg['t']}] {text[:6000]}")


@client.event
async def on_message(message: discord.Message):
    # Solo los canales configurados; no se ignoran bots: se quiere inspeccionarlos.
    if message.channel.id in (DICE_CHANNEL_ID, MEDIA_CHANNEL_ID, MUSIC_CHANNEL_ID):
        dump_message(message, "Mensaje")


@client.event
async def on_message_edit(_before: discord.Message, after: discord.Message):
    # Los bots de música suelen editar su aviso de "now playing".
    if MUSIC_CHANNEL_ID and after.channel.id == MUSIC_CHANNEL_ID:
        dump_message(after, "Edición (MÚSICA)")


client.run(TOKEN)
