"""Exercise the real isolated helper using the provisioned local runtime."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import hermes_state
from hermes_state import SessionDB
import tui_bridge


class InventoryHelperTests(unittest.TestCase):
    def test_real_helper_preserves_projection_and_refuses_other_authority(self):
        root = Path(hermes_state.__file__).resolve().parent
        paths = os.environ.get("PYTHONPATH", "").split(os.pathsep)
        if (sys.platform != "linux" or len(paths) != 2 or Path(paths[0]).resolve() != root
                or Path("/etc/hermes").exists()):
            self.skipTest("requires the provisioned local TUI's two-path Linux runtime")
        source = Path(tui_bridge.__file__).resolve().parent
        with tempfile.TemporaryDirectory(prefix="pins-helper-") as tmp:
            base = Path(tmp)
            home = base / "profiles" / "work"
            plugins = home / "plugins"
            plugins.mkdir(parents=True)
            link = plugins / "session-pins"
            link.symlink_to(source, target_is_directory=True)
            config = home / "config.yaml"
            config.write_text('{"plugins":{"enabled":["session-pins"]}}', encoding="utf-8")
            with SessionDB(db_path=home / "state.db") as db:
                db.create_session("root", source="cli", model="old-model")
                db.set_session_title("root", "Root title")
                db.set_session_pinned("root", True)
                db.end_session("root", "compression")
                db.create_session("tip", source="cli", model="new-model", parent_session_id="root")
                db.append_message("tip", "user", "fixture-only transcript")
                db.create_session("hidden", source="cli")
                db.set_session_hidden("hidden", True)
            data = tui_bridge.inventory(home)
            self.assertEqual(["tip"], [row["id"] for row in data["rows"]])
            self.assertTrue(data["rows"][0]["pinned"])
            before = (home / "state.db").read_bytes()

            def run(**env):
                return subprocess.run(
                    [sys.executable, "-I", "-S", "-B", str(link / "tui_inventory.py"),
                     str(home), *paths], env={"HERMES_HOME": str(home), **env},
                    cwd=base, capture_output=True, timeout=10,
                )

            result = run()
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout), data)
            self.assertNotIn(b"fixture-only transcript", result.stdout)
            for env in ({"HERMES_HOME": str(base)}, {"HERMES_SAFE_MODE": "1"}):
                result = run(**env)
                self.assertEqual((result.returncode, result.stdout), (1, b""))
            config.write_text('{"plugins":{"enabled":["session-pins"],"disabled":["session-pins"]}}', encoding="utf-8")
            result = run()
            self.assertEqual((result.returncode, result.stdout), (1, b""))
            self.assertEqual((home / "state.db").read_bytes(), before)
