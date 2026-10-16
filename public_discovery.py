"""Bounded keyless token candidates. Balances must be verified separately on RPC."""
import json
import hashlib
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


def _fetch_body(url, timeout, output, body, extra_headers=None, envelope=False):
    # An isolated reader can be stopped even during DNS or a trickling body.
    request=urllib.request.Request(url,data=json.dumps(body).encode() if body is not None else None,headers={'User-Agent':'KiraWallet (+https://kirawallet.app)','Accept':'application/json, text/event-stream','Content-Type':'application/json',**(extra_headers or {})})
    try:
        with urllib.request.urlopen(request,timeout=timeout) as response:
            body=response.read(2_000_001 if envelope else 4_000_001)
            if envelope:
                if len(body)>2_000_000:raise ValueError('Response limit')
                body=json.dumps({'http_status':response.status,'session':response.headers.get('Mcp-Session-Id'), 'body':body.decode('utf-8')}).encode()
        if len(body)>4_000_000:body=b'{"error":{"code":"response_limit"}}'
        output.send_bytes(body)
    except urllib.error.HTTPError as error:
        retry=error.headers.get('Retry-After','')
        output.send_bytes(json.dumps({'error':{'code':'http_error','http_status':error.code,
            'retry_after':min(3600,int(retry)) if retry.isdigit() else None}}).encode())
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


def fetch_bounded(url, timeout, body=None, *, headers=None, envelope=False):
    """An isolated, size-limited reader with a total body deadline, no pacing."""
    end=time.monotonic()+timeout
    if timeout<=0:return {'error':{'code':'deadline'}}
    ctx=multiprocessing.get_context('spawn')
    incoming,outgoing=ctx.Pipe(duplex=False)
    reader=ctx.Process(target=_fetch_body,args=(url,timeout,outgoing,body,headers,envelope),daemon=True)
    try:
        reader.start();outgoing.close()
        if not incoming.poll(max(0,end-time.monotonic())):return {'error':{'code':'deadline'}}
        body=incoming.recv_bytes(4_000_000)
        if time.monotonic()>end:return {'error':{'code':'deadline'}}
        try:return json.loads(body)
        except ValueError:
            # Streamable MCP responses contain complete SSE data events. Never
            # execute provider instructions or follow a provider-supplied URL.
            events=[line[5:].strip() for line in body.decode('utf-8').splitlines() if line.startswith('data:')]
            if len(events)!=1:raise ValueError('Invalid event response')
            return json.loads(events[0])
    except (OSError,ValueError,EOFError):return {'error':{'code':'provider_unavailable'}}
    finally:
        if reader.pid:
            if reader.is_alive():reader.terminate()
            reader.join(timeout=.5)
            if reader.is_alive():reader.kill();reader.join(timeout=.5)
        incoming.close();outgoing.close()


def valid_state(state, address, chain_id, provider='routescan'):
    return (isinstance(state, dict) and state.get('schema_version') == 1
            and state.get('provider') == provider and state.get('wallet') == address.lower()
            and type(state.get('chain_id')) is int and state['chain_id'] == chain_id
            and type(state.get('complete')) is bool
            and type(state.get('page')) is int and state['page'] >= 1
            and type(state.get('started_at')) is int and state['started_at'] >= 0
            and ('retry_not_before' not in state or type(state['retry_not_before']) is int and state['retry_not_before'] >= 0)
            and 'cursor' in state and (state['cursor'] is None or isinstance(state['cursor'], str) and 0 < len(state['cursor']) <= 4096)
            and (state['complete'] or (state['page'] == 1) == (state['cursor'] is None))
            and isinstance(state.get('seen_cursors'), list)
            and all(isinstance(value, str) and re.fullmatch(r'[0-9a-f]{64}', value) for value in state['seen_cursors'])
            and isinstance(state.get('tokens'), list)
            and all(isinstance(token, dict) and token.get('chain_id') == chain_id
                    and isinstance(token.get('address'), str) and re.fullmatch(r'0x[0-9a-fA-F]{40}', token['address'])
                    for token in state['tokens']))


def discover(address, chain_id, *, fetch=fetch_page, budget=25, max_pages=20, state=None, save=lambda value: None, continue_only=False):
    if chain_id not in CHAINS:
        return {'chain_id':chain_id,'source':DOCS,'provider':'routescan','tokens':[],'native':[],
                'pages':[],'complete':False,'discovery_status':'unsupported','error':None}
    base=f'https://api.routescan.io/v2/network/mainnet/evm/{chain_id}/address/{address}/erc20-holdings'
    def page_url(cursor):
        return base+'?'+urlencode({'limit':100,**({'next':cursor} if cursor else {})})
    return discover_pages(address,chain_id,provider='routescan',source=DOCS,page_url=page_url,
        fetch=fetch,budget=budget,max_pages=max_pages,state=state,save=save,continue_only=continue_only)


