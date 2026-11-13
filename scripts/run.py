#!/usr/bin/env python3
"""Orquestador de SuperRolScreen.

Levanta en una sola consola el backend FastAPI, el overlay (Vite o build de
produccion) y el bot de Discord, unifica sus registros con prefijos y los
detiene todos de forma limpia con Ctrl+C.

Solo usa la biblioteca estandar: se ejecuta con el Python del venv o con
``py -3.12``.

Uso::

    python scripts/run.py [dev|obs] [--no-bot] [--no-client]
"""

from __future__ import annotations

import argparse
import os
import shutil
import signal
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import IO

# --------------------------------------------------------------------------- #
# Rutas (relativas a la ubicacion de este script, no al directorio actual)
# --------------------------------------------------------------------------- #

REPO_ROOT = Path(__file__).resolve().parent.parent
SERVER_DIR = REPO_ROOT / "server"
CLIENT_DIR = REPO_ROOT / "client"
VENV_PYTHON = SERVER_DIR / ".venv" / "Scripts" / "python.exe"
NODE_MODULES = CLIENT_DIR / "node_modules"
ENV_FILE = SERVER_DIR / ".env"

BACKEND_HOST = "127.0.0.1"
BACKEND_PORT = 8000
CLIENT_PORT = 5173
HEALTH_URL = f"http://{BACKEND_HOST}:{BACKEND_PORT}/api/health"

IS_WINDOWS = sys.platform == "win32"

# --------------------------------------------------------------------------- #
# Salida unificada con prefijos, colores opcionales y lock anti-intercalado
# --------------------------------------------------------------------------- #

_PRINT_LOCK = threading.Lock()
_COLORS = {
    "backend": "\033[36m",  # cian
    "client": "\033[35m",   # magenta
    "bot": "\033[33m",      # amarillo
    "run": "\033[32m",      # verde
}
_RESET = "\033[0m"

# NO_COLOR (https://no-color.org) desactiva los colores.
_USE_COLOR = not os.environ.get("NO_COLOR") and sys.stdout.isatty()


def _get_npm() -> str | None:
    """Devuelve la ruta a npm (npm.cmd en Windows) o None si no esta en el PATH."""
    return shutil.which("npm.cmd" if IS_WINDOWS else "npm")


def log(prefix: str, message: str) -> None:
    """Imprime una linea con prefijo, sin mezclarla con las de otros hilos."""
    if _USE_COLOR:
        line = f"{_COLORS.get(prefix, '')}[{prefix}]{_RESET} {message}"
    else:
        line = f"[{prefix}] {message}"
    with _PRINT_LOCK:
        try:
            print(line, flush=True)
        except UnicodeEncodeError:
            # Consola con codificacion limitada: degradar solo esta linea.
            enc = sys.stdout.encoding or "ascii"
            print(line.encode(enc, "replace").decode(enc), flush=True)


def log_run(message: str) -> None:
    """Atajo para mensajes del propio orquestador."""
    log("run", message)


# --------------------------------------------------------------------------- #
# Preflight
# --------------------------------------------------------------------------- #


def port_is_free(port: int) -> bool:
    """Comprueba si un puerto TCP esta libre en localhost (IPv4 e IPv6).

    No se usa SO_REUSEADDR: en Windows permite enlazar un puerto ya ocupado y
    el chequeo daria falsos negativos. Ademas se intenta conectar, porque un
    servidor escuchando en 0.0.0.0/:: (Vite con host:true) no siempre impide
    enlazar 127.0.0.1.
    """
    for family, addr in ((socket.AF_INET, "127.0.0.1"), (socket.AF_INET6, "::1")):
        try:
            with socket.socket(family, socket.SOCK_STREAM) as sock:
                sock.settimeout(0.3)
                if sock.connect_ex((addr, port)) == 0:
                    return False
        except OSError:
            pass  # familia no disponible
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        if IS_WINDOWS and hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        try:
            sock.bind((BACKEND_HOST, port))
        except OSError:
            return False
    return True


