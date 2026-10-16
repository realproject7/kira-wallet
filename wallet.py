"""Register, analyse and publish supplied wallets to the local read-only viewer."""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
import fcntl
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
import threading

import research as h
from kira_config import ASSETS, data_root, load_config

ROOT = data_root()
class MarketPause(ValueError):
    """A resumable time budget, distinct from provider failure."""
ALCHEMY = {1:'eth-mainnet',8453:'base-mainnet',81457:'blast-mainnet',10:'opt-mainnet',42161:'arb-mainnet',
    43114:'avax-mainnet',137:'polygon-mainnet',56:'bnb-mainnet',130:'unichain-mainnet',7777777:'zora-mainnet',
    33139:'apechain-mainnet',4663:'robinhood-mainnet',11155111:'eth-sepolia',84532:'base-sepolia',
    168587773:'blast-sepolia',43113:'avax-fuji'}
PORTFOLIO = {**ALCHEMY,137:'matic-mainnet'}
EXPLORERS = {109:'https://shibariumscan.io',7560:'https://cyberscan.co',177:'https://hashkey.blockscout.com',
    5112:'https://explorer.ham.fun'}
DEX = {1:'ethereum',8453:'base',81457:'blast',10:'optimism',42161:'arbitrum',43114:'avalanche',137:'polygon',
    56:'bsc',109:'shibarium',7560:'cyber',8217:'kaia',130:'unichain',7777777:'zora',33139:'apechain',177:'hashkey',4663:'robinhood'}
NATIVE = {137:'POL',56:'BNB',43114:'AVAX',109:'BONE',8217:'KAIA',33139:'APE',177:'HSK',54176:'OVER',157:'BONE',43113:'AVAX'}
CONTRACT_SOURCE = 'https://raw.githubusercontent.com/Steemhunt/mint.club-v2-sdk/main/src/constants/contracts.ts'
SOURCE_NAMES = {1:'mainnet',8453:'base',81457:'blast',10:'optimism',42161:'arbitrum',43114:'avalanche',137:'polygon',56:'bsc',
    109:'shibarium',7560:'cyber',5112:'ham',8217:'kaia',130:'unichain',7777777:'zora',33139:'apeChain',177:'hashkey',
    4663:'robinhood',54176:'over',11155111:'sepolia',84532:'baseSepolia',168587773:'blastSepolia',157:'shibariumTestnet',43113:'avalancheFuji',111557560:'cyberTestnet'}


def read(path):
    return json.loads(Path(path).read_text())


def atomic(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix+'.tmp')
    text = data if isinstance(data, str) else json.dumps(data, indent=2, ensure_ascii=False)+'\n'
    # Providers occasionally include credentialed URLs in an error response.
    try:values=h.secrets().values()
    except ValueError:values=[]
    for secret in values:
        if secret:
            text=text.replace(secret,'[redacted]')
    with temp.open('w') as stream:
        stream.write(text);stream.flush();os.fsync(stream.fileno())
    os.replace(temp, path)
    descriptor=os.open(path.parent,os.O_RDONLY)
    try:os.fsync(descriptor)
    finally:os.close(descriptor)


def event(stage, **data):
    print(json.dumps({'stage':stage, **data}, ensure_ascii=False), flush=True)


def fetch(url, body=None, deadline=None):
    for attempt in range(3):
        remaining=deadline-time.monotonic() if deadline is not None else 25
        if remaining<=0:return {'research_pending':True}
        if deadline is None:response=h.fetch(url,body,timeout=25)
        else:
            from public_discovery import fetch_bounded
            response=fetch_bounded(url,min(25,remaining),body)
            if isinstance(response,dict) and response.get('error',{}).get('code')=='deadline' and time.monotonic()>=deadline:return {'research_pending':True}
            if isinstance(response,dict) and response.get('error'):response={'transport_error':{'message':'Provider response unavailable within the read limit.'}}
        error = response.get('transport_error') if isinstance(response, dict) else None
        if not error or (error.get('status') not in (429,500,502,503,504) and 'status' in error):
            return response
        if attempt < 2:
            time.sleep(min(attempt+1,max(0,deadline-time.monotonic())) if deadline is not None else attempt+1)
    return response


def validate_address(address):
    if not re.fullmatch(r'0x[0-9a-fA-F]{40}', address):
        raise ValueError('Expected a 20-byte EVM wallet address.')
    node = subprocess.run(['node','-e',"const v=require('./onchain.cjs').viem;const a=process.argv[1];if(!v.isAddress(a))process.exit(1);process.stdout.write(v.getAddress(a))",address],
        cwd=ASSETS, capture_output=True, text=True, timeout=10)
    if node.returncode:
        raise ValueError('Invalid EVM address checksum.')
    return node.stdout


def register(registry, address, tag):
    key = address.lower()
    wallet = next((w for w in registry['wallets'] if w['address_key']==key), None)
    if wallet is None:
        wallet = {'address':address,'address_key':key,'tags':[],'registered_at':h.now()}
        registry['wallets'].append(wallet)
    if tag and tag not in wallet['tags']:
        wallet['tags'].append(tag)
        registry.setdefault('tag_history',[]).append({'address_key':key,'tag':tag,'action':'add','observed_at':h.now(),'source':'operator'})
    return wallet


