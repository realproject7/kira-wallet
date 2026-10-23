"""Cached, paged views of published local records. Never contacts providers."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import sys
import threading
from decimal import Decimal, InvalidOperation
from kira_jobs import JobError

sys.path.insert(0, str(Path(__file__).resolve().parent / 'viewer'))
from model import load_state, within
from details import project_details, wallet_identity, coverage_for, coverage_status


def signature(path):
    try:
        stat = path.stat()
        return stat.st_mtime_ns, stat.st_size, stat.st_ino
    except FileNotFoundError:
        return None


def page_bounds(offset=0, limit=100):
    if type(offset) is not int or offset < 0 or type(limit) is not int or not 1 <= limit <= 100:
        raise JobError('invalid_page', 'Use a nonnegative offset and a limit from 1 to 100.')
    return offset, limit


def page(rows, offset=0, limit=100, *, key='assets'):
    offset, limit = page_bounds(offset, limit)
    selected = rows[offset:offset + limit]
    end = offset + len(selected)
    return {key: selected, 'matched_count': len(rows), 'offset': offset,
            'next_offset': end if end < len(rows) else None}


def filter_assets(rows, *, query='', chain_id=None, minimum_value_usd='0',
                  sort='value', pricing='all', include_testnets=True):
    if not isinstance(query, str) or len(query) > 500:
        raise JobError('invalid_query', 'Use a search string of up to 500 characters.')
    if chain_id is not None and (type(chain_id) is not int or chain_id < 1):
        raise JobError('invalid_chain', 'Expected a positive chain ID.')
    if sort not in ('value', 'name', 'wallets') or pricing not in ('all', 'priced', 'unpriced') or type(include_testnets) is not bool:
        raise JobError('invalid_filter', 'Choose supported sorting and price filters.')
    try:
        if type(minimum_value_usd) not in (str, int, float) or len(str(minimum_value_usd)) > 80:raise ValueError()
        minimum = Decimal(str(minimum_value_usd))
        if not minimum.is_finite() or minimum < 0:raise ValueError()
    except (InvalidOperation, ValueError):
        raise JobError('invalid_filter', 'Use a finite nonnegative minimum value.') from None
    query = query.strip().casefold()
    result = []
    for asset in rows:
        value = asset.get('value_usd')
        if chain_id is not None and asset['chain_id'] != chain_id:continue
        if not include_testnets and asset.get('environment') != 'mainnet':continue
        if minimum and (value is None or Decimal(str(value)) < minimum):continue
        if pricing == 'priced' and value is None or pricing == 'unpriced' and value is not None:continue
        if query and not any(query in str(asset.get(k) or ('native' if k == 'address' else '')).casefold() for k in ('symbol', 'name', 'address')):continue
        result.append(asset)
    if sort == 'name':result.sort(key=lambda a: (str(a.get('symbol') or '').casefold(), a['id']))
    elif sort == 'wallets':result.sort(key=lambda a: (-a.get('wallet_count', 1), a['id']))
    else:result.sort(key=lambda a: (a.get('value_usd') is None, -(a.get('value_usd') or 0), a['id']))
    return result


class StateCache:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.lock = threading.RLock()
        self.registry_signature = None
        self.paths = []
        self.folders = []
        self.revision = None
        self.state = None
        self.body = None
        self.builds = 0

    def data_revision(self):
        """Stat published inputs before projecting; also sees legacy writers and crash gaps."""
        with self.lock:
            registry = self.root / 'wallets.json'
            current = signature(registry)
            if current != self.registry_signature or not self.paths:
                value = json.loads(registry.read_text())
                paths = {registry, self.root / 'networks.json', self.root / 'cache/token-images.json'}
                folders=[]
                for entry in value.get('wallets', []):
                    latest = entry.get('latest_snapshot') or {}
                    if latest.get('result'):paths.add(within(self.root, latest['result']))
                    if not latest.get('directory'):continue
                    folder = within(self.root, latest['directory'])
                    paths.update((folder / 'market-prices.json', folder / 'token-market-metadata.json'))
                    # A pending all-network snapshot can acquire saved chain evidence.
                    folders.append(folder)
                self.paths = sorted(paths)
                self.folders = folders
                self.registry_signature = current
            paths = list(self.paths)
            for folder in self.folders:
                paths.extend(folder.glob('chain-*.json'))
            values = [(str(p.relative_to(self.root)), signature(p)) for p in paths]
            return hashlib.sha256(json.dumps(values, separators=(',', ':')).encode()).hexdigest()

    def refresh(self):
        with self.lock:
            revision = self.data_revision()
            if revision == self.revision and self.state is not None:return self.state
            try:
                for _ in range(3):
                    state, _, _ = load_state(self.root, include_details=False, encode=False)
                    state['details'] = project_details(state['wallets'], self.root, include_wallets=False)
                    after = self.data_revision()
                    if revision == after:break
                    revision = after
                else:raise ValueError('Published data changed during projection.')
                wallets = []
                for wallet in state['wallets']:
                    mainnet = [a for a in wallet['assets'] if a.get('environment') == 'mainnet']
                    wallets.append({**wallet, 'assets': [], 'asset_count': len(wallet['assets']),
                                    'mainnet_asset_count': len(mainnet),
                                    'mainnet_unpriced_count': sum(a.get('value_usd') is None for a in mainnet)})
                networks = [{k: v for k, v in n.items() if k not in ('wallets', 'token_ids')} for n in state['details']['networks']]
                summary = {**state, 'wallets': wallets, 'details': {'tokens': [], 'networks': networks},
                           'paged': True, 'data_revision': revision}
                body = json.dumps(summary, ensure_ascii=False, allow_nan=False, separators=(',', ':')).encode()
            except (OSError, ValueError, KeyError):
                if self.state is None:raise
                return self.state
            self.state, self.body, self.revision = state, body, revision
            self.builds += 1
            return state

    def summary(self):
        self.refresh()
        return self.body, self.revision

    def wallet(self, selector, offset=0, limit=100, **filters):
        from kira_jobs import JobStore
        with self.lock:
            state = self.refresh()
            key = JobStore(self.root).wallet(selector)['address_key']
            wallet = next(w for w in state['wallets'] if w['key'] == key)
            return {**wallet, **page(filter_assets(wallet['assets'], **filters), offset, limit),
                    'asset_count': len(wallet['assets']), 'data_revision': self.revision}

    def holdings(self, offset=0, limit=100, **filters):
        with self.lock:
            tokens = self.refresh()['details']['tokens']
            return {**page(filter_assets(tokens, **filters), offset, limit),
                    'asset_count': len(tokens), 'data_revision': self.revision}

    def token(self, chain_id, address):
        from kira_jobs import ADDRESS
        if type(chain_id) is not int or chain_id < 1 or not isinstance(address, str):
            raise JobError('invalid_token', 'Expected a chain and contract identity.')
        address = address.lower()
        if address != 'native' and not ADDRESS.fullmatch(address):raise JobError('invalid_token', 'Use native or an EVM contract address.')
        identity = str(chain_id) + ':' + address
        with self.lock:
            state = self.refresh()
            token = next((t for t in state['details']['tokens'] if t['id'] == identity), None)
            if token is None:raise JobError('not_found', 'No saved token evidence. Missing data is unknown.')
            rows = []
            for wallet in state['wallets']:
                asset = next((a for a in wallet['assets'] if a['id'] == identity), None)
                coverage = coverage_status(wallet, coverage_for(wallet, chain_id))
                rows.append({**wallet_identity(wallet), 'asset': asset, 'coverage': coverage,
                             'balance_observed_at': asset.get('balance_observed_at') if asset else None,
                             'price_observed_at': (asset.get('price') or {}).get('observed_at') if asset else None,
                             'status': 'Held' if asset else 'No holding recorded' if coverage == 'Researched' else 'Unknown'})
            return {**token, 'wallets': rows, 'data_revision': self.revision}

    def network(self, chain_id):
        if type(chain_id) is not int or chain_id < 1:raise JobError('invalid_chain', 'Expected a positive chain ID.')
        with self.lock:
            row = next((n for n in self.refresh()['details']['networks'] if n['id'] == chain_id), None)
            if row is None:raise JobError('not_found', 'No recorded network evidence.')
            return {k: v for k, v in row.items() if k != 'token_ids'}
