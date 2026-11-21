"""Astra plugin follow-ups, using only synthetic stores and callers."""
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock, patch

from hermes_state import SessionDB
import session_pins as pins


class AstraPluginFollowups(unittest.TestCase):
    def setUp(self):
        tmp = TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.home = Path(tmp.name)
        env = patch.dict(os.environ, HERMES_HOME=str(self.home))
        env.start()
        self.addCleanup(env.stop)
        self.db = SessionDB(db_path=self.home / 'state.db')
        self.addCleanup(self.db.close)
        self.ctx = Mock()
        self.ctx.session_surface.return_value = 'tui'

    def tool(self, args, caller='caller'):
        return json.loads(pins.discovery_tool(self.ctx, args, session_id=caller))

    def test_bulk_refuses_missing_and_foreign_scopes_with_colliding_local_ids(self):
        target = 'exact target'
        other = self.home / 'other'
        other.mkdir()
        with SessionDB(db_path=other / 'state.db') as other_db:
            for db in (self.db, other_db):
                for sid in ('caller', target):
                    db.create_session(sid, source='cli')
            found = self.tool({'action': 'find', 'query': target})
            self.assertEqual((1, None, [target]), (
                found['total'], found['next_offset'], [r['id'] for r in found['sessions']],
            ))
            scope = found['scope']
            self.assertTrue(scope)
            with patch.dict(os.environ, HERMES_HOME=str(other)):
                other_found = self.tool({'action': 'find', 'query': target})
            self.assertEqual([target], [r['id'] for r in other_found['sessions']])
            self.assertNotEqual(scope, other_found['scope'])

            for action, before in (('pin', False), ('unpin', True)):
                for db in (self.db, other_db):
                    self.assertTrue(db.set_session_pinned(target, before))
                args = {'action': action, 'ids': [target]}
                for home, supplied in ((self.home, {}), (self.home, {'scope': None}),
                                       (other, {'scope': scope})):
                    with self.subTest(action=action, home=home, supplied=supplied):
                        with patch.dict(os.environ, HERMES_HOME=str(home)):
                            refused = self.tool({**args, **supplied})
                        self.assertEqual({'error'}, set(refused))
                        for db in (self.db, other_db):
                            self.assertEqual(before, bool(db.get_session(target)['pinned']))

    def test_valid_scope_does_not_replace_stored_owner_check(self):
        self.db.create_session('caller', source='cli')
        self.db.create_session('remote', source='telegram')
        self.db.create_session('hidden', source='cli')
        self.db.set_session_hidden('hidden', True)
        self.db.create_session('target', source='cli')
        scope = self.tool({'action': 'find', 'query': 'target'})['scope']
        for caller in ('remote', 'hidden', 'missing'):
            with self.subTest(caller=caller):
                result = self.tool({'action': 'pin', 'scope': scope, 'ids': ['target']}, caller)
                self.assertIn('stored local owner chat', result['error'])
                self.assertFalse(self.db.get_session('target')['pinned'])

    def test_stock_pins_uses_projected_metadata_and_safe_resume_only(self):
        fixtures = [
            ('visible session', None, 'cli', {}),
            ('unsafe\tid', 'Unsafe ID label', 'cli', {}),
            ('background-id', 'Background title', 'cron', {}),
            ('delegate-id', 'Delegate title', 'cli', {'model_config': {'_delegate_from': 'visible session'}}),
            ('lineage-root', 'Root title', 'cli', {}),
        ]
        for sid, title, source, kwargs in fixtures:
            self.db.create_session(sid, source=source, **kwargs)
            if title is not None:
                self.db.set_session_title(sid, title)
            self.db.append_message(sid, 'user', 'TRANSCRIPT-CANARY ' + sid)
        self.db.end_session('lineage-root', 'compression')
        self.db.create_session('hidden-tip', source='cli', parent_session_id='lineage-root')
        self.db.set_session_title('hidden-tip', 'Hidden tip title')
        self.db.append_message('hidden-tip', 'user', 'TRANSCRIPT-CANARY Tip')
        for sid, *_ in fixtures:
            self.assertTrue(self.db.set_session_pinned(sid, True))
        self.db.set_session_hidden('hidden-tip', True)
        self.assertTrue(self.db.get_session('hidden-tip')['hidden'])
        # Native hiding follows the compression lineage; listing must preserve it.
        self.assertTrue(self.db.get_session('lineage-root')['hidden'])

        for surface in ('cli', 'tui', 'desktop'):
            for mode in ('', 'list', 'manage'):
                with self.subTest(surface=surface, mode=mode):
                    result = pins.command_pins(self.ctx, mode, platform=surface)
                    self.assertIn('★ Untitled chat\n  /resume visible session', result)
                    self.assertIn('★ Unsafe ID label\n  Resume command unavailable', result)
                    self.assertEqual(['/resume visible session'], [
                        line.strip() for line in result.splitlines() if line.strip().startswith('/resume ')
                    ])
                    for text in ('TRANSCRIPT-CANARY', 'background-id', 'Background title',
                                 'delegate-id', 'Delegate title', 'lineage-root', 'Root title',
                                 'hidden-tip', 'Hidden tip title', '\t'):
                        self.assertNotIn(text, result)
        self.ctx.ask_choice.assert_not_called()
        for sid, *_ in fixtures:
            self.assertTrue(self.db.get_session(sid)['pinned'])
        self.assertTrue(self.db.get_session('hidden-tip')['hidden'])
        self.assertTrue(self.db.get_session('lineage-root')['hidden'])