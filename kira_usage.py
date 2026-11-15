"""Alchemy usage: Kira's own estimate and, with an Access Key, the account's official totals.

Kira's estimate is a ledger. Every process that sends Alchemy requests appends one line per
piece of work to usage/alchemy-YYYY-MM.jsonl: when, which job or batch, how many requests and
their compute units by method, priced from Alchemy's compute unit costs table. Reading the
ledger never contacts a provider.

The official totals come from Alchemy's Admin API (usage summary). It needs an Access Key
with Usage read permission, entered at a hidden terminal prompt (kira connect alchemy-usage)
and kept in the workspace's private .secrets folder. The key is never sent to the browser,
never written to a log and never printed.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import re
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

SUMMARY_URL = 'https://admin-api.alchemy.com/v1/usage/summary'
ACCESS_ENV = 'ALCHEMY_ACCESS_KEY'
ACCESS_FILE = 'alchemy-access.env'
OFFICIAL_CACHE = 'cache/alchemy-usage-official.json'
# Data API requests by path ending, priced from Alchemy's compute unit costs table.
DATA_API = (
    ('/assets/tokens/balances/by-address', 'token_balances_by_wallet', 200),
    ('/assets/tokens/by-address', 'tokens_by_wallet', 360),
    ('/tokens/by-address', 'token_prices_by_address', 40),
    ('/tokens/by-symbol', 'token_prices_by_symbol', 40),
    ('/tokens/historical', 'token_prices_historical', 40),
)
# Alchemy bills nothing for a throttled (429) or refused (403) request.
UNBILLED = (403, 429)
# The job a request belongs to, for work several jobs share in one process (a batch).
current_job = lambda: os.environ.get('KIRA_JOB_ID')  # noqa: E731


def root_dir(root=None):
    if root is not None:
        return Path(root)
    from kira_config import data_root
    return Path(data_root())


def ledger(root, month):
    return root_dir(root) / 'usage' / f'alchemy-{month}.jsonl'


def append(line, root=None):
    """One write per line, so lines from several processes and threads never interleave."""
    path = ledger(root, line['at'][:7])
    try:
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        data = (json.dumps(line, separators=(',', ':')) + '\n').encode()
        fd = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
        try:
            os.write(fd, data)
        finally:
            os.close(fd)
    except OSError:
        pass  # Usage is an estimate for the operator; it never fails research.


def now():
    return dt.datetime.now(dt.timezone.utc).isoformat().replace('+00:00', 'Z')


def note_request(url, status=None, root=None):
    """Record one Alchemy data API request (token lists, prices). Other hosts are ignored."""
    try:
        parsed = urlparse(url)
    except ValueError:
        return
    if parsed.hostname != 'api.g.alchemy.com' or status in UNBILLED:
        return
    for ending, method, cu in DATA_API:
        if parsed.path.endswith(ending):
            append({'at': now(), 'source': 'python', 'job': current_job(), 'batch': os.environ.get('KIRA_BATCH_ID'),
                    'cu': cu, 'requests': 1, 'methods': {method: [1, cu]}}, root)
            return


def note_batch(batch, jobs, scope, root=None):
    """A batch reads for many jobs at once; this line ties its usage to them."""
    append({'at': now(), 'source': 'batch', 'job': None, 'batch': batch, 'jobs': list(jobs), 'scope': scope,
            'cu': 0, 'requests': 0, 'methods': {}}, root)


def lines(root=None, months=2, today=None):
    today = today or dt.datetime.now(dt.timezone.utc)
    first = today.replace(day=1)
    keys = []
    for _ in range(months):
        keys.append(first.strftime('%Y-%m'))
        first = (first - dt.timedelta(days=1)).replace(day=1)
    rows = []
    for key in reversed(keys):
        path = ledger(root, key)
        try:
            text = path.read_text()
        except OSError:
            continue
        for raw in text.splitlines():
            try:
                row = json.loads(raw)
                if isinstance(row, dict) and isinstance(row.get('at'), str) and isinstance(row.get('cu'), int):
                    rows.append(row)
            except ValueError:
                continue
    return rows


def summary(root=None, now_at=None):
    """Kira's own Alchemy use: today, the last seven days, this billing month and the last run."""
    current = now_at or dt.datetime.now(dt.timezone.utc)
    local = current.astimezone()
    rows = lines(root, today=current)
    stamp = lambda row: dt.datetime.fromisoformat(row['at'].replace('Z', '+00:00'))  # noqa: E731
    totals = {'today': [0, 0], 'last_7_days': [0, 0], 'this_month': [0, 0]}
    batches, jobs = {}, {}
    for row in rows:
        at = stamp(row)
        pair = (row.get('cu', 0), row.get('requests', 0))
        if at.astimezone().date() == local.date():
            totals['today'][0] += pair[0]; totals['today'][1] += pair[1]
        if current - at <= dt.timedelta(days=7):
            totals['last_7_days'][0] += pair[0]; totals['last_7_days'][1] += pair[1]
        if at.year == current.year and at.month == current.month:
            totals['this_month'][0] += pair[0]; totals['this_month'][1] += pair[1]
        if row.get('batch'):
            group = batches.setdefault(row['batch'], {'id': row['batch'], 'kind': 'batch', 'cu': 0, 'requests': 0, 'jobs': [], 'scope': None, 'first': row['at'], 'last': row['at']})
            if row.get('source') == 'batch':
                group['jobs'] = row.get('jobs') or []; group['scope'] = row.get('scope')
        elif row.get('job'):
            group = jobs.setdefault(row['job'], {'id': row['job'], 'kind': 'job', 'cu': 0, 'requests': 0, 'first': row['at'], 'last': row['at']})
        else:
            continue
        group['cu'] += pair[0]; group['requests'] += pair[1]
        group['first'] = min(group['first'], row['at']); group['last'] = max(group['last'], row['at'])
    runs = [g for g in [*batches.values(), *jobs.values()] if g['requests']]
    last = max(runs, key=lambda g: g['last'], default=None)
    return {'totals': {k: {'cu': v[0], 'requests': v[1]} for k, v in totals.items()},
            'last_run': last and {k: v for k, v in last.items() if k != 'jobs'} | ({'wallets': len(last['jobs'])} if last['kind'] == 'batch' else {}),
            'basis': "Kira's own Alchemy requests, priced from Alchemy's compute unit costs. Other apps on the same account are not included."}


