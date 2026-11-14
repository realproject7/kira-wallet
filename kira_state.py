"""Cached, paged views of published local records. Never contacts providers."""
from __future__ import annotations
import hashlib
import json
import re
from pathlib import Path
import sys
import threading
from collections import OrderedDict
from decimal import Decimal, InvalidOperation
from kira_jobs import JobError
from asset_policy import STATUSES

sys.path.insert(0, str(Path(__file__).resolve().parent / 'viewer'))
from model import load_state, within, dashboard
from details import project_details, wallet_identity, coverage_for, coverage_status, native_markets


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
                  sort='value', pricing='all', include_testnets=True, portfolio_status='portfolio'):
    if not isinstance(query, str) or len(query) > 500:
        raise JobError('invalid_query', 'Use a search string of up to 500 characters.')
    if chain_id is not None and (type(chain_id) is not int or chain_id < 1):
        raise JobError('invalid_chain', 'Expected a positive chain ID.')
    if sort not in ('value', 'name', 'wallets', 'sell_out') or pricing not in ('all', 'priced', 'unpriced') or type(include_testnets) is not bool:
        raise JobError('invalid_filter', 'Choose supported sorting and price filters.')
    if portfolio_status not in STATUSES:raise JobError('invalid_filter', 'Choose a supported portfolio status.')
    try:
        if type(minimum_value_usd) not in (str, int, float) or len(str(minimum_value_usd)) > 80:raise ValueError()
        minimum = Decimal(str(minimum_value_usd))
        if not minimum.is_finite() or minimum < 0:raise ValueError()
    except (InvalidOperation, ValueError):
        raise JobError('invalid_filter', 'Use a finite nonnegative minimum value.') from None
    query = query.strip().casefold()
    result = []
    for asset in rows:
        if portfolio_status != 'all' and asset.get('portfolio_status','portfolio') != portfolio_status:continue
        value = asset.get('value_usd')
        if chain_id is not None and asset['chain_id'] != chain_id:continue
        if not include_testnets and asset.get('environment') != 'mainnet':continue
        if minimum and (value is None or Decimal(str(value)) < minimum):continue
        if pricing == 'priced' and value is None or pricing == 'unpriced' and value is not None:continue
        if query and not any(query in str(asset.get(k) or ('native' if k == 'address' else '')).casefold() for k in ('symbol', 'name', 'address')):continue
        result.append(asset)
    if sort == 'name':result.sort(key=lambda a: (str(a.get('symbol') or '').casefold(), a['id']))
    elif sort == 'wallets':result.sort(key=lambda a: (-a.get('wallet_count', 1), a['id']))
    elif sort == 'sell_out':
        def sale_value(asset):
            if asset.get('sell_out_summary') is not None:return asset['sell_out_summary'].get('value_usd')
            quote=(asset.get('sell_out') or {}).get('value_usd')
            return quote if quote is not None else (asset.get('sell_out_reference') or {}).get('value_usd')
        result.sort(key=lambda a:(sale_value(a) is None,-(sale_value(a) or 0),a['id']))
    else:result.sort(key=lambda a: (a.get('value_usd') is None, -(a.get('value_usd') or 0), a['id']))
    return result


