"""USD 1 route eligibility. Never substitute spot holding value for proceeds."""
from decimal import Decimal, InvalidOperation, localcontext
import json
from pathlib import Path
import re

CRITERIA = {'version': 1, 'minimum_quoted_usd': '1', 'mintclub_redemption_included': True,
            'gas_included': False, 'execution_verified': False,
            'scope': 'Recorded amount-specific routes only; unindexed and unsupported routes remain unknown.'}
ADDRESS = re.compile(r'0x[0-9a-fA-F]{40}')
HASH = re.compile(r'0x[0-9a-fA-F]{64}')
_known = json.loads((Path(__file__).resolve().parent/'sources/known-tokens.json').read_text())['tokens']
# Identity comes from the reviewed contract catalogue, never a provider's symbol.
# Other reserve/output tokens need a further amount-specific liquidation leg.
TERMINAL_ASSETS = {(row['chain_id'], row['address'].lower()) for row in _known
                   if row['symbol'] in ('USDC', 'USDC.e', 'USDT', 'USDT0', 'DAI', 'WETH', 'WBNB', 'WAVAX', 'WMATIC')}


def decimal(value):
    text = str(value)
    if len(text) > 350 or not re.fullmatch(r'[0-9]+(?:\.[0-9]+)?', text):
        return None
    try:
        number = Decimal(text)
        return number if number.is_finite() else None
    except InvalidOperation:
        return None


def output_price(chain_id, address, market):
    """Resolve the output asset's USD reference, never a nested curve spot."""
    if not isinstance(address, str) or not ADDRESS.fullmatch(address):
        return None
    if (chain_id, address.lower()) not in TERMINAL_ASSETS:
        return None
    rows = [p for p in market.get('tokens', []) if p.get('chain_id') == chain_id
            and isinstance(p.get('address'), str) and p['address'].lower() == address.lower()]
    for row in rows:
        price = decimal(row.get('usd'))
        if (price is not None and price > 0 and row.get('quality') == 'estimated'
                and row.get('basis') in ('DEX market', 'Market index')
                and row.get('observed_at') and row.get('source') and not row.get('retained_from_previous')):
            return {**row, 'usd': format(price, 'f')}
    return None


def classify(token, market, *, environment='mainnet'):
    result = {'criteria_version': CRITERIA['version'], 'minimum_quoted_usd': '1',
              'status': 'unknown', 'gas_included': False, 'execution_verified': False,
              'excluded': False, 'quotes': [], 'unknown_routes': []}
    if environment != 'mainnet':
        result.update(status='outside_usd_scope', reason='Testnet assets have no USD eligibility classification.')
        return result
    holding = decimal(token.get('wallet_balance_raw'))
    block, block_hash = str(token.get('balance_block_number')), token.get('balance_block_hash')
    if (holding is None or holding <= 0 or holding != holding.to_integral_value()
            or not re.fullmatch(r'[1-9][0-9]*', block)
            or not isinstance(block_hash, str) or not HASH.fullmatch(block_hash)):
        result['reason'] = 'Pinned holding identity unavailable.'
        return result
    routes = [p.get('cashout_quote') for p in token.get('dex_pools', [])]
    mint = token.get('mintclub') or {}
    full = mint.get('wallet_full_burn')
    if full and not mint.get('wallet_full_burn_error'):
        routes.append({'status': 'quoted', 'kind': 'mintclub_burn',
                       'input_amount_raw': token['wallet_balance_raw'],
                       'holding_amount_raw': token['wallet_balance_raw'],
                       'output_amount': full.get('net_refund'), 'output_address': mint.get('reserve_token'),
                       'block_number': mint.get('block_number'), 'block_hash': mint.get('block_hash'),
                       'observed_at': mint.get('observed_at'), 'gas_included': full.get('gas_included'),
                       'route_fees_included': True, 'price_impact_included': True,
                       'reserve_balance': mint.get('reserve_balance'), 'funded': mint.get('funded')})
    if mint.get('wallet_full_burn_error') or token.get('mintclub_error') or token.get('mintclub_pending'):
        result['unknown_routes'].append('Mint Club redemption unavailable or pending.')
    for quote in routes:
        if not isinstance(quote, dict) or quote.get('status') != 'quoted':
            result['unknown_routes'].append('Pool quote unavailable or unsupported.')
            continue
        amount, output = decimal(quote.get('input_amount_raw')), decimal(quote.get('output_amount'))
        quoted_holding = decimal(quote.get('holding_amount_raw'))
        if (amount is None or not 0 < amount <= holding or amount != amount.to_integral_value()
                or quoted_holding != holding or output is None
                or str(quote.get('block_number')) != block or quote.get('block_hash') != block_hash
                or quote.get('gas_included') is not False or quote.get('route_fees_included') is not True
                or quote.get('price_impact_included') is not True or not quote.get('observed_at')):
            result['unknown_routes'].append('Quote does not match the pinned holding or fee contract.')
            continue
        if quote.get('kind') == 'mintclub_burn':
            backing = decimal(quote.get('reserve_balance'))
            if quote.get('funded') is not True or backing is None or output > backing:
                result['unknown_routes'].append('Funded redemption backing not established.')
                continue
        price = output_price(token['chain_id'], quote.get('output_address'), market)
        if price is None:
            result['unknown_routes'].append('Terminal output USD price unavailable; another liquidation leg or nested curve spot is not cash proceeds.')
            continue
        with localcontext() as context:
            context.prec = 800
            proceeds = output * Decimal(price['usd'])
        result['quotes'].append({'kind': quote.get('kind'), 'input_amount_raw': str(quote['input_amount_raw']),
                                 'output_amount': format(output, 'f'), 'output_address': quote['output_address'].lower(),
                                 'quoted_output_usd': format(proceeds, 'f'), 'qualifies': proceeds >= Decimal('1'),
                                 'block_number': block, 'block_hash': block_hash, 'observed_at': quote['observed_at'],
                                 'output_price': price, 'partial_input': amount < holding,
                                 'transfer_tax_included': quote.get('transfer_tax_included'),
                                 'execution_verified': False, 'gas_included': False})
    if any(q['qualifies'] for q in result['quotes']):
        result['status'] = 'quoted_at_least_1_usd'
    elif result['quotes']:
        result['status'] = 'recorded_quotes_below_1_usd'
    result['reason'] = 'Quotes are gas-excluded estimates. Transfer restrictions and other routes are not verified; no global exclusion is inferred.'
    return result


def annotate(snapshot, market):
    environments = {c['chain_id']: c.get('environment') for c in snapshot.get('coverage', [])}
    for token in snapshot.get('tokens', []):
        token['cashout_eligibility'] = classify(token, market, environment=environments.get(token['chain_id'], 'unknown'))
    snapshot['cashout_criteria'] = dict(CRITERIA)
    snapshot['cashout_counts'] = {status: sum(t['cashout_eligibility']['status'] == status for t in snapshot.get('tokens', []))
                                 for status in ('quoted_at_least_1_usd', 'recorded_quotes_below_1_usd', 'unknown', 'outside_usd_scope')}
