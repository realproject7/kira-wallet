"""The pre-push check stops private data and personal identities before a push leaves the machine."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

HOOK = Path(__file__).resolve().parent / 'scripts' / 'pre-push-check.py'
ADDRESS = '0x' + 'ab' * 20
REMOVED = '0x' + 'cd' * 20
NAME, EMAIL = 'fixture', '1+fixture@users.noreply.github.com'
ZERO = '0' * 40


class PrePushCheckTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.repo, self.data, home = root / 'repo', root / 'data', root / 'home'
        for folder in (self.repo, self.data, home):
            folder.mkdir()
        (root / 'gitconfig').write_text('')
        # No identity or registry of the machine running the tests can leak in.
        self.env = {'PATH': os.environ['PATH'], 'HOME': str(home), 'GIT_CONFIG_GLOBAL': str(root / 'gitconfig'),
                    'GIT_CONFIG_NOSYSTEM': '1', 'KIRA_DATA_DIR': str(self.data), 'LANG': 'en_US.UTF-8'}
        (self.data / 'wallets.json').write_text(json.dumps({
            'wallets': [{'address': '0x' + 'AB' * 20, 'address_key': ADDRESS, 'tags': ['Fixture vault']}],
            'removed_wallets': {'one': {'wallet': {'address': REMOVED, 'address_key': REMOVED, 'tags': []}}}}))
        self.git('init', '-q', '-b', 'main')
        self.git('config', 'user.name', NAME)
        self.git('config', 'user.email', EMAIL)
        self.first = self.commit('README.md', 'A public file.\n')

    def tearDown(self):
        self.temp.cleanup()

    def git(self, *args, **env):
        return subprocess.run(['git', *args], cwd=self.repo, env={**self.env, **env}, capture_output=True, text=True, check=True).stdout.strip()

    def commit(self, path, content, message=None, **env):
        file = self.repo / path
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_bytes(content if isinstance(content, bytes) else content.encode())
        self.git('add', '-A')
        self.git('commit', '-q', '-m', message or 'Change ' + path, **env)
        return self.git('rev-parse', 'HEAD')

    def push(self, local=None, remote_sha=ZERO, remote='origin'):
        local = local or self.git('rev-parse', 'HEAD')
        return subprocess.run([sys.executable, str(HOOK), remote, 'https://example.invalid/repo.git'], cwd=self.repo, env=self.env,
                              input=f'refs/heads/main {local} refs/heads/main {remote_sha}\n', capture_output=True, text=True)

    def assertStopped(self, result, *expected):
        self.assertEqual(result.returncode, 1, result.stderr)
        for text in expected:
            self.assertIn(text, result.stderr)
        for private in (ADDRESS[2:], REMOVED[2:], 'fixture vault'):
            self.assertNotIn(private, result.stderr.casefold(), 'A finding names the place, never the value.')

    def test_public_commits_pass_silently(self):
        result = self.push()
        self.assertEqual((result.returncode, result.stderr), (0, ''))

    def test_registered_address_stops_the_push_in_any_form(self):
        for name, text in (('upper.cjs', 'const wallet="0x' + 'AB' * 20 + '";'), ('padded.json', '{"topic":"0x' + '0' * 24 + 'ab' * 20 + '"}'),
                           ('removed.py', 'WALLET = "' + REMOVED + '"')):
            with self.subTest(name=name):
                self.commit('fixtures/' + name, text)
                self.assertStopped(self.push(), 'fixtures/' + name + ': portfolio identifier')

    def test_quoted_wallet_name_is_guarded_and_plain_words_are_not(self):
        self.commit('notes.md', 'The fixture vault of a museum is not a wallet name.\n')
        self.assertEqual(self.push().returncode, 0)
        self.commit('fixture.json', '{"tags":["Fixture vault"]}')
        self.assertStopped(self.push(), 'fixture.json: portfolio identifier')

    def test_commit_message_is_read_too(self):
        self.commit('change.txt', 'public\n', message='Debug ' + ADDRESS)
        self.assertStopped(self.push(), 'commit message: portfolio identifier')

    def test_personal_paths_credentials_and_runtime_files_stop_the_push(self):
        self.commit('log.txt', 'saved to /Us' + 'ers/someone/kira/out.json\n')
        self.commit('config.txt', 'token = gh' + 'p_' + 'a' * 24 + '\n')
        self.commit('snapshots/demo/results.json', '{}')
        self.assertStopped(self.push(), 'log.txt: personal filesystem path', 'config.txt: credential pattern',
                           'snapshots/demo/results.json: private runtime file', '3 privacy findings in 4 new commits')

    def test_a_commit_made_under_another_identity_stops_the_push(self):
        self.commit('a.txt', 'public\n', GIT_AUTHOR_EMAIL='person@example.com', GIT_COMMITTER_EMAIL='person@example.com')
        self.assertStopped(self.push(), 'commit identity: email is not a noreply address')
        self.git('reset', '-q', '--hard', self.first)
        self.commit('b.txt', 'public\n', GIT_AUTHOR_NAME='Another Name', GIT_COMMITTER_NAME='Another Name')
        self.assertStopped(self.push(), "commit identity: name differs from this clone's configured name")

    def test_only_commits_the_remote_lacks_are_read(self):
        old = self.commit('old.txt', 'earlier ' + ADDRESS + '\n')
        self.commit('new.txt', 'public\n')
        self.assertStopped(self.push(), 'old.txt: portfolio identifier')
        # The remote's own ref says it already has the earlier commit.
        self.assertEqual(self.push(remote_sha=old).returncode, 0)
        # So does a remote-tracking ref, for a named remote or an unnamed address.
        self.git('remote', 'add', 'origin', 'https://example.invalid/repo.git')
        self.git('update-ref', 'refs/remotes/origin/main', old)
        self.assertEqual(self.push().returncode, 0)
        self.assertEqual(self.push(remote='https://example.invalid/other.git').returncode, 0)

    def test_deleting_a_ref_publishes_nothing(self):
        self.commit('private.txt', ADDRESS)
        self.assertEqual(self.push(local=ZERO, remote_sha=self.first).returncode, 0)

    def test_binary_files_are_not_read_and_the_check_says_so(self):
        self.commit('image.png', b'\x89PNG\x00' + ADDRESS.encode())
        result = self.push()
        self.assertEqual(result.returncode, 0)
        self.assertIn('1 binary files were not read', result.stderr)

    def test_without_a_registry_the_other_rules_still_apply(self):
        (self.data / 'wallets.json').unlink()
        self.commit('address.txt', ADDRESS)
        self.assertEqual(self.push().returncode, 0)
        self.commit('path.txt', '/ho' + 'me/someone/file\n')
        self.assertStopped(self.push(), 'path.txt: personal filesystem path')


if __name__ == '__main__':
    unittest.main()
