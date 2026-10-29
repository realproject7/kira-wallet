"""Agent discovery and optional h402 handoff, without network or wallet access."""
import contextlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import kira_cli
from kira_config import default_config, load_config
from kira_integrations import h402_status
from kira_jobs import JobError, atomic
from kira_service import Application, READ_TOOLS, WRITE_TOOLS


class IntegrationsTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name) / 'workspace'
        self.env = patch.dict(os.environ, {'KIRA_DATA_DIR': str(self.root), 'KIRA_CONFIG': str(self.root / '.kira.local.json')})
        self.env.start(); self.addCleanup(self.env.stop)

    def cli(self, *args):
        output = io.StringIO()
        with patch.object(sys, 'argv', ['kira', *args, '--json']), contextlib.redirect_stdout(output):
            code = kira_cli.main()
        return code, json.loads(output.getvalue())

    def test_catalog_matches_mcp_without_creating_workspace(self):
        code, catalog = self.cli('describe')
        self.assertEqual(code, 0)
        self.assertEqual(catalog['tools'], READ_TOOLS + WRITE_TOOLS)
        self.assertFalse(self.root.exists())
        self.assertEqual(self.cli('describe', 'wallet_read')[1], next(t for t in READ_TOOLS if t['name'] == 'wallet_read'))
        code, error = self.cli('describe', 'missing_tool')
        self.assertEqual(code, 1); self.assertEqual(error['error']['code'], 'unsupported_tool')
        self.assertFalse(self.root.exists())

    def test_opt_out_does_not_execute_even_an_installed_cli(self):
        with patch('kira_integrations.shutil.which', return_value='/synthetic/h402'), patch('kira_integrations.subprocess.run') as run:
            result = h402_status(default_config())
        run.assert_not_called()
        self.assertEqual(result['status'], 'disabled'); self.assertTrue(result['installed'])
        self.assertIsNone(result['version']); self.assertFalse(result['enabling_authorizes_payments'])

    def test_missing_broken_and_timed_out_cli_leave_saved_holdings_readable(self):
        kira_cli.initialize(self.root); kira_cli.sample(self.root)
        config = default_config(); config['integrations'] = {'h402': {'enabled': True}}
        atomic(self.root / '.kira.local.json', config)
        app = Application(self.root)
        cases = [(None, None, 'not_installed'), ('/synthetic/h402', OSError('private diagnostic'), 'unavailable'),
                 ('/synthetic/h402', subprocess.TimeoutExpired('h402', 2), 'unavailable')]
        for executable, failure, status in cases:
            with self.subTest(status=status), patch('kira_integrations.shutil.which', return_value=executable), patch('kira_integrations.subprocess.run', side_effect=failure) as run:
                result = app.call('workspace_status')
                self.assertEqual(result['integrations']['h402']['status'], status)
                self.assertNotIn('private diagnostic', json.dumps(result))
                self.assertIn('complete_defi_positions', result['data_scope']['not_established'])
                self.assertEqual(app.call('wallet_read', {'wallet': 'Demo wallet'})['known_value_usd'], 125)
                if executable is None: run.assert_not_called()

    def test_version_probe_is_the_only_command_and_filters_untrusted_output(self):
        config = {'integrations': {'h402': {'enabled': True}}}
        for stdout, returncode, expected in [('0.1.8\n', 0, '0.1.8'), ('h402 v0.2.0-beta.1\n', 0, '0.2.0-beta.1'), ('secret diagnostic', 0, None), ('0.1.8', 1, None)]:
            probe = subprocess.CompletedProcess([], returncode, stdout, 'private stderr')
            with patch('kira_integrations.shutil.which', return_value='/synthetic/h402'), patch('kira_integrations.subprocess.run', return_value=probe) as run:
                result = h402_status(config)
            run.assert_called_once_with(['/synthetic/h402', '--version'], capture_output=True, text=True, timeout=2)
            self.assertEqual(result['version'], expected)
            self.assertEqual(result['status'], 'available' if expected else 'unavailable')
            self.assertNotIn('private stderr', json.dumps(result)); self.assertNotIn('secret diagnostic', json.dumps(result))

    def test_preference_is_durable_idempotent_and_preserves_existing_records(self):
        kira_cli.initialize(self.root); kira_cli.sample(self.root)
        app = Application(self.root)
        before = {p.relative_to(self.root): p.read_bytes() for p in (self.root / 'snapshots').rglob('*') if p.is_file()}
        original = default_config(); original['rpc']['priority'] = 'custom_first'
        atomic(self.root / '.kira.local.json', original)
        with patch.object(app.jobs, 'launch'), patch('kira_integrations.subprocess.run') as external:
            args = {'enabled': True, 'idempotency_key': 'enable-h402-fixture'}
            receipt = app.call('settings_h402', args, allow_write=True)
            self.assertEqual(receipt['job_id'], app.call('settings_h402', args, allow_write=True)['job_id'])
            self.assertNotIn('integrations', load_config())
            app.jobs.worker()
            self.assertEqual(app.jobs.get(receipt['job_id'])['result']['integration'], {'name': 'h402', 'enabled': True})
            self.assertEqual(load_config()['rpc'], original['rpc'])
            self.assertTrue(load_config()['integrations']['h402']['enabled'])
            with self.assertRaises(JobError): app.call('settings_h402', {'enabled': False, 'idempotency_key': 'read-only-setting'})
            for value in ('true', 1, None):
                with self.assertRaises(JobError): app.jobs.normalize('settings.h402', {'enabled': value})
            app.call('settings_h402', {'enabled': False, 'idempotency_key': 'disable-h402-fixture'}, allow_write=True)
            app.jobs.worker()
            self.assertFalse(load_config()['integrations']['h402']['enabled'])
        external.assert_not_called()
        for path, contents in before.items(): self.assertEqual((self.root / path).read_bytes(), contents)

    def test_new_agent_session_reads_preference_and_only_invokes_version(self):
        kira_cli.initialize(self.root)
        tools = Path(self.directory.name) / 'bin'; tools.mkdir()
        calls = tools / 'calls'; executable = tools / 'h402'
        executable.write_text('#!/bin/sh\nprintf "%s\\n" "$*" >> "'+str(calls)+'"\nprintf "0.1.8\\n"\n')
        executable.chmod(0o755)
        config = default_config(); config['integrations'] = {'h402': {'enabled': True}}
        atomic(self.root / '.kira.local.json', config)
        for command in ('info', 'integrations'):
            result = subprocess.run([sys.executable, str(Path(kira_cli.__file__)), command, '--json'],
                                    cwd=self.directory.name, env={**os.environ, 'PATH': str(tools)}, capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr)
            data = json.loads(result.stdout)
            self.assertEqual((data['integrations'] if command == 'info' else data)['h402']['status'], 'available')
        self.assertEqual(calls.read_text().splitlines(), ['--version', '--version'])

    def test_invalid_preference_cannot_be_used_as_a_command(self):
        kira_cli.initialize(self.root)
        for integration in ({'h402': {'enabled': 'yes'}}, {'h402': {'enabled': True, 'command': 'anything'}}, {'other': {'enabled': True}}):
            atomic(self.root / '.kira.local.json', {**default_config(), 'integrations': integration})
            with self.assertRaisesRegex(ValueError, 'integration'): load_config()


if __name__ == '__main__': unittest.main()
