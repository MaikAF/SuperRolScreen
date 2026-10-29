r"""Pruebas de humo del backend y de MediaCache (sin Discord).

Uso (desde server/):  .\.venv\Scripts\python.exe tests\smoke_test.py
Requiere que NO haya otro proceso en los puertos 8765 / 8766.
"""

from __future__ import annotations

import asyncio
import json
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

from aiohttp import web
import websockets

SERVER_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVER_DIR))

from media_cache import MediaCache, extract_og_candidates, sniff  # noqa: E402

API_PORT = 8765
FIXTURE_PORT = 8766

GIF = b"GIF89a" + b"\x01\x00\x01\x00\x80\x00\x00" + b"\x00" * 64
MP4 = b"\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00mp42isom" + b"\x00" * 64
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
WEBP = b"RIFF\x24\x00\x00\x00WEBPVP8 " + b"\x00" * 64

results: list[tuple[str, bool, str]] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    results.append((name, bool(cond), detail))


# ----------------------------------------------------------------------------
def test_sniff_and_og() -> None:
    check("sniff gif", sniff(GIF) == ("image", "gif"))
    check("sniff mp4", sniff(MP4) == ("video", "mp4"))
    check("sniff png", sniff(PNG) == ("image", "png"))
    check("sniff webp", sniff(WEBP) == ("image", "webp"))
    check("sniff html -> None", sniff(b"<!doctype html><html>") is None)
    html = (
        '<html><head><meta property="og:image" content="/still.png">'
        '<meta property="og:video" content="https://x.test/anim.mp4"></head></html>'
    )
    cands = extract_og_candidates(html, "https://klipy.com/gifs/abc")
    check("og: video antes que image", cands == ["https://x.test/anim.mp4", "https://klipy.com/still.png"], str(cands))


# ----------------------------------------------------------------------------
async def fixture_app() -> web.AppRunner:
    base = f"http://127.0.0.1:{FIXTURE_PORT}"
    app = web.Application()

    async def lying_png(_): return web.Response(body=GIF, content_type="image/png")  # GIF disfrazado
    async def fake_gif(_): return web.Response(body=MP4, content_type="image/gif")  # MP4 disfrazado
    async def anim(_): return web.Response(body=MP4, content_type="video/mp4")
    async def page(_):
        return web.Response(
            text=f'<html><head><meta property="og:video:url" content="{base}/anim.mp4">'
            f'<meta property="og:image" content="{base}/lying.png"></head></html>',
            content_type="text/html",
        )
    async def page_no_og(_): return web.Response(text="<html><body>nada</body></html>", content_type="text/html")
    async def heic(_): return web.Response(body=b"\x00\x00\x00\x18ftypheic" + b"\x00" * 64)

    app.router.add_get("/lying.png", lying_png)
    app.router.add_get("/fake.gif", fake_gif)
    app.router.add_get("/anim.mp4", anim)
    app.router.add_get("/gifs/klipy-page", page)
    app.router.add_get("/nada", page_no_og)
    app.router.add_get("/photo.heic", heic)
    runner = web.AppRunner(app)
    await runner.setup()
    await web.TCPSite(runner, "127.0.0.1", FIXTURE_PORT).start()
    return runner


async def test_media_cache() -> None:
    base = f"http://127.0.0.1:{FIXTURE_PORT}"
    runner = await fixture_app()
    tmp = Path(tempfile.mkdtemp(prefix="srs-cache-"))
    cache = MediaCache(tmp, "/media/cache")
    await cache.start()
    try:
        r = await cache.resolve([f"{base}/lying.png"])
        check("GIF con extensión .png -> image/.gif", r is not None and r.media_type == "image" and r.url.endswith(".gif"), str(r))

        r = await cache.resolve([f"{base}/fake.gif"])
        check("MP4 con extensión .gif -> video/.mp4", r is not None and r.media_type == "video" and r.url.endswith(".mp4"), str(r))

        r = await cache.resolve([f"{base}/gifs/klipy-page"])
        check("Página HTML (Klipy) -> og:video mp4", r is not None and r.media_type == "video", str(r))

        r = await cache.resolve([f"{base}/404", f"{base}/anim.mp4"])
        check("Candidato 404 -> usa el siguiente", r is not None and r.media_type == "video", str(r))

        r = await cache.resolve([f"{base}/nada"])
        check("HTML sin OG -> None", r is None, str(r))

        r = await cache.resolve([f"{base}/photo.heic"])
        check("HEIC -> rechazado", r is None, str(r))

        r = await cache.resolve(["http://127.0.0.1:1/caido.gif"])
        check("Host caído con .gif -> fallback URL remota", r is not None and r.url.startswith("http://127.0.0.1:1"), str(r))

        n_before = len(list(tmp.iterdir()))
        await cache.resolve([f"{base}/lying.png"])
        check("Cache hit no duplica archivos", len(list(tmp.iterdir())) == n_before)
        check("Sin .part huérfanos", not list(tmp.glob("*.part")))
    finally:
        await cache.close()
        await runner.cleanup()
        shutil.rmtree(tmp, ignore_errors=True)


