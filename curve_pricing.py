"""Resolve spot prices through external Mint Club reserve curves."""
from concurrent.futures import ThreadPoolExecutor
import json
import math
from pathlib import Path
import subprocess
import sys
import research as h


def resolve(graph, prices):
    nodes={(r['chain_id'],r['address'].lower()):r for r in graph if r.get('address')}
    known={(r['chain_id'],r['address'].lower()):r for r in prices}
    cache={}
    def visit(key,seen):
        if key in cache:return cache[key]
        if key in seen:return None
        existing=known.get(key)
        node=nodes.get(key)
        unfunded=node and not node.get('error') and node.get('is_curve') and node.get('funded') is False
        if existing and existing.get('usd') is not None and existing.get('quality') not in ('unfunded','unreliable') and (existing.get('basis')!='Curve spot' or not unfunded):
            cache[key]=existing;return existing
        if not node or node.get('error') or not node.get('is_curve'):return None
        if not node['funded']:
            record={'chain_id':key[0],'address':node['address'],'usd':None,'basis':'Curve spot','quality':'unfunded',
                    'curve_reserve':node.get('curve_reserve'),'source':node.get('source'),
                    'observed_at':node.get('observed_at'),'block_number':node.get('block_number')}
            cache[key]=record;return record
        parent=visit((key[0],node['reserve_token'].lower()),seen|{key})
        if not parent or parent.get('usd') is None:return None
        usd=float(node['price_in_reserve'])*parent['usd']
        if not math.isfinite(usd) or usd<0:return None
        record={'chain_id':key[0],'address':node['address'],'usd':usd,'basis':'Curve spot','quality':'estimated',
                'source':node['source'],'observed_at':node['observed_at'],'block_number':node['block_number'],
                'curve_price_in_reserve':node['price_in_reserve'],'curve_reserve':node['curve_reserve'],'reserve_symbol':node['reserve_symbol'],
                'price_path':[node['address']]+parent.get('price_path',[node['reserve_token']])}
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
        'market_budget_ms':max(0,int((deadline-time.monotonic())*1000)) if deadline is not None else 180_000})
    run_node('reserves',input_path,folder/'reserve-graph.json',deadline=deadline)
    recorded=json.loads((folder/'reserve-graph.json').read_text());graph=recorded['tokens']
    if recorded.get('market_pending'):raise MarketPause('Reserve checks reached the market time budget. Resume saved checks in Activity.')
    ordinary=[r for r in graph if r.get('address') and r.get('is_curve') is False and r['chain_id'] in ALCHEMY]
    prices=list(market.get('tokens',[]))
    # Only reserve assets are requested. Identify prices by network and contract, never symbol.
    requests=[{'network':ALCHEMY[r['chain_id']],'address':r['address']} for r in ordinary]
    inverse={value:key for key,value in ALCHEMY.items()}
    responses=[]
    key=h.secrets().get('ALCHEMY_CUSTOM_APY_KEY')
    for i in range(0,len(requests) if key else 0,25):
        import hashlib
        batch=requests[i:i+25];identity=hashlib.sha256(json.dumps(batch,sort_keys=True).encode()).hexdigest()
        file=folder/('reserve-price-cache-'+identity+'.json')
        record=json.loads(file.read_text()) if file.exists() else None
        if not record:
            response=fetch('https://api.g.alchemy.com/prices/v1/'+h.secrets()['ALCHEMY_CUSTOM_APY_KEY']+'/tokens/by-address',{'addresses':batch},deadline=deadline)
            record={'observed_at':h.now(),'source':'Alchemy token prices by address','request':batch,'response':response}
            if isinstance(response,dict) and isinstance(response.get('data'),list):atomic(file,record)
        response=record['response'];responses.append(record)
        for record in response.get('data') or []:
            p=next((p for p in record.get('prices',[]) if p.get('currency')=='usd' and p.get('value') is not None),None)
            if p and not record.get('error'):
                value=float(p['value'])
                if math.isfinite(value) and value>0:
                    prices.append({'chain_id':inverse[record['network']],'address':record['address'],'usd':value,'basis':'Market index','quality':'estimated',
                                   'observed_at':p.get('lastUpdatedAt'),'source':'https://www.alchemy.com/docs/data/prices-api/prices-api-endpoints/prices-api-endpoints/get-token-prices-by-address'})
    atomic(folder/'reserve-market-prices.json',responses)
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
