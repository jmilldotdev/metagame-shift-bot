import json
from datetime import datetime, timedelta
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import bot

SHEET = ',Friday (11/6),,,Saturday (11/7),Sunday (11/8)\n,1pm-5pm (3),5pm-9pm (3),9pm-12am (2),9pm-12am (2),9pm-12am (2)\nAlice,Shift,,shift,shift,shift\nBob,,shift,,,\nshifts filled:,1,1,1,1,1\n'


class ScheduleTests(unittest.TestCase):
    def setUp(self):
        self.config = bot.configuration()
        self.schedule = bot.parse_schedule(SHEET, self.config)

    def active(self, at):
        return bot.active_at(self.schedule, datetime.fromisoformat(at), self.config)

    def test_boundaries(self):
        self.assertEqual(self.active('2026-11-06T12:59:59-08:00'), set())
        self.assertEqual(self.active('2026-11-06T13:00:00-08:00'), {'Alice'})
        self.assertEqual(self.active('2026-11-06T16:59:59-08:00'), {'Alice'})
        self.assertEqual(self.active('2026-11-06T17:00:00-08:00'), {'Bob'})
        self.assertEqual(self.active('2026-11-06T21:00:00-08:00'), {'Alice'})

    def test_midnight_every_day(self):
        for day in ('06', '07', '08'):
            self.assertEqual(self.active(f'2026-11-{day}T23:59:59-08:00'), {'Alice'})
            end = datetime.fromisoformat(f'2026-11-{day}T00:00:00-08:00') + timedelta(days=1)
            self.assertEqual(bot.active_at(self.schedule, end, self.config), set())

    def test_pst_and_utc(self):
        self.assertEqual(self.active('2026-11-06T21:00:00+00:00'), {'Alice'})
        self.assertEqual(self.schedule['Alice'][0][0].utcoffset(), timedelta(hours=-8))
        self.assertEqual(self.schedule['Alice'][0][0].tzname(), 'PST')
        with self.assertRaises(ValueError):
            self.active('2026-11-06T14:00:00')

    def test_grace(self):
        self.config.update(grace_before_minutes=5, grace_after_minutes=10)
        self.assertEqual(self.active('2026-11-06T12:55:00-08:00'), {'Alice'})
        self.assertEqual(self.active('2026-11-06T17:09:59-08:00'), {'Alice', 'Bob'})
        self.assertEqual(self.active('2026-11-06T17:10:00-08:00'), {'Bob'})

    def test_names(self):
        matched, issues = bot.match_names([' Alice (Team Lead)\n', 'Unknown', 'Twin', 'None'], [('Alice', 'alice'), ('Twin', 'a'), ('Twin', 'b'), ('None', 'no discord')], {})
        self.assertEqual(matched, {' Alice (Team Lead)\n': 'alice'})
        self.assertEqual({i['name']: i['reason'] for i in issues}, {'Unknown': 'unmatched', 'Twin': 'ambiguous', 'None': 'no Discord'})
        matched, issues = bot.match_names(['Alias'], [('Alice', 'alice')], {'Alias': 'Alice'})
        self.assertEqual(matched, {'Alias': 'alice'})

    def test_invalid_snapshot(self):
        for text in ('<html>error</html>', ',Friday (11/6)\n,unknown\nAlice,shift'):
            with self.assertRaises(ValueError):
                bot.parse_schedule(text, self.config)

    def test_diff_idempotence(self):
        self.assertEqual(bot.plan({'1', '2'}, {'2', '3'}), (['1'], ['3']))
        self.assertEqual(bot.plan({'1', '2'}, {'1', '2'}), ([], []))

    def test_last_good_fallback(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(bot.os.environ, {'CACHE_FILE': str(Path(folder) / 'state.json')}):
            cache = bot.Cache()
            cache.data['sheet'] = SHEET
            cache.save()
            with patch.object(bot, 'urlopen', side_effect=OSError('offline')):
                self.assertEqual(bot.fetch_schedule(self.config, bot.Cache()), self.schedule)

    def test_live_reconcile_and_mention_scope(self):
        class FakeDiscord:
            calls = []
            def __init__(self, token, guild):
                pass
            def members(self):
                return [{'user': {'id': '1'}, 'roles': []}, {'user': {'id': '2'}, 'roles': ['99']}]
            def resolve(self, handle):
                return {'alice': '1', 'bob': '2'}[handle], None
            def request(self, *args, **kwargs):
                self.calls.append((args, kwargs))
        with tempfile.TemporaryDirectory() as folder, patch.dict(bot.os.environ, {'CACHE_FILE': str(Path(folder) / 'state.json'), 'GUILD_ID': '88', 'ROLE_ID': '99'}), patch.object(bot, 'fetch_schedule', return_value=self.schedule), patch.object(bot, 'load_mapping', return_value=[('Alice', 'alice'), ('Bob', 'bob')]), patch.object(bot, 'secrets', return_value=('token', 'https://discord.com/api/webhooks/test/token')), patch.object(bot, 'Discord', FakeDiscord):
            result = bot.reconcile(self.config, bot.Cache(), datetime.fromisoformat('2026-11-06T14:00:00-08:00'), False)
        self.assertEqual(result['role_adds'], ['1'])
        self.assertEqual(result['role_removes'], ['2'])
        self.assertEqual(FakeDiscord.calls[0][0][0], 'DELETE')
        self.assertEqual(FakeDiscord.calls[1][0][0], 'PUT')
        payload = FakeDiscord.calls[2][0][2]
        self.assertEqual(payload, {'content': 'Now on shift: <@1>', 'allowed_mentions': {'parse': [], 'users': ['1']}})


class ConfigurationAndCliTests(unittest.TestCase):
    def test_optional_local_configuration(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(bot, 'ROOT', Path(folder)):
            root = Path(folder)
            (root / 'config.json').write_text(json.dumps({'year': 2030, 'sheet_url': 'placeholder', 'name_overrides': {}}))
            self.assertEqual(bot.configuration()['sheet_url'], 'placeholder')
            (root / 'config.local.json').write_text(json.dumps({'sheet_url': 'local-sheet', 'name_overrides': {'Alias': 'Example'}}))
            self.assertEqual(bot.configuration(), {'year': 2030, 'sheet_url': 'local-sheet', 'name_overrides': {'Alias': 'Example'}})

    def test_cli_exit_status(self):
        for arguments, result, expected in (
            (['bot.py', '--live'], {'blocked': 'unresolved'}, 1),
            (['bot.py', '--live'], {'blocked': 'unresolved', 'stale_sheet': {'saved_at': None, 'error_type': 'OSError'}}, 1),
            (['bot.py', '--live'], {'role_adds': [], 'role_removes': []}, 0),
            (['bot.py'], {'dry_run': True}, 0),
        ):
            with self.subTest(arguments=arguments, result=result), patch('sys.argv', arguments), patch.object(bot, 'configuration', return_value={}), patch.object(bot, 'Cache'), patch.object(bot, 'reconcile', return_value=result), patch('builtins.print'):
                self.assertEqual(bot.main(), expected)

    def test_stale_sheet_exit_status(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(bot.os.environ, {'CACHE_FILE': str(Path(folder) / 'state.json')}):
            cache = bot.Cache()
            cache.data.update(sheet=SHEET, sheet_saved_at='2030-01-01T00:00:00+00:00')
            cache.save()
            with patch('sys.argv', ['bot.py']), patch.object(bot, 'urlopen', side_effect=OSError('offline')), patch.object(bot, 'load_mapping', return_value=[('Alice', 'alice'), ('Bob', 'bob')]), patch('builtins.print') as output:
                self.assertEqual(bot.main(), 75)
            result = json.loads(output.call_args.args[0])
            self.assertEqual(result['stale_sheet'], {'saved_at': '2030-01-01T00:00:00+00:00', 'error_type': 'OSError'})


if __name__ == '__main__':
    unittest.main()
