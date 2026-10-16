"""Cross-wallet token and network views derived only from recorded holdings."""
from decimal import Decimal, InvalidOperation
import json
from chain_images import chain_image


def total_value(assets):
    values = [a['value_usd'] for a in assets
              if a.get('environment') == 'mainnet' and a.get('value_usd') is not None]
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
    if coverage.get('rpc_pending') or coverage.get('rpc_status') == 'pending': return 'Research pending'
    if not coverage.get('rpc_available'): return 'RPC unavailable'
    if coverage.get('registry_phase')=='deferred' or type(coverage.get('candidate_deferred')) is int and coverage['candidate_deferred']>0: return 'Research pending'
    if any(type(coverage.get(k)) is int and coverage[k]>0 for k in ('candidate_balance_errors','balance_errors','registry_errors')) or coverage.get('registry_complete') is False: return 'Incomplete on-chain checks'
    if not coverage.get('complete'): return 'Incomplete discovery'
    return 'Researched'


def observed_range(rows, key):
    dates = [r[key] for r in rows if r.get(key)]
    return {'from': min(dates, default=None), 'to': max(dates, default=None)}


def project_details(wallets, root):
    catalog = {}
    path = root / 'networks.json'
    if path.exists():
        for c in json.loads(path.read_text()).get('networks', []):
            catalog[c['chain_id']] = {'id': c['chain_id'], 'name': c['name'], 'environment': c['environment']}
    for wallet in wallets:
        for c in wallet['chains']:
            catalog.setdefault(c['id'], {k: c[k] for k in ('id', 'name', 'environment') if k in c})
    for c in catalog.values(): c['image_url'] = chain_image(c['id'])

    groups = {}
    for wallet in wallets:
        for asset in wallet['assets']:
            groups.setdefault(asset['id'], []).append((wallet, asset))
    tokens = []
    for identity, holdings in groups.items():
        first = holdings[0][1]
        network = catalog.get(first['chain_id'], {'id': first['chain_id'], 'name': str(first['chain_id']), 'environment': 'unknown'})
        assets = [a for _, a in holdings]
        token = {k: first.get(k) for k in ('id', 'chain_id', 'symbol', 'name', 'address', 'is_native', 'image_url')}
        token.update({'network': network, 'environment': network['environment'],
                      'balance': total_balance(assets), 'value_usd': total_value(assets),
                      'wallet_count': len(holdings), 'unpriced_count': sum(a.get('value_usd') is None for a in assets)})
        links = {(link['label'], link['url']): link for a in assets for link in a['links']}
        token['links'] = list(links.values())
        pools={}
        for asset in assets:
            for pool in asset.get('market_pools',[]):
                previous=pools.get(pool['url'])
                # Market evidence has its own clock, independent of wallet reads.
                if previous is None or (pool.get('observed_at') or '') > (previous.get('observed_at') or ''):
                    pools[pool['url']]=pool
        token['market_pools']=sorted(pools.values(),key=lambda p:-(p.get('liquidity_usd') or 0))
        rows = []
        by_wallet = {w['key']: a for w, a in holdings}
        for wallet in wallets:
            asset = by_wallet.get(wallet['key'])
            coverage = coverage_for(wallet, first['chain_id'])
            row = wallet_identity(wallet)
            row.update({'asset': asset, 'coverage': coverage_status(wallet, coverage),
                        'balance_observed_at':asset.get('balance_observed_at') if asset else None,
                        'price_observed_at':(asset.get('price') or {}).get('observed_at') if asset else None,
                        'status': 'Held' if asset else 'No holding recorded' if coverage_status(wallet,coverage)=='Researched' else 'Unknown'})
            rows.append(row)
        token['wallets'] = rows
        held_rows = [r for r in rows if r['asset']]
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
                            'coverage': coverage_status(wallet, coverage), 'has_holdings': bool(held)})
            rows.append(account)
        value = total_value(assets)
        if not assets and rows and all(r['coverage'] == 'Researched' for r in rows) and network['environment'] == 'mainnet': value = 0
        row.update({'value_usd': value, 'position_count': len(assets), 'unique_asset_count': len(chain_tokens),
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
