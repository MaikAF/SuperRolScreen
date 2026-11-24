r"""Tests de la función `origin_allowed` del backend.

Uso (desde server/):  .\.venv\Scripts\python.exe tests\test_origin.py -v
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from main import origin_allowed  # noqa: E402


class OriginAllowedTest(unittest.TestCase):
    def test_none_origin_allowed(self):
        """None (clientes no navegador) está permitido."""
        self.assertTrue(origin_allowed(None))

    def test_localhost_5173_allowed(self):
        """http://localhost:5173 está permitido."""
        self.assertTrue(origin_allowed("http://localhost:5173"))

    def test_127_0_0_1_5173_allowed(self):
        """http://127.0.0.1:5173 está permitido."""
        self.assertTrue(origin_allowed("http://127.0.0.1:5173"))

    def test_localhost_8000_allowed(self):
        """http://localhost:8000 está permitido (WebSocket desde overlay)."""
        self.assertTrue(origin_allowed("http://localhost:8000"))

    def test_127_0_0_1_8000_allowed(self):
        """http://127.0.0.1:8000 está permitido (WebSocket desde overlay)."""
        self.assertTrue(origin_allowed("http://127.0.0.1:8000"))

    def test_empty_string_not_allowed(self):
        """String vacío no está permitido."""
        self.assertFalse(origin_allowed(""))

    def test_null_string_not_allowed(self):
        """String \"null\" no está permitido."""
        self.assertFalse(origin_allowed("null"))

    def test_evil_origin_not_allowed(self):
        """Origen evil no está permitido."""
        self.assertFalse(origin_allowed("http://evil.test"))

    def test_wrong_port_not_allowed(self):
        """Puerto 5174 no está permitido."""
        self.assertFalse(origin_allowed("http://localhost:5174"))

    def test_https_not_allowed(self):
        """HTTPS no está permitido."""
        self.assertFalse(origin_allowed("https://localhost:5173"))

    def test_trailing_slash_not_allowed(self):
        """Origen con barra final no está permitido."""
        self.assertFalse(origin_allowed("http://localhost:5173/"))

    def test_local_network_not_allowed(self):
        """IP de red local no está permitido."""
        self.assertFalse(origin_allowed("http://192.168.1.10:5173"))


if __name__ == "__main__":
    unittest.main()