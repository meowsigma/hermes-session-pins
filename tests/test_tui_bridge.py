"""Read-only inventory / explicit widget installation regressions.

Not executed on the owner's PC: retained for authorized isolated acceptance.
"""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock

from hermes_state import SessionDB
import session_pins as pins
import tui_bridge


class NativeInventoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="pins-native-inventory-")
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name)
        self.db = SessionDB(db_path=self.home / "state.db")
        self.addCleanup(self.db.close)

    def chat(self, sid, title):
        self.db.create_session(sid, source="cli", model="synthetic-stored-model")
        self.db.set_session_title(sid, title)
        self.db.append_message(sid, "user", "synthetic test message, not UI metadata")

    def test_inventory_uses_all_visible_rows_and_full_titles_without_mutation(self):
        # Exercise the maximum legal native title; its distinguishing search
        # term still lies beyond the old 90-character presentation cap.
        suffix = "needle"
        long = "a" * (SessionDB.MAX_TITLE_LENGTH - len(suffix)) + suffix
        self.assertEqual(SessionDB.MAX_TITLE_LENGTH, len(long))
        self.assertGreaterEqual(long.index(suffix), 90)
        self.chat("ordinary", long)
        self.chat("pinned", "Pinned project")
        self.db.set_session_pinned("pinned", True)
        before = {sid: self.db.get_session(sid) for sid in ("ordinary", "pinned")}
        data = tui_bridge.inventory(self.home)
        self.assertEqual(str(self.home), data["home"])
        self.assertEqual(["pinned", "ordinary"], [row["id"] for row in data["rows"]])
        ordinary = data["rows"][1]
        self.assertEqual(long, ordinary["title"])
        self.assertEqual("synthetic-stored-model", ordinary["model"])
        self.assertEqual({"id", "title", "pinned", "model", "updated"}, set(ordinary))
        self.assertNotIn("synthetic test message", json.dumps(data))
        self.assertEqual(before, {sid: self.db.get_session(sid) for sid in before})

    def test_native_visibility_and_profile_binding_are_preserved(self):
        self.chat("visible", "Source profile")
        self.chat("hidden", "Hidden project")
        self.chat("archived", "Archived project")
        self.db.set_session_hidden("hidden", True)
        self.db.set_session_archived("archived", True, notify=False)
        rows = tui_bridge.inventory(self.home)["rows"]
        self.assertEqual(["visible"], [row["id"] for row in rows])
        self.assertTrue(self.db.get_session("hidden")["hidden"])
        self.assertTrue(self.db.get_session("archived")["archived"])

    def test_install_remove_preserve_unrelated_and_changed_user_files(self):
        path = tui_bridge.install(self.home)
        source = Path(tui_bridge.__file__).parent / "tui" / "pins.mjs"
        self.assertEqual(source.read_bytes(), path.read_bytes())
        self.assertEqual(path, tui_bridge.install(self.home))
        other = path.parent / "unrelated.mjs"
        other.write_text("// unrelated owner widget")
        path.write_text("// owner changed this widget")
        with self.assertRaises(pins.PinsError):
            tui_bridge.install(self.home)
        with self.assertRaises(pins.PinsError):
            tui_bridge.remove(self.home)
        self.assertEqual("// owner changed this widget", path.read_text())
        self.assertTrue(other.exists())

    def test_ink_fallback_never_enters_clarification(self):
        self.chat("pinned", "Pinned project")
        self.db.set_session_pinned("pinned", True)
        from unittest.mock import patch
        with patch.object(pins, "get_hermes_home", return_value=self.home):
            for mode in ("", "manage"):
                ctx = Mock()
                response = pins.command_pins(ctx, mode, platform="tui")
                self.assertIn("/widgets-reload", response)
                ctx.ask_choice.assert_not_called()
        self.assertTrue(self.db.get_session("pinned")["pinned"])
