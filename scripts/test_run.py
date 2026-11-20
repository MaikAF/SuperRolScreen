import unittest
from unittest.mock import patch
from pathlib import Path
import os
import shutil
import sys

# Añadir el root al path para poder importar scripts.run
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.append(str(REPO_ROOT))

from scripts.run import (
    build_window_args,
    GAMEPLAY_WINDOW_SIZE,
    HUD_WINDOW_SIZE,
    LANDSCAPE_WINDOW_SIZE,
    parse_args,
    find_edge,
    with_layout,
    window_specs,
)

class TestRun(unittest.TestCase):
    def test_build_window_args(self):
        browser = "msedge.exe"
        url = "http://localhost:5173"
        profile_dir = Path("C:/tmp/profile")
        args = build_window_args(browser, url, profile_dir)
        
        self.assertEqual(
            args,
            [
                browser,
                f"--user-data-dir={profile_dir}",
                f"--app={url}",
                "--window-size=1920,1080",
                "--no-first-run",
                "--no-default-browser-check",
                "--autoplay-policy=no-user-gesture-required",
                "--disable-background-timer-throttling",
                "--disable-backgrounding-occluded-windows",
                "--disable-renderer-backgrounding",
                "--disable-features=CalculateNativeWinOcclusion,IntensiveWakeUpThrottling",
            ],
        )

    def test_build_window_args_tiktok(self):
        browser = "msedge.exe"
        url = "http://localhost:5173"
        profile_dir = Path("C:/tmp/profile")
        # Test gameplay size (1920,1080)
        args_gameplay = build_window_args(browser, url, profile_dir, size=GAMEPLAY_WINDOW_SIZE)
        self.assertIn("--window-size=1920,1080", args_gameplay)
        self.assertNotIn("--window-size=1080,1920", args_gameplay)
        
        # Test HUD size (1080,656)
        args_hud = build_window_args(browser, url, profile_dir, size=HUD_WINDOW_SIZE)
        self.assertIn("--window-size=1080,656", args_hud)
        self.assertNotIn("--window-size=1920,1080", args_hud)

    def test_with_layout(self):
        self.assertEqual(with_layout("http://localhost:5173", None), "http://localhost:5173")
        self.assertEqual(with_layout("http://localhost:5173", "gameplay"), "http://localhost:5173?layout=gameplay")
        self.assertEqual(
            with_layout("http://localhost:8000/overlay/", "hud"), "http://localhost:8000/overlay/?layout=hud"
        )

    def test_parse_args_window(self):
        args = parse_args(["dev", "--window"])
        self.assertTrue(args.window)
        
        args = parse_args(["dev"])
        self.assertFalse(args.window)

    def test_parse_args_tiktok(self):
        args = parse_args(["dev", "--window", "--tiktok"])
        self.assertTrue(args.tiktok)
        
        args = parse_args(["dev"])
        self.assertFalse(args.tiktok)

    @patch("shutil.which")
    @patch("os.environ.get")
    def test_find_edge_path(self, mock_env_get, mock_which):
        mock_which.return_value = "C:\\msedge.exe"
        self.assertEqual(find_edge(), "C:\\msedge.exe")

    @patch("shutil.which")
    @patch("os.environ.get")
    @patch("pathlib.Path.is_file", return_value=True)
    def test_find_edge_programfiles(self, mock_isfile, mock_env_get, mock_which):
        mock_which.return_value = None
        mock_env_get.side_effect = lambda k, d=None: "C:\\Program Files (x86)" if k == "ProgramFiles(x86)" else d
        self.assertEqual(
            find_edge(), str(Path("C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe"))
        )

    @patch("shutil.which")
    @patch("os.environ.get")
    @patch("pathlib.Path.is_file", return_value=False)
    def test_find_edge_none(self, mock_isfile, mock_env_get, mock_which):
        mock_which.return_value = None
        self.assertIsNone(find_edge())

    def test_window_specs(self):
        # No tiktok mode
        specs = window_specs(False)
        self.assertEqual(len(specs), 1)
        self.assertEqual(specs[0][0], "overlay")
        self.assertIsNone(specs[0][1])  # No layout
        self.assertEqual(specs[0][2], LANDSCAPE_WINDOW_SIZE)
        
        # Tiktok mode
        specs = window_specs(True)
        self.assertEqual(len(specs), 2)
        
        # Gameplay spec
        gameplay_spec = next(s for s in specs if s[0] == "gameplay")
        self.assertEqual(gameplay_spec[0], "gameplay")
        self.assertEqual(gameplay_spec[1], "gameplay")
        self.assertEqual(gameplay_spec[2], GAMEPLAY_WINDOW_SIZE)
        
        # HUD spec
        hud_spec = next(s for s in specs if s[0] == "hud")
        self.assertEqual(hud_spec[0], "hud")
        self.assertEqual(hud_spec[1], "hud")
        self.assertEqual(hud_spec[2], HUD_WINDOW_SIZE)

    def test_shutdown_order_and_targets(self):
        from unittest.mock import MagicMock, call
        import scripts.run as run

        bot, client, backend = object(), object(), object()
        edges = [object(), object()]
        calls = MagicMock()
        with patch.object(run, "stop_process", calls.stop_process), patch.object(
            run, "stop_window", calls.stop_window
        ):
            run.shutdown(bot=bot, edges=edges, client=client, backend=backend)

        self.assertEqual(
            calls.mock_calls,
            [
                call.stop_process(bot, "bot"),
                call.stop_window(edges[0]),
                call.stop_window(edges[1]),
                call.stop_process(client, "client"),
                call.stop_process(backend, "backend"),
            ],
        )


if __name__ == "__main__":
    unittest.main()
