"""Alchemy usage: Kira's ledger, the official summary with an Access Key, and the app's usage view."""
import datetime as dt
import io
import json
import os
from pathlib import Path
import socket
import stat
import tempfile
import unittest
import urllib.error
from unittest.mock import patch

import kira_usage
from kira_cli import initialize, sample
from kira_jobs import JobError, JobStore, atomic
from kira_service import Application

KEY = 'synthetic-access-key-0123456789'
NOW = dt.datetime(2026, 11, 15, 12, 0, tzinfo=dt.timezone.utc)
Z = lambda t: t.isoformat().replace('+00:00', 'Z')  # noqa: E731
SUMMARY = {'data': {'totals': {'monthToDate': {'amount': '4210000', 'unit': 'CU', 'usd': 0},
                               'last7Days': {'amount': 2900000, 'unit': 'CU', 'usd': 0},
                               'last30Days': {'amount': 6800000.0, 'unit': 'CU', 'usd': 0}},
                    'billingPeriod': {'start': '2026-11-01', 'end': '2026-11-30'},
                    'usageLimit': {'unit': 'CU', 'limit': 30000000, 'used': 4210000, 'remaining': 25790000, 'percentUsed': 14.03},
                    'freshness': {'dataThrough': '2026-11-15T11:50:00Z', 'containsPartialToday': True, 'updateCadence': 'minute'}}}


class Response(io.BytesIO):
    status = 200
    def __enter__(self): return self
    def __exit__(self, *args): return False


def opener_returning(body, status=200, seen=None):
    def opener(request, timeout):
        if seen is not None:
            seen.append((request.full_url, request.get_header('Authorization'), timeout))
        if status != 200:
            raise urllib.error.HTTPError(request.full_url, status, 'refused', {}, io.BytesIO(json.dumps(body).encode()))
        return Response(json.dumps(body).encode())
    return opener


def write_ledger(root, rows):
    for row in rows:
        kira_usage.append(row, root)


class LedgerTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def test_data_api_requests_are_priced_and_other_hosts_or_refusals_are_not(self):
        with patch.object(kira_usage, 'current_job', lambda: 'job-a'), patch.dict(os.environ, {'KIRA_BATCH_ID': ''}):
            kira_usage.note_request('https://api.g.alchemy.com/data/v1/KEY/assets/tokens/balances/by-address', 200, self.root)
            kira_usage.note_request('https://api.g.alchemy.com/prices/v1/KEY/tokens/by-address', None, self.root)
            kira_usage.note_request('https://api.g.alchemy.com/data/v1/KEY/assets/tokens/by-address', 429, self.root)
            kira_usage.note_request('https://api.g.alchemy.com/prices/v1/KEY/tokens/by-symbol', 403, self.root)
            kira_usage.note_request('https://example.com/assets/tokens/balances/by-address', 200, self.root)
            kira_usage.note_request('not a url at all', 200, self.root)
        rows = kira_usage.lines(self.root)
        self.assertEqual([(r['methods'], r['cu'], r['job']) for r in rows],
                         [({'token_balances_by_wallet': [1, 200]}, 200, 'job-a'), ({'token_prices_by_address': [1, 40]}, 40, 'job-a')])
        files = list((self.root / 'usage').glob('*.jsonl'))
        self.assertEqual(len(files), 1)
        self.assertEqual(stat.S_IMODE(files[0].stat().st_mode), 0o600)
        self.assertNotIn('KEY', files[0].read_text())

    def test_summary_totals_and_last_run_group_a_batch(self):
        batch_jobs = ['job-1', 'job-2', 'job-3']
        write_ledger(self.root, [
            {'at': Z(NOW - dt.timedelta(days=40)), 'source': 'node', 'job': 'old', 'batch': None, 'cu': 999, 'requests': 9, 'methods': {}},
            {'at': Z(NOW - dt.timedelta(days=9)), 'source': 'node', 'job': 'job-0', 'batch': None, 'cu': 100, 'requests': 4, 'methods': {}},
            {'at': Z(NOW - dt.timedelta(days=2)), 'source': 'node', 'job': 'job-0b', 'batch': None, 'cu': 50, 'requests': 2, 'methods': {}},
            {'at': Z(NOW - dt.timedelta(minutes=30)), 'source': 'batch', 'job': None, 'batch': 'batch-x', 'jobs': batch_jobs, 'scope': 'fast', 'cu': 0, 'requests': 0, 'methods': {}},
            {'at': Z(NOW - dt.timedelta(minutes=29)), 'source': 'node', 'job': None, 'batch': 'batch-x', 'cu': 1000, 'requests': 40, 'methods': {}},
            {'at': Z(NOW - dt.timedelta(minutes=28)), 'source': 'python', 'job': 'job-2', 'batch': 'batch-x', 'cu': 360, 'requests': 1, 'methods': {}},
        ])
        with (self.root / 'usage' / 'alchemy-2026-11.jsonl').open('a') as stream:
            stream.write('not json\n{"at": 5}\n')
        view = kira_usage.summary(self.root, now_at=NOW)
        self.assertEqual(view['totals']['this_month'], {'cu': 1510, 'requests': 47})
        self.assertEqual(view['totals']['last_7_days'], {'cu': 1410, 'requests': 43})
        self.assertEqual(view['totals']['today']['cu'], 1360)
        self.assertEqual({k: view['last_run'][k] for k in ('kind', 'cu', 'requests', 'wallets', 'scope')},
                         {'kind': 'batch', 'cu': 1360, 'requests': 41, 'wallets': 3, 'scope': 'fast'})
        self.assertNotIn('jobs', view['last_run'])
        self.assertIn('Other apps', view['basis'])

    def test_job_usage_reports_a_batch_total_or_the_job_alone(self):
        write_ledger(self.root, [
            {'at': kira_usage.now(), 'source': 'batch', 'job': None, 'batch': 'batch-y', 'jobs': ['a', 'b'], 'scope': 'full', 'cu': 0, 'requests': 0, 'methods': {}},
            {'at': kira_usage.now(), 'source': 'node', 'job': None, 'batch': 'batch-y', 'cu': 700, 'requests': 30, 'methods': {}},
            {'at': kira_usage.now(), 'source': 'node', 'job': 'solo', 'batch': None, 'cu': 80, 'requests': 3, 'methods': {}},
            {'at': kira_usage.now(), 'source': 'python', 'job': 'solo', 'batch': None, 'cu': 360, 'requests': 1, 'methods': {}},
        ])
        self.assertEqual(kira_usage.job_usage('b', self.root), {'cu': 700, 'requests': 30, 'batch_wallets': 2})
        self.assertEqual(kira_usage.job_usage('solo', self.root), {'cu': 440, 'requests': 4})
        self.assertIsNone(kira_usage.job_usage('unknown', self.root))


