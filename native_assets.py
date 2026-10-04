"""Explicit native-asset identities and public market metadata. No wallet input."""
from datetime import datetime, timezone
import math
from urllib.parse import urlencode

import research as h

# Chain identity is required. An ERC20 called APE or ETH is never matched here.
NATIVE_ASSETS = {chain: ('ETH', 'ethereum') for chain in
    (1, 8453, 81457, 10, 42161, 7560, 130, 7777777, 5112, 4663,
     11155111, 84532, 168587773, 111557560)}
NATIVE_ASSETS.update({137: ('POL', 'polygon-ecosystem-token'), 56: ('BNB', 'binancecoin'),
    43114: ('AVAX', 'avalanche-2'), 43113: ('AVAX', 'avalanche-2'),
    109: ('BONE', 'bone-shibaswap'), 157: ('BONE', 'bone-shibaswap'),
    8217: ('KAIA', 'kaia'), 33139: ('APE', 'apecoin'), 177: ('HSK', 'hashkey-platform-token')})


def native_identity(chain_id, symbol):
    row = NATIVE_ASSETS.get(chain_id)
    return row[1] if row and row[0] == symbol else None


def market_metadata(coverage, *, fetch=None, observed=None):
    """Fetch one public batch by coin ID, independent of indexer configuration."""
    observed = observed or datetime.now(timezone.utc)
    identities = {native_identity(c['chain_id'], c.get('native_symbol')): c.get('native_symbol')
                  for c in coverage if c.get('environment') == 'mainnet'}
    identities.pop(None, None)
    if not identities:
        return {'prices': {}, 'images': {}, 'evidence': None}
    source = 'https://api.coingecko.com/api/v3/coins/markets?' + urlencode({
        'vs_currency': 'usd', 'ids': ','.join(sorted(identities))})
    response = (fetch or h.fetch)(source)
    evidence = {'source': source, 'observed_at': observed.isoformat(), 'response': response}
    prices, images = {}, {}
    for row in response if isinstance(response, list) else []:
        if not isinstance(row, dict): continue
        asset = row.get('id'); symbol = identities.get(asset)
        if not symbol or not isinstance(row.get('symbol'), str) or row['symbol'].upper() != symbol: continue
        if isinstance(row.get('image'), str):
            images[asset] = {'image_url': row['image'], 'observed_at': observed.isoformat()}
        try:
            price = float(row['current_price'])
            timestamp = row.get('last_updated')
            if not isinstance(timestamp, str): continue
            updated = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
            age = (observed - updated).total_seconds()
            if isinstance(row['current_price'], bool) or not math.isfinite(price) or price <= 0 or not -60 <= age <= 3600:
                continue
        except (KeyError, TypeError, ValueError, OverflowError): continue
        prices[symbol + '_USD'] = {'value': price, 'observed_at': updated.isoformat(),
            'source': source, 'basis': 'Market index', 'asset_id': asset}
    return {'prices': prices, 'images': images, 'evidence': evidence}
