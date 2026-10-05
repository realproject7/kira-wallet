"""Startup UX and explicit mode boundaries for the local app."""
import contextlib
import io
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import kira_cli


class StartTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix='kira-start-test-')
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name).resolve()
        self.env = patch.dict(os.environ, {'KIRA_DATA_DIR': str(self.root)}, clear=True)
        self.env.start()
        self.addCleanup(self.env.stop)

    def invoke(self, *arguments):
        with patch.object(sys, 'argv', ['kira', *arguments]), \
                patch.object(kira_cli, 'start', return_value='http://127.0.0.1:8787') as start, \
                patch('webbrowser.open') as browser, contextlib.redirect_stdout(io.StringIO()):
            kira_cli.main()
            return start.call_args, browser.call_args

    def test_plain_start_opens_the_app_with_local_controls(self):
        start, browser = self.invoke('start')
        self.assertEqual(start.args, (self.root, 8787, True))
        self.assertEqual(browser.args, ('http://127.0.0.1:8787',))

    def test_read_only_is_explicit_and_headless_does_not_open_browser(self):
        start, browser = self.invoke('start', '--read-only', '--no-open')
        self.assertEqual(start.args, (self.root, 8787, False))
        self.assertIsNone(browser)

    def test_existing_controls_scripts_keep_working(self):
        start, browser = self.invoke('start', '--controls', '--no-open')
        self.assertEqual(start.args, (self.root, 8787, True))
        self.assertIsNone(browser)

    def test_setup_still_opens_its_setup_route(self):
        start, browser = self.invoke('setup')
        self.assertEqual(start.args, (self.root, 8787, True))
        self.assertEqual(browser.args, ('http://127.0.0.1:8787/?setup=1',))

    def test_conflicting_modes_are_rejected(self):
        with patch.object(sys, 'argv', ['kira', 'start', '--read-only', '--controls']), \
                contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as error:
            kira_cli.main()
        self.assertEqual(error.exception.code, 2)

    def test_live_mode_is_reused_without_starting_another_process(self):
        for controls in (True, False):
            with self.subTest(controls=controls), \
                    patch.object(kira_cli, 'live_record', return_value={'port': 8788}), \
                    patch.object(kira_cli, 'health', return_value={'controls': controls}), \
                    patch.object(kira_cli.subprocess, 'Popen') as child, \
                    contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(kira_cli.start(self.root, 8787, controls), 'http://127.0.0.1:8788')
                child.assert_not_called()

    def test_running_mode_is_never_silently_changed_or_misreported(self):
        for controls in (True, False):
            with self.subTest(controls=controls), \
                    patch.object(kira_cli, 'live_record', return_value={'port': 8788}), \
                    patch.object(kira_cli, 'health', return_value={'controls': not controls}), \
                    patch.object(kira_cli.subprocess, 'Popen') as child:
                with self.assertRaisesRegex(ValueError, 'Run kira stop'):
                    kira_cli.start(self.root, 8787, controls)
                child.assert_not_called()


if __name__ == '__main__':
    unittest.main()