def discover(wallet, n, folder, budget=None):
    cid = n['chain_id']
    evidence = folder/f'discovery-{cid}.json'
    if evidence.exists():
        cached=read(evidence)
        if cached['wallet'].lower()==wallet.lower() and cached['complete']:
            return cached
    row = {'wallet':wallet,'chain_id':cid,'observed_at':h.now(),'complete':False,'tokens':[],'native':[], 'pages':[],'source':None,'discovery_status':'incomplete'}
    cfg=load_config();deadline=time.monotonic()+budget if budget else None
    try:key=h.secrets().get('ALCHEMY_CUSTOM_APY_KEY') if cfg['discovery']['provider']=='alchemy' else None
    except ValueError:key=None
    if cid in ALCHEMY and key:
        row['source']='Alchemy Portfolio Tokens By Wallet'
        network=PORTFOLIO[cid]
        endpoint=f'https://api.g.alchemy.com/data/v1/{key}/assets/tokens/by-address'
        body={'addresses':[{'address':wallet,'networks':[network]}], 'withMetadata':True,'withPrices':True,
              'includeNativeTokens':True,'includeErc20Tokens':True,'includeBlockMetadata':True}
        seen=set()
        for page in range(100):
            if deadline:
                from public_discovery import fetch_page
                remaining=deadline-time.monotonic()
                if remaining<=0:
                    row['error']={'message':'Token discovery time budget reached. Saved candidates remain usable.'};break
                response=fetch_page(endpoint,min(8,remaining),body)
            else:response=fetch(endpoint,body)
            row['pages'].append({'observed_at':h.now(),'request':dict(body),'response':response})
            if not isinstance(response,dict) or not isinstance(response.get('data'),dict) or not isinstance(response['data'].get('tokens'),list):
                row['error']=(response.get('error') or response.get('transport_error')) if isinstance(response,dict) else None
                row['error']=row['error'] or {'message':'Token provider returned an invalid or missing token list.'}
                break
            data=response['data']
            for t in data.get('tokens',[]):
                if not isinstance(t,dict):
                    row['error']={'message':'Token provider returned an invalid token record.'};continue
                if not isinstance(t.get('network'),str) or not t['network'] or not isinstance(t.get('address'),str) or not re.fullmatch(r'0x[0-9a-fA-F]{40}',t['address']):
                    row['error']={'message':'A token record identity was missing or invalid.'};continue
                if t['network']!=network or t['address'].lower()!=wallet.lower():
                    continue
                try:
                    if not isinstance(t.get('tokenBalance'),str) or not re.fullmatch(r'0x[0-9a-fA-F]+',t['tokenBalance']):raise ValueError('Invalid balance')
                    balance=int(t['tokenBalance'],16)
                except (TypeError,ValueError):
                    row['error']={'message':'A token balance was missing or invalid.'}
                    continue
                if not t.get('tokenAddress'):
                    row['native'].append(t)
                elif balance>0:
                    if not isinstance(t['tokenAddress'],str) or not re.fullmatch(r'0x[0-9a-fA-F]{40}',t['tokenAddress']):
                        row['error']={'message':'A token contract address was invalid.'};continue
                    meta=t.get('tokenMetadata') or {}
                    row['tokens'].append({'chain_id':cid,'address':t['tokenAddress'],'name':meta.get('name'),'symbol':meta.get('symbol'),
                                          'decimals':meta.get('decimals'),'prices':t.get('tokenPrices') or []})
            if response.get('error') or response.get('transport_error') or row.get('error'):
                row['error']=response.get('error') or response.get('transport_error') or row['error']
                break
            cursor=data.get('pageKey')
            if not cursor:
                row['complete']=True
                break
            if cursor in seen:
                row['error']={'message':'Repeated pagination cursor'}
                break
            seen.add(cursor)
            body['pageKey']=cursor
        else:
            row['error']={'message':'Pagination safety limit reached; discovery incomplete'}
    elif cid in EXPLORERS and cfg['discovery'].get('explorers'):
        row['source']=EXPLORERS[cid]+'/api/v2/addresses/'+wallet+'/token-balances'
        response=fetch(row['source'])
        row['pages'].append({'observed_at':h.now(),'response':response})
        if isinstance(response,list):
            row['complete']=True
            for t in response:
                meta=t.get('token') or {}
                if meta.get('type')=='ERC-20' and int(t.get('value') or 0)>0:
                    row['tokens'].append({'chain_id':cid,'address':meta['address_hash'],'name':meta.get('name'),'symbol':meta.get('symbol'),
                                          'decimals':int(meta['decimals']) if meta.get('decimals') is not None else None,'prices':[]})
        else:
            row['error']=response
    elif cfg['discovery'].get('public',True) and n.get('environment')=='mainnet' and not (cfg.get('rpc',{}).get('mode')=='custom' and cfg['rpc'].get('allow_public_fallback') is False):
        from public_discovery import discover as free_discover
        row.update(free_discover(wallet,cid))
    else:
        status='disabled' if cfg['discovery']['provider']=='none' else 'missing_credential' if cid in ALCHEMY and not key else 'unsupported'
        row['discovery_status']=status
        messages={'disabled':'Token discovery is off. Configure an indexer to discover other ERC20 holdings.',
                  'missing_credential':'The selected indexer credential is unavailable. Configure its private environment reference, then refresh holdings.',
                  'unsupported':'No general ERC20 indexer is available for this network.'}
        row['error']={'message':messages[status]+' Mint Club registry and native balances are queried independently.'}
    if row['complete']:row['discovery_status']='checked'
    elif row['source'] and row['discovery_status']=='incomplete':row['discovery_status']='provider_error'
    row['tokens']=list({t['address'].lower():t for t in row['tokens']}.values())
    atomic(evidence,row)
    return row


