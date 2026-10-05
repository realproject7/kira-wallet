"""Contract-scoped token artwork. Only research refreshes the local catalog."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode, urlparse
import json
import os
import re
import urllib.request
from native_assets import NATIVE_ASSETS, native_identity
from chain_images import chain_image

ROOT = Path(os.environ.get('KIRA_DATA_DIR',Path(__file__).resolve().parents[1])).expanduser().resolve()
API = 'https://mint.club/api'
IMAGE_HOSTS = ('mint.club', 'tokens.1inch.io', 'coin-images.coingecko.com', 'fc.hunt.town',
               'mint-club-v2.s3.us-west-2.amazonaws.com', 'cdn.dexscreener.com')
DEX_CHAINS = {1:'ethereum', 8453:'base', 81457:'blast', 4663:'robinhood',
              10:'optimism', 42161:'arbitrum', 56:'bsc', 137:'polygon',
              43114:'avalanche', 130:'unichain', 33139:'apechain'}
LP_CATALOG = 'https://lptoken.fun/api/markets?sort=volume&limit=100'
# Contract-verified CoinGecko artwork fallback, checked 2026-10-05.
KNOWN_TOKEN_ARTWORK = {
    '81457:0xb1a5700fa2358173fe465e6ea4ff52e36e88e2ad':
        'https://coin-images.coingecko.com/coins/images/35494/small/Blast.jpg?1719385662',
    '81457:0x4300000000000000000000000000000000000003':
        'https://coin-images.coingecko.com/coins/images/35595/small/65c67f0ebf2f6a1bd0feb13c_usdb-icon-yellow.png?1709255427',
}


def identity(chain_id, address):
    if not isinstance(chain_id, int) or chain_id <= 0 or not isinstance(address, str): return None
    if not re.fullmatch(r'0x[0-9a-fA-F]{40}', address): return None
    return f'{chain_id}:{address.lower()}'


def safe_image(raw):
    if not isinstance(raw, str): return None
    try:
        u = urlparse(raw)
        if u.scheme == 'https' and u.hostname in IMAGE_HOSTS and not u.username and not u.password and u.port in (None, 443):
            return raw
    except ValueError: pass
    return None


def mint_logo(chain_id, address):
    if not identity(chain_id, address): return None
    return API + '/tokens/logo?' + urlencode({'chainId': chain_id, 'address': address})


def reserve_logo(chain_id, address):
    if not identity(chain_id, address): return None
    return f'https://fc.hunt.town/tokens/logo/{chain_id}/{address.lower()}/image'


def read_catalog(root=ROOT):
    path = root / 'cache/token-images.json'
    return json.loads(path.read_text()) if path.exists() else {'tokens': {}}


def image_for(catalog, chain_id, address=None, *, mint=False, native_symbol=None):
    if native_symbol:
        asset = native_identity(chain_id, native_symbol)
        if not asset: return None
        image = safe_image(catalog.get('native', {}).get(asset, {}).get('image_url'))
        if image: return image
        # Artwork fallback is selected by the native currency, not the L2 logo.
        return chain_image(1 if native_symbol == 'ETH' else chain_id)
    if mint: return mint_logo(chain_id, address)
    row = catalog.get('tokens', {}).get(identity(chain_id, address)) or {}
    image = safe_image(row.get('image_url')) or KNOWN_TOKEN_ARTWORK.get(identity(chain_id,address))
    # Mint Club still returns legacy 1inch URLs that reject requests with HTTP 403.
    # Its Hunt token-image endpoint serves the same reserve contract's logo.
    if image and urlparse(image).hostname == 'tokens.1inch.io':
        return reserve_logo(chain_id, address)
    return image


def fetch_metadata(url):
    try:
        request = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 KiraWallet/0.1', 'Accept':'application/json'})
        with urllib.request.urlopen(request, timeout=15) as response: return json.load(response)
    except (OSError, ValueError): return None


def refresh_catalog(snapshots, root=ROOT, *, force=False, fetch=fetch_metadata, native_images=None):
    """Share images by chain/address. Reuse successful metadata for 24 hours."""
    catalog = read_catalog(root)
    now = datetime.now(timezone.utc)
    observed = now.isoformat()
    def fresh(raw):
        try: return 0 <= (now - datetime.fromisoformat(raw)).total_seconds() < 86400
        except (ValueError, TypeError): return False
    records = catalog.setdefault('tokens', {})
    artwork_checked=catalog.setdefault('artwork_checked',{})
    wanted = {identity(t.get('chain_id'),t.get('token_address')):t
              for snapshot in snapshots for t in snapshot.get('tokens',[])
              if not t.get('mintclub') and identity(t.get('chain_id'),t.get('token_address'))}
    for asset,row in (native_images or {}).items():
        image = safe_image(row.get('image_url'))
        if image and asset in {value[1] for value in NATIVE_ASSETS.values()}:
            catalog.setdefault('native', {})[asset] = {**row, 'image_url': image}
    errors = 0
    # lpTOKEN uses chain-specific imageUrl metadata, often from DEX Screener.
    # Read public catalog metadata without sending a wallet address.
    missing = {key:t for key,t in wanted.items()
               if force or not fresh(artwork_checked.get(key) or records.get(key,{}).get('observed_at'))}
    if any(t['chain_id'] in (4663,8453,1) for t in missing.values()):
        response = fetch(LP_CATALOG)
        if isinstance(response,dict) and isinstance(response.get('items'),list):
            for market in response['items'][:100]:
                if not isinstance(market,dict):continue
                token=market.get('token') or {};chain=market.get('chain') or {}
                if not isinstance(token,dict) or not isinstance(chain,dict):continue
                key=identity(chain.get('id'),token.get('address'));image=safe_image(token.get('imageUrl'))
                if key in missing and image:
                    records[key]={'image_url':image,'source':LP_CATALOG,'observed_at':observed}
                    artwork_checked[key]=observed
                    missing.pop(key)
        else:errors+=1
    batches=[]
    for chain_id,slug in DEX_CHAINS.items():
        addresses=[t['token_address'].lower() for t in missing.values() if t['chain_id']==chain_id]
        for offset in range(0,len(addresses),30):
            batch=addresses[offset:offset+30]
            batches.append((chain_id,slug,set(batch),'https://api.dexscreener.com/tokens/v1/'+slug+'/'+','.join(batch)))
    def dex_get(batch):return batch,fetch(batch[3])
    with ThreadPoolExecutor(max_workers=4) as pool:
        for (chain_id,slug,addresses,source),response in pool.map(dex_get,batches):
            if not isinstance(response,list):errors+=1;continue
            for address in addresses:artwork_checked[identity(chain_id,address)]=observed
            for pair in response[:1000]:
                if not isinstance(pair,dict) or pair.get('chainId')!=slug:continue
                token=pair.get('baseToken') or {};info=pair.get('info') or {}
                if not isinstance(token,dict) or not isinstance(info,dict):continue
                address=token.get('address');key=identity(chain_id,address)
                image=safe_image(info.get('imageUrl'))
                if key and isinstance(address,str) and address.lower() in addresses and image:
                    records[key]={'image_url':image,'source':source,'observed_at':observed}
    def add(token, source):
        if not isinstance(token, dict): return
        key = identity(token.get('chainId'), token.get('tokenAddress'))
        image = safe_image(token.get('logo')) or reserve_logo(token.get('chainId'), token.get('tokenAddress'))
        if key and image:
            records[key] = {'image_url': image, 'source': source, 'observed_at': observed}
    if force or not fresh(catalog.get('reserve_catalog_at')):
        success = True
        for endpoint in ['/reserve-tokens/list', '/reserve-tokens/stats', '/reserve-tokens/popular']:
            source = API + endpoint
            response = fetch(source)
            if isinstance(response, list): tokens = response
            elif isinstance(response, dict) and isinstance(response.get('tokens'), list):
                tokens = [t.get('reserveToken', t) for t in response['tokens']]
            else: success = False; errors += 1; continue
            for token in tokens: add(token, source)
        if success: catalog['reserve_catalog_at'] = observed
    candidates = {identity(t['chain_id'], t['token_address']): t
                  for snapshot in snapshots for t in snapshot.get('tokens', []) if t.get('mintclub')}
    checked = catalog.setdefault('mint_details', {})
    candidates = [t for key, t in candidates.items() if key and (force or not fresh(checked.get(key)))]
    def get(t):
        source = f"{API}/tokens/details/{t['chain_id']}/{t['token_address']}"
        return t, source, fetch(source)
    with ThreadPoolExecutor(max_workers=4) as pool:
        for token, source, detail in pool.map(get, candidates):
            key = identity(token['chain_id'], token['token_address'])
            # Reject a response for a different chain or token.
            if not isinstance(detail, dict) or identity(detail.get('chainId'), detail.get('tokenAddress')) != key:
                errors += 1; continue
            add(detail.get('reserveToken'), source)
            checked[key] = observed
    catalog['observed_at'] = observed
    path = root / 'cache/token-images.json'
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.json.tmp')
    temporary.write_text(json.dumps(catalog, ensure_ascii=False, indent=2) + '\n')
    os.replace(temporary, path)
    return {'reserve_images': len(records), 'mint_details_checked': len(candidates), 'provider_errors': errors}


if __name__ == '__main__':
    import argparse
    import fcntl
    parser = argparse.ArgumentParser(description='Refresh Mint Club token image metadata for the viewer.')
    parser.add_argument('--wallet', help='Registered address or exact tag. Omit for all wallets.')
    parser.add_argument('--force', action='store_true', help='Refresh metadata even when less than 24 hours old.')
    args = parser.parse_args()
    analysis_lock = (ROOT / '.analysis.lock').open('a')
    try: fcntl.flock(analysis_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError: raise SystemExit('Another wallet analysis is running. Retry after it finishes.')
    from model import within
    registry = json.loads((ROOT / 'wallets.json').read_text())
    wallets = [w for w in registry['wallets'] if w.get('latest_snapshot') and
               (not args.wallet or args.wallet.lower() == w['address_key'] or args.wallet in w['tags'])]
    if not wallets: raise SystemExit('No analysed registered wallet matches this selection.')
    snapshots = [json.loads(within(ROOT, w['latest_snapshot']['result']).read_text()) for w in wallets]
    print(json.dumps(refresh_catalog(snapshots, force=args.force)))
