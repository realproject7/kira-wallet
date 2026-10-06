"""Read-only projection of wallet research snapshots into viewer data."""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
from pathlib import Path
import hashlib
import json
import math
import os
import re
from token_images import image_for, read_catalog
from chain_images import chain_image
from native_assets import native_identity
from details import project_details

ROOT = Path(os.environ.get('KIRA_DATA_DIR',Path(__file__).resolve().parents[1])).expanduser().resolve()
EXPLORERS = {1:'https://etherscan.io',8453:'https://basescan.org',81457:'https://blastscan.io',
    10:'https://optimistic.etherscan.io',42161:'https://arbiscan.io',43114:'https://snowtrace.io',
    137:'https://polygonscan.com',56:'https://bscscan.com',109:'https://shibariumscan.io',
    7560:'https://cyberscan.co',8217:'https://kaiascan.io',130:'https://uniscan.xyz',
    7777777:'https://explorer.zora.energy',33139:'https://apescan.io',177:'https://hashkey.blockscout.com',
    4663:'https://robinhoodchain.blockscout.com',11155111:'https://sepolia.etherscan.io',
    84532:'https://sepolia.basescan.org',168587773:'https://sepolia.blastscan.io',
    157:'https://puppyscan.shib.io',43113:'https://testnet.snowtrace.io'}

def read(path): return json.loads(path.read_text())
def number(value):
    try:
        n = float(Decimal(str(value)))
        return n if math.isfinite(n) and n >= 0 else None
    except (InvalidOperation, TypeError, ValueError, OverflowError): return None

def within(root, relative):
    path = (root / relative).resolve()
    if not path.is_relative_to(root.resolve()): raise ValueError('Snapshot path outside research directory')
    return path

def pool_has_liquidity(p):
    return (p.get('reported_liquidity') or {}).get('usd',0)>0 or (p.get('factory_measurement') or {}).get('active_liquidity_verified',False)

def exit_quote(token):
    """Project a saved full-balance burn quote, never a spot-price cash estimate."""
    mint = token.get('mintclub') or {}
    quote = mint.get('wallet_full_burn') or {}
    block = str(mint.get('block_number'))
    reserve = mint.get('reserve_token')
    if (not quote or mint.get('wallet_full_burn_error') or
            quote.get('gas_included') is not False or
            not isinstance(reserve, str) or len(reserve) != 42 or
            not reserve.startswith('0x') or
            not all(c in '0123456789abcdefABCDEF' for c in reserve[2:]) or
            not re.fullmatch(r'[1-9][0-9]{0,29}', block) or
            str(token.get('balance_block_number')) != block or not mint.get('observed_at') or
            not isinstance(mint.get('reserve_symbol'), str)):
        return None
    try:
        amounts = [str(quote['net_refund']), str(mint['reserve_balance']), str(token['wallet_balance'])]
        if any(len(value)>350 or not re.fullmatch(r'[0-9]+(?:\.[0-9]+)?',value) for value in amounts):
            return None
        refund, backing, balance = map(Decimal, amounts)
        if not all(n.is_finite() for n in (refund, backing, balance)) or refund < 0 or refund > backing or balance <= 0:
            return None
    except (KeyError, InvalidOperation, ValueError):
        return None
    return {'kind': 'mintclub_burn', 'input_amount': token['wallet_balance'],
            'output_amount': format(refund, 'f'),
            'output_address': reserve.lower(), 'output_symbol': mint['reserve_symbol'],
            'chain_id': token['chain_id'], 'block_number': block,
            'observed_at': mint['observed_at'], 'royalty_included': True,
            'gas_included': False}

def dex_price(token, observed):
    """Reject an extreme one-sided TVL as a USD price reference. Keep its evidence."""
    candidates=[]; suspect=False
    for p in token.get('dex_pools',[]):
        price=number(p.get('reported_price_usd'))
        pair=p.get('paired_tokens',[])
        if price is None or len(pair)!=2 or pair[0]['address'].lower()!=token['token_address'].lower(): continue
        liq=p.get('reported_liquidity') or {}
        tvl=number(liq.get('usd')); base=number(liq.get('base'))
        # Source-reported TVL can consist almost entirely of the self-priced token.
        # Do not use such a pool as the wallet's market value.
        if tvl and base is not None and base*price/tvl>0.98:
            suspect=True; continue
        if tvl and pool_has_liquidity(p): candidates.append((tvl,price,p))
    if candidates:
        _,price,p=max(candidates,key=lambda v:v[0])
        return {'usd':price,'basis':'DEX market','source':p['source_url'],'observed_at':observed,'quality':'estimated'}
    if suspect:return {'usd':None,'basis':'Thin quote side','quality':'unreliable','observed_at':observed}
    for p in token.get('indexer_price_references',[]):
        price=number(p.get('value'))
        if p.get('currency')=='usd' and price is not None and price>0:
            return {'usd':price,'basis':'Market index','source':'https://www.alchemy.com','observed_at':p.get('lastUpdatedAt'),'quality':'estimated'}
    return None