def unpriced_hidden(rows, **filters):
    """Count unpriced holdings that only the price filter keeps off the page.

    A list that shows priced holdings must still say how many it leaves out:
    an unknown value is not a zero balance.
    """
    if filters.get('pricing', 'all') != 'priced' and not Decimal(str(filters.get('minimum_value_usd', '0'))):
        return 0
    return len(filter_assets(rows, **{**filters, 'minimum_value_usd': '0', 'pricing': 'unpriced'}))


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
        self.wallet_cache = {}
        self.scope_cache = OrderedDict()
        self.scope_builds = 0
        self.overview_state = None

    def data_revision(self):
        """Stat published inputs before projecting; also sees legacy writers and crash gaps."""
        with self.lock:
            registry = self.root / 'wallets.json'
            current = signature(registry)
            if current != self.registry_signature or not self.paths:
                value = json.loads(registry.read_text())
                paths = {registry, self.root / 'networks.json', self.root / 'cache/token-images.json', self.root / 'token-policy.json', self.root / 'wallet-folders.json',self.root/'positions/index.json'}
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
            from sell_analysis import analysis_index, snapshot_path, _job
            value=json.loads(registry.read_text())
            for entry in value.get('wallets',[]):
                if entry.get('research_generation'):
                    path=self.root/'jobs'/(entry['research_generation']+'.json')
                    try:
                        baseline=_job(str(path),signature(path))
                        values.append((entry['address_key'],baseline['state'],(baseline['result'] or {}).get('snapshot_id')))
                    except (OSError,ValueError,TypeError):pass
            for address, analysis in sorted(analysis_index(self.root).items()):
                folder=snapshot_path(self.root,analysis['snapshot_id']).parent
                values.append((address,analysis['job_id'],analysis['analysed_at'],
                               signature(folder/'results.json'),signature(folder/'market-prices.json'),signature(folder/'token-market-metadata.json')))
            return hashlib.sha256(json.dumps(values, separators=(',', ':')).encode()).hexdigest()

    def refresh(self):
        with self.lock:
            revision = self.data_revision()
            if revision == self.revision and self.state is not None:return self.state
            try:
                for _ in range(3):
                    state, _, _ = load_state(self.root, include_details=False, encode=False, wallet_cache=self.wallet_cache)
                    state['details'] = project_details(state['wallets'], self.root, include_wallets=False)
                    from kira_folders import catalog
                    state['wallet_folders'] = catalog(self.root,state['wallets'])
                    after = self.data_revision()
                    if revision == after:break
                    revision = after
                else:raise ValueError('Published data changed during projection.')
                summary = self.compact(state,revision)
                body = json.dumps(summary, ensure_ascii=False, allow_nan=False, separators=(',', ':')).encode()
            except (OSError, ValueError, KeyError):
                if self.state is None:raise
                return self.state
            self.state, self.body, self.revision = state, body, revision
            self.overview_state = summary
            self.scope_cache.clear()
            self.builds += 1
            return state

    def summary(self):
        self.refresh()
        return self.body, self.revision

    @staticmethod
    def compact(state,revision):
        wallets=[]
        for wallet in state['wallets']:
            mainnet=[a for a in wallet['assets'] if a.get('environment')=='mainnet']
            wallets.append({**wallet,'assets':[],'positions':[],'asset_count':len(wallet['assets']),
                            'mainnet_asset_count':len(mainnet),
                            'mainnet_unpriced_count':sum(a.get('value_usd') is None for a in mainnet)})
        networks=[{k:v for k,v in n.items() if k not in ('wallets','token_ids')} for n in state['details']['networks']]
        return {**state,'wallets':wallets,'details':{'tokens':[],'networks':networks},'paged':True,'data_revision':revision}

    def scoped(self,folder_id=None):
        """Aggregate only selected cached positions, once per revision and scope."""
        with self.lock:
            state=self.refresh()
            if folder_id in (None,'all'):return state
            if folder_id not in self.scope_cache:
                from kira_folders import members
                wallets=members(state['wallet_folders'],state['wallets'],folder_id)
                selected={**state,'wallets':wallets,'folder_id':folder_id,'dashboard':dashboard(wallets),
                          'details':project_details(wallets,self.root,include_wallets=False)}
                self.scope_cache[folder_id]=(selected,self.compact(selected,self.revision))
                self.scope_builds+=1
                if len(self.scope_cache)>8:self.scope_cache.popitem(last=False)
            self.scope_cache.move_to_end(folder_id)
            return self.scope_cache[folder_id][0]

    def overview(self,folder_id=None):
        with self.lock:
            self.scoped(folder_id)
            return self.overview_state if folder_id in (None,'all') else self.scope_cache[folder_id][1]

    def wallet(self, selector, offset=0, limit=100, **filters):
        from kira_jobs import JobStore
        with self.lock:
            state = self.refresh()
            key = JobStore(self.root).wallet(selector)['address_key']
            wallet = next(w for w in state['wallets'] if w['key'] == key)
            return {**wallet, 'positions':[], **page(filter_assets(wallet['assets'], **filters), offset, limit),
                    'unpriced_hidden_count': unpriced_hidden(wallet['assets'], **filters),
                    'asset_count': len(wallet['assets']), 'data_revision': self.revision}

    def holdings(self, offset=0, limit=100, *, folder_id=None, **filters):
        with self.lock:
            tokens = self.scoped(folder_id)['details']['tokens']
            return {**page(filter_assets(tokens, **filters), offset, limit),
                    'unpriced_hidden_count': unpriced_hidden(tokens, **filters),
                    'asset_count': len(tokens), 'data_revision': self.revision}

    def positions(self, wallet=None, folder_id=None, token_id=None, chain_id=None, platform=None, offset=0, limit=50):
        from positions import read_positions
        from kira_jobs import JobStore
        with self.lock:
            wallets=self.scoped(folder_id)['wallets']
            if wallet:
                key=JobStore(self.root).wallet(wallet)['address_key'];wallets=[w for w in wallets if w['key']==key]
            if token_id and (not isinstance(token_id,str) or not re.fullmatch(r'[1-9][0-9]*:(?:native|0x[0-9a-fA-F]{40})',token_id)):raise JobError('invalid_token','Use a chain and contract identity.')
            if chain_id is not None and (type(chain_id) is not int or chain_id<1):raise JobError('invalid_chain','Use a positive chain ID.')
            from positions import PLATFORMS
            if platform is not None and platform not in PLATFORMS:raise JobError('invalid_platform','Choose a recorded platform ID.')
            return {**read_positions(self.root,wallets,offset,limit,token_id=token_id.lower() if token_id else None,chain_id=chain_id,platform=platform),'data_revision':self.revision}

    def token(self, chain_id, address, *, folder_id=None):
        from kira_jobs import ADDRESS
        if type(chain_id) is not int or chain_id < 1 or not isinstance(address, str):
            raise JobError('invalid_token', 'Expected a chain and contract identity.')
        address = address.lower()
        if address != 'native' and not ADDRESS.fullmatch(address):raise JobError('invalid_token', 'Use native or an EVM contract address.')
        identity = str(chain_id) + ':' + address
        with self.lock:
            state = self.scoped(folder_id)
            token = next((t for t in state['details']['tokens'] if t['id'] == identity), None)
            if token is None:
                a=next((a for w in state['wallets'] for p in w.get('positions',[]) if p['chain_id']==chain_id for a in p['assets'] if a['address'].lower()==address),None)
                if a:
                    networks=json.loads((self.root/'networks.json').read_text())['networks'];name=next((n.get('name',n['network']) for n in networks if n['chain_id']==chain_id),str(chain_id))
                    token={'id':identity,'chain_id':chain_id,'address':None if address=='native' else address,'is_native':address=='native','symbol':a['symbol'],'name':a['symbol'],'balance':'0','value_usd':None,'wallet_count':0,'unpriced_count':0,'environment':'mainnet','network':{'id':chain_id,'name':name},'balance_times':{},'price_times':{},'market_pools':[],'links':[]}
            if token is None:raise JobError('not_found', 'No saved token evidence. Missing data is unknown.')
            rows = []
            for wallet in state['wallets']:
                asset = next((a for a in wallet['assets'] if a['id'] == identity), None)
                coverage = coverage_status(wallet, coverage_for(wallet, chain_id))
                rows.append({**wallet_identity(wallet), 'asset': asset, 'coverage': coverage,
                             'balance_observed_at': asset.get('balance_observed_at') if asset else None,
                             'price_observed_at': (asset.get('price') or {}).get('observed_at') if asset else None,
                             'status': 'Held' if asset else 'No holding recorded' if coverage == 'Researched' else 'Unknown'})
            recorded=self.refresh()['details']['tokens'];market=next((t for t in recorded if t['id']==identity),token)
            pools=market.get('market_pools',[]);via=None
            if address=='native' and not pools:
                # BNB or ETH has no contract of its own. Show the saved pools of its wrapped token.
                catalog=json.loads((Path(__file__).resolve().parent/'sources/known-tokens.json').read_text())['tokens']
                pools,via=native_markets(chain_id,recorded,catalog)
            from positions import allocation
            return {**token,'capital_allocation':allocation(state['wallets'],token_id=identity),'market_pools':pools,'market_via':via,'links':market.get('links',[]),'curve_reserve':market.get('curve_reserve'),
                    'market_scope':'workspace', 'wallets': rows, 'data_revision': self.revision}

    def network(self, chain_id, *, folder_id=None):
        if type(chain_id) is not int or chain_id < 1:raise JobError('invalid_chain', 'Expected a positive chain ID.')
        with self.lock:
            row = next((n for n in self.scoped(folder_id)['details']['networks'] if n['id'] == chain_id), None)
            if row is None:raise JobError('not_found', 'No recorded network evidence.')
            from positions import allocation
            return {**{k: v for k, v in row.items() if k != 'token_ids'},'capital_allocation':allocation(self.scoped(folder_id)['wallets'],chain_id=chain_id),'data_revision':self.revision}