def preflight(need_client: bool, need_bot: bool) -> None:
    """Verifica los requisitos previos y aborta con un mensaje accionable."""
    if not VENV_PYTHON.is_file():
        log_run(f"No se encontro el interprete del venv: {VENV_PYTHON}")
        log_run("Instala el backend (README -> Instalacion):")
        log_run("  cd server")
        log_run("  py -3.12 -m venv .venv")
        log_run("  .\\.venv\\Scripts\\python.exe -m pip install -r requirements.txt")
        raise SystemExit(1)

    if need_client and not NODE_MODULES.is_dir():
        log_run(f"No se encontro {NODE_MODULES}")
        log_run("Instala el cliente (README -> Instalacion):")
        log_run("  cd client")
        log_run("  npm ci")
        raise SystemExit(1)

    if need_bot and not ENV_FILE.is_file():
        log_run(f"No existe {ENV_FILE}.")
        log_run("Crea server/.env con DISCORD_TOKEN y DICE_CHANNEL_ID (README -> Configuracion de Discord y archivos).")
        log_run("O arranca sin bot con --no-bot (pruebas manuales via /api/events).")
        raise SystemExit(1)

    ports = [BACKEND_PORT]
    if need_client:
        ports.append(CLIENT_PORT)
    for port in ports:
        if not port_is_free(port):
            log_run(f"El puerto {port} esta ocupado en {BACKEND_HOST}.")
            log_run("Probablemente ya hay una instancia de SuperRolScreen corriendo; detenla antes de continuar.")
            raise SystemExit(1)

    log_run("Preflight OK.")


# --------------------------------------------------------------------------- #
# Lanzamiento de hijos
# --------------------------------------------------------------------------- #


