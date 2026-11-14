"""Cross-wallet token and network views derived only from recorded holdings."""
from decimal import Decimal, InvalidOperation
import json
from chain_images import chain_image
from market_records import pool_identity
from sell_summary import summarize_sell_out
from asset_policy import included, summary as policy_summary


def total_value(assets, *, reported=False):
    values = [a['value_usd'] for a in assets
              if (reported or included(a)) and a.get('environment') == 'mainnet' and a.get('value_usd') is not None]
    return sum(values) if values else None


def total_balance(assets):
    try:
        quantities = [Decimal(a['balance']) for a in assets]
        if not quantities or any(not q.is_finite() or q < 0 for q in quantities): return None
        # Decimal's default precision could round large or very small holdings.
        from decimal import localcontext
        with localcontext() as context:
            context.prec = max(80, sum(len(q.as_tuple().digits) + abs(q.as_tuple().exponent) for q in quantities) + 10)
            return format(sum(quantities, Decimal(0)), 'f')
    except (InvalidOperation, TypeError, KeyError): return None


def wallet_identity(wallet):
    return {k: wallet.get(k) for k in ('key', 'name', 'address', 'tags', 'analysed_at', 'prices_at')}


def coverage_for(wallet, chain_id):
    return next((c for c in wallet['chains'] if c['id'] == chain_id), None)


def coverage_status(wallet, coverage):
    if not wallet.get('analysed_at'): return 'Awaiting analysis'
    if not coverage: return 'Not researched'
    if coverage.get('lifecycle',{}).get('status')=='retired':return 'Archived network'
    if coverage.get('lifecycle',{}).get('status')=='retirement_reported':return 'Retirement reported'
    if coverage.get('head_status')=='stale':return 'Stale observed head'
    if coverage.get('rpc_pending') or coverage.get('rpc_status') == 'pending': return 'Research pending'
    if not coverage.get('rpc_available'): return 'RPC unavailable'
    if coverage.get('registry_phase')=='deferred' or type(coverage.get('candidate_deferred')) is int and coverage['candidate_deferred']>0: return 'Research pending'
    if any(type(coverage.get(k)) is int and coverage[k]>0 for k in ('candidate_balance_errors','balance_errors','registry_errors')) or coverage.get('registry_complete') is False: return 'Incomplete on-chain checks'
    if not coverage.get('complete'): return 'Incomplete discovery'
    return 'Researched'


def native_markets(chain_id, tokens, catalog, limit=50):
    """Recorded pools that trade a chain's native asset, directly or through its wrapped token.

    A native asset has no contract, so no pool is recorded under it. Saved research
    already holds these pools under the wrapped token. Pools saved under another token
    count only when their other side is a catalogued token, so an unknown token's
    reported liquidity cannot stand in for the native market. No chain read.
    """
    from native_assets import wrapped_native
    wrapped = wrapped_native(chain_id, catalog)
    address = wrapped['address'].lower() if wrapped else None
    targets = {'0x' + '0' * 40} | ({address} if address else set())
    known = {str(t['address']).lower() for t in catalog if t.get('chain_id') == chain_id}
    pools = {}
    for token in tokens:
        if token.get('chain_id') != chain_id: continue
        own = address is not None and token.get('id') == str(chain_id) + ':' + address
        for pool in token.get('market_pools') or []:
            coins = [str(coin.get('address') or '').lower() for coin in pool.get('pair') or []]
            if not any(coin in targets for coin in coins): continue
            if not own and not all(coin in targets or coin in known for coin in coins): continue
            identity = pool_identity(pool); previous = pools.get(identity)
            if previous is None or (pool.get('observed_at') or '') > (previous.get('observed_at') or ''): pools[identity] = pool
    rows = sorted(pools.values(), key=lambda p: (-(p.get('liquidity_usd') or 0), str(p.get('pool'))))[:limit]
    return rows, ({'symbol': wrapped['symbol'], 'address': address} if wrapped and rows else None)

def observed_range(rows, key):
    dates = [r[key] for r in rows if r.get(key)]
    return {'from': min(dates, default=None), 'to': max(dates, default=None)}


