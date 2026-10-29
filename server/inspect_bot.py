import os
import discord
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")
# Convertimos el ID a entero (int) para poder compararlo con message.channel.id
DICE_CHANNEL_ID = int(os.getenv("DICE_CHANNEL_ID", "0"))

if not TOKEN or DICE_CHANNEL_ID == 0:
    raise ValueError("Debes configurar DISCORD_TOKEN y DICE_CHANNEL_ID en tu archivo .env")

# Configuramos los intents requeridos para leer mensajes
intents = discord.Intents.default()
intents.message_content = True

client = discord.Client(intents=intents)


@client.event
async def on_ready():
    print(f"=== Bot conectado como {client.user} ===")
    print(f"Escuchando mensajes en el canal ID: {DICE_CHANNEL_ID}...\n")


@client.event
async def on_message(message: discord.Message):
    # Ignorar mensajes de otros canales
    if message.channel.id != DICE_CHANNEL_ID:
        return

    # No ignoramos bots aquí porque precisamente queremos inspeccionar al bot de dados
    print("\n-------------------------------------------")
    print(f"Autor: {message.author.name} (Bot: {message.author.bot})")
    print(f"Contenido plano (content):\n{repr(message.content)}")

    if message.embeds:
        print(f"\nTiene {len(message.embeds)} embed(s):")
        for i, embed in enumerate(message.embeds):
            print(f"--- Embed {i + 1} ---")
            print(f"Title: {embed.title}")
            print(f"Description: {embed.description}")
            if embed.fields:
                print("Fields:")
                for f in embed.fields:
                    print(f"  - {f.name}: {f.value}")
    print("-------------------------------------------\n")


client.run(TOKEN)