def job_usage(job_id, root=None):
    """What one job spent, or the batch it ran in."""
    rows = lines(root)
    batch = next((r for r in rows if r.get('source') == 'batch' and job_id in (r.get('jobs') or [])), None)
    if batch:
        spent = [r for r in rows if r.get('batch') == batch['batch']]
        return {'cu': sum(r['cu'] for r in spent), 'requests': sum(r.get('requests', 0) for r in spent), 'batch_wallets': len(batch.get('jobs') or [])}
    spent = [r for r in rows if r.get('job') == job_id and not r.get('batch')]
    if not spent:
        return None
    return {'cu': sum(r['cu'] for r in spent), 'requests': sum(r.get('requests', 0) for r in spent)}


def access_key(root=None):
    if os.environ.get(ACCESS_ENV):
        return os.environ[ACCESS_ENV].strip()
    try:
        text = (root_dir(root) / '.secrets' / ACCESS_FILE).read_text()
    except OSError:
        return None
    match = re.search(r'^\s*' + ACCESS_ENV + r'\s*=\s*(\S+)\s*$', text, re.M)
    return match[1].strip('"\'') if match else None


def valid_key(key):
    return isinstance(key, str) and 8 <= len(key) <= 512 and re.fullmatch(r'[A-Za-z0-9._~+/=-]+', key) is not None


def save_access_key(key, root=None):
    if not valid_key(key):
        raise ValueError('Enter the Access Key itself, without a URL or spaces.')
    directory = root_dir(root) / '.secrets'
    directory.mkdir(mode=0o700, exist_ok=True)
    if directory.is_symlink():
        raise ValueError('The private key directory must not be a symlink.')
    temp = directory / (ACCESS_FILE + '.tmp')
    fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, 'w') as stream:
        stream.write(f'{ACCESS_ENV}={key}\n'); stream.flush(); os.fsync(stream.fileno())
    os.replace(temp, directory / ACCESS_FILE)


