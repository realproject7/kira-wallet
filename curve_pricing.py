"""Resolve spot prices through external Mint Club reserve curves."""
from concurrent.futures import ThreadPoolExecutor
import json
import math
from pathlib import Path
import sys
import research as h


def index_prices(identities, folder, deadline=None):
    """Read bounded Alchemy batches by exact chain/contract, retaining source time."""
    from wallet import ALCHEMY, atomic, fetch
    sys.path.insert(0,str(h.ASSETS/'viewer'))
    from model import dex_price
    import hashlib
    import re
    wanted=sorted({(cid,address.lower()) for cid,address in identities
                   if cid in ALCHEMY and isinstance(address,str) and re.fullmatch(r'0x[0-9a-fA-F]{40}',address)})
    key=h.secrets().get('ALCHEMY_CUSTOM_APY_KEY') if wanted else None
    prices={}
    for start in range(0,len(wanted) if key else 0,25):
        batch=wanted[start:start+25]
        requests=[{'network':ALCHEMY[cid],'address':address} for cid,address in batch]
        file=Path(folder)/('reserve-price-cache-'+hashlib.sha256(json.dumps(requests,sort_keys=True).encode()).hexdigest()+'.json')
        record=json.loads(file.read_text()) if file.exists() else None
        if record is None:
            response=fetch('https://api.g.alchemy.com/prices/v1/'+key+'/tokens/by-address',{'addresses':requests},deadline=deadline)
            record={'observed_at':h.now(),'source':'Alchemy token prices by address','request':requests,'response':response}
            if isinstance(response,dict) and isinstance(response.get('data'),list):atomic(file,record)
        response=record.get('response')
        expected={(ALCHEMY[cid],address):(cid,address) for cid,address in batch}
        for row in response.get('data',[]) if isinstance(response,dict) and isinstance(response.get('data'),list) else []:
            if not isinstance(row,dict) or row.get('error') or not isinstance(row.get('network'),str) or not isinstance(row.get('address'),str):continue
            identity=expected.get((row['network'],row['address'].lower()))
            if identity is None or not isinstance(row.get('prices'),list):continue
            price=dex_price({'token_address':identity[1],'indexer_price_references':[p for p in row['prices'] if isinstance(p,dict)]},None)
            if price:prices[identity]={'chain_id':identity[0],'address':identity[1],**price}
    return {'tokens':list(prices.values()),'status':'partial' if len(prices)<len(wanted) else 'checked'}


def resolve(graph, prices):
    nodes={(r['chain_id'],r['address'].lower()):r for r in graph if r.get('address')}
    known={(r['chain_id'],r['address'].lower()):r for r in prices}
    cache={}
    def rejected_reserve(key,seen):
        if key in seen:return False
        node=nodes.get(key);price=known.get(key)
        if not node or not node.get('is_curve'):return bool(price and price.get('quality') in ('unfunded','unreliable'))
        if price and price.get('usd') is not None and price.get('basis')!='Curve spot' and price.get('quality') not in ('unfunded','unreliable'):return False
        if not node.get('error') and node.get('funded') is False:return True
        return rejected_reserve((key[0],node['reserve_token'].lower()),seen|{key})
    def visit(key,seen):
        if key in cache:return cache[key]
        if key in seen:return None
        existing=known.get(key)
        node=nodes.get(key)
        if existing and existing.get('quality') in ('unfunded','unreliable') and not (node and node.get('is_curve')):
            cache[key]={**existing,'usd':None};return cache[key]
        unfunded=node and not node.get('error') and node.get('is_curve') and node.get('funded') is False
        if existing and existing.get('usd') is not None and existing.get('quality') not in ('unfunded','unreliable') and (existing.get('basis')!='Curve spot' or not unfunded and not rejected_reserve(key,set())):
            cache[key]=existing;return existing
        if not node or node.get('error') or not node.get('is_curve'):return None
        if not node['funded']:
            record={'chain_id':key[0],'address':node['address'],'usd':None,'basis':'Curve spot','quality':'unfunded',
                    'curve_reserve':node.get('curve_reserve'),'source':node.get('source'),
                    'observed_at':node.get('observed_at'),'block_number':node.get('block_number')}
            cache[key]=record;return record
        parent=visit((key[0],node['reserve_token'].lower()),seen|{key})
        if parent and parent.get('quality') in ('unfunded','unreliable'):
            record={'chain_id':key[0],'address':node['address'],'usd':None,'basis':'Curve spot','quality':parent['quality'],
                    'source':node.get('source'),'observed_at':node.get('observed_at'),'block_number':node.get('block_number')}
            cache[key]=record;return record
        if not parent or parent.get('usd') is None:return None
        usd=float(node['price_in_reserve'])*parent['usd']
        if not math.isfinite(usd) or usd<0:return None
        record={'chain_id':key[0],'address':node['address'],'usd':usd,'basis':'Curve spot','quality':'estimated',
                'source':node['source'],'observed_at':node['observed_at'],'block_number':node['block_number'],
                'curve_price_in_reserve':node['price_in_reserve'],'curve_reserve':node['curve_reserve'],'reserve_symbol':node['reserve_symbol'],
                'price_path':[node['address']]+parent.get('price_path',[node['reserve_token']])}
        if parent.get('retained_from_previous'):
            record.update(retained_from_previous=True,latest_price_status='unavailable',observed_at=parent.get('observed_at'))
        cache[key]=record
        return record
    for key in nodes:visit(key,set())
    return list(cache.values())