def project_details(wallets, root, *, include_wallets=True):
    catalog = {}
    path = root / 'networks.json'
    if path.exists():
        for c in json.loads(path.read_text()).get('networks', []):
            catalog[c['chain_id']] = {'id': c['chain_id'], 'name': c['name'], 'environment': c['environment']}
    for wallet in wallets:
        for c in wallet['chains']:
            catalog.setdefault(c['id'], {k: c[k] for k in ('id', 'name', 'environment') if k in c})
    from chain_lifecycle import lifecycle
    for c in catalog.values():
        c['image_url'] = chain_image(c['id'])
        c['lifecycle'] = lifecycle(c['id'])

    groups = {}
    for wallet in wallets:
        for asset in wallet['assets']:
            groups.setdefault(asset['id'], []).append((wallet, asset))
    tokens = []
    for identity, holdings in groups.items():
        first = holdings[0][1]
        network = catalog.get(first['chain_id'], {'id': first['chain_id'], 'name': str(first['chain_id']), 'environment': 'unknown'})
        assets = [a for _, a in holdings]
        token = {k: first.get(k) for k in ('id', 'chain_id', 'symbol', 'name', 'address', 'is_native', 'image_url', 'curve_reserve', 'portfolio_status', 'included_in_totals', 'valuation_policy', 'risk_check')}
        token['portfolio_status']=first.get('portfolio_status') or 'portfolio'
        token['included_in_totals']=included(first)
        token.update({'network': network, 'environment': network['environment'],
                      'balance': total_balance(assets), 'value_usd': total_value(assets,reported=True),
                      'wallet_count': len(holdings), 'unpriced_count': sum(a.get('value_usd') is None for a in assets)})
        # Separate wallet quotes may consume the same pool or curve backing.
        # Never sum them into a purported combined full-position sale.
        token['sell_out_summary'] = summarize_sell_out(assets)
        token['sell_out'] = assets[0].get('sell_out') if len(assets) == 1 else None
        token['sell_out_reference'] = assets[0].get('sell_out_reference') if len(assets) == 1 else None
        links = {(link['label'], link['url']): link for a in assets for link in a['links']}
        token['links'] = list(links.values())
        curves=[a['curve_reserve'] for a in assets if a.get('curve_reserve')]
        if curves:token['curve_reserve']=max(curves,key=lambda c:c.get('observed_at') or '')
        pools={}
        for asset in assets:
            for pool in asset.get('market_pools',[]):
                identity=pool_identity(pool);previous=pools.get(identity)
                # Market evidence has its own clock, independent of wallet reads.
                if previous is None or (pool.get('observed_at') or '') > (previous.get('observed_at') or ''):
                    pools[identity]=pool
        token['market_pools']=sorted(pools.values(),key=lambda p:-(p.get('liquidity_usd') or 0))
        rows = []
        by_wallet = {w['key']: a for w, a in holdings}
        for wallet in wallets if include_wallets else []:
            asset = by_wallet.get(wallet['key'])
            coverage = coverage_for(wallet, first['chain_id'])
            row = wallet_identity(wallet)
            row.update({'asset': asset, 'coverage': coverage_status(wallet, coverage),
                        'balance_observed_at':asset.get('balance_observed_at') if asset else None,
                        'price_observed_at':(asset.get('price') or {}).get('observed_at') if asset else None,
                        'status': 'Held' if asset else 'No holding recorded' if coverage_status(wallet,coverage)=='Researched' else 'Unknown'})
            rows.append(row)
        token['wallets'] = rows
        held_rows = [r for r in rows if r['asset']] if include_wallets else [dict(wallet_identity(w), price_observed_at=(a.get('price') or {}).get('observed_at')) for w,a in holdings]
        token['analysis_times'] = observed_range(held_rows, 'analysed_at')
        token['price_times'] = observed_range(held_rows, 'price_observed_at')
        tokens.append(token)
    tokens.sort(key=lambda a: (-(a['value_usd'] if a['value_usd'] is not None else -1), a['id']))

    networks = []
    for chain_id, network in catalog.items():
        row = dict(network)
        chain_tokens = [t for t in tokens if t['chain_id'] == chain_id]
        assets = [a for wallet in wallets for a in wallet['assets'] if a['chain_id'] == chain_id]
        rows = []
        for wallet in wallets:
            coverage = coverage_for(wallet, chain_id)
            held = [a for a in wallet['assets'] if a['chain_id'] == chain_id]
            account = wallet_identity(wallet)
            value = total_value(held)
            if not held and coverage_status(wallet,coverage)=='Researched' and network['environment'] == 'mainnet': value = 0
            account.update({'position_count': len(held), 'value_usd': value,
                            'unpriced_count': sum(a.get('value_usd') is None for a in held),
                            'coverage': 'Archived network' if network['lifecycle'].get('status') == 'retired' else coverage_status(wallet, coverage), 'has_holdings': bool(held)})
            rows.append(account)
        value = total_value(assets)
        if not assets and rows and all(r['coverage'] == 'Researched' for r in rows) and network['environment'] == 'mainnet': value = 0
        row.update({'asset_policy_summary':policy_summary(assets),'sell_out_summary':summarize_sell_out(assets),'value_usd': value, 'position_count': len(assets), 'unique_asset_count': len(chain_tokens),
                    'wallet_count': sum(r['has_holdings'] for r in rows),
                    'unpriced_count': sum(a.get('value_usd') is None for a in assets),
                    'wallets': rows, 'tokens': chain_tokens,
                    'analysis_times': observed_range(rows, 'analysed_at'),
                    'price_times': observed_range([a.get('price') or {} for a in assets], 'observed_at')})
        networks.append(row)
    networks.sort(key=lambda c: (c['environment'] != 'mainnet', -(c['value_usd'] if c['value_usd'] is not None else -1), c['name']))
    # Network tokens reference the same objects in memory. Serialize only their
    # IDs; the client joins them against tokens rather than duplicating records.
    for network in networks: network['token_ids'] = [t['id'] for t in network.pop('tokens')]
    return {'tokens': tokens, 'networks': networks}