class ReaderCountTest(unittest.TestCase):
    """The isolated reader counts what Alchemy answered, not what it throttled, refused or never received."""
    URL = 'https://api.g.alchemy.com/data/v1/KEY/assets/tokens/balances/by-address'

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.root = Path(self.temp.name)
        self.env = patch.dict(os.environ, {'KIRA_DATA_DIR': str(self.root), 'KIRA_BATCH_ID': '', 'KIRA_JOB_ID': 'job-r'}); self.env.start()

    def tearDown(self):
        self.env.stop(); self.temp.cleanup()

    def read(self, body):
        import multiprocessing
        import public_discovery

        class Reader:
            def __init__(self, target, args, daemon):
                self.output, self.pid = args[2], None
            def start(self):
                self.output.send_bytes(body)
            def is_alive(self):
                return False
            def join(self, timeout=None):
                pass

        class Context:
            Pipe = staticmethod(multiprocessing.Pipe)
            Process = Reader

        with patch.object(public_discovery.multiprocessing, 'get_context', return_value=Context()), patch.object(kira_usage, 'current_job', lambda: 'job-r'):
            return public_discovery.fetch_bounded(self.URL, 5, {'addresses': []})

    def test_only_answers_alchemy_bills_are_counted(self):
        import public_discovery
        self.assertEqual(public_discovery.answered(b'{"data": {"tokens": []}}'), (True, None))
        self.assertEqual(public_discovery.answered(b'{"error": {"code": "http_error", "http_status": 429, "retry_after": 3}}'), (True, 429))
        self.assertEqual(public_discovery.answered(b'{"error":{"code":"provider_unavailable"}}'), (False, None))
        self.assertEqual(public_discovery.answered(b'{"error":{"code":"response_limit"}}'), (True, None))
        self.assertEqual(public_discovery.answered(b'{"error": "text"}'), (True, None))
        self.assertEqual(public_discovery.answered(b'{"error":'), (True, None))
        self.assertEqual(self.read(b'{"data": {"tokens": []}}'), {'data': {'tokens': []}})
        for refused in (429, 403):
            self.read(json.dumps({'error': {'code': 'http_error', 'http_status': refused, 'retry_after': None}}).encode())
        self.read(b'{"error":{"code":"provider_unavailable"}}')
        self.read(json.dumps({'error': {'code': 'http_error', 'http_status': 500, 'retry_after': None}}).encode())
        rows = kira_usage.lines(self.root)
        self.assertEqual([(r['cu'], r['job']) for r in rows], [(200, 'job-r'), (200, 'job-r')], 'The answer and the server error count; 429, 403 and no answer do not.')
        self.assertEqual(stat.S_IMODE((self.root / 'usage').stat().st_mode), 0o700)


class OfficialUsageTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.root = Path(self.temp.name)
        self.env = patch.dict(os.environ, {}, clear=False); self.env.start(); os.environ.pop(kira_usage.ACCESS_ENV, None)

    def tearDown(self):
        self.env.stop(); self.temp.cleanup()

    def test_access_key_is_private_and_validated(self):
        for bad in ('', 'short', 'https://admin-api.alchemy.com/' + KEY, KEY + ' extra', 'x' * 600):
            self.assertFalse(kira_usage.valid_key(bad), bad)
            if bad:
                with self.assertRaises(ValueError):
                    kira_usage.save_access_key(bad, self.root)
        self.assertIsNone(kira_usage.access_key(self.root))
        kira_usage.save_access_key(KEY, self.root)
        path = self.root / '.secrets' / kira_usage.ACCESS_FILE
        self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(path.parent.stat().st_mode), 0o700)
        self.assertEqual(kira_usage.access_key(self.root), KEY)
        self.assertTrue(kira_usage.view(self.root)['access_key'])
        kira_usage.store_official(200, SUMMARY, self.root)
        kira_usage.forget_access_key(self.root)
        self.assertIsNone(kira_usage.access_key(self.root))
        self.assertIsNone(kira_usage.official(self.root))

    def test_check_saves_the_fields_the_app_shows_and_never_the_key(self):
        self.assertIsNone(kira_usage.check_official(self.root, opener=opener_returning(SUMMARY)))
        kira_usage.save_access_key(KEY, self.root)
        seen = []
        record = kira_usage.check_official(self.root, timeout=7, opener=opener_returning(SUMMARY, seen=seen))
        self.assertEqual(seen, [(kira_usage.SUMMARY_URL, 'Bearer ' + KEY, 7)])
        self.assertTrue(record['ok'])
        summary = record['summary']
        self.assertEqual((summary['month_to_date']['cu'], summary['last_7_days']['cu'], summary['last_30_days']['cu']), (4210000, 2900000, 6800000))
        self.assertEqual(summary['usage_limit'], {'unit': 'CU', 'limit': 30000000, 'used': 4210000, 'remaining': 25790000, 'percent_used': 14.03})
        self.assertEqual(summary['data_through'], '2026-11-15T11:50:00Z')
        cache = (self.root / kira_usage.OFFICIAL_CACHE).read_text()
        self.assertNotIn(KEY, cache)
        self.assertEqual(kira_usage.view(self.root)['official']['summary'], summary)
        self.assertTrue(kira_usage.recently_checked(self.root, 60))

    def test_a_refused_check_keeps_the_last_good_summary_and_redacts_the_key(self):
        kira_usage.save_access_key(KEY, self.root)
        good = kira_usage.check_official(self.root, opener=opener_returning(SUMMARY))
        refused = kira_usage.check_official(self.root, opener=opener_returning({'error': {'message': 'Invalid token ' + KEY}}, status=401))
        self.assertFalse(refused['ok'])
        self.assertEqual(refused['error']['status'], 401)
        self.assertIn('Security tab', refused['error']['hint'])
        self.assertNotIn(KEY, json.dumps(refused))
        self.assertIn('[redacted]', refused['error']['message'])
        self.assertEqual(refused['summary'], good['summary'])
        self.assertEqual(refused['summary_checked_at'], good['checked_at'])
        def offline(request, timeout):
            raise urllib.error.URLError('offline')
        failed = kira_usage.check_official(self.root, opener=offline)
        self.assertEqual(failed['error']['status'], None)
        self.assertIsNone(failed['error']['hint'])
        self.assertEqual(failed['summary'], good['summary'])

    def test_a_summary_without_a_limit_or_with_odd_numbers_stays_readable(self):
        record = kira_usage.store_official(200, {'data': {'totals': {'monthToDate': {'amount': 'n/a'}}}}, self.root)
        self.assertEqual(record['summary']['month_to_date'], {'cu': None, 'usd': None})
        self.assertIsNone(record['summary']['usage_limit'])


class ApplicationUsageTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.root = Path(self.temp.name)
        self.env = patch.dict(os.environ, {'KIRA_DATA_DIR': str(self.root), 'KIRA_CONFIG': str(self.root / '.kira.local.json')}); self.env.start()
        os.environ.pop(kira_usage.ACCESS_ENV, None)
        initialize(self.root); sample(self.root)
        registry = json.loads((self.root / 'wallets.json').read_text()); registry['demo'] = False
        atomic(self.root / 'wallets.json', registry)
        self.app = Application(self.root)
        self.no_network = patch.object(socket.socket, 'connect', side_effect=AssertionError('Offline test contacted a provider')); self.no_network.start()

    def tearDown(self):
        self.no_network.stop(); self.env.stop(); self.temp.cleanup()

    def request(self):
        return {'schema_version': 1, 'operation': 'alchemy.usageCheck', 'input': {}, 'idempotency_key': 'usage-check-1'}

    def test_usage_names_networks_the_alchemy_app_has_not_enabled(self):
        file = self.root / 'snapshots/demo/initial/results.json'
        snapshot = json.loads(file.read_text())
        snapshot['coverage'][0]['endpoint_issues'] = [
            {'endpoint_class': 'custom', 'provider': 'alchemy', 'network': 'base-mainnet', 'reason': 'network_not_enabled', 'url': 'https://base-mainnet.g.alchemy.com/v2/' + KEY},
            {'endpoint_class': 'custom', 'provider': 'alchemy', 'network': 'Not A Name!', 'reason': 'network_not_enabled'},
            {'endpoint_class': 'public', 'provider': None, 'network': None, 'reason': 'network_not_enabled'}]
        atomic(file, snapshot)
        usage = self.app.usage()
        self.assertEqual(usage['networks_not_enabled'], [{'network': 'base-mainnet', 'name': 'Base', 'chain_id': 8453}])
        self.assertEqual(usage['kira']['totals']['this_month'], {'cu': 0, 'requests': 0})
        self.assertIsNone(usage['official'])
        self.assertFalse(usage['access_key'])
        self.assertNotIn(KEY, json.dumps(usage))
        chain = self.app.views.refresh()['wallets'][0]['chains'][0]
        self.assertEqual(chain['endpoint_issues'], [{'provider': 'alchemy', 'network': 'base-mainnet', 'reason': 'network_not_enabled'}])

    def test_usage_check_needs_a_key_and_returns_the_new_view(self):
        with self.assertRaises(JobError) as missing:
            self.app.submit(self.request())
        self.assertEqual(missing.exception.code, 'usage_key_missing')
        with self.assertRaises(JobError):
            self.app.submit({**self.request(), 'input': {'force': True}})
        kira_usage.save_access_key(KEY, self.root)
        with patch.object(kira_usage, 'read_summary', return_value=(200, SUMMARY)) as read:
            result = self.app.submit(self.request())
        read.assert_called_once()
        self.assertEqual(result['status'], 'completed')
        self.assertEqual(result['usage']['official']['summary']['month_to_date']['cu'], 4210000)
        self.assertTrue(result['usage']['access_key'])
        self.assertNotIn(KEY, json.dumps(result))
        self.assertEqual(self.app.jobs.page(0, 50)['jobs'], [])

    def test_a_sample_workspace_never_checks_usage(self):
        registry = json.loads((self.root / 'wallets.json').read_text()); registry['demo'] = True
        atomic(self.root / 'wallets.json', registry)
        kira_usage.save_access_key(KEY, self.root)
        with patch.object(kira_usage, 'read_summary', side_effect=AssertionError('Sample contacted Alchemy')):
            with self.assertRaises(JobError) as refused:
                self.app.submit(self.request())
        self.assertEqual(refused.exception.code, 'demo_read_only')

    def test_the_worker_checks_usage_after_research_at_most_once_a_minute(self):
        store = JobStore(self.root)
        with patch.object(kira_usage, 'check_official') as check:
            store.refresh_usage()
            check.assert_not_called()
            kira_usage.save_access_key(KEY, self.root)
            store.refresh_usage()
            check.assert_called_once_with(self.root.resolve(), timeout=10)
        kira_usage.store_official(200, SUMMARY, self.root)
        with patch.object(kira_usage, 'check_official') as check:
            store.refresh_usage()
            check.assert_not_called()
        with patch.object(kira_usage, 'recently_checked', return_value=False), patch.object(kira_usage, 'check_official', side_effect=OSError('disk')):
            store.refresh_usage()


if __name__ == '__main__':
    unittest.main()
