"""Read-only projection of wallet research snapshots into viewer data."""
from __future__ import annotations

from decimal import Decimal, InvalidOperation, localcontext
from pathlib import Path
import hashlib
import json
import math
import os
import re
from token_images import image_for, read_catalog, safe_image
from chain_images import chain_image
from native_assets import native_identity
from details import project_details
from sell_quotes import classify_with_cache as cashout_classification
from market_records import canonical_token, canonical_source, merge_pools, market_url

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

def safe_routes(routes):
    result=[]
    if not isinstance(routes,list):return result
    for route in routes[:104]:
        if not isinstance(route,dict) or route.get('endpoint_class') not in ('public','custom') or route.get('outcome') not in ('succeeded','failed','skipped','queue_timeout','local_timeout'):continue
        item={key:route[key] for key in ('endpoint_class','outcome')}
        for key in ('endpoint_index','http_status','rpc_code','count'):
            if type(route.get(key)) is int and abs(route[key])<=2**53-1:item[key]=route[key]
        if route.get('reason') in ('transport','throttle','size','method','contract','cooldown','queue','qualification','local_deadline'):item['reason']=route['reason']
        result.append(item)
    return result

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

def sell_out_estimate(quote, eligibility, reserve_price):
    """Value saved full-position outputs without treating reserve spot as cash.

    Amount-specific terminal routes take priority. A burn-only estimate values
    the received reserve token, not a subsequent sale of that reserve. The quote
    and the USD reference keep their independent clocks.
    """
    routes = [q for q in eligibility.get('quotes', [])
              if q.get('partial_input') is False and number(q.get('quoted_output_usd')) is not None
              and number((checked_price(q.get('output_price')) or {}).get('usd')) is not None]
    if routes:
        best = max(routes, key=lambda q: Decimal(q['quoted_output_usd']))
        symbol = best.get('output_symbol') or (best.get('output_price') or {}).get('symbol')
        if quote and best.get('output_address') == quote['output_address']:
            symbol = quote['output_symbol']
        return {**best, 'value_usd': number(best['quoted_output_usd']),
                'valuation': 'terminal_reference', 'output_symbol': symbol}
    if not quote:
        return None
    price = reserve_price or {}
    usd = number(price.get('usd'))
    usable = (usd is not None and usd > 0 and price.get('quality') == 'estimated'
              and price.get('basis') in ('DEX market', 'Market index')
              and price.get('observed_at') and price.get('source')
              and not price.get('retained_from_previous'))
    with localcontext() as context:
        context.prec = 800
        value = number(Decimal(quote['output_amount']) * Decimal(str(usd))) if usable else None
    return {**quote, 'value_usd': value, 'valuation': 'reserve_reference',
            'output_price': price if usable else None, 'execution_verified': False}

MIN_PRICE_LIQUIDITY_USD=1000

def checked_price(price, pools=()):
    """A spot quote needs a meaningful observed market, including saved quotes."""
    if not price or price.get('basis')!='DEX market':return price
    liquidity=number(price.get('liquidity_usd'))
    if liquidity is None:
        pool=next((p for p in pools if p.get('source_url')==price.get('source')),None)
        liquidity=number((pool.get('reported_liquidity') or {}).get('usd')) if pool else None
        base=number((pool.get('reported_liquidity') or {}).get('base')) if pool else None
        usd=number(price.get('usd'))
        if liquidity and base is not None and usd is not None and base*usd/liquidity>0.98:
            return {**price,'usd':None,'quality':'unreliable','basis':'Insufficient market liquidity','liquidity_usd':liquidity}
    if liquidity is None or liquidity<MIN_PRICE_LIQUIDITY_USD:
        return {**price,'usd':None,'quality':'unreliable','basis':'Insufficient market liquidity','liquidity_usd':liquidity}
    return {**price,'liquidity_usd':liquidity}

