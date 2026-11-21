"""Regression contracts for explicit profile and option-shaped resume IDs."""
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import tempfile
import unittest

import session_pins as pins

from tests.test_picker_style import line_text, profile, render_picker


class ResumeArgumentTests(unittest.TestCase):
    def test_option_shaped_id_is_an_exact_resume_value_not_a_profile_flag(self):
        for sid in ('--profile=other', '--profile', '-p', '--', '-123'):
            with self.subTest(sid=sid):
                home = Path('/synthetic/default-home')
                expected = ['chat', '--resume=' + sid, '--profile', 'default']
                self.assertEqual(expected, pins.resume_argv(sid, home))
                if os.name == 'posix':
                    self.assertEqual(['env', 'HERMES_HOME=' + str(home), 'hermes', *expected],
                                     shlex.split(pins.resume_command(sid, home=home)))

    def test_named_home_does_not_reselect_default(self):
        home = Path('/synthetic/root/profiles/work')
        self.assertEqual(['chat', '--resume', 'exact chat ID'], pins.resume_argv('exact chat ID', home))

    @unittest.skipUnless(shutil.which('hermes'), 'needs the installed Hermes CLI')
    def test_real_cli_parser_keeps_option_shaped_id_out_of_profile_selection(self):
        with tempfile.TemporaryDirectory(prefix='pins-option-profile-') as temp:
            home = Path(temp)
            (home / 'active_profile').write_text('does-not-exist\n')
            argv = pins.resume_argv('--profile=also-does-not-exist', home)
            result = subprocess.run([shutil.which('hermes'), *argv, '--help'],
                                    env=dict(os.environ, HERMES_HOME=temp),
                                    capture_output=True, text=True, timeout=35)
            self.assertEqual(0, result.returncode, result.stdout + result.stderr)
            self.assertIn('--resume', result.stdout)

    def test_unsafe_slash_ids_are_refused_not_rewritten(self):
        for sid in ('007', '[chat]', '<chat>', '"chat"', "'chat'", 'trailing ', '\x1b[31mchat', 'line\nchat'):
            with self.subTest(sid=repr(sid)), self.assertRaises(pins.PinsError):
                pins.resume_command(sid)

    def test_unsafe_home_is_not_emitted_as_a_shell_command(self):
        if os.name != 'posix':
            self.skipTest('POSIX command generation only')
        for path in ('/synthetic/$HOME/path', '/synthetic/line\npath', '/synthetic/trailing '):
            with self.subTest(path=repr(path)), self.assertRaises(pins.PinsError):
                pins.resume_command('exact-id', home=Path(path))


class NarrowTitleTests(unittest.TestCase):
    def test_forty_columns_reserves_room_for_title_and_star(self):
        rows = [{'id': 'long-session-id', 'title': 'Important pinned project', 'pinned': True,
                 'started_at': 1, 'message_count': 9999}]
        with profile():
            _, frames = render_picker(rows, width=40, height=10)
        text = '\n'.join(line_text(line) for line in frames[0][0])
        self.assertIn('★ Important pinned', text)


if __name__ == '__main__':
    unittest.main()
