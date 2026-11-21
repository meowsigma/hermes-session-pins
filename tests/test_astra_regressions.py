"""Named-profile shell handoff through the installed Hermes CLI, without chat startup."""
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import tempfile
import unittest

from hermes_state import SessionDB


@unittest.skipUnless(os.name == "posix" and shutil.which("hermes"), "needs a local POSIX Hermes CLI")
class ShellHandoffTests(unittest.TestCase):
    def test_named_profile_handoff_pastes_into_default_shell(self):
        hermes = shutil.which("hermes")
        with tempfile.TemporaryDirectory(prefix="hermes-pins-profile-") as scratch:
            root = Path(scratch)
            default = root / "default home's sessions"
            work = default / "profiles" / "work"
            target = work / "plugins" / "session-pins"
            target.mkdir(parents=True)
            source = Path(__file__).resolve().parents[1]
            for name in ("plugin.yaml", "__init__.py", "session_pins.py"):
                shutil.copy2(source / name, target / name)
            sid = "shared chat's ID"
            for home, title in ((default, "Default chat"), (work, "Work chat")):
                with SessionDB(db_path=home / "state.db") as db:
                    db.create_session(sid, source="cli")
                    db.set_session_title(sid, title)
                    db.append_message(sid, "user", "Synthetic profile isolation test")
                    db.set_session_pinned(sid, True)

            origin = dict(os.environ, HERMES_HOME=str(default), TERM="dumb", COLUMNS="40")
            for args in (["plugins", "enable", "session-pins"], ["pins", "list"]):
                result = subprocess.run([hermes, "-p", "work", *args], env=origin,
                                        capture_output=True, text=True, timeout=35)
                self.assertEqual(0, result.returncode, result.stdout + result.stderr)
            self.assertIn("★ Work chat", result.stdout)
            self.assertNotIn("Default chat", result.stdout)
            commands = [line for line in result.stdout.splitlines() if line.startswith("env ")]
            self.assertEqual(1, len(commands), result.stdout)
            command = commands[0]
            self.assertEqual(["env", f"HERMES_HOME={work}", "hermes", "chat", "--resume", sid],
                             shlex.split(command))

            # Paste the literal generated text into the originating shell, with a
            # recorder in place of chat so no provider or gateway is contacted.
            bin_dir = root / "bin"
            bin_dir.mkdir()
            recorder = bin_dir / "hermes"
            recorder.write_text('#!/bin/sh\nprintf "%s\\n" "$HERMES_HOME" "$@"\n', encoding="utf-8")
            recorder.chmod(0o700)
            result = subprocess.run(["/bin/sh", "-c", command], env=dict(origin, PATH=f"{bin_dir}:{origin['PATH']}"),
                                    capture_output=True, text=True, timeout=10)
            self.assertEqual(0, result.returncode, result.stdout + result.stderr)
            selected_home, verb, option, selected_id = result.stdout.splitlines()
            self.assertEqual((str(work), "chat", "--resume", sid), (selected_home, verb, option, selected_id))
            with SessionDB(db_path=Path(selected_home) / "state.db", read_only=True) as db:
                self.assertEqual("Work chat", db.get_session(selected_id)["title"])
