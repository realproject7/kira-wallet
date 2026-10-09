"""Bounded keyless token candidates. Balances must be verified separately on RPC."""
import json
import multiprocessing
import re
import threading
import time
import urllib.error
import urllib.request
from urllib.parse import urlencode

# Individually verified keyless routes. Never use the paid multichain `all` route.
CHAINS = {1, 43114, 81457}
DOCS = 'https://routescan.io/docs/api/addresses'
_permit = threading.Lock()
_last = 0.0


def _fetch_body(url, timeout, output, body):
    # An isolated reader can be stopped even during DNS or a trickling body.
    request=urllib.request.Request(url,data=json.dumps(body).encode() if body is not None else None,headers={'User-Agent':'KiraWallet (+https://kirawallet.app)','Accept':'application/json','Content-Type':'application/json'})
    try:
        with urllib.request.urlopen(request,timeout=timeout) as response:
            body=response.read(4_000_001)
        if len(body)>4_000_000:body=b'{"error":{"code":"response_limit"}}'
        output.send_bytes(body)
    except (OSError,ValueError):
        output.send_bytes(b'{"error":{"code":"provider_unavailable"}}')
    finally:output.close()


def fetch_page(url, timeout, body=None):
    global _last
    end=time.monotonic()+timeout
    if not _permit.acquire(timeout=max(0,timeout)):return {'error':{'code':'deadline'}}
    try:
        wait=max(0,_last+1-time.monotonic())
        if wait>=end-time.monotonic():return {'error':{'code':'deadline'}}
        if wait:time.sleep(wait)
        _last=time.monotonic()
    finally:_permit.release()
    remaining=end-time.monotonic()
    if remaining<=0:return {'error':{'code':'deadline'}}
    return fetch_bounded(url,remaining,body)


def fetch_bounded(url, timeout, body=None):
    """An isolated, size-limited reader with a total body deadline, no pacing."""
    end=time.monotonic()+timeout
    if timeout<=0:return {'error':{'code':'deadline'}}
    ctx=multiprocessing.get_context('spawn')
    incoming,outgoing=ctx.Pipe(duplex=False)
    reader=ctx.Process(target=_fetch_body,args=(url,timeout,outgoing,body),daemon=True)
    try:
        reader.start();outgoing.close()
        if not incoming.poll(max(0,end-time.monotonic())):return {'error':{'code':'deadline'}}
        body=incoming.recv_bytes(4_000_000)
        if time.monotonic()>end:return {'error':{'code':'deadline'}}
        return json.loads(body)
    except (OSError,ValueError,EOFError):return {'error':{'code':'provider_unavailable'}}
    finally:
        if reader.pid:
            if reader.is_alive():reader.terminate()
            reader.join(timeout=.5)
            if reader.is_alive():reader.kill();reader.join(timeout=.5)
        incoming.close();outgoing.close()


def discover(address, chain_id, *, fetch=fetch_page, budget=25, max_pages=20):
    row = {'chain_id': chain_id, 'source': DOCS, 'provider': 'routescan',
           'tokens': [], 'native': [], 'pages': [], 'complete': False,
           'discovery_status': 'unsupported', 'error': None}
    if chain_id not in CHAINS: return row
    end = time.monotonic() + budget
    base = f'https://api.routescan.io/v2/network/mainnet/evm/{chain_id}/address/{address}/erc20-holdings'
    seen = set(); cursor = None
    row['discovery_status'] = 'provider_error'
    for page in range(max_pages):
        remaining = end - time.monotonic()
        if remaining <= 0:
            row['error'] = {'message': 'Free discovery time budget reached. Saved candidates remain usable.'}; break
        query = {'limit': 100}
        if cursor: query['next'] = cursor
        data = fetch(base + '?' + urlencode(query), min(8, remaining))
        row['pages'].append({'page': page + 1})
        if not isinstance(data, dict) or not isinstance(data.get('items'), list) or not isinstance(data.get('link'), dict):
            row['error'] = {'message': 'Free token discovery is unavailable or returned invalid data.'}; break
        invalid = False
        for token in data['items']:
            if not isinstance(token, dict): invalid = True; continue
            contract = token.get('tokenAddress'); quantity = token.get('tokenQuantity'); cid = token.get('chainId')
            if not isinstance(contract, str) or not re.fullmatch(r'0x[0-9a-fA-F]{40}', contract) or str(cid) != str(chain_id) or not isinstance(quantity, str) or not re.fullmatch(r'\d{1,100}', quantity):
                invalid = True; continue
            if int(quantity) == 0: continue
            decimals = token.get('tokenDecimals')
            row['tokens'].append({'chain_id': chain_id, 'address': contract,
                'name': token.get('tokenName') if isinstance(token.get('tokenName'), str) else None,
                'symbol': token.get('tokenSymbol') if isinstance(token.get('tokenSymbol'), str) else None,
                'decimals': decimals if type(decimals) is int and 0 <= decimals <= 255 else None, 'prices': []})
        if invalid:
            row['error'] = {'message': 'Free discovery contained invalid token identities or balances.'}; break
        link = data['link']; next_cursor = link.get('nextToken')
        if next_cursor is not None and (not isinstance(next_cursor,str) or not next_cursor or len(next_cursor)>4096):
            row['error'] = {'message': 'Free discovery pagination was invalid.'}; break
        if 'next' in link and link['next'] is not None and not isinstance(link['next'],str):
            row['error'] = {'message': 'Free discovery pagination was invalid.'}; break
        if next_cursor is None:
            if link.get('next'):
                row['error'] = {'message': 'Free discovery pagination was incomplete.'}
            else:
                row['complete'] = True; row['discovery_status'] = 'checked'
            break
        if not isinstance(next_cursor, str) or len(next_cursor) > 4096 or next_cursor in seen:
            row['error'] = {'message': 'Free discovery pagination was invalid.'}; break
        seen.add(next_cursor); cursor = next_cursor
    else:
        row['error'] = {'message': 'Free discovery page limit reached. Holdings may be missing.'}
    row['tokens'] = list({t['address'].lower(): t for t in row['tokens']}.values())
    return row
