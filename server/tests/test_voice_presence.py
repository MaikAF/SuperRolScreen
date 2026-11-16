"""Tests de voice_presence (build_voice_state, has_humans, SpeakingSink).

Uso (desde server/): .\.venv\Scripts\python.exe tests\test_voice_presence.py
"""

from __future__ import annotations

import asyncio
import sys
import threading
import time
import unittest
from types import SimpleNamespace
from typing import Callable

sys.path.insert(0, ".")

from main import validate_event  # noqa: E402
from voice_presence import (  # noqa: E402
    VOICE_DEBOUNCE_S,
    VOICE_HEARTBEAT_S,
    VOICE_MAX_MEMBERS,
    VOICE_NAME_MAX,
    SpeakingSink,
    build_voice_state,
    has_humans,
)


class BuildVoiceStateTest(unittest.TestCase):
    def test_basic_payload(self) -> None:
        state = build_voice_state(
            "Mesa de rol",
            [(123, "Ana", False), (456, "Beto", False)],
            {123},
        )
        self.assertEqual(state["type"], "VOICE_STATE")
        self.assertEqual(state["channel"], "Mesa de rol")
        self.assertEqual(len(state["members"]), 2)
        self.assertEqual(state["members"][0]["id"], "123")
        self.assertEqual(state["members"][0]["name"], "Ana")
        self.assertTrue(state["members"][0]["speaking"])
        self.assertEqual(state["members"][1]["id"], "456")
        self.assertEqual(state["members"][1]["name"], "Beto")
        self.assertFalse(state["members"][1]["speaking"])

    def test_excludes_bots(self) -> None:
        state = build_voice_state("Canal", [(1, "Humano", False), (2, "Bot", True)], set())
        self.assertEqual(len(state["members"]), 1)
        self.assertEqual(state["members"][0]["name"], "Humano")

    def test_sorts_case_insensitive(self) -> None:
        members = [(3, "carlos", False), (1, "Ana", False), (2, "Beto", False)]
        state = build_voice_state("Canal", members, set())
        names = [m["name"] for m in state["members"]]
        self.assertEqual(names, ["Ana", "Beto", "carlos"])

    def test_truncates_name_to_32(self) -> None:
        long_name = "x" * 40
        state = build_voice_state("Canal", [(1, long_name, False)], set())
        self.assertEqual(len(state["members"][0]["name"]), VOICE_NAME_MAX)
        self.assertEqual(len(state["members"][0]["name"]), 32)

    def test_limits_to_25_members(self) -> None:
        members = [(i, f"Usuario{i:03d}", False) for i in range(1, 31)]
        state = build_voice_state("Canal", members, set())
        self.assertEqual(len(state["members"]), VOICE_MAX_MEMBERS)

    def test_channel_none_returns_empty_members(self) -> None:
        state = build_voice_state(None, [(1, "Ana", False)], set())
        self.assertIsNone(state["channel"])
        self.assertEqual(state["members"], [])

    def test_ids_as_string(self) -> None:
        state = build_voice_state("Canal", [(123456789012345678, "Ana", False)], set())
        self.assertIsInstance(state["members"][0]["id"], str)
        self.assertEqual(state["members"][0]["id"], "123456789012345678")


class HasHumansTest(unittest.TestCase):
    def test_empty_returns_false(self) -> None:
        self.assertFalse(has_humans([]))

    def test_only_bots_returns_false(self) -> None:
        self.assertFalse(has_humans([(1, "Bot1", True), (2, "Bot2", True)]))

    def test_one_human_returns_true(self) -> None:
        self.assertTrue(has_humans([(1, "Bot", True), (2, "Humano", False)]))


