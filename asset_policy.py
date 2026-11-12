"""Local valuation preferences and explicitly requested token risk observations."""
from collections import defaultdict
from datetime import datetime, timezone
import fcntl
import hashlib
import json
from pathlib import Path
import re
import urllib.request
from market_records import number

STATUSES = ('portfolio', 'review', 'excluded', 'all')


def included(asset):
    return asset.get('included_in_totals') is not False


def summary(assets):
    groups = {status: {a['id'] for a in assets if a.get('portfolio_status', 'portfolio') == status}
              for status in STATUSES[:3]}
    return {status + '_count': len(ids) for status, ids in groups.items()}


def load(root):
    try:
        return json.loads((Path(root) / 'token-policy.json').read_text())
    except FileNotFoundError:
        return {'schema_version': 1, 'overrides': {}, 'risk_checks': {}}


def apply(wallets, root):
    """Keep all observed facts. Only the valuation membership is an overlay."""
    saved = load(root)
    groups = defaultdict(list)
    for wallet in wallets:
        for asset in wallet['assets']:
            groups[asset['id']].append(asset)
    for identity, assets in groups.items():
        risk = saved['risk_checks'].get(identity)
        reasons = list((risk or {}).get('review_reasons', []))
        mainnet = [a for a in assets if a.get('environment') == 'mainnet' and not a.get('archived')]
        value = sum(number(a.get('value_usd')) or 0 for a in mainnet)
        liquidity = max((number(p.get('liquidity_usd')) or 0 for a in mainnet
                         for p in a.get('market_pools', [])), default=0)
        # A material spot valuation larger than the observed backing pool needs
        # review. It is not a fraud verdict and does not apply to ordinary unknowns.
        if value >= 10000 and liquidity >= 1000 and value > 2 * liquidity and mainnet and all(
                (a.get('price') or {}).get('basis') == 'DEX market' and
                number((a.get('sell_out') or {}).get('value_usd')) is None for a in mainnet):
            reasons.append('Spot valuation exceeds twice the largest observed pool liquidity; no sale quote is saved.')
        override = saved['overrides'].get(identity, {}).get('mode', 'auto')
        status = 'excluded' if override == 'exclude' else 'portfolio' if override == 'include' else 'review' if reasons else 'portfolio'
        for asset in assets:
            asset.update(portfolio_status=status, included_in_totals=status == 'portfolio',
                         valuation_policy={'mode': override, 'reasons': reasons}, risk_check=risk)
    for wallet in wallets:
        assets = wallet['assets']
        wallet['asset_policy_summary'] = summary(assets)
        values = [a['value_usd'] for a in assets if included(a) and a.get('environment') == 'mainnet'
                  and a.get('value_usd') is not None]
        wallet['known_value_usd'] = sum(values) if values else None
        for chain in wallet['chains']:
            values = [a['value_usd'] for a in assets if included(a) and a['chain_id'] == chain['id']
                      and a.get('environment') == 'mainnet' and a.get('value_usd') is not None]
            chain['value_usd'] = sum(values) if values else None