def project_wallet(entry, snapshot, root=ROOT, images=None):
    images=read_catalog(root) if images is None else images
    latest=entry.get('latest_snapshot') or {}
    snapshot_dir=within(root,latest.get('directory','snapshots'))
    market_path=snapshot_dir/'market-prices.json'
    market=read(market_path) if market_path.exists() else {}
    prices={(p.get('chain_id',8453),p['address'].lower()):p for p in market.get('tokens',[])}
    refs=snapshot.get('price_references',{})
    eth=number(market.get('native_usd',{}).get('ETH',{}).get('usd')) or number(refs.get('ETH_USD',{}).get('value'))
    price_time=market.get('observed_at') or refs.get('ETH_USD',{}).get('observed_at') or snapshot.get('compiled_at')
    tokens=snapshot.get('tokens',[])
    by_address={(t['chain_id'],t['token_address'].lower()):t for t in tokens}
    cache={}
    def price_for(t,seen=None):
        k=(t['chain_id'],t['token_address'].lower())
        if k in cache:return cache[k]
        seen=set(seen or set())
        if k in seen:return None
        seen.add(k)
        override=prices.get(k)
        mint=t.get('mintclub')
        if override and override.get('quality') in ('unfunded','unreliable'):
            cache[k]={**override,'usd':None};return cache[k]
        if override and (override.get('basis')!='Curve spot' or override.get('retained_from_previous')):
            cache[k]=override;return override
        if mint:
            reserve=mint['reserve_symbol'];reserve_price=None
            reserve_identity=(t['chain_id'],mint['reserve_token'].lower())
            if reserve_identity==(8453,'0x4200000000000000000000000000000000000006'):reserve_price=eth
            elif reserve_identity==(8453,'0xcbb7c0000ab88b473b1f5afd9ef808440eed33bf'):reserve_price=number(refs.get('cbBTC_USD',{}).get('value'))
            rt=prices.get((t['chain_id'],mint['reserve_token'].lower()))
            if rt and rt.get('usd') is not None:reserve_price=number(rt['usd'])
            parent=by_address.get((t['chain_id'],mint['reserve_token'].lower()))
            if parent:
                parent_price=price_for(parent,seen)
                if parent_price:reserve_price=parent_price.get('usd')
            if reserve_price is not None:
                spot=number((override or {}).get('curve_price_in_reserve',mint['price_for_next_mint_in_reserve_token']))
                funded=number(override['curve_reserve'])>0 if override and 'curve_reserve' in override else mint.get('funded')
                p={'usd':spot*reserve_price if spot is not None else None,'basis':'Curve spot',
                   'source':mint['source_url'],'observed_at':(override or {}).get('observed_at',mint['observed_at']),
                   'quality':'estimated' if funded else 'unfunded'}
                if not funded:p['usd']=None
                cache[k]=p;return p
        p=dex_price(t,snapshot.get('compiled_at'))
        cache[k]=p;return p

    assets=[]
    for t in tokens:
        p=price_for(t);quantity=number(t['wallet_balance'])
        value=quantity*p['usd'] if p and p.get('usd') is not None and quantity is not None else None
        label=t['symbol'];name=t.get('name') or label
        market_token=prices.get((t['chain_id'],t['token_address'].lower())) or {}
        if 'http' in label.lower() or 'claim' in label.lower():label='Airdrop';name='Unverified token'
        links=[]
        if t.get('mintclub'):links.append({'label':'Mint Club','url':t['mintclub']['source_url']})
        found={}; market_pools=[]
        for pool in t.get('dex_pools',[]):
            if not pool_has_liquidity(pool):continue
            venue=pool['venue'].lower(); label_venue='Uniswap' if 'uniswap' in venue else 'Aerodrome' if 'aerodrome' in venue else venue.replace('-',' ').title()
            weight=(pool.get('reported_liquidity') or {}).get('usd',0)
            measured=pool.get('factory_measurement') or {}
            if not weight and measured.get('quote_balance'):
                weight=(number(measured['quote_balance']) or 0)*(eth or 0) if measured.get('quote_symbol')=='WETH' else number(measured['quote_balance']) or 0
            if label_venue not in found or weight>found[label_venue][0]:found[label_venue]=(weight,pool['source_url'])
            pair=[]
            for coin in pool.get('paired_tokens',[])[:2]:
                if not isinstance(coin,dict):continue
                symbol=coin.get('symbol')
                pair.append({'address':coin.get('address'),'symbol':symbol if isinstance(symbol,str) and symbol else '?',
                             'image_url':image_for(images,t['chain_id'],coin.get('address'))})
            market_pools.append({'venue':label_venue,'pool':pool.get('pool'),'url':pool['source_url'],
                'pair':pair,'liquidity_usd':number((pool.get('reported_liquidity') or {}).get('usd')),
                'price_usd':number(pool.get('reported_price_usd')),'observed_at':pool.get('observed_at') or snapshot.get('compiled_at')})
        market_pools.sort(key=lambda row:-(row['liquidity_usd'] or 0))
        links += [{'label':k,'url':v[1]} for k,v in found.items()]
        explorer=EXPLORERS.get(t['chain_id'])
        if explorer:links.append({'label':'Explorer','url':explorer+'/token/'+t['token_address']})
        assets.append({'id':f'{t["chain_id"]}:{t["token_address"].lower()}','chain_id':t['chain_id'],
            'symbol':label,'name':name,'address':t['token_address'],'balance':t['wallet_balance'],
            'price':p,'value_usd':value,'is_native':False,'links':links,'market_pools':market_pools,
            'balance_observed_at':t.get('balance_observed_at') or snapshot.get('compiled_at'),
            'burn_quote':(t.get('mintclub') or {}).get('wallet_full_burn'),
            'exit_quote':exit_quote(t),
            'exit_route': 'mintclub_burn' if t.get('mintclub') else 'dex_unquoted' if t.get('dex_liquidity_found') or any(pool_has_liquidity(pool) for pool in t.get('dex_pools',[])) else 'unverified',
            'image_url':image_for(images,t['chain_id'],t['token_address'],mint=bool(t.get('mintclub'))),
            'curve_reserve': {'amount':market_token.get('curve_reserve',t['mintclub']['reserve_balance']),'symbol':t['mintclub']['reserve_symbol']} if t.get('mintclub') else None})
    coverage=snapshot.get('coverage',[])
    for c in coverage:
        raw=c.get('native_balance');quantity=number(raw)
        if quantity is None or quantity<=0:continue
        sym=c['native_symbol'];ref=market.get('native_usd',{}).get(sym)
        px=(number(ref.get('usd')) if ref else eth if sym=='ETH' else number(refs.get(sym+'_USD',{}).get('value'))) if native_identity(c['chain_id'],sym) else None
        assets.append({'id':f'{c["chain_id"]}:native','chain_id':c['chain_id'],'symbol':sym,'name':'Ether' if sym=='ETH' else sym,
            'address':None,'balance':raw,'is_native':True,'curve_reserve':None,
            'balance_observed_at':c.get('native_observed_at'),
            'image_url':image_for(images,c['chain_id'],native_symbol=sym),
            'price':{'usd':px,'basis':ref.get('basis','Market index') if ref else 'Market index','quality':'estimated','observed_at':ref.get('observed_at') if ref else price_time,
                     'source':ref.get('source') if ref else refs.get(sym+'_USD',{}).get('source')} if px is not None else None,
            'value_usd':quantity*px if px is not None and c['environment']=='mainnet' else None,
            'links':[{'label':'Explorer','url':EXPLORERS[c['chain_id']]+'/address/'+entry['address']}] if c['chain_id'] in EXPLORERS else []})
    chains=[]
    for c in coverage:
        rows=[a for a in assets if a['chain_id']==c['chain_id']]
        for a in rows:
            a['environment']=c['environment']
            if c['environment']=='testnet':a['value_usd']=None
        chains.append({'id':c['chain_id'],'name':c['name'],'environment':c['environment'],
            'image_url':chain_image(c['chain_id']),
            'assets':len(rows),'value_usd':sum(a['value_usd'] for a in rows if a['value_usd'] is not None) if c['environment']=='mainnet' and any(a['value_usd'] is not None for a in rows) else None,
            'complete':c['general_erc20_discovery']=='indexer_checked','rpc_available':c['rpc_status']=='available',
            'discovery_status':c.get('discovery_status') if c.get('discovery_status') in ('checked','disabled','missing_credential','unsupported','provider_error') else 'incomplete',
            'registry_complete':(c.get('mintclub_registry_scan') or {}).get('complete') is True,
            'registry_errors':(c.get('mintclub_registry_scan') or {}).get('registry_errors',0),
            'balance_errors':(c.get('mintclub_registry_scan') or {}).get('balance_errors',0),
            'native_symbol':c.get('native_symbol'),
            'native_balance':c.get('native_balance') if c['rpc_status']=='available' and number(c.get('native_balance')) is not None else None,
            'native_observed_at':c.get('native_observed_at'),
            'native_block_number':c.get('native_block_number'),
            'registry_block_number':(c.get('mintclub_registry_scan') or {}).get('block_number')})
    values=[a['value_usd'] for a in assets if a['environment']=='mainnet' and a['value_usd'] is not None]
    total=sum(values) if values else None
    return {'address':entry['address'],'key':entry['address_key'],'tags':entry.get('tags',[]),
        'name':(entry.get('tags') or [entry['address'][:10]])[0],'analysed_at':snapshot.get('compiled_at'),
        'prices_at':price_time,'balance_observed_at':max((t.get('balance_observed_at','') for t in tokens),default=snapshot.get('compiled_at')),
        'known_value_usd':total,'unpriced_count':sum(a['value_usd'] is None for a in assets),
        'assets':assets,'chains':chains,'counts':snapshot.get('counts',{}),'status':snapshot.get('status'),
        'snapshot_price_references':{key:{'value':value['value'],'observed_at':value.get('observed_at')}
            for key,value in refs.items() if re.fullmatch(r'[A-Za-z][A-Za-z0-9]{0,15}_USD',key) and isinstance(value,dict) and number(value.get('value')) is not None},
        'report_url':'/api/report/'+entry['address_key']}

