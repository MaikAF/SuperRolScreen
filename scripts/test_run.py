import unittest
from unittest.mock import patch
from pathlib import Path
import os
import shutil
import sys

# Añadir el root al path para poder importar scripts.run
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.append(str(REPO_ROOT))

from scripts.run import build_window_args, parse_args, find_edge

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

    def test_parse_args_window(self):
        args = parse_args(["dev", "--window"])
        self.assertTrue(args.window)
        
        args = parse_args(["dev"])
        self.assertFalse(args.window)

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

if __name__ == "__main__":
    unittest.main()