def fetch_risk(chain_id, address):
    source = f'https://api.gopluslabs.io/api/v1/token_security/{chain_id}?contract_addresses={address}'
    result = {'provider': 'GoPlus', 'source': source,
              'observed_at': datetime.now(timezone.utc).isoformat(), 'status': 'unknown',
              'flags': [], 'review_reasons': [], 'sellability': 'unverified'}
    try:
        with urllib.request.urlopen(urllib.request.Request(source, headers={'Accept': 'application/json'}), timeout=8) as response:
            raw = response.read(1_000_001)
        if len(raw) > 1_000_000:
            raise ValueError('oversized response')
        data = json.loads(raw)
        token = data.get('result', {}).get(address)
        if data.get('code') != 1 or not isinstance(token, dict) or not token:
            raise ValueError('unavailable token response')
        fields = ('is_open_source', 'is_honeypot', 'cannot_sell_all', 'sell_tax', 'buy_tax', 'holder_count')
        result['reported'] = {key: str(token[key])[:80] for key in fields if type(token.get(key)) in (str, int, float)}
        for key, label in [('is_honeypot', 'Provider reports a honeypot.'), ('cannot_sell_all', 'Provider reports a restriction on selling the full balance.')]:
            if token.get(key) == '1':
                result['review_reasons'].append(label)
        tax = number(token.get('sell_tax'))
        if tax is not None and tax >= .5:
            result['review_reasons'].append('Provider reports a sell tax of at least 50%.')
        if token.get('is_open_source') == '0':
            result['flags'].append('Provider reports closed source; contract mechanisms remain unknown.')
        result['status'] = 'flagged' if result['review_reasons'] else 'no_high_risk_flags_reported' if all(
            token.get(key) == '0' for key in ('is_honeypot', 'cannot_sell_all')) and tax is not None else 'unknown'
        result['completed'] = True
    except (OSError, ValueError, TypeError, AttributeError):
        result.update(completed=False, flags=['Risk lookup unavailable. This does not establish safety.'])
    return result


def action(root, request):
    from kira_jobs import JobError, atomic, digest, fields
    fields(request, ['schema_version', 'operation', 'input', 'idempotency_key'])
    if type(request['schema_version']) is not int or request['schema_version'] != 1:
        raise JobError('unsupported_version', 'Expected request schema version 1.')
    operation = request['operation']; args = request['input']; key = request['idempotency_key']
    fields(args, ['chain_id', 'address', 'mode'] if operation == 'token.policy' else ['chain_id', 'address'])
    if type(args['chain_id']) is not int or args['chain_id'] < 1 or not isinstance(args['address'], str) or not re.fullmatch(r'native|0x[0-9a-fA-F]{40}', args['address']):
        raise JobError('invalid_token', 'Use a recorded chain and contract identity.')
    if operation == 'token.policy' and args['mode'] not in ('auto', 'include', 'exclude'):
        raise JobError('invalid_policy', 'Choose auto, include or exclude.')
    if operation == 'token.riskCheck' and args['address'] == 'native':
        raise JobError('invalid_token', 'Native assets do not have a token contract to check.')
    if not isinstance(key, str) or not 8 <= len(key) <= 200:
        raise JobError('invalid_key', 'Supply an idempotency key of 8 to 200 characters.')
    root = Path(root); args = {**args, 'address': args['address'].lower()}
    identity = str(args['chain_id']) + ':' + args['address']
    fingerprint = digest({'operation': operation, 'input': args})
    receipt = root / '.token-actions' / (digest(key) + '.json')
    if (root/'jobs/requests'/(digest(key)+'.json')).exists() or (root/'jobs/batches'/(digest(key)+'.json')).exists():
        raise JobError('idempotency_conflict','This request key belongs to a research operation.')
    def previous():
        if not receipt.exists(): return None
        item = json.loads(receipt.read_text())
        if item['request_hash'] != fingerprint:
            raise JobError('idempotency_conflict', 'This request key belongs to a different token action.')
        return item['result']
    with (root / '.token-policy.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        old = previous()
        if old: return old
    observation = fetch_risk(args['chain_id'], args['address']) if operation == 'token.riskCheck' else None
    with (root / '.token-policy.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        old = previous()
        if old: return old
        saved = load(root)
        if observation:
            before = saved['risk_checks'].get(identity)
            if not observation['completed'] and before and before.get('completed'):
                observation = {**before, 'last_attempt': observation}
            if not before or observation['observed_at'] >= before['observed_at']:
                saved['risk_checks'][identity] = observation
        else:
            saved['overrides'][identity] = {'mode': args['mode']}
        atomic(root / 'token-policy.json', saved)
        result = {'schema_version': 1, 'identity': identity, 'operation': operation,
                  'completed': True, 'policy': saved['overrides'].get(identity, {'mode': 'auto'}),
                  'risk_check': saved['risk_checks'].get(identity)}
        atomic(receipt, {'request_hash': fingerprint, 'result': result})
        return result