def run_node(mode, source, destination, on_chain=None, deadline=None):
    child=subprocess.Popen(['node',str(ASSETS/'pipeline-onchain.cjs'),mode,str(source),str(destination)],cwd=ASSETS,stdout=subprocess.PIPE,text=True)
    timer=None
    if deadline is not None:
        timer=threading.Timer(max(0,deadline-time.monotonic()),lambda:child.terminate() if child.poll() is None else None)
        timer.daemon=True;timer.start()
    try:
        for line in child.stdout:
            try: message=json.loads(line)
            except ValueError: continue
            if not isinstance(message,dict):continue
            print(json.dumps(message),flush=True)
            if on_chain and message.get('stage')=='chain':on_chain(message)
        if child.wait():
            if deadline is not None and time.monotonic()>=deadline:raise MarketPause('Market verification time budget reached. Resume saved checks in Activity.')
            raise ValueError('On-chain research stopped before completing this phase.')
    finally:
        if timer:timer.cancel()
        child.stdout.close()
        if child.poll() is None:child.terminate();child.wait()


@contextmanager
def registry_locked(root):
    with (Path(root)/'.registry.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        yield


def publish_snapshot(wallet, folder, result):
    relative=str(folder.relative_to(ROOT))
    with registry_locked(ROOT):
        registry=read(ROOT/'wallets.json')
        entry=next(w for w in registry['wallets'] if w['address_key']==wallet['address_key'])
        generation=os.environ.get('KIRA_RESEARCH_GENERATION')
        job_id=os.environ.get('KIRA_JOB_ID')
        if not generation and job_id and (ROOT/'jobs'/f'{job_id}.json').is_file():
            job=read(ROOT/'jobs'/f'{job_id}.json');generation=job.get('parent_job_id',job_id)
        if not generation or entry.get('research_generation') in (None,generation):
            entry['latest_snapshot']={'directory':relative,'result':relative+'/results.json','report':relative+'/report.md','observed_on':time.strftime('%Y-%m-%d'),'status':result['status']}
        runs=registry.setdefault('research_runs',[])
        if not any(r['snapshot']==relative for r in runs):
            runs.append({'address_key':wallet['address_key'],'tags':entry['tags'],'completed_at':result['compiled_at'],'status':result['status'],'snapshot':relative,'counts':result['counts']})
        atomic(ROOT/'wallets.json',registry)


def initial_result(wallet, folder, networks, discovered, chains, *, phase='baseline', prices=False):
    """Publish recorded partial facts without waiting for registry or market work."""
    by_chain={c['chain_id']:c for c in chains};by_discovery={d['chain_id']:d for d in discovered}
    coverage=[];tokens=[{**t,'dex_liquidity_found':t.get('dex_liquidity_found',False)} for c in chains for t in c['tokens']]
    for n in networks:
        c=by_chain.get(n['chain_id'],{});d=by_discovery.get(n['chain_id'],{})
        coverage.append({**{k:v for k,v in n.items() if k not in ('public_rpc','explorer')},
            'rpc_status':c.get('rpc_status','pending'),'native_symbol':NATIVE.get(n['chain_id'],'ETH'),
            'native_balance':c.get('native_balance'),'native_observed_at':c.get('observed_at'),
            'native_block_number':c.get('block_number'),'native_block_hash':c.get('block_hash'),
            'general_erc20_discovery':'indexer_checked' if d.get('complete') else 'incomplete',
            'indexer_source':d.get('source'),'indexer_complete':d.get('complete',False),'indexer_pages':len(d.get('pages',[])),
            'discovery_status':d.get('discovery_status','pending'),'candidate_balance_errors':len(c.get('balance_errors',[])),
            'candidate_scan':c.get('candidate_scan'),'mintclub_registry_scan':c.get('registry_scan'),
            'notes':['Initial balances. Remaining candidate balances, full Mint Club enumeration and market enrichment remain pending.']})
    result={'schema_version':1,'wallet_address':wallet['address'],'tags':wallet['tags'],'compiled_at':h.now(),
        'status':'completed_with_coverage_gaps','scope':'Recorded initial direct holdings. Unchecked holdings and prices remain unknown.',
        'tokens':tokens,'coverage':coverage,'price_references':{},'nested_curve_independent_redemption_estimates':[],
        'counts':{'mainnets_in_scope':sum(n['environment']=='mainnet' for n in networks),'testnets_in_scope':sum(n['environment']=='testnet' for n in networks),
            'positive_erc20_tokens_discovered':sum(t['token_type']=='ERC20' for t in tokens),'positive_erc1155_tokens_discovered':sum(t['token_type']=='ERC1155' for t in tokens),
            'mainnets_with_general_indexer':sum(c['environment']=='mainnet' and c['indexer_complete'] for c in coverage),
            'mintclub_tokens':sum(bool(t.get('mintclub')) for t in tokens),'mintclub_tokens_with_nonzero_reserve':sum(bool((t.get('mintclub') or {}).get('funded')) for t in tokens),
            'dex_tokens_with_liquidity_evidence':0,'mintclub_registry_assets_checked':0},
        'limitations':['Initial evidence is partial. Detailed registry and market research continues separately. Missing holdings and prices are unknown, not zero.',
            'Free candidate discovery and known-token catalogs do not guarantee every arbitrary ERC20 contract.'],
        'actions':{'signatures':0,'approvals':0,'swaps':0,'transfers':0,'rpc_read_only':True},
        'pipeline':{'version':2,'phase':phase,'enrichment_pending':True,'resumable':True},'evidence_files':['onchain-summary.json']}
    refs={}
    if prices:
        from native_assets import market_metadata
        refs=market_metadata(coverage,fetch=lambda url:h.fetch(url,timeout=8))['prices']
        result['price_references']=refs
    atomic(folder/'onchain-summary.json',{'wallet':wallet['address'],'chains':chains})
    atomic(folder/'results.json',result)
    atomic(folder/'market-prices.json',{'observed_at':result['compiled_at'],'wallet_address':wallet['address'],
        'native_usd':{k.removesuffix('_USD'):{'usd':float(v['value']),'observed_at':v.get('observed_at'),'basis':v.get('basis'),'source':v.get('source')} for k,v in refs.items()},'tokens':[]})
    report(result,folder)
    publish_snapshot(wallet,folder,result)
    return result


def source_check(networks, folder):
    import urllib.request
    with urllib.request.urlopen(CONTRACT_SOURCE,timeout=20) as response:
        source=response.read().decode()
    bond=source.split('  BOND: {',1)[1].split('\n  },',1)[0]
    configured={name:address.lower() for name,address in re.findall(r"\[(\w+)\.id\]:\s*'([^']+)'",bond)}
    expected={SOURCE_NAMES[n['chain_id']]:n['mintclub_bond_address'].lower() for n in networks}
    if configured!=expected:
        raise ValueError('Mint Club SDK network/deployment scope changed. Reconcile networks.json before analysis.')
    atomic(folder/'mintclub-support.json',{'observed_at':h.now(),'source':CONTRACT_SOURCE,'networks_verified':len(networks),'bond_deployments':configured})


def dex_fetch(t, folder, deadline=None):
    chain=DEX.get(t['chain_id'])
    if not chain or t.get('token_type')=='ERC1155':
        return {'chain_id':t['chain_id'],'token_address':t['token_address'],'response':[], 'observed_at':None, 'status':'outside_dex_indexer_scope'}
    name=f"dex-{t['chain_id']}-{t['token_address'].lower()}.json"
    if (folder/name).exists():
        old=read(folder/name)
        if isinstance(old.get('response'),list):return old
    url='https://api.dexscreener.com/token-pairs/v1/'+chain+'/'+t['token_address']
    response=fetch(url,deadline=deadline)
    if deadline is not None and time.monotonic()>=deadline:
        return {'chain_id':t['chain_id'],'token_address':t['token_address'],'response':[], 'observed_at':None,'status':'pending'}
    row={'chain_id':t['chain_id'],'token_address':t['token_address'],'source':url,'observed_at':h.now(),'response':response}
    atomic(folder/name,row)
    return row


def pool_row(p, observed):
    return {'pool':p['pairAddress'],'venue':p['dexId'],'version_labels':p.get('labels') or [],
            'paired_tokens':[p['baseToken'],p['quoteToken']],'reported_liquidity':p.get('liquidity'),
            'reported_volume_24h_usd':(p.get('volume') or {}).get('h24'),'reported_price_usd':p.get('priceUsd'),
            'observed_at':observed,'source_url':p['url'],'rpc_verification':None,'factory_measurement':None}


def finish(wallet, folder, networks, discovered):
    deadline=time.monotonic()+180
    checkpoint_folder=folder
    raw=read(folder/'onchain-summary.json')
    tokens=[t for c in raw['chains'] for t in c['tokens']]
    event('dex_discovery', tokens=len(tokens))
    with ThreadPoolExecutor(max_workers=5) as executor:
        responses=[]
        for response in executor.map(lambda t:dex_fetch(t,folder,deadline),tokens):
            responses.append(response);event('onchain_progress',operation='markets',checked=len(responses),total=len(tokens))
    for t,r in zip(tokens,responses):
        if isinstance(r['response'],list):
            t['dex_pools']=[pool_row(p,r.get('observed_at')) for p in r['response'] if p.get('chainId')==DEX.get(t['chain_id']) and
                            t['token_address'].lower() in {p['baseToken']['address'].lower(),p['quoteToken']['address'].lower()}]
            t['dex_discovery_status']='queried' if r.get('status') is None else r['status']
        else:
            t['dex_discovery_status']='provider_error'
    atomic(folder/'dex-input.json',{'wallet':wallet['address'],'networks':networks,'tokens':tokens,'market_budget_ms':max(0,int((deadline-time.monotonic())*1000))})
    run_node('dex',folder/'dex-input.json',folder/'dex-verified.json')
    verified=read(folder/'dex-verified.json');tokens=verified['tokens'];market_pending=verified.get('market_pending',False)
    for t in tokens:
        t['dex_liquidity_found']=any((p.get('reported_liquidity') or {}).get('usd',0)>0 or
            (p.get('factory_measurement') or {}).get('active_liquidity_verified',False) for p in t['dex_pools'])
        if t['dex_liquidity_found']:t['dex_discovery_status']='pool_liquidity_found'
    minted=[t for t in tokens if t.get('mintclub')]
    # Supplementary API metadata is not consumed by the report. Keep on-chain
    # names and bond facts without letting unused metadata block publication.
    market_pending=market_pending or time.monotonic()>=deadline
    coverage=[]
    by_discovery={d['chain_id']:d for d in discovered}
    by_raw={d['chain_id']:d for d in raw['chains']}
    for n in networks:
        c=by_raw[n['chain_id']];d=by_discovery[n['chain_id']]
        row={**{k:v for k,v in n.items() if k not in ('public_rpc','explorer')},'rpc_status':c.get('rpc_status','unavailable'),
             'native_symbol':NATIVE.get(n['chain_id'],'ETH'),'native_balance':c['native_balance'],
             'native_observed_at':c['observed_at'],'native_block_number':c.get('block_number'),
             'native_block_hash':c.get('block_hash'),
             'rpc_endpoint_indices':c.get('rpc_endpoint_indices',[]),
             'general_erc20_discovery':'indexer_checked' if d['complete'] else 'incomplete',
             'indexer_source':d['source'],'indexer_pages':len(d['pages']),'indexer_complete':d['complete'],
             'discovery_status':d.get('discovery_status','checked' if d['complete'] else 'incomplete'),
             'candidate_balance_errors':len(c.get('balance_errors',[])),
             'positive_erc20_count_discovered':sum(t['chain_id']==n['chain_id'] and t['token_type']=='ERC20' for t in tokens),
             'mintclub_inventory_scan':None,'mintclub_registry_scan':c.get('registry_scan'),'notes':[]}
        if not d['complete']:row['notes'].append('General token discovery incomplete. See discovery evidence; this is not proof of no holdings.')
        if not c.get('registry_scan',{}).get('complete'):row['notes'].append('Mint Club registry scan incomplete. Unchecked balances remain unknown.')
        if c.get('balance_errors'):row['notes'].append(f"{len(c['balance_errors'])} candidate token balances could not be read.")
        coverage.append(row)
    refs={}
    for d in discovered:
        n=next(n for n in networks if n['chain_id']==d['chain_id'])
        if n['environment']!='mainnet':continue
        symbol=NATIVE.get(d['chain_id'],'ETH')
        for t in d['native']:
            price=next((p for p in t.get('tokenPrices',[]) if p.get('currency')=='usd' and p.get('value') is not None),None)
            if price:refs[symbol+'_USD']={'value':price['value'],'observed_at':price.get('lastUpdatedAt'),'source':'Alchemy Portfolio Tokens By Wallet'}
    from native_assets import market_metadata
    if market_pending:native_market={'evidence':[],'prices':{},'images':{}}
    elif (folder/'native-market.json').exists():
        from datetime import datetime
        previous=read(folder/'native-market.json')
        try:observed=datetime.fromisoformat(previous['observed_at'])
        except (KeyError,TypeError,ValueError):observed=None
        native_market=market_metadata(coverage,fetch=lambda url:previous['response'],observed=observed) if observed is not None and isinstance(previous.get('response'),list) else market_metadata(coverage,fetch=lambda url:fetch(url,deadline=deadline))
    else:native_market=market_metadata(coverage,fetch=lambda url:fetch(url,deadline=deadline))
    market_pending=market_pending or time.monotonic()>=deadline
    if native_market['evidence']:atomic(folder/'native-market.json',native_market['evidence'])
    for key,price in native_market['prices'].items():refs.setdefault(key,price)
    # Obtain prices of reserve assets separately, including tokens not held by the wallet.
    reserve_candidates={(t['chain_id'],t['mintclub']['reserve_token'].lower()):{'chain_id':t['chain_id'],'token_address':t['mintclub']['reserve_token'],'token_type':'ERC20'} for t in minted}
    reserve_rows=[] if market_pending else list(ThreadPoolExecutor(max_workers=5).map(lambda t:dex_fetch(t,folder,deadline),reserve_candidates.values()))
    market_pending=market_pending or time.monotonic()>=deadline
    sys.path.insert(0,str(ASSETS/'viewer'))
    from model import dex_price
    reserve_prices=[]
    for t,r in zip(reserve_candidates.values(),reserve_rows):
        if not isinstance(r['response'],list):continue
        observed=r.get('observed_at')
        shadow={**t,'dex_pools':[pool_row(p,observed) for p in r['response'] if p.get('chainId')==DEX.get(t['chain_id'])],'indexer_price_references':[]}
        price=dex_price(shadow,observed)
        if price and price.get('usd') is not None:reserve_prices.append({'chain_id':t['chain_id'],'address':t['token_address'],**price})
    counts={'mainnets_in_scope':sum(n['environment']=='mainnet' for n in networks),'testnets_in_scope':sum(n['environment']=='testnet' for n in networks),
            'mainnets_with_general_indexer':sum(c['environment']=='mainnet' and c['general_erc20_discovery']=='indexer_checked' for c in coverage),
            'positive_erc20_tokens_discovered':sum(t['token_type']=='ERC20' for t in tokens),'positive_erc1155_tokens_discovered':sum(t['token_type']=='ERC1155' for t in tokens),
            'dex_tokens_with_liquidity_evidence':sum(t['dex_liquidity_found'] for t in tokens),'mintclub_tokens':len(minted),
            'mintclub_tokens_with_nonzero_reserve':sum(t['mintclub']['funded'] for t in minted),
            'mintclub_registry_assets_checked':sum(c.get('mintclub_registry_scan',{}).get('checked',0) if c.get('mintclub_registry_scan') else 0 for c in coverage)}
    gaps=market_pending or any(t.get('dex_verification_error') for t in tokens) or any(not c['indexer_complete'] or not (c.get('mintclub_registry_scan') or {}).get('complete') or c['rpc_status']!='available' or c['candidate_balance_errors'] for c in coverage)
    result={'schema_version':1,'wallet_address':wallet['address'],'tags':wallet['tags'],'compiled_at':h.now(),'status':'completed_with_coverage_gaps' if gaps else 'completed',
        'scope':'Direct ERC20, registered Mint Club ERC1155 and native holdings across all configured Mint Club EVM networks. Testnets are separate.',
        'counts':counts,'coverage':coverage,'tokens':tokens,'nested_curve_independent_redemption_estimates':[], 'price_references':refs,
        'limitations':['General indexers can omit arbitrary ERC20 assets. Failed or incomplete discovery is never interpreted as no holdings.',
            'Mint Club registry enumeration includes all reachable deployed bond assets, including ERC1155 token ID 0. Deposits or stakes held by other contracts are outside direct wallet balances.',
            'DEX discovery combines DEX Screener and supplemental Base WETH/USDC factory queries. Other quote assets, custom fee tiers and unindexed pools can be missed.',
            'DEX TVL and curve reserves describe the entire pool or curve. Spot wallet values are estimates, distinct from executable cash-out value.',
            'Full-wallet burn quotes subtract the recorded creator royalty and exclude gas. Nested reserve backing overlaps and must not be summed as independent cash reserves.',
            'Testnet assets are excluded from USD totals. Missing prices stay unknown.'],
        'actions':{'paid_provider_calls':None,'provider_billing':'Not determined; provider allowance can be consumed.','signatures':0,'approvals':0,'swaps':0,'transfers':0,'rpc_read_only':True},
        'pipeline':{'version':1,'entrypoint':'wallet.py','resumable':True,'market_pending':market_pending,'registry_cache':'Shared append-only asset identity cache. Wallet balances are not reused between wallets.'},
        'evidence_files':[f.name for f in sorted(folder.glob('*.json')) if f.name not in ('results.json','market-prices.json')]}
    atomic(folder/'results.json',result)
    prices=[]
    for t in tokens:
        p=dex_price(t,result['compiled_at'])
        if p:prices.append({'chain_id':t['chain_id'],'address':t['token_address'],**p})
    atomic(folder/'market-prices.json',{'observed_at':result['compiled_at'],'wallet_address':wallet['address'],'balance_refresh':True,
        'native_usd':{k.removesuffix('_USD'):{'usd':float(p['value']),'observed_at':p.get('observed_at'),
            'source':p.get('source'),'asset_id':p.get('asset_id'),'basis':p.get('basis','Market index')} for k,p in refs.items()},
        'tokens':prices+reserve_prices,'note':'DEX and reserve prices observed during this run. Curve spot prices use recorded on-chain state. Unknown prices remain null.'})
    from curve_pricing import enrich
    if not market_pending:
        try:atomic(folder/'market-prices.json',enrich(result,read(folder/'market-prices.json'),folder,deadline=deadline))
        except MarketPause:market_pending=True
    from token_images import refresh_catalog
    try:
        if not market_pending and time.monotonic()<deadline:
            event('token_images',tokens=len(tokens))
            event('token_images',**refresh_catalog([result],ROOT,native_images=native_market['images'],fetch=lambda url:fetch(url,deadline=deadline)))
    except (OSError,ValueError):event('token_images',status='unavailable')
    result['evidence_files']=[f.name for f in sorted(folder.glob('*.json')) if f.name not in ('results.json','market-prices.json')]
    atomic(folder/'results.json',result)
    report(result,folder)
    if market_pending:
        result['pipeline']['market_pending']=True;result['status']='completed_with_coverage_gaps'
        index=1
        while (checkpoint_folder/f'market-initial-{index:04d}').exists():index+=1
        previous_folder=folder;folder=checkpoint_folder/f'market-initial-{index:04d}';folder.mkdir(parents=True)
        atomic(folder/'market-prices.json',read(previous_folder/'market-prices.json'))
        result['evidence_files']=['market-prices.json']
        result['limitations'].append('Market verification reached its time budget. Recorded balances and completed registry checks remain available. Remaining pool checks are pending, not verified absent. Resume this job in Activity to continue saved checks.')
        atomic(folder/'results.json',result);report(result,folder);publish_snapshot(wallet,folder,result)
        event('first_evidence',snapshot=str(folder.relative_to(ROOT)))
        event('market_paused')
        raise MarketPause('Market verification paused at its time budget. Saved balances and market checkpoints are available to resume in Activity.')
    return result


def md(value):
    return str(value if value is not None else 'Unknown').replace('|','\\|').replace('\n',' ')


def table(headers, rows):
    return '\n'.join(['| '+' | '.join(headers)+' |','| '+' | '.join(['---']*len(headers))+' |']+['| '+' | '.join(md(x) for x in row)+' |' for row in rows])


def report(result, folder):
    tokens=result['tokens'];counts=result['counts']
    lines=[f"# {', '.join(result['tags'])} wallet research",'',f"Wallet: `{result['wallet_address']}`. Compiled: {result['compiled_at']}.",'',
        f"{counts['positive_erc20_tokens_discovered']} ERC20 and {counts['positive_erc1155_tokens_discovered']} registered Mint Club ERC1155 holdings were found. "
        f"{counts['mintclub_tokens']} holdings have Mint Club curves; {counts['mintclub_tokens_with_nonzero_reserve']} have nonzero reserves. "
        f"{counts['dex_tokens_with_liquidity_evidence']} holdings have DEX liquidity evidence.",'',
        '## Mint Club holdings','',table(['Chain','Token','Balance','Entire curve reserve','Full wallet burn, net'],[
            (t['network'],f"[{md(t['symbol'])}]({t['mintclub']['source_url']})",t['wallet_balance'],
             t['mintclub']['reserve_balance']+' '+t['mintclub']['reserve_symbol'],
             (t['mintclub']['wallet_full_burn']['net_refund']+' '+t['mintclub']['reserve_symbol']) if t['mintclub']['wallet_full_burn'] else 'Unknown')
            for t in tokens if t.get('mintclub')]),'',
        '## Held tokens with DEX liquidity','',table(['Chain','Token','Balance','Venues','Largest source-reported pool TVL'],[
            (t['network'],t['symbol'],t['wallet_balance'],', '.join(sorted({p['venue'] for p in t['dex_pools']})),
             max(((p.get('reported_liquidity') or {}).get('usd',0) or 0 for p in t['dex_pools']),default=0)) for t in tokens if t['dex_liquidity_found']]),'',
        '## Network coverage','',table(['Network','Environment','General discovery','Mint registry checked / total','RPC'],[
            (c['name'],c['environment'],c['general_erc20_discovery'],
             f"{c['mintclub_registry_scan']['checked']} / {c['mintclub_registry_scan']['registry_count']}" if c.get('mintclub_registry_scan') else 'Unknown',c['rpc_status']) for c in result['coverage']]),'',
        '## Limits','']+['- '+l for l in result['limitations']]+['','## Evidence','',
        '[Structured results](results.json), [on-chain balances and curve states](onchain-summary.json), [DEX verification](dex-verified.json) and per-chain discovery files preserve timestamps, fixed blocks, errors and exact quantities.', '',
        'Source interfaces: [Mint Club API](https://sdk.mint.club/docs/api), [Mint Club bond](https://github.com/Steemhunt/mint.club-v2-contract), '
        '[Alchemy Portfolio](https://www.alchemy.com/docs/data/portfolio-apis/portfolio-api-endpoints/portfolio-api-endpoints/get-tokens-by-address), '
        '[DEX Screener](https://docs.dexscreener.com/api/reference).']
    atomic(folder/'report.md','\n'.join(lines)+'\n')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest='command',required=True)
    add=sub.add_parser('add');add.add_argument('address');add.add_argument('--tag',required=True)
    refresh=sub.add_parser('refresh');refresh.add_argument('wallet',help='Registered address or exact tag')
    for p in (add,refresh):
        p.add_argument('--resume',help='Existing snapshot directory relative to the research root')
        p.add_argument('--phase',choices=('baseline','enrichment','full'),default='full')
    args=parser.parse_args()
    # Serialize shared registry and cache writers for the entire run.
    with (os.fdopen(int(os.environ['KIRA_ANALYSIS_FD']), 'a') if os.environ.get('KIRA_ANALYSIS_FD') else (ROOT/'.analysis.lock').open('a')) as lock:
        try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:raise SystemExit('Another wallet analysis is running. Resume after it finishes.')
        read(ROOT/'session.json');registry=read(ROOT/'wallets.json');registered=read(ROOT/'networks.json')['networks']
        candidates=read(ASSETS/'sources/rpc-candidates.json')
        networks=[{**n,**next((c for c in candidates if c['chain_id']==n['chain_id']),{})} for n in registered]
        if args.command=='add':
            address=validate_address(args.address)
            with registry_locked(ROOT):
                registry=read(ROOT/'wallets.json')
                wallet=next((w for w in registry['wallets'] if w['address_key']==address.lower()),None)
                admitted=os.environ.get('KIRA_JOB_ID') in registry.get('wallet_admissions',{})
                if wallet is None or not (args.resume or admitted):wallet=register(registry,address,args.tag)
                atomic(ROOT/'wallets.json',registry)
        else:
            wallet=next((w for w in registry['wallets'] if w['address_key']==args.wallet.lower() or args.wallet in w['tags']),None)
            if wallet is None:raise SystemExit('No registered wallet matches this address or tag.')
        if args.resume:
            folder=(ROOT/args.resume).resolve()
            if not folder.is_relative_to(ROOT/'snapshots'):raise ValueError('Resume path must be within snapshots/.')
            manifest=read(folder/'run.json')
            if manifest['wallet_address'].lower()!=wallet['address_key']:raise ValueError('Resume wallet mismatch.')
            relative=str(folder.relative_to(ROOT))
            published=any(w.get('latest_snapshot',{}).get('directory')==relative for w in registry['wallets']) or any(r.get('snapshot')==relative for r in registry.get('research_runs',[]))
            if manifest.get('completed_at') or published:raise ValueError('Published snapshots are immutable. Use refresh without --resume for a new analysis.')
        else:
            if os.environ.get('KIRA_JOB_SNAPSHOT'):
                folder=(ROOT/os.environ['KIRA_JOB_SNAPSHOT']).resolve()
                if not folder.is_relative_to(ROOT/'snapshots'):raise ValueError('Job path must be within snapshots/.')
            else:
                slug=re.sub(r'[^A-Za-z0-9_-]+','-',wallet['tags'][0] if wallet['tags'] else wallet['address_key']).strip('-')
                folder=ROOT/'snapshots'/slug/(time.strftime('%Y-%m-%dT%H%M%S')+'-'+wallet['address_key'][2:10])
            folder.mkdir(parents=True,exist_ok=bool(os.environ.get('KIRA_JOB_SNAPSHOT')))
        relative=str(folder.relative_to(ROOT))
        atomic(folder/'run.json',{'wallet_address':wallet['address'],'tags':wallet['tags'],'started_or_resumed_at':h.now(),'status':'running'})
        event('registered',wallet=wallet['address'],tags=wallet['tags'],snapshot=str(folder.relative_to(ROOT)))
        try:
            source_check(networks,folder)
            # Initial reports cover three active mainnets; the continuation handles
            # every configured network, exhaustive registry work and markets.
            initial_networks=[n for cid in (8453,1,81457) for n in networks if n['chain_id']==cid]
            phase_networks=initial_networks if args.phase=='baseline' else networks
            with ThreadPoolExecutor(max_workers=5) as executor:
                discovered=list(executor.map(lambda n:discover(wallet['address'],n,folder,budget=25 if args.phase=='baseline' else 60),phase_networks))
            event('discovery',complete_chains=sum(d['complete'] for d in discovered),candidates=sum(len(d['tokens']) for d in discovered))
            known=read(ASSETS/'sources/known-tokens.json')['tokens']
            atomic(folder/'scan-input.json',{'wallet':wallet['address'],'networks':phase_networks,'candidates':known+[t for d in discovered for t in d['tokens']]})
            if args.phase=='baseline':
                first=folder/'initial'
                def first_evidence(message):
                    if (first/'results.json').exists():return
                    cid=message.get('chain_id');path=folder/f'baseline-chain-{cid}.json'
                    if not path.exists():return
                    chain=read(path)
                    if chain.get('rpc_status')!='available':return
                    initial_result(wallet,first,networks,discovered,[chain],phase='initial')
                    event('first_evidence',snapshot=str(first.relative_to(ROOT)),tokens=len(chain['tokens']))
                run_node('baseline',folder/'scan-input.json',folder,on_chain=first_evidence)
                result=initial_result(wallet,folder,networks,discovered,read(folder/'onchain-summary.json')['chains'],prices=True)
            else:
                run_node('scan',folder/'scan-input.json',folder)
                result=finish(wallet,folder,networks,discovered)
            publish_snapshot(wallet,folder,result)
            atomic(folder/'run.json',{'wallet_address':wallet['address'],'tags':wallet['tags'],'completed_at':h.now(),'status':result['status']})
            event('published',snapshot=relative,counts=result['counts'],status=result['status'],viewer='http://127.0.0.1:8765')
        except Exception as error:
            atomic(folder/'run.json',{'wallet_address':wallet['address'],'tags':wallet['tags'],'failed_at':h.now(),'status':'failed','error':h.redact(str(error))})
            event('market_paused' if isinstance(error,MarketPause) else 'failed',error=h.redact(str(error)),resume=str(folder.relative_to(ROOT)))
            raise SystemExit(1)


if __name__=='__main__':
    main()
