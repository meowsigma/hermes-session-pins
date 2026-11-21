"""Drive the real standalone picker with deterministic dimensions and fixture data."""
from contextlib import contextmanager
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

from hermes_state import SessionDB
from prompt_toolkit import Application
from prompt_toolkit.data_structures import Size
from prompt_toolkit.input import create_pipe_input
from prompt_toolkit.output import DummyOutput

import session_pins as pins


class Terminal(DummyOutput):
    def __init__(self, columns, rows):
        self.size = Size(rows=rows, columns=columns)

    def get_size(self):
        return self.size


def render_picker(rows, *, steps=("\r",), width=90, height=24, before_first_key=None):
    """Capture frames before delivering each real key sequence to prompt_toolkit."""
    frames = []
    init = Application.__init__
    with create_pipe_input() as pipe:
        def observe(app, *args, **kwargs):
            def after_render(app):
                if app.is_done or len(frames) >= len(steps):
                    return
                screen = app.renderer.last_rendered_screen
                lines = [tuple(screen.data_buffer[y][x] for x in range(width))
                         for y in range(screen.height)]
                frames.append((lines, kwargs["style"]))
                if len(frames) == 1 and before_first_key is not None:
                    before_first_key()
                pipe.send_text(steps[len(frames) - 1])

            init(app, *args, **kwargs, after_render=after_render)

        with patch.object(Application, "__init__", observe):
            picked = pins.picker(rows, input=pipe, output=Terminal(width, height))
    return picked, frames


def line_text(line):
    return "".join(cell.char for cell in line).rstrip()


@contextmanager
def profile(skin="default", **env):
    with tempfile.TemporaryDirectory(prefix="pins-render-") as temp:
        home = Path(temp)
        (home / "config.yaml").write_text(f"display:\n  skin: {skin}\n", encoding="utf-8")
        (home / "skins").mkdir()
        with patch.dict(os.environ, {"HERMES_HOME": temp, "HERMES_TUI_THEME": "dark", **env}):
            yield home


class PickerStyleTests(unittest.TestCase):
    def test_missing_skin_uses_light_fallback_in_the_actual_frame(self):
        with profile("missing-skin", HERMES_TUI_THEME="light"):
            _, frames = render_picker([{"id": "exact-id", "title": "Light fallback", "pinned": True}])
        lines, style = frames[0]
        self.assertIn("★ Light fallback", line_text(lines[2]))
        self.assertEqual("956e00", style.get_attrs_for_style_str(lines[0][0].style).color)
        self.assertTrue(all(style.get_attrs_for_style_str(cell.style).bgcolor == "e0d1bf" for cell in lines[2]))

    def test_combining_marks_survive_cell_truncation(self):
        from picker_style import fit
        self.assertEqual("e\u0301…", fit("e\u0301clair", 2))
        self.assertEqual("e\u0301", fit("e\u0301", 1))

    def test_numbered_metadata_borderless_layout_and_full_row_chip(self):
        rows = [
            {"id": "20260606_123456_abcd", "title": "Pinned project", "pinned": True,
             "started_at": time.time() - 90000, "message_count": 27},
            {"id": "other-chat", "preview": "Ordinary recent chat", "message_count": 1},
        ]
        with profile():
            picked, frames = render_picker(rows)
        self.assertIs(rows[0], picked)
        lines, style = frames[0]
        text = [line_text(line) for line in lines]
        self.assertEqual(["Sessions", "2 resumable · 1 pinned"], text[:2])
        self.assertRegex(text[2], r"^▸  1\. +20260606_… +yesterday +27 msgs +★ Pinned project$")
        self.assertRegex(text[3], r"^   2\. +other-chat +1 msgs +Ordinary recent chat$")
        self.assertIn("Ctrl-P", text[4])
        self.assertNotIn("+ new", "\n".join(text))
        self.assertTrue(all(style.get_attrs_for_style_str(cell.style).bgcolor == "333355" for cell in lines[2]))
        self.assertTrue(all(not style.get_attrs_for_style_str(cell.style).bgcolor for cell in lines[3]))
        self.assertFalse(style.get_attrs_for_style_str(lines[2][0].style).reverse)

    def test_profile_skin_colors_and_readable_chip_ink(self):
        rows = [{"id": "id", "title": "Session", "pinned": True}, {"id": "other"}]
        with profile("test-picker", HERMES_TUI_THEME="light") as home:
            (home / "skins" / "test-picker.yaml").write_text(
                'name: test-picker\ncolors:\n  ui_accent: "#102030"\n  banner_dim: "#405060"\n'
                '  ui_text: "#ffffff"\n  selection_bg: "#ff0000"\n'
                'light_colors:\n  completion_menu_current_bg: "#fefeff"\n', encoding="utf-8",
            )
            _, frames = render_picker(rows)
        lines, style = frames[0]
        self.assertEqual("102030", style.get_attrs_for_style_str(lines[0][0].style).color)
        self.assertEqual("405060", style.get_attrs_for_style_str(lines[1][0].style).color)
        chip = style.get_attrs_for_style_str(lines[2][0].style)
        self.assertEqual("fefeff", chip.bgcolor)
        self.assertEqual("000000", chip.color)

    def test_narrow_scroll_keeps_selection_visible_and_handoff_exact(self):
        rows = [{"id": f"chat-{i:02}-suffix", "title": "工具設定と履歴の整理" * 3} for i in range(14)]
        with profile():
            picked, frames = render_picker(rows, steps=("\x1b[B" * 9, "\r"), width=34, height=9)
        self.assertIs(rows[9], picked)
        self.assertEqual(2, len(frames))
        lines, _ = frames[-1]
        text = [line_text(line) for line in lines]
        self.assertLessEqual(len(lines), 9)
        self.assertTrue(any("more above" in line for line in text), text)
        self.assertTrue(any("more below" in line for line in text), text)
        selected = next(line for line in text if line.startswith("▸ "))
        self.assertRegex(selected, r"^▸ 10\. +chat-09-… +工具.+…$")

    def test_filter_uses_original_id_not_its_display_abbreviation(self):
        rows = [{"id": "shared-prefix-a"},
                {"id": "shared-prefix-needle", "title": "\x1b[31m工程\n履歴", "message_count": "\x1b[0m"}]
        with profile():
            picked, frames = render_picker(rows, steps=("needle", "\r"))
        self.assertIs(rows[1], picked)
        text = "\n".join(line_text(line) for line in frames[-1][0])
        self.assertIn("1 of 2 resumable · 0 pinned", text)
        self.assertIn("Search: needle", text)
        self.assertIn("0 msgs", text)
        self.assertNotIn("\x1b", text)