def dex_price(token, observed):
    """Use the selected source observation, never a later publication clock.

    observed is an optional raw-response timestamp for callers normalizing a
    response. Snapshot callers pass None when original source time is unknown.
    """
    candidates=[]; suspect=None
    for p in token.get('dex_pools',[]):
        price=number(p.get('reported_price_usd'))
        pair=p.get('paired_tokens',[])
        if price is None or len(pair)!=2 or pair[0]['address'].lower()!=token['token_address'].lower(): continue
        liq=p.get('reported_liquidity') or {}
        tvl=number(liq.get('usd')); base=number(liq.get('base'))
        if tvl is not None and tvl<MIN_PRICE_LIQUIDITY_USD:
            suspect={'source':p.get('source_url'),'observed_at':p.get('observed_at') or observed,'liquidity_usd':tvl};continue
        # Source-reported TVL can consist almost entirely of the self-priced token.
        # Do not use such a pool as the wallet's market value.
        if tvl and base is not None and base*price/tvl>0.98:
            suspect={'source':p.get('source_url'),'observed_at':p.get('observed_at') or observed,'liquidity_usd':tvl}; continue
        if tvl and pool_has_liquidity(p): candidates.append((tvl,price,p))
    if candidates:
        _,price,p=max(candidates,key=lambda v:v[0])
        return {'usd':price,'basis':'DEX market','source':p['source_url'],'observed_at':p.get('observed_at') or observed,'quality':'estimated','liquidity_usd':number(p['reported_liquidity']['usd'])}
    if suspect:return {'usd':None,'basis':'Insufficient market liquidity','quality':'unreliable',**suspect}
    for p in token.get('indexer_price_references',[]):
        price=number(p.get('value'))
        if p.get('currency')=='usd' and price is not None and price>0:
            return {'usd':price,'basis':'Market index','source':'https://www.alchemy.com','observed_at':p.get('lastUpdatedAt'),'quality':'estimated'}
    return None