def enrich(snapshot,market,folder,deadline=None):
    import time
    from wallet import ALCHEMY, DEX, atomic, fetch, pool_row, run_node, MarketPause
    sys.path.insert(0,str(h.ASSETS/'viewer'))
    from model import dex_price
    networks=json.loads((h.ASSETS/'sources/rpc-candidates.json').read_text())
    input_path=folder/'reserve-graph-input.json'
    atomic(input_path,{'wallet':snapshot['wallet_address'],'tokens':snapshot['tokens'],'networks':networks,
        # Leave time for Node startup and the final atomic graph publication
        # before the parent's hard stop. Completed checkpoints remain useful.
        'market_budget_ms':max(0,int((deadline-time.monotonic()-1)*1000)) if deadline is not None else 180_000})
    run_node('reserves',input_path,folder/'reserve-graph.json',deadline=deadline)
    recorded=json.loads((folder/'reserve-graph.json').read_text());graph=recorded['tokens']
    if recorded.get('market_pending'):raise MarketPause('Reserve checks reached the market time budget. Resume saved checks in Activity.')
    ordinary=[r for r in graph if r.get('address') and r.get('is_curve') is False and r['chain_id'] in ALCHEMY]
    prices=list(market.get('tokens',[]))
    settled={(p['chain_id'],p['address'].lower()) for p in prices
             if p.get('usd') is not None or p.get('quality') in ('unfunded','unreliable')}
    ordinary=[r for r in ordinary if (r['chain_id'],r['address'].lower()) not in settled]
    indexed=index_prices([(r['chain_id'],r['address']) for r in ordinary],folder,deadline)
    prices.extend(indexed['tokens'])
    def get(row):
        chain=DEX.get(row['chain_id'])
        if not chain:return None
        url='https://api.dexscreener.com/token-pairs/v1/'+chain+'/'+row['address']
        from wallet import dex_fetch
        recorded=dex_fetch({'chain_id':row['chain_id'],'token_address':row['address'],'token_type':'ERC20'},folder,deadline)
        return {'row':row,'source':url,'observed_at':recorded.get('observed_at'),'response':recorded['response']}
    keys={(p['chain_id'],p['address'].lower()) for p in prices if p.get('usd') is not None}
    missing=[r for r in ordinary if (r['chain_id'],r['address'].lower()) not in keys]
    with ThreadPoolExecutor(max_workers=4) as executor:fetched=list(executor.map(get,missing))
    if deadline is not None and time.monotonic()>=deadline:raise MarketPause('Reserve pricing reached the market time budget. Resume saved checks in Activity.')
    atomic(folder/'reserve-dex-prices.json',fetched)
    for r in fetched:
        if not r or not isinstance(r['response'],list):continue
        row=r['row'];shadow={'token_address':row['address'],'dex_pools':[pool_row(p,r['observed_at']) for p in r['response']],'indexer_price_references':[]}
        p=dex_price(shadow,r['observed_at'])
        if p and p.get('usd') is not None:prices.append({'chain_id':row['chain_id'],'address':row['address'],**p})
    # Keep a supported DEX price for held tokens. Add external curve references for their children.
    resolved=resolve(graph,prices)
    by_key={(p['chain_id'],p['address'].lower()):p for p in prices}
    for p in resolved:by_key[(p['chain_id'],p['address'].lower())]=p
    market['tokens']=list(by_key.values())
    market['reserve_price_graph']={'source_file':'reserve-graph.json','observed_at':h.now(),'curve_count':sum(r.get('is_curve') is True for r in graph),'errors':sum(bool(r.get('error')) for r in graph)}
    return market