class PickerPinKeyTests(unittest.TestCase):
    def test_stock_ctrl_p_refuses_without_writing_and_enter_still_selects(self):
        with profile() as home:
            path = home / "state.db"
            with SessionDB(db_path=path) as db:
                db.create_session("target", source="cli")
                db.append_message("target", "user", "Synthetic picker test")
            rows = pins.session_rows(recent=True, home=home)
            self.assertEqual(["target"], [row["id"] for row in rows])
            with patch.object(SessionDB, "set_projected_session_pinned", None, create=True):
                picked, frames = render_picker(rows, steps=("\x10", "\r"))
            self.assertIs(rows[0], picked)
            self.assertIn("safe session selection support", "\n".join(map(line_text, frames[-1][0])))
            with SessionDB(db_path=path, read_only=True) as fresh:
                row = fresh.get_session("target")
                self.assertFalse(row["pinned"])
                self.assertFalse(row["hidden"])

    @unittest.skipUnless(callable(getattr(SessionDB, "set_projected_session_pinned", None)),
                         "needs the native projected pin writer")
    def test_ctrl_p_refuses_a_tip_hidden_or_superseded_after_display(self):
        for change in ("hide", "supersede"):
            with self.subTest(change=change), profile() as home:
                path = home / "state.db"
                with SessionDB(db_path=path) as db:
                    db.create_session("root", source="cli")
                    db.append_message("root", "user", "Synthetic picker test")
                    db.end_session("root", "compression")
                    db.create_session("tip", source="cli", parent_session_id="root")
                    db.append_message("tip", "user", "Current compression tip")
                    rows = pins.session_rows(recent=True, home=home)
                    self.assertEqual(["tip"], [row["id"] for row in rows])

                    def invalidate_selection():
                        if change == "hide":
                            self.assertTrue(db.set_session_hidden("tip", True))
                        else:
                            db.end_session("tip", "compression")
                            db.create_session("replacement", source="cli", parent_session_id="tip")

                    picked, frames = render_picker(rows, steps=("\x10", "\x04"),
                                                   before_first_key=invalidate_selection)
                self.assertIsNone(picked)
                self.assertIn("missing or not visible", "\n".join(map(line_text, frames[-1][0])))
                with SessionDB(db_path=path, read_only=True) as fresh:
                    ids = ("root", "tip", "replacement") if change == "supersede" else ("root", "tip")
                    for sid in ids:
                        row = fresh.get_session(sid)
                        self.assertFalse(row["pinned"], sid)
                        self.assertEqual(change == "hide", bool(row["hidden"]), sid)