# ----------------------------------------------------------------------------
def http_json(method: str, path: str, body: dict | None = None) -> tuple[int, dict]:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        f"http://127.0.0.1:{API_PORT}{path}", data=data, method=method,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status, json.loads(resp.read() or b"{}")
    except urllib.error.HTTPError as e:
        return e.code, {}


async def test_backend() -> None:
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "main:app", "--host", "127.0.0.1", "--port", str(API_PORT), "--log-level", "warning"],
        cwd=SERVER_DIR,
    )
    try:
        for _ in range(50):
            try:
                if http_json("GET", "/api/health")[0] == 200:
                    break
            except Exception:
                time.sleep(0.2)
        status, body = http_json("GET", "/api/clips")
        check("GET /api/clips", status == 200 and isinstance(body.get("clips"), list), str(body)[:120])

        ws_url = f"ws://127.0.0.1:{API_PORT}/ws"
        async with websockets.connect(ws_url) as overlay_a, websockets.connect(ws_url) as overlay_b, websockets.connect(ws_url) as bot:
            roll = {"type": "DICE_ROLL", "user": "Tester", "dice_count": 5, "successes": 3}
            await bot.send(json.dumps(roll))
            got_a = json.loads(await asyncio.wait_for(overlay_a.recv(), 3))
            got_b = json.loads(await asyncio.wait_for(overlay_b.recv(), 3))
            check("Fan-out a 2 overlays", got_a == roll and got_b == roll)
            try:
                await asyncio.wait_for(bot.recv(), 0.7)
                check("El emisor no recibe su propio evento", False)
            except asyncio.TimeoutError:
                check("El emisor no recibe su propio evento", True)

            await bot.send("no-json")
            await bot.send(json.dumps({"type": "HACK"}))
            media = {"type": "NEW_MEDIA", "user": "Tester", "url": "/media/cache/x.gif", "media_type": "image"}
            await bot.send(json.dumps(media))
            got = json.loads(await asyncio.wait_for(overlay_a.recv(), 3))
            check("Mensajes inválidos descartados, válido pasa", got == media, str(got))

            status, body = http_json("POST", "/api/events", media)
            got = json.loads(await asyncio.wait_for(overlay_b.recv(), 3))
            check("POST /api/events -> overlays", status == 200 and got == media, f"{status} {body}")
            status, _ = http_json("POST", "/api/events", {"type": "BAD"})
            check("POST /api/events inválido -> 422", status == 422)

        # Range request sobre el HUD (necesario para <video> en Chromium)
        req = urllib.request.Request(
            f"http://127.0.0.1:{API_PORT}/media/HUD/Dados%20Hud.png", headers={"Range": "bytes=0-99"}
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            check("Range requests en /media", resp.status == 206 and len(resp.read()) == 100, str(resp.status))
    finally:
        proc.terminate()
        proc.wait(5)


async def main() -> None:
    test_sniff_and_og()
    await test_media_cache()
    await test_backend()
    width = max(len(n) for n, *_ in results)
    for name, ok, detail in results:
        print(f"{'PASS' if ok else 'FAIL'}  {name.ljust(width)}  {'' if ok else detail}")
    failed = sum(not ok for _, ok, _ in results)
    print(f"\n{len(results) - failed}/{len(results)} OK")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    asyncio.run(main())
