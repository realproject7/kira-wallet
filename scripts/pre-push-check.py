#!/usr/bin/env python3
"""Stop a push whose new commits carry private portfolio data or a personal identity.

Git runs this file as the pre-push hook. It reads only what the remote does not
have yet and never prints a private value. Install it once for every worktree
of a clone:

    cp scripts/pre-push-check.py "$(git rev-parse --git-common-dir)/hooks/pre-push"
    chmod +x "$(git rev-parse --git-common-dir)/hooks/pre-push"

The file imports nothing from the project, so the installed copy works on any
branch. Its content rules mirror scripts/check-public.py. Guarded identifiers
come from the wallet registry in KIRA_DATA_DIR, the default Kira data folder
and the repository root. Images and other binary files are not read: check
them by eye before a push.
"""
import json
import os
import re
import subprocess
import sys
from pathlib import Path

ZERO = '0' * 40
PRIVATE_FILES = ('wallets.json', 'session.json', '.ui-context.json', 'viewer-process.json', 'token-policy.json',
                 '.token-policy.lock', 'wallet-folders.json', '.job-launch.lock')
PRIVATE_FOLDERS = ('.folder-actions/', '.wallet-actions/', '.token-actions/', 'positions/', 'snapshots/', 'conversations/',
                   'cache/', 'jobs/', 'kira-agent-workspaces/', '.agent-history/', 'site/.vercel/', '.kira-ows-requests/', '.ows/')
CREDENTIAL = re.compile(r'\b(?:gh[pousr]_[a-zA-Z0-9]{20,}|sk-(?:proj-)?[A-Za-z0-9_-]{20,}|ows_key_[a-fA-F0-9]{64})\b')
PERSONAL_PATH = re.compile(r'/(?:Users|home)/[A-Za-z0-9_.-]+/')


def git(*args, check=True):
    return subprocess.run(['git', *args], capture_output=True, check=check).stdout


def identifiers():
    """Registered wallet addresses and quoted wallet names, lower case."""
    roots = [os.environ.get('KIRA_DATA_DIR'), str(Path.home() / '.local/share/kira-wallet'),
             git('rev-parse', '--show-toplevel', check=False).decode().strip()]
    found = set()
    for root in filter(None, roots):
        try:
            saved = json.loads((Path(root).expanduser() / 'wallets.json').read_text())
            wallets = saved.get('wallets', []) + [row.get('wallet', {}) for row in saved.get('removed_wallets', {}).values()]
        except (OSError, ValueError, AttributeError):
            continue
        for wallet in wallets:
            for key in ('address', 'address_key'):
                value = wallet.get(key)
                if isinstance(value, str) and re.fullmatch(r'0x[0-9a-fA-F]{40}', value):
                    # Without the prefix too: padded and checksummed forms contain it.
                    found.add(value[2:].casefold())
            for tag in wallet.get('tags', []):
                if isinstance(tag, str) and tag:
                    # Complete quoted names only, so a short name does not match common code.
                    found.update((json.dumps(tag).casefold(), ("'" + tag + "'").casefold()))
    return found


def reasons(path, body, guarded):
    """Return why a file or message must not be pushed, and whether it is binary."""
    found, name = [], Path(path).name
    if (path in PRIVATE_FILES or path.startswith(PRIVATE_FOLDERS) or path.endswith(('.env', '.log', '.tgz'))
            or name.startswith(('.env', '.kira.')) or (name.startswith('.kira') and name.endswith('.json'))):
        found.append('private runtime file')
    if b'\x00' in body:
        return found, True
    text = body.decode('utf-8', errors='ignore')
    lowered = text.casefold()
    if any(value in lowered for value in guarded):
        found.append('portfolio identifier')
    if PERSONAL_PATH.search(text) or ('/var/' + 'folders/') in text:
        found.append('personal filesystem path')
    if CREDENTIAL.search(text):
        found.append('credential pattern')
    return found, False


def contents(shas):
    """Yield (sha, type, bytes) for each object in one git process."""
    if not shas:
        return
    out = subprocess.run(['git', 'cat-file', '--batch'], input=('\n'.join(shas) + '\n').encode(), capture_output=True, check=True).stdout
    position = 0
    while position < len(out):
        end = out.index(b'\n', position)
        sha, kind, size = out[position:end].decode().split()
        start = end + 1
        yield sha, kind, out[start:start + int(size)]
        position = start + int(size) + 1


def main():
    remote = sys.argv[1] if len(sys.argv) > 1 else ''
    known = git('remote').decode().split()
    # Commits the remote already has are not this push's responsibility.
    exclude = ['--remotes=' + remote] if remote in known else ['--remotes']
    guarded = identifiers()
    own_name = git('config', '--local', 'user.name', check=False).decode().strip()
    findings, commits_read, binary_files = [], 0, 0
    for line in sys.stdin.read().splitlines():
        parts = line.split()
        if len(parts) != 4 or parts[1] == ZERO:
            continue  # A deleted ref publishes nothing.
        local_sha, remote_sha = parts[1], parts[3]
        span = [local_sha, '--not', *exclude]
        if remote_sha != ZERO and subprocess.run(['git', 'cat-file', '-e', remote_sha + '^{commit}'], capture_output=True).returncode == 0:
            span.append(remote_sha)
        for commit in git('rev-list', *span).decode().split():
            commits_read += 1
            author, author_email, committer, committer_email, message = git(
                'show', '-s', '--format=%an%x00%ae%x00%cn%x00%ce%x00%B', commit).decode('utf-8', 'replace').split('\x00', 4)
            if not author_email.endswith('@users.noreply.github.com') or not (
                    committer_email.endswith('@users.noreply.github.com') or committer_email == 'noreply@github.com'):
                findings.append((commit[:7], 'commit identity', 'email is not a noreply address'))
            if own_name and any(name not in (own_name, 'GitHub') for name in (author, committer)):
                findings.append((commit[:7], 'commit identity', "name differs from this clone's configured name"))
            for reason in reasons('commit message', message.encode(), guarded)[0]:
                findings.append((commit[:7], 'commit message', reason))
        paths = {}
        for row in git('rev-list', '--objects', *span).decode('utf-8', 'replace').splitlines():
            sha, _, path = row.partition(' ')
            if path:
                paths.setdefault(sha, path)
        for sha, kind, body in contents(list(paths)):
            if kind != 'blob':
                continue
            found, binary = reasons(paths[sha], body, guarded)
            binary_files += binary
            findings.extend(('new file content', paths[sha], reason) for reason in found)
    findings = sorted(set(findings))
    if findings:
        print(f'Push stopped: {len(findings)} privacy finding{"" if len(findings) == 1 else "s"} in {commits_read} new commit{"" if commits_read == 1 else "s"}.', file=sys.stderr)
        for where, what, reason in findings:
            print(f'  {where}: {what}: {reason}', file=sys.stderr)
        print('Private values are not shown. Fix the commits and push again.', file=sys.stderr)
        return 1
    if binary_files:
        print(f'Privacy check passed for {commits_read} new commits. {binary_files} binary files were not read: check images by eye.', file=sys.stderr)
    return 0


if __name__ == '__main__':
    sys.exit(main())