def dashboard(wallets):
    """Sum direct mainnet positions, without adding pool liquidity or curve backing."""
    chains={};assets={};positions=[]
    for wallet in wallets:
        names={c['id']:c['name'] for c in wallet['chains']}
        for asset in wallet['assets']:
            if asset.get('environment')!='mainnet':continue
            positions.append(asset)
            chain=chains.setdefault(asset['chain_id'],{'id':asset['chain_id'],'name':names[asset['chain_id']],
                'position_count':0,'wallet_keys':set(),'values':[],'unpriced_count':0})
            chain['position_count']+=1;chain['wallet_keys'].add(wallet['key'])
            row=assets.setdefault(asset['id'],{k:asset[k] for k in ['id','chain_id','symbol','name','image_url']})
            row.setdefault('wallet_keys',set()).add(wallet['key'])
            row.setdefault('values',[]);row.setdefault('unpriced_count',0)
            if asset['value_usd'] is None:
                chain['unpriced_count']+=1;row['unpriced_count']+=1
            else:
                chain['values'].append(asset['value_usd']);row['values'].append(asset['value_usd'])
    def finish(row):
        row['value_usd']=sum(row['values']) if row['values'] else None
        row['wallet_count']=len(row.pop('wallet_keys'));row.pop('values')
        return row
    network_rows=sorted((finish(c) for c in chains.values()),key=lambda c:c['value_usd'] or 0,reverse=True)
    asset_rows=sorted((finish(a) for a in assets.values()),key=lambda a:a['value_usd'] or 0,reverse=True)
    for asset in asset_rows:asset['chain_name']=chains[asset['chain_id']]['name']
    values=[a['value_usd'] for a in positions if a['value_usd'] is not None]
    dates=[w['prices_at'] for w in wallets if w.get('prices_at')]
    return {'known_value_usd':sum(values) if values else None,'wallet_count':len(wallets),
        'analysed_wallet_count':sum(bool(w.get('analysed_at')) for w in wallets),
        'position_count':len(positions),'unique_asset_count':len(assets),'chain_count':len(chains),
        'priced_count':len(values),'unpriced_count':len(positions)-len(values),
        'prices_from':min(dates,default=None),'prices_to':max(dates,default=None),
        'networks':network_rows,'largest_holdings':[a for a in asset_rows if a['value_usd'] is not None][:5]}

def load_state(root=ROOT):
    registry=read(root/'wallets.json');wallets=[];images=read_catalog(root)
    for entry in registry.get('wallets',[]):
        latest=entry.get('latest_snapshot')
        if latest and latest.get('result'):
            result=read(within(root,latest['result']))
            if result['wallet_address'].lower()!=entry['address_key']:raise ValueError('Snapshot wallet identity mismatch')
            wallets.append(project_wallet(entry,result,root,images))
        else:
            wallets.append({'address':entry['address'],'key':entry['address_key'],'tags':entry.get('tags',[]),
                'name':(entry.get('tags') or [entry['address'][:10]])[0],'assets':[],'chains':[],
                'known_value_usd':0,'unpriced_count':0,'analysed_at':None,'status':'awaiting_analysis','counts':{}})
    state={'wallets':wallets,'currency':'USD','dashboard':dashboard(wallets),
           'details':project_details(wallets,root)}
    if registry.get('demo') is True:state['demo']=True
    encoded=json.dumps(state,ensure_ascii=False,allow_nan=False,separators=(',',':')).encode()
    return state,encoded,hashlib.sha256(encoded).hexdigest()
