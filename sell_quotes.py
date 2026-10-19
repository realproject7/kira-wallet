"""Cheap direct-pool estimates cached per wallet, asset and verified quantity.

Called only by explicit research/price jobs. Projection never contacts providers.
The cache holds its own same-block balance proof without rewriting a snapshot.
"""
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import uuid
from cashout import ADDRESS, HASH, classify, decimal, output_price
from chain_lifecycle import retired
from market_records import merge_pools

LIMIT = 12
BUDGET_MS = 20000
CACHE_SECONDS = 600
FAILURE_SECONDS = 120
KINDS = ('uniswap_v2_reserves', 'uniswap_v3_quoter', 'aerodrome_pool')


def identity(token):
    return f"{token['chain_id']}:{token.get('token_address', token.get('address', '')).lower()}"


def eligible(token, environments):
    return (environments.get(token['chain_id']) == 'mainnet' and not retired(token['chain_id'])
            and token.get('token_type') == 'ERC20' and ADDRESS.fullmatch(token['token_address'])
            and (decimal(token.get('wallet_balance_raw')) or 0) > 0
            and not token.get('balance_evidence_retained') and not token.get('metadata_evidence_retained'))


def supported(pool):
    return (ADDRESS.fullmatch(str(pool.get('pool', ''))) and
            (pool.get('venue') == 'uniswap' and any(v in pool.get('version_labels', []) for v in ('v2', 'v3'))
             or pool.get('venue') == 'aerodrome' and not any(v in pool.get('version_labels', []) for v in ('v3', 'slipstream'))))


def matching(row, token):
    return (isinstance(row, dict) and identity(row) == identity(token)
            and row.get('wallet_balance_raw') == token.get('wallet_balance_raw'))


def age(row, now):
    try:
        return now - datetime.fromisoformat(row['checked_at'].replace('Z', '+00:00')).timestamp()
    except (KeyError, TypeError, ValueError):
        return float('inf')


def candidates(snapshot, market):
    environments = {n['chain_id']: n.get('environment') for n in snapshot.get('coverage', [])}
    markets = {r['id']: r.get('pools', []) for r in market.get('markets', [])}
    prices = {(r['chain_id'], r['address'].lower()): r for r in market.get('tokens', [])}
    result = []
    for token in snapshot.get('tokens', []):
        if not eligible(token, environments):
            continue
        mint = token.get('mintclub') or {}
        if mint.get('wallet_full_burn') and not mint.get('wallet_full_burn_error'):
            continue
        pools = []
        for pool in merge_pools(token.get('dex_pools', []), markets.get(identity(token), [])):
            if not supported(pool) or pool.get('venue') == 'aerodrome' and token['chain_id'] != 8453:
                continue
            pair = {str(c.get('address', '')).lower() for c in pool.get('paired_tokens', [])}
            address = token['token_address'].lower()
            if len(pair) != 2 or address not in pair:
                continue
            price = output_price(token['chain_id'], next(iter(pair - {address})), market)
            if not price or price['basis'] == 'DEX market' and (decimal(price.get('liquidity_usd')) or 0) < 1000:
                continue
            pools.append(pool)
        if not pools:
            continue
        pool = max(pools, key=lambda p: decimal((p.get('reported_liquidity') or {}).get('usd')) or 0)
        # Strip previous quotes and curve routes so this pass checks only this pool.
        clean = {k: v for k, v in pool.items() if k not in ('cashout_quote', 'rpc_verification', 'factory_measurement')}
        price = prices.get((token['chain_id'], token['token_address'].lower()), {})
        value = (decimal(token.get('wallet_balance')) or 0) * (decimal(price.get('usd')) or 0)
        result.append((value, {k: token[k] for k in ('chain_id', 'token_address', 'token_type', 'wallet_balance_raw')}, clean))
    return [{**t, 'dex_pools': [p]} for _, t, p in sorted(result, key=lambda row: (-row[0], identity(row[1])))]


