"""Read-only current-chat status on real synthetic native session stores."""
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import Mock, patch

from hermes_state import SessionDB
import session_pins as pins


class PinStatusTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="pins-status-")
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name)
        self.env = patch.dict(os.environ, HERMES_HOME=str(self.home))
        self.env.start()
        self.addCleanup(self.env.stop)
        self.db = SessionDB(db_path=self.home / "state.db")
        self.addCleanup(self.db.close)
        self.db.create_session("current-exact", source="cli")
        self.db.set_session_title("current-exact", "Current project")
        self.db.append_message("current-exact", "user", "Synthetic fixture only")

    def command(self, sid="current-exact", platform="tui"):
        ctx = Mock()
        pins.register(ctx)
        commands = dict(call.args[:2] for call in ctx.register_command.call_args_list)
        return commands["pin"]("status", session_id=sid, platform=platform)

    def test_reports_both_states_without_writer_or_metadata_changes(self):
        original = pins.database
        for pinned in (False, True):
            self.db.set_session_pinned("current-exact", pinned)
            before = self.db.get_session("current-exact")
            messages = self.db.get_messages("current-exact")
            with patch.object(pins, "database", wraps=original) as database:
                result = self.command()
            self.assertEqual([{"home": self.home}], [c.kwargs for c in database.call_args_list])
            self.assertEqual("★ This chat is pinned: Current project" if pinned else
                             "This chat is not pinned: Current project\nUse /pin to pin it.", result)
            self.assertEqual(before, self.db.get_session("current-exact"))
            self.assertEqual(messages, self.db.get_messages("current-exact"))

    def test_empty_current_id_does_not_open_storage(self):
        with patch.object(pins, "database", side_effect=AssertionError("no storage")):
            self.assertIn("No current session yet", self.command(sid=""))

    def test_missing_current_id_never_falls_back_to_prefix_or_title(self):
        self.db.create_session("gone-longer", source="cli")
        self.db.set_session_title("gone-longer", "gone")
        self.db.set_session_pinned("gone-longer", True)
        self.assertIn("no longer exists", self.command(sid="gone"))
        self.assertTrue(self.db.get_session("gone-longer")["pinned"])

    def test_status_keyword_never_pins_a_chat_titled_status(self):
        self.db.create_session("title-status", source="cli")
        self.db.set_session_title("title-status", "status")
        self.assertIn("not pinned: Current project", self.command())
        self.assertFalse(self.db.get_session("title-status")["pinned"])
        self.assertIn("Pinned: status", pins.command_pin("title-status", platform="tui"))
        ctx = Mock()
        pins.register(ctx)
        commands = dict(call.args[:2] for call in ctx.register_command.call_args_list)
        self.assertIn("Unpinned: status", commands["unpin"]("status", session_id="current-exact", platform="tui"))

    def test_uppercase_status_remains_a_registered_title_selector(self):
        self.db.create_session("upper-status", source="cli")
        self.db.set_session_title("upper-status", "Status")
        ctx = Mock()
        pins.register(ctx)
        commands = dict(call.args[:2] for call in ctx.register_command.call_args_list)
        self.assertIn("Pinned: Status", commands["pin"]("Status", session_id="current-exact", platform="tui"))
        self.assertTrue(self.db.get_session("upper-status")["pinned"])
        self.assertFalse(self.db.get_session("current-exact")["pinned"])

    def test_messaging_and_unknown_surfaces_refuse_before_storage(self):
        for platform in ("telegram", "discord", "", "unknown"):
            with self.subTest(platform=platform), patch.object(pins, "database", side_effect=AssertionError("no storage")):
                self.assertIn("not messaging chats", self.command(platform=platform))

    def test_duplicate_id_in_other_profile_does_not_supply_status(self):
        other = self.home / "profiles" / "work"
        other.mkdir(parents=True)
        with SessionDB(db_path=other / "state.db") as db:
            db.create_session("current-exact", source="cli")
            db.set_session_title("current-exact", "Other profile")
            db.set_session_pinned("current-exact", True)
        self.assertIn("not pinned: Current project", self.command())
        with patch.dict(os.environ, HERMES_HOME=str(other)):
            self.assertEqual("★ This chat is pinned: Other profile", self.command())
        self.assertFalse(self.db.get_session("current-exact")["pinned"])

    def test_hidden_unpinned_chat_is_reported_without_unhiding(self):
        self.db.set_session_hidden("current-exact", True)
        before = self.db.get_session("current-exact")
        self.assertIn("not pinned", self.command())
        self.assertEqual(before, self.db.get_session("current-exact"))

    def test_missing_database_is_not_created(self):
        other = self.home / "empty"
        other.mkdir()
        with patch.dict(os.environ, HERMES_HOME=str(other)):
            self.assertIn("No sessions yet", self.command())
        self.assertFalse((other / "state.db").exists())

    def test_storage_failure_is_sanitized_not_reported_as_unpinned(self):
        with patch.object(pins, "database", side_effect=sqlite3.OperationalError("unavailable\x1b[31m\r")):
            result = self.command()
        self.assertTrue(result.startswith("Session Pins:"))
        self.assertIn("unavailable", result)
        self.assertNotIn("not pinned", result)
        self.assertTrue(result.isprintable())


if __name__ == "__main__":
    unittest.main()