def discover_pages(address, chain_id, *, provider, source, page_url, fetch=fetch_page,
                   budget=25, max_pages=20, state=None, save=lambda value:None, continue_only=False):
    """Shared durable pagination over normalized, provider-labelled holdings pages."""
    row = {'chain_id': chain_id, 'source': source, 'provider': provider,
           'tokens': [], 'native': [], 'pages': [], 'complete': False,
           'discovery_status': 'unsupported', 'error': None,
           'complete_inventory_guaranteed': False, 'completion_scope': 'Provider-reported holdings pages only.'}
    if not isinstance(address, str) or not re.fullmatch(r'0x[0-9a-fA-F]{40}', address):
        raise ValueError('Invalid wallet.')
    if state is not None and not valid_state(state, address, chain_id, provider):
        row.update(discovery_status='checkpoint_error', error={'message': 'Discovery checkpoint does not match this wallet or source. Saved evidence was preserved.'})
        return row
    current = json.loads(json.dumps(state)) if state is not None else None
    if current and current['complete'] and continue_only:
        row.update(tokens=current['tokens'],complete=True,discovery_status='checked',
                   pagination={'pages_checked':current['page']-1,'cursor_pending':False,'complete':True,'started_at':current['started_at']})
        return row
    if current is None or current['complete']:
        current = {'schema_version': 1, 'provider': provider, 'wallet': address.lower(), 'chain_id': chain_id,
                   'cursor': None, 'page': 1, 'tokens': current['tokens'] if current else [],
                   'seen_cursors': [], 'complete': False, 'started_at': int(time.time())}
        save(current)
    end = time.monotonic() + budget
    seen = set(current['seen_cursors']); cursor = current['cursor']
    candidates = {token['address'].lower(): token for token in current['tokens']}
    row['discovery_status'] = 'provider_error'
    if current.get('retry_not_before', 0) > time.time():
        row.update(tokens=list(candidates.values()), discovery_status='throttled', retry_not_before=current['retry_not_before'],
                   error={'message': 'Free discovery is waiting for the provider retry interval.'})
        return row
    for page in range(max_pages):
        remaining = end - time.monotonic()
        if remaining <= 0:
            row['discovery_status'] = 'history_pending'
            row['error'] = {'message': 'Free discovery time budget reached. Saved candidates remain usable.'}; break
        data = fetch(page_url(cursor), min(8, remaining))
        row['pages'].append({'page': current['page']})
        if not isinstance(data, dict) or not isinstance(data.get('items'), list) or not isinstance(data.get('link'), dict):
            error = data.get('error', {}) if isinstance(data, dict) else {}
            if isinstance(error, dict) and error.get('http_status') == 429:
                retry = error.get('retry_after')
                current['retry_not_before'] = int(time.time()) + max(60, min(3600, retry) if type(retry) is int else 60)
                row.update(discovery_status='throttled', retry_not_before=current['retry_not_before'])
                save(current)
            row['error'] = {'message': 'Free token discovery is unavailable or returned invalid data.'}; break
        invalid = False
        for token in data['items']:
            if not isinstance(token, dict): invalid = True; continue
            contract = token.get('tokenAddress'); quantity = token.get('tokenQuantity'); cid = token.get('chainId')
            if not isinstance(contract, str) or not re.fullmatch(r'0x[0-9a-fA-F]{40}', contract) or str(cid) != str(chain_id) or not isinstance(quantity, str) or not re.fullmatch(r'\d{1,100}', quantity):
                invalid = True; continue
            if int(quantity) == 0: continue
            decimals = token.get('tokenDecimals')
            candidates[contract.lower()] = {'chain_id': chain_id, 'address': contract,
                'name': token['tokenName'][:256] if isinstance(token.get('tokenName'), str) else None,
                'symbol': token['tokenSymbol'][:64] if isinstance(token.get('tokenSymbol'), str) else None,
                'decimals': decimals if type(decimals) is int and 0 <= decimals <= 255 else None, 'prices': [],'suspicious_zero_check':True}
        current['tokens'] = list(candidates.values())
        save(current)
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
                current.update(complete=True, cursor=None, page=current['page'] + 1)
                save(current)
            break
        digest = hashlib.sha256(next_cursor.encode()).hexdigest()
        if digest in seen:
            row['error'] = {'message': 'Free discovery pagination was invalid.'}; break
        seen.add(digest); cursor = next_cursor
        current.update(cursor=cursor, seen_cursors=sorted(seen), page=current['page'] + 1)
        current.pop('retry_not_before', None)
        save(current)
    else:
        row['discovery_status'] = 'history_pending'
        row['error'] = {'message': 'Free discovery page limit reached. Holdings may be missing.'}
    row['tokens'] = list(candidates.values())
    row['pagination'] = {'pages_checked': current['page'] - 1, 'cursor_pending': current['cursor'] is not None,
                         'complete': current['complete'], 'started_at': current['started_at']}
    return row