def enrich(snapshot, market, folder, *, previous=None, run=None, now=None):
    """Bound new quote work; reuse positive and negative observations briefly."""
    import research as h
    now = datetime.now(timezone.utc).timestamp() if now is None else now
    wallet = snapshot['wallet_address'].lower()
    prior = (previous or market).get('sell_quotes', {})
    saved = {identity(r): r for r in prior.get('records', [])} if prior.get('wallet_address') == wallet else {}
    plans = candidates(snapshot, market)
    records = {identity(t): saved[identity(t)] for t in plans if matching(saved.get(identity(t)), t)
               and saved[identity(t)].get('pool') == t['dex_pools'][0]['pool'].lower()}
    needed = [t for t in plans if identity(t) not in records or not
              0 <= age(records[identity(t)], now) < (CACHE_SECONDS if records[identity(t)].get('status') == 'quoted' else FAILURE_SECONDS)]
    selected = needed[:LIMIT]
    result = {'status': 'checked', 'records': []}
    if selected:
        from kira_config import require_alchemy
        require_alchemy()
        folder = Path(folder)/uuid.uuid4().hex; folder.mkdir(parents=True, exist_ok=True)
        payload = {'wallet': wallet, 'tokens': selected, 'networks': snapshot.get('coverage', []), 'budget_ms': BUDGET_MS}
        if run:
            result = run(payload)
        else:
            source, destination = folder/'sell-quote-input.json', folder/'sell-quote-result.json'
            h.save(source, payload)
            try:
                subprocess.run(['node', str(Path(__file__).with_name('sell-quotes.cjs')), str(source), str(destination)],
                               capture_output=True, text=True, timeout=BUDGET_MS/1000+5, check=False)
            except (subprocess.TimeoutExpired, OSError):
                pass
            try:
                result = json.loads(destination.read_text())
            except (OSError, ValueError):
                result = {'status': 'partial', 'records': []}
        returned = {identity(r): r for r in result.get('records', [])}
        for token in selected:
            key = identity(token)
            row = returned.get(key)
            # Fail closed after a fresh attempt, including a changed balance.
            records[key] = row if matching(row, token) else {
                'chain_id': token['chain_id'], 'address': token['token_address'].lower(),
                'wallet_balance_raw': token['wallet_balance_raw'], 'pool': token['dex_pools'][0]['pool'].lower(),
                'checked_at': datetime.fromtimestamp(now, timezone.utc).isoformat(), 'status': 'unknown',
                'reason': 'Quote check unavailable or budget reached'}
    cache = {'version': 1, 'wallet_address': wallet, 'records': list(records.values()),
             'candidate_count': len(plans), 'attempted': len(selected), 'reused': len(plans)-len(needed),
             'deferred': max(0, len(needed)-LIMIT), 'budget_ms': BUDGET_MS, 'limit': LIMIT,
             'status': 'partial' if len(needed)>LIMIT or result['status']!='checked' else 'checked'}
    return {**market, 'sell_quotes': cache}


def classify_with_cache(token, market, *, wallet_address, environment='mainnet'):
    """Keep historical quote pins intact; independently validate the cached pin."""
    result = classify(token, market, environment=environment)
    cache = market.get('sell_quotes', {})
    if (cache.get('version') != 1 or cache.get('wallet_address') != wallet_address.lower()
            or not eligible(token, {token['chain_id']: environment})):
        return result
    row = next((r for r in cache.get('records', []) if matching(r, token)), None)
    if not row or row.get('status') != 'quoted' or not row.get('balance_observed_at'):
        return result
    quote = row.get('quote') or {}
    if (quote.get('kind') not in KINDS or quote.get('input_address') != token['token_address'].lower()
            or quote.get('input_amount_raw') != token['wallet_balance_raw'] or quote.get('partial_input') is not False
            or not ADDRESS.fullmatch(str(row.get('pool', ''))) or quote.get('pool', '').lower() != row['pool'].lower()
            or not HASH.fullmatch(str(row.get('balance_block_hash', '')))):
        return result
    fresh = {**token, 'balance_block_number': row.get('balance_block_number'), 'balance_block_hash': row['balance_block_hash'],
             'mintclub': None, 'liquidation_routes': [], 'liquidation_unknown_routes': [], 'dex_pools': [{'cashout_quote': quote}]}
    observation = classify(fresh, market, environment=environment)
    if observation['quotes']:
        result['quotes'] += observation['quotes']
        result['status'] = 'quoted_at_least_1_usd' if any(q['qualifies'] for q in result['quotes']) else 'recorded_quotes_below_1_usd'
    return result
