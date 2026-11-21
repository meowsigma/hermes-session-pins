"""Exercise plugin discovery and a real terminal without connecting a model."""
import os
from pathlib import Path
import select
import shutil
import subprocess
import tempfile
import time
import unittest

from hermes_state import SessionDB


@unittest.skipUnless(os.name == "posix" and shutil.which("hermes"), "needs a local POSIX Hermes CLI")
class CLIIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix="hermes-pins-cli-")
        cls.home = Path(cls.tmp.name)
        cls.env = dict(os.environ, HERMES_HOME=str(cls.home), TERM="xterm-256color")
        cls.hermes = shutil.which("hermes")
        source = Path(__file__).resolve().parents[1]
        target = cls.home / "plugins" / "session-pins"
        target.mkdir(parents=True)
        for filename in ("plugin.yaml", "__init__.py", "session_pins.py"):
            shutil.copy2(source / filename, target / filename)
        enabled = subprocess.run([cls.hermes, "plugins", "enable", "session-pins"], env=cls.env, capture_output=True, text=True, timeout=35)
        if enabled.returncode:
            cls.tmp.cleanup()
            raise RuntimeError(enabled.stdout + enabled.stderr)
        with SessionDB(db_path=cls.home / "state.db") as db:
            db.create_session("important-old", source="cli")
            db.set_session_title("important-old", "Important project")
            db.append_message("important-old", "user", "Synthetic pin test")
            db.set_session_pinned("important-old", True)
            db.create_session("ordinary-new", source="cli")
            db.set_session_title("ordinary-new", "Ordinary recent chat")
            db.append_message("ordinary-new", "user", "Synthetic recent test")

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_real_cli_discovers_and_lists_plugin(self):
        result = subprocess.run([self.hermes, "pins", "list"], env=self.env, capture_output=True, text=True, timeout=35)
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertIn("★ Important project", result.stdout)
        self.assertIn("hermes chat --resume important-old", result.stdout)
        self.assertNotIn("ordinary-new", result.stdout)
        help_result = subprocess.run([self.hermes, "pins", "--help"], env=self.env, capture_output=True, text=True, timeout=35)
        self.assertEqual(0, help_result.returncode, help_result.stderr)
        self.assertIn("--print", help_result.stdout)

    def test_real_pty_star_highlight_and_enter_print_handoff(self):
        import fcntl
        import pty
        import struct
        import termios
        master, slave = pty.openpty()
        fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", 32, 110, 0, 0))
        process = subprocess.Popen([self.hermes, "pins", "--print"], env=self.env, stdin=slave, stdout=slave, stderr=slave, start_new_session=True)
        os.close(slave)
        data = bytearray()
        sent = False
        deadline = time.monotonic() + 35
        try:
            while time.monotonic() < deadline:
                if select.select([master], [], [], 0.2)[0]:
                    try:
                        chunk = os.read(master, 65536)
                    except OSError:
                        break
                    if not chunk:
                        break
                    data.extend(chunk)
                    if b"\x1b[6n" in chunk:
                        os.write(master, b"\x1b[1;1R")
                    if not sent and b"Important project" in data and b"Ordinary recent chat" in data:
                        os.write(master, b"\r")
                        sent = True
                if process.poll() is not None:
                    break
            if process.poll() is None:
                process.terminate()  # Only the exact test child started above.
                process.wait(timeout=5)
                self.fail("Picker timed out: " + data.decode(errors="replace"))
            text = data.decode(errors="replace")
            self.assertEqual(0, process.returncode, text)
            self.assertTrue(sent, text)
            self.assertIn("★ Important project", text)
            self.assertIn("hermes chat --resume important-old", text)
            self.assertLess(text.index("Important project"), text.index("Ordinary recent chat"))
            self.assertIn("\x1b[0;1;7m", text)  # Bold reverse selected row, real ANSI output.
            print("\nReal CLI/PTY: starred pin first; bold/reverse selection; Enter returned exact resume command.")
        finally:
            os.close(master)
            if process.poll() is None:
                process.terminate()
                process.wait(timeout=5)