class SpeakingSinkTest(unittest.TestCase):
    def test_wants_opus_is_true(self) -> None:
        async def _noop(*args, **kwargs) -> None:
            pass

        loop = asyncio.new_event_loop()
        try:
            sink = SpeakingSink(loop, _noop)
            self.assertTrue(sink.wants_opus())
        finally:
            loop.close()

    def test_listeners_dispatch_via_call_soon_threadsafe(self) -> None:
        received: list[tuple[int, bool]] = []
        loop = asyncio.new_event_loop()
        ready = threading.Event()
        started = threading.Event()

        def on_change(member_id: int, speaking: bool) -> None:
            received.append((member_id, speaking))

        sink = SpeakingSink(loop, on_change)

        def run_loop() -> None:
            asyncio.set_event_loop(loop)
            ready.set()
            loop.run_forever()

        t = threading.Thread(target=run_loop, daemon=True)
        t.start()
        ready.wait(2)

        fake_member = SimpleNamespace(id=1, display_name="Tester")

        # Llamar desde otro hilo simula el SpeakingTimer
        def fire_start() -> None:
            sink.on_voice_member_speaking_start(fake_member)
            started.set()

        th = threading.Thread(target=fire_start, daemon=True)
        th.start()
        started.wait(2)

        # Dar tiempo al loop para ejecutar el callback
        for _ in range(50):
            if received:
                break
            time.sleep(0.02)

        self.assertIn((1, True), received)

        # Ahora el stop
        stop_evt = threading.Event()

        def fire_stop() -> None:
            sink.on_voice_member_speaking_stop(fake_member)
            stop_evt.set()

        th2 = threading.Thread(target=fire_stop, daemon=True)
        th2.start()
        stop_evt.wait(2)

        for _ in range(50):
            if (1, False) in received:
                break
            time.sleep(0.02)

        self.assertIn((1, False), received)

        loop.call_soon_threadsafe(loop.stop)
        t.join(timeout=2)
        loop.close()


class ValidateEventTest(unittest.TestCase):
    def test_valid_voice_state_passes(self) -> None:
        payload = {
            "type": "VOICE_STATE",
            "channel": "Mesa de rol",
            "members": [{"id": "123", "name": "Ana", "speaking": True}],
        }
        result = validate_event(payload)
        self.assertIsNotNone(result)
        self.assertEqual(result["type"], "VOICE_STATE")

    def test_extra_keys_removed(self) -> None:
        payload = {
            "type": "VOICE_STATE",
            "channel": "Mesa",
            "members": [{"id": "1", "name": "A", "speaking": False, "extra": "x"}],
            "extra_top": "drop",
        }
        result = validate_event(payload)
        self.assertIsNotNone(result)
        self.assertNotIn("extra_top", result)
        self.assertNotIn("extra", result["members"][0])

    def test_speaking_not_strict_bool_rejected(self) -> None:
        payload = {
            "type": "VOICE_STATE",
            "channel": "C",
            "members": [{"id": "1", "name": "A", "speaking": 1}],
        }
        self.assertIsNone(validate_event(payload))

    def test_speaking_int_zero_rejected(self) -> None:
        payload = {
            "type": "VOICE_STATE",
            "channel": "C",
            "members": [{"id": "1", "name": "A", "speaking": 0}],
        }
        self.assertIsNone(validate_event(payload))

    def test_non_numeric_id_rejected(self) -> None:
        payload = {
            "type": "VOICE_STATE",
            "channel": "C",
            "members": [{"id": "abc", "name": "A", "speaking": False}],
        }
        self.assertIsNone(validate_event(payload))

    def test_too_many_members_rejected(self) -> None:
        payload = {
            "type": "VOICE_STATE",
            "channel": "C",
            "members": [{"id": str(i), "name": f"U{i}", "speaking": False} for i in range(26)],
        }
        self.assertIsNone(validate_event(payload))

    def test_empty_name_rejected(self) -> None:
        payload = {
            "type": "VOICE_STATE",
            "channel": "C",
            "members": [{"id": "1", "name": "", "speaking": False}],
        }
        self.assertIsNone(validate_event(payload))

    def test_name_33_chars_rejected(self) -> None:
        payload = {
            "type": "VOICE_STATE",
            "channel": "C",
            "members": [{"id": "1", "name": "x" * 33, "speaking": False}],
        }
        self.assertIsNone(validate_event(payload))

    def test_members_not_list_rejected(self) -> None:
        payload = {"type": "VOICE_STATE", "channel": "C", "members": "nope"}
        self.assertIsNone(validate_event(payload))

    def test_channel_numeric_rejected(self) -> None:
        payload = {"type": "VOICE_STATE", "channel": 123, "members": []}
        self.assertIsNone(validate_event(payload))

    def test_channel_null_ok_with_empty_members(self) -> None:
        payload = {"type": "VOICE_STATE", "channel": None, "members": []}
        result = validate_event(payload)
        self.assertIsNotNone(result)
        self.assertIsNone(result["channel"])
        self.assertEqual(result["members"], [])


if __name__ == "__main__":
    unittest.main(verbosity=2)