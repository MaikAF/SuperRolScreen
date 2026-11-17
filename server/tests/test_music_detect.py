r"""Tests de music_detect y de la validación de NOW_PLAYING en main.validate_event.

Uso (desde server/): .\.venv\Scripts\python.exe tests\test_music_detect.py
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from main import validate_event  # noqa: E402
from music_detect import (  # noqa: E402
    NOW_PLAYING_TITLE_MAX,
    clean_title,
    extract_now_playing,
    is_music_bot,
)


def embed(title=None, description=None, author=None, fields=None):
    return SimpleNamespace(
        title=title,
        description=description,
        author=SimpleNamespace(name=author) if author is not None else None,
        fields=[SimpleNamespace(name=n, value=v) for n, v in (fields or [])],
    )


class IsMusicBotTest(unittest.TestCase):
    def test_flavibot(self) -> None:
        self.assertTrue(is_music_bot(SimpleNamespace(bot=True, name="FlaviBot", display_name="FlaviBot")))

    def test_hint_in_display_name_only(self) -> None:
        self.assertTrue(is_music_bot(SimpleNamespace(bot=True, name="music", display_name="Flavi")))

    def test_human_named_flavio(self) -> None:
        self.assertFalse(is_music_bot(SimpleNamespace(bot=False,name="Flavio", display_name="Flavio")))

    def test_other_bot(self) -> None:
        self.assertFalse(is_music_bot(SimpleNamespace(bot=True, name="DiceBot")))

    def test_none(self) -> None:
        self.assertFalse(is_music_bot(None))


class CleanTitleTest(unittest.TestCase):
    def test_markdown_and_link(self) -> None:
        self.assertEqual(clean_title("**[Canción](https://youtu.be/x)** - 3:45"), "Canción - 3:45")

    def test_loose_url_removed(self) -> None:
        self.assertEqual(clean_title("Canción https://youtu.be/x"), "Canción")

    def test_keeps_underscores_inside_words(self) -> None:
        self.assertEqual(clean_title("my_song"), "my_song")

    def test_first_meaningful_line(self) -> None:
        self.assertEqual(clean_title("\n🎵\nCanción\nPedida por Ana"), "Canción")

    def test_truncate(self) -> None:
        result = clean_title("A" * 300)
        assert result is not None
        self.assertLessEqual(len(result), NOW_PLAYING_TITLE_MAX)
        self.assertTrue(result.endswith("…"))

    def test_empty(self) -> None:
        self.assertIsNone(clean_title(""))
        self.assertIsNone(clean_title("   "))
        self.assertIsNone(clean_title(None))

    def test_unicode(self) -> None:
        self.assertEqual(clean_title("¡Canción! 😊"), "¡Canción! 😊")


class ExtractNowPlayingTest(unittest.TestCase):
    def test_title_with_song(self) -> None:
        self.assertEqual(extract_now_playing("", [embed(title="Now Playing: Artista - Canción")]), "Artista - Canción")

    def test_title_emoji_dash(self) -> None:
        self.assertEqual(extract_now_playing("", [embed(title="🎶 Now playing - Canción")]), "Canción")

    def test_title_bold_song(self) -> None:
        self.assertEqual(extract_now_playing("", [embed(title="Now playing **Canción**")]), "Canción")

    def test_header_title_song_in_description(self) -> None:
        e = embed(title="🎶 Now Playing", description="[Canción](https://youtu.be/x) - 3:45")
        self.assertEqual(extract_now_playing("", [e]), "Canción - 3:45")

    def test_header_in_author_song_in_title(self) -> None:
        e = embed(title="Canción", author="Now playing")
        self.assertEqual(extract_now_playing("", [e]), "Canción")

    def test_header_in_author_song_in_description(self) -> None:
        e = embed(title="Canción (link)", description="**Canción**", author="Now playing 🎵")
        self.assertEqual(extract_now_playing("", [e]), "Canción")

    def test_field(self) -> None:
        e = embed(fields=[("Now Playing", "**Canción**")])
        self.assertEqual(extract_now_playing("", [e]), "Canción")

    def test_spanish_header(self) -> None:
        self.assertEqual(extract_now_playing("", [embed(title="Reproduciendo ahora: Canción")]), "Canción")

    def test_description_with_header(self) -> None:
        e = embed(description="**Now playing:** [Canción](https://x.y)")
        self.assertEqual(extract_now_playing("", [e]), "Canción")

    def test_content_plain(self) -> None:
        self.assertEqual(extract_now_playing("Now playing: Canción", []), "Canción")

    def test_queue_ignored(self) -> None:
        self.assertIsNone(extract_now_playing("", [embed(title="Added to queue", description="Canción")]))
        self.assertIsNone(extract_now_playing("Paused", []))

    def test_header_without_song(self) -> None:
        self.assertIsNone(extract_now_playing("", [embed(title="Now Playing")]))

    def test_empty_embed_and_none(self) -> None:
        self.assertIsNone(extract_now_playing("", [embed()]))
        self.assertIsNone(extract_now_playing(None, [None]))
        self.assertIsNone(extract_now_playing("", None))

    def test_long_title_truncated(self) -> None:
        result = extract_now_playing("", [embed(title="Now playing: " + "B" * 300)])
        assert result is not None
        self.assertLessEqual(len(result), NOW_PLAYING_TITLE_MAX)
        self.assertTrue(result.endswith("…"))


def text(content):
    return SimpleNamespace(content=content)


def container(*children, accessory=None):
    return SimpleNamespace(children=list(children), accessory=accessory)


class ComponentsV2Test(unittest.TestCase):
    def test_header_and_song_in_same_text_display(self) -> None:
        comps = [container(text("## 🎶 Now Playing\n**[Canción](https://youtu.be/x)**\nPedida por Ana"))]
        self.assertEqual(extract_now_playing("", [], comps), "Canción")

    def test_header_and_song_in_separate_blocks(self) -> None:
        section = SimpleNamespace(children=[text("Now playing"), text("Artista - Canción")], accessory=None)
        comps = [container(section, SimpleNamespace(children=[SimpleNamespace(label="Pause")]))]
        self.assertEqual(extract_now_playing("", [], comps), "Artista - Canción")

    def test_inline_header(self) -> None:
        comps = [container(text("**Now playing:** Canción `3:45`"))]
        self.assertEqual(extract_now_playing("", [], comps), "Canción 3:45")

    def test_queue_message_ignored(self) -> None:
        comps = [container(text("## Added to queue\nCanción"))]
        self.assertIsNone(extract_now_playing("", [], comps))

    def test_buttons_only(self) -> None:
        comps = [SimpleNamespace(children=[SimpleNamespace(label="Now playing")])]
        self.assertIsNone(extract_now_playing("", [], comps))

    def test_real_flavibot_message(self) -> None:
        # Estructura real volcada por inspect_bot.py (2026-11-16).
        thumb = SimpleNamespace(media=SimpleNamespace(url="https://i.scdn.co/image/x"))
        btn = lambda label: SimpleNamespace(label=label, custom_id="np_" + label.lower())  # noqa: E731
        comps = [
            container(
                text("### [Now playing](https://flavibot.xyz/music-player)"),
                SimpleNamespace(spacing=None),
                SimpleNamespace(
                    accessory=thumb,
                    children=[
                        text("**[Black Eyed Peas - I Gotta Feeling](https://open.spotify.com/track/2H1047e0oMSj10dgp7p2VG)**"),
                        text("- Added by <@398176983424434191>\n- <#1381032178166665267>"),
                    ],
                ),
                SimpleNamespace(accessory=btn("Like"), children=[text("Queue Size: `0` · Volume: `100%` · Loop: `Off`")]),
                SimpleNamespace(items=[SimpleNamespace(media=SimpleNamespace(url="https://cdn.discordapp.com/progress.png"))]),
                SimpleNamespace(children=[btn("Pause"), btn("Skip"), btn("Stop")]),
            ),
            SimpleNamespace(children=[btn("Love this"), btn("Not for me")]),
        ]
        self.assertEqual(extract_now_playing("", [], comps), "Black Eyed Peas - I Gotta Feeling")

    def test_linked_header_in_embed_title(self) -> None:
        e = embed(title="[Now playing](https://flavibot.xyz/music-player)", description="Canción")
        self.assertEqual(extract_now_playing("", [e]), "Canción")

    def test_mentions_removed(self) -> None:
        self.assertEqual(clean_title("Canción <@398176983424434191> <#1381032178166665267>"), "Canción")

    def test_content_header_then_song_line(self) -> None:
        self.assertEqual(extract_now_playing("Now playing\nCanción", []), "Canción")


class ValidateNowPlayingTest(unittest.TestCase):
    def test_valid_strips_extra_keys(self) -> None:
        out = validate_event({"type": "NOW_PLAYING", "title": "  Canción  ", "evil": "<script>"})
        self.assertEqual(out, {"type": "NOW_PLAYING", "title": "Canción"})

    def test_max_length_ok(self) -> None:
        self.assertIsNotNone(validate_event({"type": "NOW_PLAYING", "title": "x" * 120}))

    def test_invalid(self) -> None:
        for title in ("", "   ", "x" * 121, 123, None, ["a"]):
            with self.subTest(title=title):
                self.assertIsNone(validate_event({"type": "NOW_PLAYING", "title": title}))
        self.assertIsNone(validate_event({"type": "NOW_PLAYING"}))


if __name__ == "__main__":
    unittest.main()
