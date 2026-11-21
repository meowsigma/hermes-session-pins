"""Discovery and exact-ID mutation contracts; all fixtures are synthetic."""
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock, patch

from hermes_state import SessionDB
import session_pins as pins


class DiscoveryTests(unittest.TestCase):
    def setUp(self):
        tmp = TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.home = Path(tmp.name)
        env = patch.dict(os.environ, HERMES_HOME=str(self.home))
        env.start()
        self.addCleanup(env.stop)
        self.db = SessionDB(db_path=self.home / 'state.db')
        self.addCleanup(self.db.close)

    def chat(self, sid, title, source='cli', **kwargs):
        self.db.create_session(sid, source=source, model='stored-test-model', **kwargs)
        self.db.set_session_title(sid, title)
        self.db.append_message(sid, 'user', 'transcript-canary')
        return sid

    def test_word_search_reaches_older_chats_and_returns_truthful_pages(self):
        old = self.chat('old-one', 'Alpha PLAN review')
        for i in range(45):
            self.chat(f'recent-{i}', f'Unrelated {i}')
        recent = self.chat('new-two', 'Plan for alpha')
        self.db.set_session_pinned(old, True)
        first = pins.discover_sessions('plan ALPHA', limit=1, home=self.home)
        second = pins.discover_sessions('plan ALPHA', limit=1, offset=1, home=self.home)
        self.assertEqual((2, 1, [old]), (first['total'], first['next_offset'], [r['id'] for r in first['sessions']]))
        self.assertEqual((2, None, [recent]), (second['total'], second['next_offset'], [r['id'] for r in second['sessions']]))
        self.assertEqual(0, pins.discover_sessions('transcript-canary', home=self.home)['total'])
        row = first['sessions'][0]
        self.assertEqual('stored-test-model', row['recorded_model'])
        self.assertGreater(row['last_active'], 0)
        self.assertNotIn('preview', row)

    def test_search_matches_word_at_end_of_full_stored_title(self):
        full_title = 'ordinary words ' * 6 + 'uniquetail'
        sid = self.chat('local-long-title', full_title)
        self.assertEqual(full_title, self.db.get_session(sid)['title'], 'fixture must store the suffix')

        page = json.loads(pins.command_pins_ui(
            json.dumps({'op': 'list', 'query': 'ordinary uniquetail'}), platform='tui',
        ))
        self.assertEqual(1, page['total'])
        row, = page['sessions']
        self.assertEqual(sid, row['id'])
        self.assertEqual(full_title[:90], row['title'])

    def test_projection_keeps_compression_separate_from_fork_and_excludes_hidden_workers(self):
        root = self.chat('root', 'Original project')
        fork = self.chat('fork', 'Forked project', parent_session_id=root, model_config={'_branched_from': root})
        worker = self.chat('worker', 'Hidden worker', parent_session_id=root, model_config={'_delegate_from': root})
        hidden = self.chat('hidden', 'Hidden user project')
        self.db.set_session_hidden(hidden, True)
        self.chat('cron', 'Scheduled project', source='cron')
        self.db.end_session(root, 'compression')
        tip = self.chat('tip', 'Continued project', parent_session_id=root)
        rows = {row['id']: row for row in pins.discover_sessions(home=self.home)['sessions']}
        self.assertEqual({tip, fork}, set(rows))
        self.assertEqual('original', rows[tip]['relationship'])
        self.assertEqual(('fork', tip), (rows[fork]['relationship'], rows[fork]['original_id']))
        self.assertNotIn(worker, rows)

    def test_exact_bulk_keeps_stale_and_hidden_ids_from_redirecting_or_unhiding(self):
        target = self.chat('real id ', 'Real project')
        longer = self.chat('removed-longer', 'removed')
        hidden = self.chat('hidden', 'Hidden project')
        self.db.set_session_hidden(hidden, True)
        results = pins.bulk_set_pins([target, 'removed', hidden, target], True, home=self.home)
        self.assertEqual([target, 'removed', hidden], [r['id'] for r in results])
        self.assertEqual([True, False, False], [r['ok'] for r in results])
        self.assertTrue(self.db.get_session(target)['pinned'])
        self.assertFalse(self.db.get_session(longer)['pinned'])
        self.assertTrue(self.db.get_session(hidden)['hidden'])
        self.assertFalse(self.db.get_session(hidden)['pinned'])

    def test_tool_refuses_messaging_or_missing_caller_before_opening_database(self):
        ctx = Mock()
        pins.register(ctx)
        handler = ctx.register_tool.call_args.kwargs['handler']
        for platform, sid in [('telegram', 'not-local'), ('tui', ''), ('', 'missing-context')]:
            ctx.session_surface.return_value = platform
            with patch.object(pins, 'database', side_effect=AssertionError('unauthorized DB access')):
                self.assertIn('error', json.loads(handler({'action': 'find'}, session_id=sid)))

    def test_registered_tool_uses_selected_exact_ids(self):
        caller = self.chat('caller', 'Local caller')
        target = self.chat('target exact ', 'Another project')
        longer = self.chat('target exact longer', 'Different project')
        ctx = Mock()
        ctx.session_surface.return_value = 'tui'
        pins.register(ctx)
        handler = ctx.register_tool.call_args.kwargs['handler']
        with patch.object(pins, 'get_hermes_home', return_value=self.home) as active_home:
            found = json.loads(handler({'action': 'find', 'query': 'another'}, session_id=caller))
            active_home.assert_called_once_with()
        self.assertEqual([target], [r['id'] for r in found['sessions']])
        for action, expected in [('pin', True), ('unpin', False)]:
            args = {'action': action, 'ids': [found['sessions'][0]['id']], 'scope': found['scope']}
            with patch.object(pins, 'get_hermes_home', return_value=self.home) as active_home:
                result = json.loads(handler(args, session_id=caller))
                active_home.assert_called_once_with()
            self.assertEqual([{'id': target, 'ok': True, 'pinned': expected}], result['results'])
            self.assertEqual(expected, bool(self.db.get_session(target)['pinned']))
            self.assertFalse(self.db.get_session(longer)['pinned'])
            self.assertFalse(self.db.get_session(caller)['pinned'])

    def test_stock_local_pins_never_opens_clarify(self):
        self.db.set_session_pinned(self.chat('pinned-chat', 'Pinned project'), True)
        ctx = Mock()
        for surface in ('cli', 'tui', 'local', 'desktop'):
            for mode in ('', 'list', 'manage'):
                self.assertIn('Pinned project', pins.command_pins(ctx, mode, platform=surface))
        ctx.ask_choice.assert_not_called()

    def test_text_search_returns_metadata_without_opening_a_question(self):
        self.chat('matched', 'My old project')
        ctx = Mock()
        result = pins.command_pins(ctx, 'find PROJECT old', platform='tui')
        self.assertIn('Showing 1 of 1 matching chats', result)
        self.assertIn('recorded model: stored-test-model', result)
        self.assertIn('last active:', result)
        self.assertNotIn('transcript-canary', result)
        ctx.ask_choice.assert_not_called()

    def test_ui_protocol_refuses_mutation_after_profile_scope_changes(self):
        sid = self.chat('same-id', 'Source project')
        opened = json.loads(pins.command_pins_ui('{"op":"list"}', platform='tui'))
        other = self.home / 'other'
        other.mkdir()
        with SessionDB(db_path=other / 'state.db') as db:
            db.create_session(sid, source='cli')
            request = json.dumps({'op': 'set', 'scope': opened['scope'], 'id': sid, 'pinned': True})
            with patch.dict(os.environ, HERMES_HOME=str(other)):
                self.assertIn('error', json.loads(pins.command_pins_ui(
                    request, platform='tui', widget_admit=lambda: True)))
            self.assertFalse(db.get_session(sid)['pinned'])
        # A matching profile is necessary, but native widget admission is also
        # required. SelectionFollowups separately regresses missing admission.
        self.assertTrue(json.loads(pins.command_pins_ui(
            request, platform='tui', widget_admit=lambda: True))['ok'])
        self.assertTrue(self.db.get_session(sid)['pinned'])
