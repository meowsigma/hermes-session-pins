"""Offline CPU-only tests against real Hermes session databases and picker UI."""
from __future__ import annotations

import argparse
from contextlib import redirect_stdout
import io
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from hermes_state import SessionDB
from prompt_toolkit.input import create_pipe_input
from prompt_toolkit.output import DummyOutput

import session_pins as pins


class PinsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="hermes-pins-test-")
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name)
        self.env = patch.dict(os.environ, {"HERMES_HOME": str(self.home)})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.db = SessionDB(db_path=self.home / "state.db")
        self.addCleanup(self.db.close)

    def chat(self, sid="chat-main", title="Main project", **kwargs):
        self.db.create_session(sid, source="cli", **kwargs)
        self.db.set_session_title(sid, title)
        self.db.append_message(sid, "user", "synthetic test message")
        return sid

    def test_pin_current_chat_is_idempotent_and_durable(self):
        sid = self.chat()
        for _ in range(2):
            self.assertIn("★ Pinned", pins.command_pin("", session_id=sid, platform="tui"))
        with SessionDB(db_path=self.home / "state.db", read_only=True) as reopened:
            self.assertEqual(1, reopened.get_session(sid)["pinned"])
        self.assertEqual([sid], [r["id"] for r in pins.session_rows()])

    def test_unpin_and_no_content_or_timestamp_changes(self):
        sid = self.chat()
        before = self.db.get_session(sid)
        messages = self.db.get_messages(sid)
        pins.set_pin(sid, True)
        pins.set_pin(sid, False)
        after = self.db.get_session(sid)
        for key in ("title", "started_at", "ended_at", "message_count"):
            self.assertEqual(before[key], after[key], key)
        self.assertEqual(messages, self.db.get_messages(sid))
        self.assertEqual([], pins.session_rows())

    def test_old_pins_backfill_beyond_recent_page_and_sort_first(self):
        old = self.chat("old-important", "Important old chat")
        pins.set_pin(old, True)
        for i in range(55):
            self.chat(f"recent-{i:03}", f"Recent {i}")
        rows = pins.session_rows(recent=True)
        self.assertEqual(old, rows[0]["id"])
        self.assertEqual(41, len(rows))
        self.assertEqual([old], [r["id"] for r in pins.session_rows()])

    def test_all_pins_returned_not_only_the_first_page(self):
        for i in range(45):
            sid = self.chat(f"pinned-{i:03}", f"Pinned {i}")
            self.db.set_session_pinned(sid, True)
        rows = pins.session_rows()
        self.assertEqual(45, len(rows))
        self.assertEqual(45, len({r["id"] for r in rows}))

    def test_prefix_ambiguity_refuses_without_modifying_sessions(self):
        self.chat("ambiguous-one", "One")
        self.chat("ambiguous-two", "Two")
        with self.assertRaisesRegex(pins.PinsError, "ambiguous"):
            pins.set_pin("ambiguous", True)
        self.assertEqual([], pins.session_rows())
        self.assertEqual("ambiguous-one", pins.set_pin("ambiguous-o", True)["id"])

    def test_empty_session_id_refuses(self):
        response = pins.command_pin("", platform="tui")
        self.assertIn("No current session", response)
        self.assertEqual([], pins.session_rows())

    def test_messaging_cannot_list_or_mutate_pins(self):
        sid = self.chat()
        for platform in ("telegram", "discord", "", "unknown"):
            self.assertIn("not messaging chats", pins.command_pin(sid, platform=platform))
            self.assertIn("not messaging chats", pins.command_pins(None, "list", platform=platform))
        self.assertEqual([], pins.session_rows())

    def test_named_profile_isolation(self):
        sid = self.chat()
        pins.set_pin(sid, True)
        other = self.home / "other-profile"
        other.mkdir()
        with patch.dict(os.environ, {"HERMES_HOME": str(other)}):
            with SessionDB(db_path=other / "state.db") as db:
                db.create_session(sid, source="cli")
                self.assertEqual([], pins.session_rows())
                pins.set_pin(sid, True)
                self.assertEqual([sid], [r["id"] for r in pins.session_rows()])
                pins.set_pin(sid, False)
        self.assertEqual([sid], [r["id"] for r in pins.session_rows()])

    def test_compression_pin_and_unpin_cover_lineage(self):
        root = self.chat("root-session", "Long conversation")
        self.db.end_session(root, "compression")
        tip = self.chat("tip-session", "Long conversation continued", parent_session_id=root)
        pins.set_pin(tip, True)
        self.assertEqual(1, self.db.get_session(root)["pinned"])
        rows = pins.session_rows()
        self.assertEqual([tip], [r["id"] for r in rows])
        pins.set_pin(tip, False)
        self.assertEqual(0, self.db.get_session(root)["pinned"])
        self.assertEqual([], pins.session_rows())

    def test_archived_pin_is_still_reachable(self):
        sid = self.chat()
        self.db.set_session_archived(sid, True)
        pins.set_pin(sid, True)
        self.assertEqual([sid], [r["id"] for r in pins.session_rows()])

    def test_slash_picker_returns_resume_command_not_a_fake_switch(self):
        sid = self.chat()
        pins.set_pin(sid, True)
        class Context:
            def ask_choice(self, question, choices):
                self.choices = choices
                return sid
        ctx = Context()
        result = pins.command_pins(ctx, "", platform="tui")
        self.assertIn("Run this in your current chat:", result)
        self.assertIn(f"/resume {sid}", result)
        self.assertTrue(ctx.choices[0]["label"].startswith("★ "))

    def test_slash_manager_unpins_and_cancel_is_noop(self):
        sid = self.chat()
        pins.set_pin(sid, True)
        class Context:
            def __init__(self, answers):
                self.answers = iter(answers)
            def ask_choice(self, question, choices):
                return next(self.answers)
        self.assertIn("No chat selected", pins.command_pins(Context([None]), "", platform="tui"))
        self.assertEqual(1, self.db.get_session(sid)["pinned"])
        self.assertIn("Unpinned", pins.command_pins(Context([sid, "unpin"]), "manage", platform="tui"))
        self.assertEqual(0, self.db.get_session(sid)["pinned"])

    def test_picker_real_keyboard_enter_search_and_cancel(self):
        self.chat("first-chat", "First")
        target = self.chat("second-chat", "Second")
        pins.set_pin("first-chat", True)
        rows = pins.session_rows(recent=True)
        with create_pipe_input() as input:
            input.send_text("second\r")
            chosen = pins.picker(rows, input=input, output=DummyOutput())
        self.assertEqual(target, chosen["id"])
        with create_pipe_input() as input:
            input.send_text("\x1b")
            chosen = pins.picker(rows, input=input, output=DummyOutput())
        self.assertIsNone(chosen)

    def test_picker_keyboard_pin_toggle_persists(self):
        sid = self.chat()
        with create_pipe_input() as input:
            input.send_text("\x10\r")  # Ctrl-P then Enter
            chosen = pins.picker(pins.session_rows(recent=True), input=input, output=DummyOutput())
        self.assertEqual(sid, chosen["id"])
        self.assertEqual(1, self.db.get_session(sid)["pinned"])

    def test_picker_renders_star_and_highlight_styles(self):
        self.chat("pinned", "Pinned chat")
        self.chat("ordinary", "Ordinary chat")
        pins.set_pin("pinned", True)
        seen = {}
        from prompt_toolkit import Application
        real_init = Application.__init__
        def observe(app, *args, **kwargs):
            seen["style"] = dict(kwargs["style"].style_rules)
            controls = list(kwargs["layout"].find_all_controls())
            texts = [c.text() if callable(getattr(c, "text", None)) else getattr(c, "text", "") for c in controls]
            seen["text"] = str(texts)
            return real_init(app, *args, **kwargs)
        with create_pipe_input() as input, patch.object(Application, "__init__", observe):
            input.send_text("\r")
            chosen = pins.picker(pins.session_rows(recent=True), input=input, output=DummyOutput())
        self.assertEqual("pinned", chosen["id"])
        self.assertIn("★ Pinned chat", seen["text"])
        self.assertEqual("ansiyellow bold", seen["style"]["pinned"])
        self.assertEqual("reverse bold", seen["style"]["selected"])

    def test_cli_resume_handoff_no_shell_and_same_profile(self):
        sid = self.chat()
        args = argparse.Namespace(action="pick", session_id=None, print_only=False)
        with patch.object(pins.sys, "stdin") as stdin, patch.object(pins.sys, "stdout") as stdout:
            stdin.isatty.return_value = stdout.isatty.return_value = True
            with patch.object(pins, "picker", return_value={"id": sid}), patch.object(pins.shutil, "which", return_value="/usr/bin/hermes"), patch.object(pins.subprocess, "call", return_value=0) as call:
                self.assertEqual(0, pins.cli(args))
                call.assert_called_once_with(["/usr/bin/hermes", "chat", "--resume", sid])
                self.assertEqual(str(self.home), os.environ["HERMES_HOME"])

    def test_cli_list_plain_output(self):
        sid = self.chat()
        pins.set_pin(sid, True)
        out = io.StringIO()
        with redirect_stdout(out):
            self.assertEqual(0, pins.cli(argparse.Namespace(action="list", session_id=None, print_only=False)))
        self.assertIn("★ Main project", out.getvalue())
        self.assertIn(f"hermes chat --resume {sid}", out.getvalue())

    def test_labels_strip_control_characters(self):
        self.assertNotIn("\x1b", pins.clean_label("\x1b[31mred\nline\x07"))
        self.assertNotIn("\n", pins.clean_label("a\nb"))
        self.assertEqual(90, len(pins.clean_label("a" * 120)))


if __name__ == "__main__":
    unittest.main()
