"""Selected mutations use the native writer, never a read-then-legacy-write fallback."""
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from hermes_state import SessionDB
import session_pins as pins


class SelectionFollowups(unittest.TestCase):
    def setUp(self):
        tmp = TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.home = Path(tmp.name)
        env = patch.dict(os.environ, HERMES_HOME=tmp.name)
        env.start()
        self.addCleanup(env.stop)
        self.db = SessionDB(db_path=self.home / 'state.db')
        self.addCleanup(self.db.close)
        self.db.create_session('root', source='cli')
        self.db.end_session('root', 'compression')
        self.db.create_session('tip', source='cli', parent_session_id='root')

    def test_selected_mutation_refuses_stock_core_without_breaking_explicit_pin_unpin(self):
        with patch.object(SessionDB, 'set_projected_session_pinned', None, create=True):
            result, = pins.bulk_set_pins(['tip'], True, home=self.home)
            self.assertFalse(result['ok'])
            self.assertIn('safe session selection support', result['error'])
            self.assertFalse(self.db.get_session('tip')['pinned'])
            self.assertTrue(pins.set_pin('tip', True, exact=True, home=self.home)['pinned'])
            self.assertFalse(pins.set_pin('tip', False, exact=True, home=self.home)['pinned'])

    def test_helper_has_no_mutation_authority_outside_widget_launch(self):
        page = json.loads(pins.command_pins_ui('{"op":"list"}', platform='tui'))
        request = dict(op='set', scope=page['scope'], id='tip', pinned=True)
        reply = json.loads(pins.command_pins_ui(json.dumps(request), platform='tui'))
        self.assertIn('active native session selector', reply['error'])
        self.assertFalse(self.db.get_session('tip')['pinned'])

    def test_write_rechecks_projected_tip_inside_transaction(self):
        native = SessionDB.set_projected_session_pinned
        cases = ['hide', 'supersede', 'background', 'delegate', 'eligible']
        for case in cases:
            with self.subTest(case=case):
                root, tip = f'{case}-root', f'{case}-tip'
                self.db.create_session(root, source='cli')
                self.db.end_session(root, 'compression')
                self.db.create_session(tip, source='cli', parent_session_id=root)
                listing = pins.discover_sessions(tip, home=self.home)
                self.assertEqual([tip], [row['id'] for row in listing['sessions']])

                def at_writer(db, exact_id, pinned, **kwargs):
                    # Commit from another connection immediately before the native writer starts.
                    self.assertEqual(tip, exact_id)
                    if case == 'hide':
                        self.db.set_session_hidden(tip, True)
                    elif case == 'supersede':
                        self.db.end_session(tip, 'compression')
                        self.db.create_session('replacement', source='cli', parent_session_id=tip)
                    elif case == 'background':
                        self.db._execute_write(lambda c: c.execute('UPDATE sessions SET source=? WHERE id=?', ('cron', tip)))
                    elif case == 'delegate':
                        self.db._execute_write(lambda c: c.execute('UPDATE sessions SET model_config=? WHERE id=?',
                                                                  (json.dumps({'_delegate_from': root}), tip)))
                    return native(db, exact_id, pinned, **kwargs)

                with patch.object(SessionDB, 'set_projected_session_pinned', at_writer):
                    result, = pins.bulk_set_pins([tip], True, home=self.home)
                self.assertEqual(case == 'eligible', result['ok'], result)
                self.assertEqual(case == 'eligible', bool(self.db.get_session(tip)['pinned']))
                self.assertEqual(case == 'eligible', bool(self.db.get_session(root)['pinned']))
                self.assertEqual(case == 'hide', bool(self.db.get_session(tip)['hidden']))
        result, = pins.bulk_set_pins(['eligible-tip'], False, home=self.home)
        self.assertTrue(result['ok'], result)
        self.assertFalse(self.db.get_session('eligible-root')['pinned'])
        self.assertFalse(self.db.get_session('eligible-tip')['pinned'])
