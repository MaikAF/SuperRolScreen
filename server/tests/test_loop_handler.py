r"""Tests del handler de excepción del bucle de eventos (_ignore_proactor_reset).

Uso (desde server/): .\.venv\Scripts\python.exe tests\test_loop_handler.py -v
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from main import _ignore_proactor_reset  # noqa: E402


class _Handle:
    """Handle simulado: repr() de una instancia usa el __repr__ de la clase."""

    def __init__(self, text: str) -> None:
        self._text = text

    def __repr__(self) -> str:
        return self._text


def _make_context(exception, handle=None, message=""):
    return {
        "exception": exception,
        "handle": handle,
        "message": message,
    }


class IgnoreProactorResetTest(unittest.TestCase):
    def test_connection_reset_error_call_connection_lost_not_call_default(self):
        """ConnectionResetError con _call_connection_lost no llama al handler por defecto."""
        default_handler = MagicMock()
        loop = MagicMock()
        loop.default_exception_handler = default_handler

        handle = _Handle("<Handle _call_connection_lost()>")

        context = _make_context(ConnectionResetError("conexión reseteada"), handle=handle)
        _ignore_proactor_reset(loop, context)

        default_handler.assert_not_called()

    def test_connection_aborted_error_call_connection_lost_not_call_default(self):
        """ConnectionAbortedError con _call_connection_lost no llama al handler por defecto."""
        default_handler = MagicMock()
        loop = MagicMock()
        loop.default_exception_handler = default_handler

        handle = _Handle("<Handle _call_connection_lost()>")

        context = _make_context(ConnectionAbortedError("conexión abortada"), handle=handle)
        _ignore_proactor_reset(loop, context)

        default_handler.assert_not_called()

    def test_connection_reset_error_other_callback_calls_default(self):
        """ConnectionResetError en otro callback SÍ llama al handler por defecto."""
        default_handler = MagicMock()
        loop = MagicMock()
        loop.default_exception_handler = default_handler

        handle = _Handle("<Handle otro_callback()>")

        context = _make_context(ConnectionResetError("conexión reseteada"), handle=handle)
        _ignore_proactor_reset(loop, context)

        default_handler.assert_called_once_with(context)

    def test_value_error_call_connection_lost_calls_default(self):
        """ValueError en _call_connection_lost SÍ llama al handler por defecto."""
        default_handler = MagicMock()
        loop = MagicMock()
        loop.default_exception_handler = default_handler

        handle = _Handle("<Handle _call_connection_lost()>")

        context = _make_context(ValueError("otro error"), handle=handle)
        _ignore_proactor_reset(loop, context)

        default_handler.assert_called_once_with(context)

    def test_context_without_exception_calls_default(self):
        """Contexto sin exception SÍ llama al handler por defecto."""
        default_handler = MagicMock()
        loop = MagicMock()
        loop.default_exception_handler = default_handler

        context = _make_context(None)
        _ignore_proactor_reset(loop, context)

        default_handler.assert_called_once_with(context)

    def test_connection_reset_error_message_contains_call_connection_lost_not_call_default(self):
        """ConnectionResetError cuyo message menciona _call_connection_lost no llama al default."""
        default_handler = MagicMock()
        loop = MagicMock()
        loop.default_exception_handler = default_handler

        context = _make_context(
            ConnectionResetError("error"),
            handle=None,
            message="Exception in callback _call_connection_lost()",
        )
        _ignore_proactor_reset(loop, context)

        default_handler.assert_not_called()


if __name__ == "__main__":
    unittest.main()
