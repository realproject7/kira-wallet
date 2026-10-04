"""Check tracked text and optional Git history without printing private values."""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT)


def private_values(extra_roots=()):
    identifiers, secrets = set(), set()
    for registry in [ROOT/'wallets.json',*[Path(p).expanduser()/'wallets.json' for p in extra_roots]]:
        if not registry.exists():continue
        for wallet in json.loads(registry.read_text()).get('wallets', []):
            for key in ('address', 'address_key'):
                if isinstance(wallet.get(key), str):
                    identifiers.add(wallet[key].casefold())
            for tag in wallet.get('tags', []):
                if isinstance(tag, str) and tag:
                    # Match complete quoted tags, so a short name does not match common code.
                    identifiers.update((json.dumps(tag).casefold(), ("'" + tag + "'").casefold()))
    for key, value in os.environ.items():
        if re.search(r'(api_key|secret|token|password)', key, re.I) and len(value) > 12:
            secrets.add(value)
    return identifiers, secrets


def check(path, body, identifiers, secrets):
    reasons = []
    name = Path(path).name
    if path in ('wallets.json', 'session.json') or path.startswith(('snapshots/', 'conversations/', 'cache/', 'jobs/', '.agent-history/', 'site/.vercel/', '.kira-ows-requests/', '.ows/')) or path.endswith(('.env', '.log', '.tgz')) or name.startswith(('.env', '.kira.')) or (name.startswith('.kira') and name.endswith('.json')):
        reasons.append('private runtime file')
    if b'\x00' in body:
        return reasons  # Images need a separate visual review.
    text = body.decode('utf-8', errors='ignore')
    if any(value in text.casefold() for value in identifiers):
        reasons.append('portfolio identifier')
    if any(value in text for value in secrets):
        reasons.append('loaded secret')
    if re.search(r'/(?:Users|home)/[A-Za-z0-9_.-]+/', text) or ('/var/' + 'folders/') in text:
        reasons.append('personal filesystem path')
    if re.search(r'\b(?:gh[pousr]_[a-zA-Z0-9]{20,}|sk-(?:proj-)?[A-Za-z0-9_-]{20,}|ows_key_[a-fA-F0-9]{64})\b', text):
        reasons.append('credential pattern')
    return reasons


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--history', action='store_true')
    parser.add_argument('--ref', default='HEAD', help='Only the reachable public history of this ref is checked.')
    parser.add_argument('--private-data-dir',action='append',default=[],help='Also guard identifiers from a private test portfolio without printing them.')
    args = parser.parse_args()
    identifiers, secrets = private_values(args.private_data_dir)
    findings, count = [], 0
    for raw in git('ls-files', '-z').split(b'\x00'):
        if not raw:
            continue
        path = raw.decode(); file = ROOT / path
        if not file.exists():
            continue
        count += 1
        reasons = check(path, file.read_bytes(), identifiers, secrets)
        if reasons:
            findings.append({'path': path, 'reasons': reasons})
    history_blobs = set()
    if args.history:
        for commit in git('rev-list', args.ref).decode().splitlines():
            metadata = git('show', '-s', '--format=%ae%n%ce%n%B', commit).decode()
            author,committer=metadata.splitlines()[:2]
            if not author.endswith('@users.noreply.github.com') or not (committer.endswith('@users.noreply.github.com') or committer=='noreply@github.com'):
                findings.append({'commit': commit[:7], 'reasons': ['non-noreply commit identity']})
            reasons = check('commit message', metadata.encode(), identifiers, secrets)
            if reasons:
                findings.append({'commit': commit[:7], 'reasons': reasons})
            for row in git('ls-tree', '-r', '-z', commit).split(b'\x00'):
                if not row:
                    continue
                meta, path = row.decode().split('\t', 1); blob = meta.split()[2]
                if blob in history_blobs:
                    continue
                history_blobs.add(blob)
                reasons = check(path, git('cat-file', 'blob', blob), identifiers, secrets)
                if reasons:
                    findings.append({'commit': commit[:7], 'path': path, 'reasons': reasons})
    print(json.dumps({'tracked_files': count, 'history_blobs': len(history_blobs), 'findings': findings}, indent=2))
    if findings:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