def _child_env() -> dict[str, str]:
    """Copia el entorno actual y asegura UTF-8 sin perdida."""
    env = dict(os.environ)
    env["PYTHONUNBUFFERED"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    return env


def _spawn(args: list[str], cwd: Path) -> subprocess.Popen[str]:
    """Lanza un proceso con lista de argumentos, sin shell."""
    # Grupo propio en Windows: Ctrl+C no llega directo a los hijos y el
    # orquestador controla el orden de apagado (CTRL_BREAK -> taskkill).
    flags = subprocess.CREATE_NEW_PROCESS_GROUP if IS_WINDOWS else 0
    return subprocess.Popen(
        args,
        cwd=str(cwd),
        creationflags=flags,
        stdin=subprocess.DEVNULL,
        env=_child_env(),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
    )


def _pump(proc: subprocess.Popen[str], prefix: str) -> None:
    """Hilo: reenvia la salida del hijo a la consola unificada."""
    stream: IO[str] | None = proc.stdout
    if stream is None:
        return
    try:
        for raw in stream:
            line = raw.rstrip("\r\n")
            if line:
                log(prefix, line)
    except (ValueError, OSError):
        # El flujo se cerro al terminar el proceso: nada que hacer.
        pass


def _start_reader(proc: subprocess.Popen[str], prefix: str) -> None:
    threading.Thread(target=_pump, args=(proc, prefix), daemon=True).start()


def start_backend() -> subprocess.Popen[str]:
    """Lanza uvicorn con el Python del venv."""
    log_run(f"Iniciando backend en http://{BACKEND_HOST}:{BACKEND_PORT} ...")
    proc = _spawn(
        [
            str(VENV_PYTHON),
            "-m",
            "uvicorn",
            "main:app",
            "--host",
            BACKEND_HOST,
            "--port",
            str(BACKEND_PORT),
        ],
        SERVER_DIR,
    )
    _start_reader(proc, "backend")
    return proc


def start_client() -> subprocess.Popen[str]:
    """Lanza el servidor de desarrollo de Vite."""
    npm = _get_npm()
    if npm is None:
        log_run("No se encontro npm en el PATH. Instala Node.js 22 (README -> Requisitos).")
        raise SystemExit(1)
    log_run(f"Iniciando overlay Vite en http://localhost:{CLIENT_PORT} ...")
    proc = _spawn([npm, "run", "dev"], CLIENT_DIR)
    _start_reader(proc, "client")
    return proc


def start_bot() -> subprocess.Popen[str]:
    """Lanza el listener de Discord con el Python del venv."""
    log_run("Iniciando bot de Discord ...")
    proc = _spawn([str(VENV_PYTHON), "discord_listener.py"], SERVER_DIR)
    _start_reader(proc, "bot")
    return proc


def wait_for_health(backend: subprocess.Popen[str], timeout: float = 20.0) -> None:
    """Espera a que /api/health responda; aborta si el backend muere."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if backend.poll() is not None:
            log_run(f"El backend termino durante el arranque (codigo {backend.returncode}).")
            raise SystemExit(backend.returncode or 1)
        try:
            with urllib.request.urlopen(HEALTH_URL, timeout=1.0) as resp:
                if resp.status == 200:
                    log_run("Backend listo (/api/health = 200).")
                    return
        except (urllib.error.URLError, OSError, TimeoutError):
            pass
        time.sleep(0.5)
    log_run(f"El backend no respondio en {HEALTH_URL} tras {int(timeout)} s.")
    raise SystemExit(1)


def run_build() -> None:
    """Ejecuta el build de produccion del cliente para el modo OBS."""
    npm = _get_npm()
    if npm is None:
        log_run("No se encontro npm en el PATH. Instala Node.js 22 (README -> Requisitos).")
        raise SystemExit(1)
    log_run("Compilando overlay (npm run build) ...")
    result = subprocess.run(
        [npm, "run", "build"],
        cwd=str(CLIENT_DIR),
        env=_child_env(),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    for line in (result.stdout or "").splitlines():
        if line.strip():
            log("client", line)
    if result.returncode != 0:
        log_run(f"El build fallo (codigo {result.returncode}). Se aborta el arranque.")
        raise SystemExit(result.returncode)
    log_run("Build completado.")


# --------------------------------------------------------------------------- #
# Apagado
# --------------------------------------------------------------------------- #


def stop_process(proc: subprocess.Popen[str] | None, name: str) -> None:
    """Detiene un hijo; idempotente si ya termino. Mata el arbol en Windows."""
    if proc is None or proc.poll() is not None:
        return
    log_run(f"Deteniendo {name} (PID {proc.pid}) ...")
    if IS_WINDOWS:
        # taskkill sin /F no cierra procesos de consola sin ventana; se envia
        # CTRL_BREAK al grupo (uvicorn/node/python lo atienden) y, si no basta,
        # se fuerza el cierre del arbol completo.
        try:
            os.kill(proc.pid, signal.CTRL_BREAK_EVENT)
        except OSError:
            pass
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            log_run(f"{name} sigue vivo; forzando cierre del arbol.")
            subprocess.run(
                ["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                log_run(f"No se pudo detener {name} (PID {proc.pid}).")
    else:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()


def shutdown(
    bot: subprocess.Popen[str] | None,
    client: subprocess.Popen[str] | None,
    backend: subprocess.Popen[str] | None,
) -> None:
    """Detiene en orden inverso al arranque: bot -> Vite -> backend."""
    stop_process(bot, "bot")
    stop_process(client, "client")
    stop_process(backend, "backend")


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Orquestador de procesos de SuperRolScreen.",
    )
    parser.add_argument(
        "mode",
        nargs="?",
        default="dev",
        choices=("dev", "obs"),
        help="dev (por defecto): backend + Vite + bot. obs: build + backend + bot.",
    )
    parser.add_argument("--no-bot", action="store_true", help="No lanzar el bot de Discord.")
    parser.add_argument("--no-client", action="store_true", help="No lanzar Vite (solo en dev).")
    return parser.parse_args(argv)


def _install_break_handler() -> None:
    """En Windows trata Ctrl+Break como Ctrl+C para pasar por el apagado limpio."""
    if IS_WINDOWS and hasattr(signal, "SIGBREAK"):
        def _handler(signum: int, frame: object) -> None:
            raise KeyboardInterrupt
        signal.signal(signal.SIGBREAK, _handler)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    _install_break_handler()
    wants_client = args.mode == "dev" and not args.no_client
    wants_bot = not args.no_bot

    preflight(need_client=(wants_client or args.mode == "obs"), need_bot=wants_bot)

    if args.mode == "obs":
        run_build()

    backend: subprocess.Popen[str] | None = None
    client: subprocess.Popen[str] | None = None
    bot: subprocess.Popen[str] | None = None
    exit_code = 0

    try:
        backend = start_backend()
        wait_for_health(backend)

        if wants_client:
            client = start_client()

        if wants_bot:
            bot = start_bot()

        if args.mode == "obs":
            log_run(f"Overlay OBS: http://localhost:{BACKEND_PORT}/overlay/")
        elif wants_client:
            log_run(f"Overlay web: http://localhost:{CLIENT_PORT}")

        activos = ["backend"]
        if client is not None:
            activos.append("Vite")
        if bot is not None:
            activos.append("bot")
        log_run("Procesos activos: " + ", ".join(activos) + ". Pulsa Ctrl+C para detener.")

        # Supervision: el backend y Vite son criticos; el bot no.
        while True:
            if backend.poll() is not None:
                log_run(f"El backend termino con codigo {backend.returncode}. Deteniendo todo.")
                exit_code = backend.returncode or 1
                break
            if client is not None and client.poll() is not None:
                log_run(f"Vite termino con codigo {client.returncode}. Deteniendo todo.")
                exit_code = client.returncode or 1
                break
            if bot is not None and bot.poll() is not None:
                log_run(
                    f"el bot termino con codigo {bot.returncode}; "
                    "se mantienen backend y overlay activos."
                )
                bot = None
            time.sleep(0.25)

    except KeyboardInterrupt:
        log_run("Ctrl+C recibido. Deteniendo procesos ...")
        exit_code = 0
    except SystemExit as exc:
        exit_code = int(exc.code or 0)
        raise
    finally:
        shutdown(bot, client, backend)
        log_run("Todo detenido.")

    return exit_code


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        # Ctrl+C durante preflight o build: no hay hijos persistentes que detener.
        log_run("Interrumpido.")
        sys.exit(130)