def project_wallet(entry, snapshot, root=ROOT, images=None):
    images=read_catalog(root) if images is None else images
    latest=entry.get('latest_snapshot') or {}
    snapshot_dir=within(root,latest.get('directory','snapshots'))
    all_networks=snapshot.get('pipeline',{}).get('phase') in ('holdings','sell') or snapshot.get('pipeline',{}).get('holdings_scope')=='all_configured'
    market_path=snapshot_dir/'market-prices.json'
    market=read(market_path) if market_path.exists() else {}
    prices={(p.get('chain_id',8453),p['address'].lower()):p for p in market.get('tokens',[])}
    recorded_markets={p['id']:p.get('pools',[]) for p in market.get('markets',[])}
    legacy_pools={}
    metadata=snapshot_dir/'token-market-metadata.json'
    if metadata.is_file() and any(p.get('basis')=='DEX market' and 'liquidity_usd' not in p for p in prices.values()):
        from wallet import DEX, pool_row
        inverse={slug:cid for cid,slug in DEX.items()}
        for record in read(metadata):
            for pair in record.get('response',[]) if isinstance(record.get('response'),list) else []:
                try:
                    key=(inverse[pair['chainId']],pair['baseToken']['address'].lower())
                    legacy_pools.setdefault(key,[]).append(pool_row(pair,record.get('observed_at')))
                except (KeyError,TypeError,AttributeError):continue
    refs=snapshot.get('price_references',{})
    eth=number(market.get('native_usd',{}).get('ETH',{}).get('usd')) or number(refs.get('ETH_USD',{}).get('value'))
    price_time=market.get('observed_at') or refs.get('ETH_USD',{}).get('observed_at') or snapshot.get('compiled_at')
    tokens=[canonical_token(t) for t in snapshot.get('tokens',[])]
    by_address={(t['chain_id'],t['token_address'].lower()):t for t in tokens}
    cache={}
    def price_for(t,seen=None):
        if snapshot.get('pipeline',{}).get('phase')=='initial':return None
        k=(t['chain_id'],t['token_address'].lower())
        if k in cache:return cache[k]
        seen=set(seen or set())
        if k in seen:return None
        seen.add(k)
        override=checked_price(prices.get(k),t.get('dex_pools',[])+legacy_pools.get(k,[]))
        if override and 'source' in override:override={**override,'source':canonical_source(override['source'],t)}
        mint=t.get('mintclub')
        if override and override.get('quality') in ('unfunded','unreliable'):
            cache[k]={**override,'usd':None};return cache[k]
        if override and (override.get('basis')!='Curve spot' or override.get('retained_from_previous')):
            cache[k]=override;return override
        if mint:
            reserve=mint['reserve_symbol'];reserve_price=None;retained_reserve=None
            reserve_identity=(t['chain_id'],mint['reserve_token'].lower())
            if reserve_identity==(8453,'0x4200000000000000000000000000000000000006'):reserve_price=eth
            elif reserve_identity==(8453,'0xcbb7c0000ab88b473b1f5afd9ef808440eed33bf'):reserve_price=number(refs.get('cbBTC_USD',{}).get('value'))
            rt=checked_price(prices.get(reserve_identity),legacy_pools.get(reserve_identity,[]))
            if rt and rt.get('usd') is not None:
                reserve_price=number(rt['usd']);retained_reserve=rt if rt.get('retained_from_previous') else None
            parent=by_address.get((t['chain_id'],mint['reserve_token'].lower()))
            if parent:
                parent_price=price_for(parent,seen)
                if parent_price:
                    reserve_price=parent_price.get('usd');retained_reserve=parent_price if parent_price.get('retained_from_previous') else None
            if reserve_price is not None:
                spot=number((override or {}).get('curve_price_in_reserve',mint['price_for_next_mint_in_reserve_token']))
                funded=number(override['curve_reserve'])>0 if override and 'curve_reserve' in override else mint.get('funded')
                p={'usd':spot*reserve_price if spot is not None else None,'basis':'Curve spot',
                   'source':mint['source_url'],'observed_at':(override or {}).get('observed_at',mint['observed_at']),
                   'quality':'estimated' if funded else 'unfunded'}
                if not funded:p['usd']=None
                elif retained_reserve:p.update(retained_from_previous=True,latest_price_status='unavailable',observed_at=retained_reserve.get('observed_at'))
                cache[k]=p;return p
        p=dex_price(t,None)
        cache[k]=p;return p

    assets=[]
    for t in tokens:
        t={**t,'dex_pools':merge_pools(t.get('dex_pools',[]),recorded_markets.get(f"{t['chain_id']}:{t['token_address'].lower()}",[]))}
        p=price_for(t);quantity=number(t['wallet_balance'])
        value=quantity*p['usd'] if p and p.get('usd') is not None and quantity is not None else None
        label=t['symbol'];name=t.get('name') or label
        market_token=prices.get((t['chain_id'],t['token_address'].lower())) or {}
        if 'http' in label.lower() or 'claim' in label.lower():label='Airdrop';name='Unverified token'
        links=[]
        if t.get('mintclub'):links.append({'label':'Mint Club','url':t['mintclub']['source_url']})
        found={}; market_pools=[]
        for pool in t.get('dex_pools',[]):
            venue=pool['venue'].lower(); label_venue='Uniswap' if 'uniswap' in venue else 'Aerodrome' if 'aerodrome' in venue else venue.replace('-',' ').title()
            weight=(pool.get('reported_liquidity') or {}).get('usd',0)
            measured=pool.get('factory_measurement') or {}
            if not weight and measured.get('quote_balance'):
                weight=(number(measured['quote_balance']) or 0)*(eth or 0) if measured.get('quote_symbol')=='WETH' else number(measured['quote_balance']) or 0
            destination=market_url(t['chain_id'],pool)
            if label_venue not in found or weight>found[label_venue][0]:found[label_venue]=(weight,destination)
            pair=[]
            for coin in pool.get('paired_tokens',[])[:2]:
                if not isinstance(coin,dict):continue
                symbol=coin.get('symbol')
                pair.append({'address':coin.get('address'),'symbol':symbol if isinstance(symbol,str) and symbol else '?',
                             'image_url':image_for(images,t['chain_id'],coin.get('address'),native_symbol=symbol if coin.get('address')=='0x'+'0'*40 else None)})
            market_pools.append({'venue':label_venue,'pool':pool.get('pool'),'url':destination,'source_url':pool['source_url'],
                'pair':pair,'version_labels':pool.get('version_labels',[]),'fee_bps':pool.get('fee_bps'),'pool_kind':pool.get('pool_kind'),'liquidity_usd':number((pool.get('reported_liquidity') or {}).get('usd')),
                'price_usd':number(pool.get('reported_price_usd')),'observed_at':pool.get('observed_at')})
        market_pools.sort(key=lambda row:-(row['liquidity_usd'] or 0))
        links += [{'label':k,'url':v[1]} for k,v in found.items()]
        explorer=EXPLORERS.get(t['chain_id'])
        if explorer:links.append({'label':'Explorer','url':explorer+'/token/'+t['token_address']})
        assets.append({'id':f'{t["chain_id"]}:{t["token_address"].lower()}','chain_id':t['chain_id'],
            'symbol':label,'name':name,'address':t['token_address'],'balance':t['wallet_balance'],
            'price':p,'value_usd':value,'is_native':False,'links':links,'market_pools':market_pools,
            'balance_observed_at':t.get('balance_observed_at') or snapshot.get('compiled_at'),
            'quantity_retained':bool(t.get('metadata_evidence_retained') or t.get('balance_evidence_retained')),
            'burn_quote':(t.get('mintclub') or {}).get('wallet_full_burn'),
            'exit_quote':exit_quote(t),
            'cashout_eligibility':cashout_classification(t,market,wallet_address=entry['address'],environment=next((c.get('environment') for c in snapshot.get('coverage',[]) if c.get('chain_id')==t['chain_id']),'unknown')),
            'exit_route': 'mintclub_burn' if t.get('mintclub') else 'dex_unquoted' if t.get('dex_liquidity_found') or any(pool_has_liquidity(pool) for pool in t.get('dex_pools',[])) else 'unverified',
            'image_url':safe_image(t.get('indexer_image_url')) or image_for(images,t['chain_id'],t['token_address'],mint=bool(t.get('mintclub'))),
            'curve_reserve': {'amount':market_token.get('curve_reserve',t['mintclub']['reserve_balance']),'symbol':t['mintclub']['reserve_symbol'],'address':t['mintclub']['reserve_token'],
                'image_url':image_for(images,t['chain_id'],t['mintclub']['reserve_token'])} if t.get('mintclub') else None})
        if t.get('mintclub'):
            mint=t['mintclub']
            assets[-1]['curve_state']={k:mint.get(k) for k in ('reserve_token','reserve_symbol','reserve_balance','current_supply','price_for_next_mint_in_reserve_token','burn_royalty_bps','block_number','observed_at')}
    # Reuse prices already on disk. No RPC, route simulation or quote refresh.
    for asset, token in zip(assets, tokens):
        quote = asset['exit_quote']
        reserve_price = None
        if quote:
            key = (token['chain_id'], quote['output_address'])
            parent = by_address.get(key)
            reserve_price = price_for(parent) if parent else checked_price(prices.get(key), legacy_pools.get(key, []))
        asset['sell_out'] = sell_out_estimate(quote, asset['cashout_eligibility'], reserve_price)
        estimate = asset['sell_out']
        if estimate and not estimate.get('output_symbol'):
            output_token = by_address.get((token['chain_id'], estimate['output_address']))
            if output_token: estimate['output_symbol'] = output_token['symbol']
    coverage=[dict(c) for c in snapshot.get('coverage',[])]
    market_pending=(snapshot.get('pipeline') or {}).get('market_pending') is True
    for c in coverage:
        if all_networks and c.get('rpc_status')=='pending':
            evidence=snapshot_dir/f"chain-{c['chain_id']}.json"
            if evidence.is_file():
                raw=read(evidence)
                if raw.get('wallet','').lower()==entry['address_key'] and raw.get('status')=='unavailable':c['rpc_status']='unavailable'
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
    from chain_lifecycle import lifecycle, retired
    for c in coverage:
        # Older snapshots retained this count only in a fixed pipeline note.
        failed_balances=c.get('candidate_balance_errors')
        if type(failed_balances) is not int or failed_balances<0:
            failed_balances=max((int(m.group(1)) for note in c.get('notes',[]) or [] if isinstance(note,str)
                and (m:=re.fullmatch(r'([0-9]{1,9}) candidate token balances could not be read\.',note))),default=0)
        rows=[a for a in assets if a['chain_id']==c['chain_id']]
        for a in rows:
            a['environment']=c['environment']
            if c['environment']=='testnet':a['value_usd']=None
            a['archived']=retired(c['chain_id'])
            if a['archived']:a['historical_value_usd']=a['value_usd'];a['value_usd']=None
            if a['environment'] != 'mainnet' or a['archived'] or a.get('quantity_retained'):
                a['sell_out'] = None
        chains.append({'id':c['chain_id'],'name':c['name'],'environment':c['environment'],
            'image_url':chain_image(c['chain_id']),
            'assets':len(rows),'value_usd':sum(a['value_usd'] for a in rows if a['value_usd'] is not None) if c['environment']=='mainnet' and any(a['value_usd'] is not None for a in rows) else None,
            'complete':c['general_erc20_discovery']=='indexer_checked','rpc_available':c['rpc_status']=='available',
            'discovery_status':c.get('discovery_status') if c.get('discovery_status') in ('checked','disabled','missing_credential','unsupported','provider_error','history_pending','throttled','checkpoint_error','source_limited') else 'incomplete',
            'rpc_routes':safe_routes(c.get('rpc_routes')),
            'head_status':c.get('head_status') if c.get('head_status') in ('stale','observed','saved_observation') else None,
            'head_age_seconds':c.get('head_age_seconds') if type(c.get('head_age_seconds')) is int else None,
            'lifecycle':lifecycle(c['chain_id']),
            'discovery_provider':c.get('discovery_provider') if c.get('discovery_provider') in ('etherscan_keyless','routescan','explorer','multiple') else 'alchemy' if c.get('indexer_source')=='Alchemy Portfolio Tokens By Wallet' else None,
            'discovery_sources':[{'provider':s['provider'],'complete':s.get('complete') is True,
                                  'status':s.get('discovery_status') if s.get('discovery_status') in ('checked','history_pending','throttled','provider_error','checkpoint_error','source_limited') else 'incomplete'}
                                 for s in (c.get('discovery_sources') if isinstance(c.get('discovery_sources'),list) else []) if isinstance(s,dict) and s.get('provider') in ('etherscan_keyless','routescan','explorer')][:3],
            'history_window':{k:v for k,v in (c.get('history_window') or {}).items() if k in ('startblock','endblock','page','complete','records','started_at','pagination_limit_reached','pages_checked','pending_ranges','completed_ranges','blocked_ranges') and type(v) in (int,bool)} if isinstance(c.get('history_window'),dict) else None,
            'recent_window':{k:v for k,v in (c.get('recent_window') or {}).items() if k in ('startblock','endblock','page','complete','records') and type(v) in (int,bool)} if isinstance(c.get('recent_window'),dict) else None,
            'discovery_filters':{'spam_filter':False,'minimum_value':None,'minimum_liquidity':None} if c.get('discovery_provider')=='etherscan_keyless' else None,
            'registry_complete':(c.get('mintclub_registry_scan') or {}).get('complete') is True,
            'registry_phase':(c.get('mintclub_registry_scan') or {}).get('phase'),
            'rpc_pending':c.get('rpc_status')=='pending',
            'rpc_status':'retired' if retired(c['chain_id']) else c.get('rpc_status','unknown'),
            'market_pending':market_pending and not all_networks,
            'market_errors':0 if all_networks else sum(bool(t.get('dex_verification_error')) for t in tokens if t['chain_id']==c['chain_id']),
            'sell_analysis_errors':sum(bool(t.get('dex_verification_error')) for t in tokens if t['chain_id']==c['chain_id']) if all_networks else 0,
            'registry_errors':(c.get('mintclub_registry_scan') or {}).get('registry_errors',0),
            'balance_errors':(c.get('mintclub_registry_scan') or {}).get('balance_errors',0),
            'candidate_balance_errors':failed_balances,
            'token_detail_errors':sum(bool(t.get('mintclub_error')) or t.get('wallet_balance') is None for t in tokens if t['chain_id']==c['chain_id']),
            'candidate_deferred':(c.get('candidate_scan') or {}).get('deferred',0),
            'native_symbol':c.get('native_symbol'),
            'native_balance':c.get('native_balance') if c['rpc_status']=='available' and number(c.get('native_balance')) is not None else None,
            'native_observed_at':c.get('native_observed_at'),
            'native_block_number':c.get('native_block_number'),
            'registry_block_number':(c.get('mintclub_registry_scan') or {}).get('block_number')})
    values=[a['value_usd'] for a in assets if a['environment']=='mainnet' and a['value_usd'] is not None]
    total=sum(values) if values else None
    return {'address':entry['address'],'key':entry['address_key'],'tags':entry.get('tags',[]),
        'lookup_mode':'all_networks' if all_networks else 'legacy',
        'sell_analysis_pending':market_pending and all_networks,
        'snapshot_id':(entry.get('latest_snapshot') or {}).get('directory'),
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

def load_state(root=ROOT, *, include_details=True, encode=True):
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
           'details':project_details(wallets,root) if include_details else {'tokens':[], 'networks':[]}}
    if registry.get('demo') is True:state['demo']=True
    if not encode:return state,None,None
    encoded=json.dumps(state,ensure_ascii=False,allow_nan=False,separators=(',',':')).encode()
    return state,encoded,hashlib.sha256(encoded).hexdigest()
