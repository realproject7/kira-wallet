"""Indicative sums of independent saved quotes, never a combined exit quote."""
from decimal import Decimal, localcontext
import json
from pathlib import Path
from market_records import number
from native_assets import native_identity
from asset_policy import included

STABLE_ASSETS = {(row['chain_id'],row['address'].lower())
                 for row in json.loads((Path(__file__).parent/'sources/known-tokens.json').read_text())['tokens']
                 if row['symbol'] in ('USDC','USDC.e','USDT','USDT0','DAI')}


def spot_sell_reference(asset):
    """A saved market reference for recognized assets, never an execution quote."""
    if asset.get('environment')!='mainnet' or asset.get('archived') or asset.get('quantity_retained'):
        return None
    native=asset.get('is_native') is True and asset.get('address') is None and native_identity(asset.get('chain_id'),asset.get('symbol'))
    stable=(asset.get('chain_id'),str(asset.get('address') or '').lower()) in STABLE_ASSETS
    price=asset.get('price') or {};value=number(asset.get('value_usd'))
    if not (native or stable) or value is None or value<0 or price.get('quality')!='estimated' or price.get('retained_from_previous') or price.get('basis') not in ('Market index','DEX market') or not price.get('observed_at') or not price.get('source'):
        return None
    return {'value_usd':value,'kind':'native_market_reference' if native else 'stable_market_reference',
            'observed_at':price['observed_at'],'source':price['source'],'gas_included':False,'execution_verified':False}


def summarize_sell_out(assets):
    positions = [a for a in assets if included(a) and a.get('environment') == 'mainnet' and not a.get('archived')]
    quotes = [a['sell_out'] for a in positions
              if not a.get('quantity_retained') and number((a.get('sell_out') or {}).get('value_usd')) is not None]
    references = [a['sell_out_reference'] for a in positions if number((a.get('sell_out') or {}).get('value_usd')) is None
                  and a.get('sell_out_reference') and not a.get('quantity_retained')]
    dates = [q['observed_at'] for q in quotes if q.get('observed_at')]
    with localcontext() as context:
        context.prec = 800
        value = number(sum((Decimal(str(q['value_usd'])) for q in quotes+references), Decimal(0))) if quotes or references else None
    return {'value_usd': value, 'quoted_count': len(quotes), 'position_count': len(positions),
            'reference_count':len(references),'missing_count': len(positions) - len(quotes) - len(references), 'observed_from': min(dates, default=None),
            'observed_to': max(dates, default=None), 'basis': 'independent_quotes_and_market_references' if references else 'independent_saved_quotes',
            'gas_included': False, 'combined_execution_verified': False}