def forget_access_key(root=None):
    path = root_dir(root) / '.secrets' / ACCESS_FILE
    path.unlink(missing_ok=True)
    (root_dir(root) / OFFICIAL_CACHE).unlink(missing_ok=True)


def read_summary(key, timeout=12, opener=urllib.request.urlopen):
    """Ask Alchemy for the account's usage summary. Returns (status, data or error)."""
    request = urllib.request.Request(SUMMARY_URL, headers={'Authorization': 'Bearer ' + key, 'Accept': 'application/json', 'User-Agent': 'kira-wallet'})
    try:
        with opener(request, timeout=timeout) as response:
            return response.status, json.loads(response.read(1_000_000))
    except urllib.error.HTTPError as error:
        try:
            body = json.loads(error.read(20_000) or b'{}')
        except ValueError:
            body = {}
        finally:
            error.close()
        message = ((body.get('error') or {}).get('message') if isinstance(body, dict) else None) or f'HTTP {error.code}'
        return error.code, {'message': str(message).replace(key, '[redacted]')[:200]}
    except (OSError, ValueError) as error:
        return None, {'message': f'Alchemy usage unavailable: {type(error).__name__}'}


def number(value):
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def public_summary(data):
    """Keep the fields the app shows. Amounts are compute units; usd is Alchemy's estimate."""
    data = data.get('data', data) if isinstance(data, dict) else {}
    totals = data.get('totals') or {}
    span = lambda name: {'cu': number((totals.get(name) or {}).get('amount')), 'usd': (totals.get(name) or {}).get('usd')}  # noqa: E731
    limit = data.get('usageLimit')
    return {'month_to_date': span('monthToDate'), 'last_7_days': span('last7Days'), 'last_30_days': span('last30Days'),
            'billing_period': data.get('billingPeriod'), 'data_through': (data.get('freshness') or {}).get('dataThrough'),
            'usage_limit': {'unit': limit.get('unit'), 'limit': number(limit.get('limit')), 'used': number(limit.get('used')),
                            'remaining': number(limit.get('remaining')), 'percent_used': limit.get('percentUsed')} if isinstance(limit, dict) else None}


def check_official(root=None, timeout=12, opener=urllib.request.urlopen):
    """Ask Alchemy once and save the answer. Keeps the last good summary when a check fails."""
    key = access_key(root)
    if not key:
        return None
    return store_official(*read_summary(key, timeout, opener), root=root)


def store_official(status, data, root=None):
    path = root_dir(root) / OFFICIAL_CACHE
    try:
        previous = json.loads(path.read_text())
    except (OSError, ValueError):
        previous = {}
    record = {'checked_at': now(), 'ok': status == 200}
    if status == 200:
        record['summary'] = public_summary(data)
    else:
        record['error'] = {'status': status, 'message': data.get('message'),
                           'hint': 'Alchemy did not accept the Access Key. Create one in the dashboard Security tab with Usage read access, then run kira connect alchemy-usage.' if status in (401, 403) else None}
        if previous.get('summary'):
            record['summary'] = previous['summary']; record['summary_checked_at'] = previous.get('summary_checked_at') or previous.get('checked_at')
    if status == 200:
        record['summary_checked_at'] = record['checked_at']
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_name(path.name + '.tmp')
        temp.write_text(json.dumps(record) + '\n'); os.replace(temp, path)
    except OSError:
        pass
    return record


def recently_checked(root=None, seconds=60):
    checked = (official(root) or {}).get('checked_at')
    try:
        return checked is not None and (dt.datetime.now(dt.timezone.utc) - dt.datetime.fromisoformat(checked.replace('Z', '+00:00'))).total_seconds() < seconds
    except ValueError:
        return False


def official(root=None):
    try:
        return json.loads((root_dir(root) / OFFICIAL_CACHE).read_text())
    except (OSError, ValueError):
        return None


def view(root=None):
    """Everything the app shows about usage, from saved records only."""
    return {'kira': summary(root), 'official': official(root), 'access_key': access_key(root) is not None}
