"""Register, analyse and publish supplied wallets to the local read-only viewer."""
from __future__ import annotations
from market_records import pool_row, collected_markets, merge_pools, canonical_token

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import contextmanager
import fcntl
import hashlib
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
ResearchPause=h.ResearchPause
MarketPause=h.MarketPause
ALCHEMY = {1:'eth-mainnet',8453:'base-mainnet',81457:'blast-mainnet',10:'opt-mainnet',42161:'arb-mainnet',
    43114:'avax-mainnet',137:'polygon-mainnet',56:'bnb-mainnet',130:'unichain-mainnet',7777777:'zora-mainnet',
    33139:'apechain-mainnet',4663:'robinhood-mainnet',11155111:'eth-sepolia',84532:'base-sepolia',
    168587773:'blast-sepolia',43113:'avax-fuji'}
PORTFOLIO = {**ALCHEMY,137:'matic-mainnet'}
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


def free_sources(wallet, cid, budget, *, continue_only=False, public=True, explorers=False):
    """Union admitted keyless sources; each source owns a separate frontier."""
    import discovery_state
    import transfer_discovery
    import public_discovery
    import explorer_discovery
    sources=[]
    if public and cid in transfer_discovery.CHAINS:sources.append(('etherscan_keyless',f'{cid}.json',transfer_discovery.discover,transfer_discovery.DOCS))
    if public and cid in public_discovery.CHAINS:sources.append(('routescan',f'routescan-{cid}.json',public_discovery.discover,public_discovery.DOCS))
    if explorers and cid in explorer_discovery.CHAINS:sources.append(('explorer',f'explorer-{cid}.json',explorer_discovery.discover,explorer_discovery.DOCS))
    rows=[]
    for provider,name,adapter,source in sources:
        frontier=ROOT/'cache/free-discovery'/wallet.lower()/name
        try:
            state=discovery_state.load(frontier,wallet,cid,provider)
            options={'history_strategy':'balanced_ranges_v1','max_pages':20 if budget>25 else 3,
                     'page_size':1000 if cid==8453 else 100} if provider=='etherscan_keyless' else {}
            def save(value):
                discovery_state.save(frontier,value,wallet,cid,provider)
                if provider=='etherscan_keyless':event('onchain_progress',operation='history',chain_id=cid,provider=provider,
                    checked=value.get('pages_checked',0),pending_ranges=len(value.get('pending_ranges',[])),candidates=len(value.get('contracts',[])))
            row=adapter(wallet,cid,state=state,budget=budget/len(sources),continue_only=continue_only,
                save=save,**options)
        except (OSError,ValueError,KeyError,TypeError):
            row={'source':source,'provider':provider,'complete':False,'tokens':[],'pages':[],
                 'discovery_status':'checkpoint_error','error':{'message':'Discovery checkpoint could not be read or saved. Existing evidence was preserved.'}}
        row.setdefault('provider',provider)
        rows.append(row)
    if not rows:
        return {'source':None,'provider':None,'complete':False,'tokens':[],'pages':[],
                'discovery_status':'unsupported','error':{'message':'No admitted keyless ERC20 discovery route is available for this network.'}}
    complete=all(row['complete'] for row in rows)
    status='checked' if complete else next((label for label in ('history_pending','throttled','checkpoint_error','provider_error','source_limited')
                                           if any(row['discovery_status']==label for row in rows)),'incomplete')
    merged={**rows[0],'complete':complete,'discovery_status':status,'complete_inventory_guaranteed':False,
            'provider':rows[0]['provider'] if len(rows)==1 else 'multiple',
            'source':'; '.join(row['source'] for row in rows),'native':[],
            'tokens':merge_candidates([],[],[token for row in rows for token in row['tokens']]),
            'pages':[dict(page,provider=row['provider']) for row in rows for page in row['pages']],
            'sources':[{key:value for key,value in row.items() if key not in ('tokens','native','pages')} for row in rows]}
    merged['error']=None if complete else {'message':'At least one discovery source has unfinished or unavailable evidence. Completed source pages do not establish a complete inventory.'}
    return merged


def candidate_input(wallet, networks, policy, discovered, prior, known):
    return {'wallet':wallet,'networks':networks,'inventory_policy':policy,
            'candidates':merge_candidates([t for t in prior if t.get('token_type','ERC20')=='ERC20'],known,
                [t for d in discovered for t in d['tokens']]),
            'mintclub_id0_candidates':merge_candidates([t for t in prior if t.get('token_type')=='ERC1155'],[],
                [t for d in discovered for t in d.get('mintclub_id0_discovery',{}).get('tokens',[])])}


def acquire_candidate_slices(wallet, networks, folder, policy, acquire, prior, known):
    """Consume each ready chain while other source reads continue, one writer."""
    discovered={};chains={}
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures={executor.submit(acquire,n):n for n in networks}
        for future in as_completed(futures):
            n=futures[future];row=future.result();discovered[n['chain_id']]=row
            atomic(folder/'scan-slice-input.json',candidate_input(wallet,[n],policy,[row],prior,known))
            run_node('scan-slice',folder/'scan-slice-input.json',folder)
            for chain in read(folder/'onchain-summary.json')['chains']:chains[chain['chain_id']]=chain
    ordered=[discovered[n['chain_id']] for n in networks]
    atomic(folder/'scan-input.json',candidate_input(wallet,networks,policy,ordered,prior,known))
    atomic(folder/'onchain-summary.json',{'wallet':wallet,'observed_at':h.now(),'chains':[chains[n['chain_id']] for n in networks]})
    return ordered


def discover(wallet, n, folder, budget=None, *, continue_only=False, indexed_only=False):
    cid = n['chain_id']
    evidence = folder/f'discovery-{cid}.json'
    if evidence.exists():
        cached=read(evidence)
        if cached['wallet'].lower()==wallet.lower() and cached['complete'] and cached.get('coverage_version')==2 and (not indexed_only or cached.get('source')=='Alchemy Portfolio Tokens By Wallet' or cached.get('provider')=='explorer'):
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
                    row['tokens'].append({'chain_id':cid,'address':t['tokenAddress'],'name':meta.get('name'),'symbol':meta.get('symbol'),'suspicious_zero_check':True,
                                          'decimals':meta.get('decimals'),'image_url':meta.get('logo'),'prices':t.get('tokenPrices') or []})
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
    elif indexed_only:
        row.update(free_sources(wallet,cid,budget or 25,continue_only=continue_only,public=False,explorers=True))
    elif n.get('environment') in ('mainnet','testnet') and (cfg['discovery'].get('public',True) or cfg['discovery'].get('explorers')) and not (cfg.get('rpc',{}).get('mode')=='custom' and cfg['rpc'].get('allow_public_fallback') is False):
        row.update(free_sources(wallet,cid,budget or 25,continue_only=continue_only,
                               public=cfg['discovery'].get('public',True),explorers=cfg['discovery'].get('explorers',False)))
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
    row['coverage_version']=2
    atomic(evidence,row)
    return row


def prior_candidates(wallet):
    """Durable positive identities survive baseline publication and failed rereads."""
    cache=ROOT/'cache/prior-positive'/f"{wallet['address_key']}.json"
    prior=[];imported=set()
    try:
        saved=read(cache) if cache.is_file() and cache.stat().st_size<=8000000 else {}
        if isinstance(saved,dict) and saved.get('wallet')==wallet['address_key'] and isinstance(saved.get('candidates'),list):
            prior=saved['candidates']
            sources=saved.get('imported_snapshots',[])
            if isinstance(sources,list):imported={p for p in sources if isinstance(p,str)}
    except (OSError,ValueError):pass
    def import_snapshot(relative, *, historical=False):
        if not isinstance(relative,str) or historical and relative in imported:return
        try:
            source=(ROOT/relative).resolve()
            if not source.is_relative_to(ROOT/'snapshots') or not source.is_file() or source.stat().st_size>32_000_000:return
            old=read(source)
            if not isinstance(old,dict) or old.get('wallet_address','').lower()!=wallet['address_key'] or not isinstance(old.get('tokens'),list):return
            for t in old.get('tokens',[]):
                if not isinstance(t,dict):continue
                # Bootstrap upgrades from this wallet's own published history.
                # A historical positive identity is a new-read candidate only.
                raw=str(t.get('wallet_balance_raw',''))
                if historical and (not re.fullmatch(r'[0-9]{1,78}',raw) or int(raw)<=0):continue
                if t.get('token_type')=='ERC20' or t.get('token_type')=='ERC1155' and str(t.get('token_id'))=='0' and (t.get('mintclub') or t.get('mintclub_membership_status')=='verified'):
                    prior.append({'chain_id':t.get('chain_id'),'address':t.get('token_address'),
                                  **({'token_type':'ERC1155','token_id':'0'} if t.get('token_type')=='ERC1155' else {})})
            imported.add(relative)
        except (OSError,ValueError,TypeError,AttributeError):return
    import_snapshot((wallet.get('latest_snapshot') or {}).get('result'))
    try:registry=read(ROOT/'wallets.json')
    except (OSError,ValueError):registry={}
    runs=registry.get('research_runs',[]) if isinstance(registry,dict) else []
    for run in runs if isinstance(runs,list) else []:
        if isinstance(run,dict) and run.get('address_key')==wallet['address_key'] and isinstance(run.get('snapshot'),str):
            import_snapshot(run['snapshot'].rstrip('/')+'/results.json',historical=True)
    candidates={}
    for token in prior if isinstance(prior,list) else []:
        if isinstance(token,dict) and type(token.get('chain_id')) is int and token['chain_id']>0 and isinstance(token.get('address'),str) and re.fullmatch(r'0x[0-9a-fA-F]{40}',token['address']):
            kind=token.get('token_type','ERC20')
            if kind not in ('ERC20','ERC1155') or kind=='ERC1155' and str(token.get('token_id'))!='0':continue
            identity=(token['chain_id'],token['address'].lower(),kind)
            candidates[identity]={'chain_id':identity[0],'address':identity[1],'suspicious_zero_check':True,'prices':[],
                                  **({'token_type':'ERC1155','token_id':'0','requires_mintclub_membership':True} if kind=='ERC1155' else {})}
    atomic(cache,{'wallet':wallet['address_key'],'candidates':list(candidates.values()),'imported_snapshots':sorted(imported)})
    return list(candidates.values())


def merge_candidates(prior, known, discovered):
    merged={}
    for token in prior+known+discovered:
        key=(token['chain_id'],token['address'].lower());previous=merged.get(key,{})
        merged[key]={**previous,**{k:v for k,v in token.items() if v is not None},
            'suspicious_zero_check':previous.get('suspicious_zero_check',False) or token.get('suspicious_zero_check',False)}
    return list(merged.values())


def inventory_policy(requested=None, manifest=None):
    """A resume never reinterprets checkpoints under a different inventory scope."""
    saved=manifest.get('inventory_policy','full_registry') if manifest is not None else None
    chosen={'market':'wallet_candidates_v1','full':'full_registry'}.get(requested)
    if manifest is not None and chosen is not None and chosen!=saved:
        raise ValueError('Resume inventory scope mismatch. Start a new holdings analysis.')
    policy=saved or chosen or 'full_registry'
    if policy not in ('wallet_candidates_v1','full_registry'):raise ValueError('Invalid saved inventory scope.')
    return policy


def discover_mintclub_id0(wallet, n, folder, budget=15, *, continue_only=False):
    """Separate ID0 frontier. Provider identities are never NFT balance evidence."""
    import discovery_state
    import transfer_discovery
    cid=n['chain_id'];provider=transfer_discovery.provider_for('erc1155')
    evidence=folder/f'discovery-erc1155-id0-{cid}.json'
    if evidence.exists():
        cached=read(evidence)
        if cached.get('wallet','').lower()==wallet.lower() and cached.get('complete') and cached.get('coverage_version')==1:return cached
    row={'wallet':wallet,'chain_id':cid,'observed_at':h.now(),'provider':provider,'tokens':[],
         'complete':False,'pages':[],'source':transfer_discovery.DOCS,'discovery_status':'disabled',
         'complete_inventory_guaranteed':False,'completion_scope':'Validated ERC1155 ID0 transfer pages only; Mint Club membership and balances are separate.'}
    cfg=load_config()
    permitted=cfg['discovery'].get('public',True) and not (cfg.get('rpc',{}).get('mode')=='custom' and cfg['rpc'].get('allow_public_fallback') is False)
    if permitted and n.get('environment') in ('mainnet','testnet'):
        frontier=ROOT/'cache/free-discovery'/wallet.lower()/f'erc1155-id0-{cid}.json'
        try:
            state=discovery_state.load(frontier,wallet,cid,provider)
            def save(value):
                discovery_state.save(frontier,value,wallet,cid,provider)
                event('onchain_progress',operation='history',chain_id=cid,provider=provider,
                    checked=value.get('pages_checked',0),pending_ranges=len(value.get('pending_ranges',[])),candidates=len(value.get('contracts',[])))
            row.update(transfer_discovery.discover(wallet,cid,standard='erc1155',state=state,budget=budget,continue_only=continue_only,
                history_strategy='balanced_ranges_v1',max_pages=20,page_size=1000 if cid==8453 else 100,
                save=save))
        except (OSError,ValueError,KeyError,TypeError):
            row.update(discovery_status='checkpoint_error',error={'message':'ID0 discovery checkpoint could not be read or saved. Existing evidence was preserved.'})
    else:row['error']={'message':'Public ID0 candidate discovery is disabled by configuration. Mint Club holdings remain unknown.'}
    row['coverage_version']=1;atomic(evidence,row)
    return row


def discovery_sources(row):
    sources=list(row.get('sources') or [row])
    if row.get('mintclub_id0_discovery'):sources.append(row['mintclub_id0_discovery'])
    return sources


def id0_coverage(row):
    return {key:value for key,value in (row.get('mintclub_id0_discovery') or {}).items() if key not in ('wallet','tokens','pages','native')}


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


def refresh_metadata(snapshot, market, folder, *, native_images=None, discover_prices=False, supplemental=False):
    """Price and illustrate saved holdings independently of deep market review."""
    from curve_pricing import enrich, resolve
    sys.path.insert(0,str(ASSETS/'viewer'))
    from model import dex_price, checked_price
    from token_images import refresh_catalog
    deadline=time.monotonic()+45
    price_deadline=deadline-10
    tokens=[canonical_token(t) for t in snapshot['tokens']];rows={(p['chain_id'],p['address'].lower()):checked_price(p) for p in market.get('tokens',[])}
    markets={p['id']:p for p in market.get('markets',[])}
    mainnets={c['chain_id'] for c in snapshot.get('coverage',[]) if c.get('environment')=='mainnet'}
    wanted={(t['chain_id'],t['token_address'].lower()):t for t in tokens
            if t['chain_id'] in mainnets and t.get('token_type')!='ERC1155'}
    for t in tokens:
        mint=t.get('mintclub')
        if mint and t['chain_id'] in mainnets:
            key=(t['chain_id'],mint['reserve_token'].lower())
            wanted.setdefault(key,{'chain_id':key[0],'token_address':key[1]})
    metadata=read(folder/'token-market-metadata.json') if (folder/'token-market-metadata.json').exists() else []
    if discover_prices and wanted:
        event('dex_discovery',tokens=len(wanted))
        requests=[]
        for cid,slug in DEX.items():
            addresses=sorted(address for chain,address in wanted if chain==cid)
            requests.extend((cid,slug,set(addresses[i:i+30]),'https://api.dexscreener.com/tokens/v1/'+slug+'/'+','.join(addresses[i:i+30])) for i in range(0,len(addresses),30))
        def get(request):
            response=fetch(request[3],deadline=price_deadline)
            return request,{'source':request[3],'observed_at':h.now(),'response':response}
        evidence=[]
        with ThreadPoolExecutor(max_workers=4) as executor:
            for (cid,slug,addresses,source),record in executor.map(get,requests):
                evidence.append(record)
                markets={row['id']:row for row in collected_markets([record],DEX,wanted,markets.values())}
                for address in addresses:
                    group=markets.get(f'{cid}:{address}',{}).get('pools',[])
                    p=dex_price({'token_address':address,'dex_pools':group},record['observed_at'])
                    if p:rows[(cid,address)]={'chain_id':cid,'address':address,**p}
        atomic(folder/'token-market-metadata.json',evidence)
        metadata=evidence
        for key,t in wanted.items():
            if key not in rows:
                p=dex_price(t,None)
                if p:rows[key]={'chain_id':key[0],'address':key[1],**p}
    graph=[]
    for t in tokens:
        mint=t.get('mintclub')
        if mint and t['chain_id'] in mainnets and type(mint.get('funded')) is bool and mint.get('price_for_next_mint_in_reserve_token') is not None:
            graph.append({'chain_id':t['chain_id'],'address':t['token_address'],'is_curve':True,
                'reserve_token':mint['reserve_token'],'reserve_symbol':mint['reserve_symbol'],
                'price_in_reserve':mint['price_for_next_mint_in_reserve_token'],'funded':mint.get('funded'),
                'curve_reserve':mint['reserve_balance'],'source':mint['source_url'],
                'observed_at':mint['observed_at'],'block_number':mint.get('block_number')})
    for p in resolve(graph,list(rows.values())):rows[(p['chain_id'],p['address'].lower())]=p
    market={**market,'tokens':list(rows.values()),'markets':list(markets.values())}
    pricing_tokens=[t for t in tokens if t['chain_id'] in mainnets]
    missing=[t for t in pricing_tokens if t.get('mintclub') and t['mintclub'].get('funded')
             and rows.get((t['chain_id'],t['token_address'].lower()),{}).get('usd') is None
             and rows.get((t['chain_id'],t['token_address'].lower()),{}).get('quality') not in ('unfunded','unreliable')]
    if missing and time.monotonic()<price_deadline:
        try:market=enrich({**snapshot,'tokens':missing},market,folder,deadline=price_deadline)
        except (MarketPause,OSError,ValueError):
            market['reserve_price_status']='partial'
            partial=folder/'reserve-graph.json'
            if partial.exists():
                try:
                    for p in resolve(read(partial).get('tokens',[]),market['tokens']):
                        rows[(p['chain_id'],p['address'].lower())]=p
                    market['tokens']=list(rows.values())
                except (OSError,ValueError):pass
    if tokens or native_images:
        try:
            event('token_images',tokens=len(tokens))
            event('token_images',**refresh_catalog([snapshot],ROOT,native_images=native_images or {},market_metadata=metadata,fetch=lambda url:fetch(url,deadline=deadline)))
        except (OSError,ValueError):market['image_refresh_status']='unavailable'
    if supplemental:
        from market_discovery import discover
        observed=discover(snapshot,folder,deadline=time.monotonic()+60)
        for row in observed['markets']:
            identity=row['id'];markets[identity]={'id':identity,'pools':merge_pools(markets.get(identity,{}).get('pools',[]),row['pools'])}
        market['market_discovery_status']=observed['status']
        market['markets']=list(markets.values())
    return market


def initial_result(wallet, folder, networks, discovered, chains, *, phase='baseline', prices=False):
    """Publish first balances, then bounded price and artwork metadata."""
    by_chain={c['chain_id']:c for c in chains};by_discovery={d['chain_id']:d for d in discovered}
    coverage=[];tokens=[{**t,'dex_liquidity_found':t.get('dex_liquidity_found',False)} for c in chains for t in c['tokens']]
    for n in networks:
        c=by_chain.get(n['chain_id'],{});d=by_discovery.get(n['chain_id'],{})
        coverage.append({**{k:v for k,v in n.items() if k not in ('public_rpc','explorer')},
            'rpc_status':c.get('rpc_status','unavailable' if c else 'pending'),'native_symbol':NATIVE.get(n['chain_id'],'ETH'),
            'native_balance':c.get('native_balance'),'native_observed_at':c.get('observed_at'),
            'native_block_number':c.get('block_number'),'native_block_hash':c.get('block_hash'),
            'rpc_endpoint_indices':c.get('rpc_endpoint_indices',[]),'rpc_routes':c.get('rpc_routes',[]),
            'head_age_seconds':c.get('head_age_seconds'),'head_status':c.get('head_status'),
            'general_erc20_discovery':'indexer_checked' if d.get('complete') else 'incomplete',
            'indexer_source':d.get('source'),'indexer_complete':d.get('complete',False),'indexer_pages':len(d.get('pages',[])),
            'discovery_status':d.get('discovery_status','pending'),'candidate_balance_errors':len(c.get('balance_errors',[])),
            'token_detail_errors':c.get('token_detail_errors',0),
            'discovery_provider':d.get('provider'), 'history_window':d.get('history_window'), 'recent_window':d.get('recent_window'), 'discovery_filters':d.get('filters'),
            'discovery_sources':d.get('sources',[]),'discovery_completion_scope':d.get('completion_scope'),'complete_inventory_guaranteed':False,
            'candidate_scan':c.get('candidate_scan'),'mintclub_registry_scan':c.get('registry_scan'),
            'inventory_policy':c.get('inventory_policy','full_registry'),'mintclub_wallet_discovery':id0_coverage(d),
            'mintclub_membership_scan':c.get('mintclub_membership_scan'),
            'notes':['Holdings lookup is still running. Remaining balances, prices and artwork are pending.']})
    result={'schema_version':1,'wallet_address':wallet['address'],'tags':wallet['tags'],'compiled_at':h.now(),
        'status':'completed_with_coverage_gaps','scope':'Recorded initial direct holdings. Unchecked holdings and prices remain unknown.',
        'tokens':tokens,'coverage':coverage,'price_references':{},'nested_curve_independent_redemption_estimates':[],
        'counts':{'mainnets_in_scope':sum(n['environment']=='mainnet' for n in networks),'testnets_in_scope':sum(n['environment']=='testnet' for n in networks),
            'positive_erc20_tokens_discovered':sum(t['token_type']=='ERC20' for t in tokens),'positive_erc1155_tokens_discovered':sum(t['token_type']=='ERC1155' for t in tokens),
            'mainnets_with_general_indexer':sum(c['environment']=='mainnet' and c['indexer_complete'] for c in coverage),
            'mintclub_tokens':sum(bool(t.get('mintclub')) for t in tokens),'mintclub_tokens_with_nonzero_reserve':sum(bool((t.get('mintclub') or {}).get('funded')) for t in tokens),
            'dex_tokens_with_liquidity_evidence':0,'mintclub_registry_assets_checked':0},
        'limitations':['Holdings lookup is still running across all configured networks. Missing balances and prices remain unknown.',
            'Indexers and unavailable networks can omit holdings. Testnet assets are excluded from USD totals.'],
        'actions':{'signatures':0,'approvals':0,'swaps':0,'transfers':0,'rpc_read_only':True},
        'pipeline':{'version':2,'phase':phase,'holdings_scope':'all_configured','enrichment_pending':True,'resumable':True},'evidence_files':['onchain-summary.json']}
    refs={}
    native_market={}
    if prices:
        from native_assets import market_metadata
        native_market=market_metadata(coverage,fetch=lambda url:h.fetch(url,timeout=8))
        refs=native_market['prices']
        result['price_references']=refs
        if native_market.get('evidence'):atomic(folder/'native-market.json',native_market['evidence'])
    market={'observed_at':result['compiled_at'],'wallet_address':wallet['address'],
        'native_usd':{k.removesuffix('_USD'):{'usd':float(v['value']),'observed_at':v.get('observed_at'),'basis':v.get('basis'),'source':v.get('source')} for k,v in refs.items()},'tokens':[]}
    if prices:market=refresh_metadata(result,market,folder,native_images=native_market.get('images'),discover_prices=True,supplemental=True)
    if phase=='holdings':
        result['scope']='Direct holdings across every configured network. Alchemy and available explorer indexes are independently verified by on-chain balance reads.'
        result['pipeline'].update(phase='holdings',enrichment_pending=False,sell_analysis_optional=True)
        result['counts']['mintclub_registry_assets_checked']=sum((c.get('registry_scan') or {}).get('checked',0) for c in chains)
        for row in coverage:
            row['notes']=[]
            if not row['indexer_complete']:row['notes'].append('Token indexing is unavailable or incomplete on this network. Missing holdings remain unknown.')
            if row['rpc_status']!='available' or row['candidate_balance_errors']:row['notes'].append('Some on-chain balances could not be verified.')
            if row['token_detail_errors']:row['notes'].append('Some token or curve details could not be checked. Missing prices remain unknown.')
            if not (row.get('mintclub_registry_scan') or {}).get('complete'):row['notes'].append('Mint Club registry checks are incomplete.')
        result['status']='completed_with_coverage_gaps' if any(c['notes'] for c in coverage) else 'completed'
        result['limitations']=['Indexers and unavailable networks can omit holdings. Missing balances and prices remain unknown.',
            'USD values use observed market or funded curve spot prices. Very thin DEX pools are excluded. These values are not executable sale proceeds.',
            'Sell-route analysis is optional and does not discover additional holdings. Testnet assets are excluded from USD totals.']
    atomic(folder/'onchain-summary.json',{'wallet':wallet['address'],'chains':chains})
    atomic(folder/'results.json',result)
    atomic(folder/'market-prices.json',market)
    report(result,folder)
    publish_snapshot(wallet,folder,result)
    return result


def research_holdings(wallet, folder, networks):
    """Enumerate all configured networks and all candidates, without market-route work."""
    with ThreadPoolExecutor(max_workers=5) as executor:
        discovered=list(executor.map(lambda n:discover(wallet['address'],n,folder,indexed_only=True),networks))
    event('discovery',complete_chains=sum(d['complete'] for d in discovered),candidates=sum(len(d['tokens']) for d in discovered))
    known=read(ASSETS/'sources/known-tokens.json')['tokens']
    atomic(folder/'scan-input.json',candidate_input(wallet['address'],networks,'full_registry',discovered,prior_candidates(wallet),known))
    published={}
    def first_evidence(message):
        path=folder/f"chain-{message.get('chain_id')}.json"
        if not path.exists():return
        chain=read(path)
        if chain.get('rpc_status')!='available':return
        key=(chain.get('status'),len(chain['tokens']))
        if published.get(chain['chain_id'])==key:return
        published[chain['chain_id']]=key
        first=folder/'initial'
        if (first/'results.json').exists():
            index=1
            while (folder/f'holdings-initial-{index:04d}').exists():index+=1
            first=folder/f'holdings-initial-{index:04d}'
        chains=[read(folder/f"chain-{n['chain_id']}.json") for n in networks if (folder/f"chain-{n['chain_id']}.json").exists()]
        initial_result(wallet,first,networks,discovered,chains,phase='initial')
        event('first_evidence',snapshot=str(first.relative_to(ROOT)),tokens=sum(len(c['tokens']) for c in chains))
    run_node('scan',folder/'scan-input.json',folder,on_chain=first_evidence)
    return initial_result(wallet,folder,networks,discovered,read(folder/'onchain-summary.json')['chains'],phase='holdings',prices=True)


def saved_holdings(wallet, snapshot_id, folder):
    """Sell analysis uses this wallet's immutable holdings, with original blocks and clocks."""
    source=(ROOT/(snapshot_id or '')).resolve()
    if not source.is_relative_to((ROOT/'snapshots').resolve()) or source==folder.resolve():
        raise ValueError('Choose a saved holdings analysis from this workspace.')
    snapshot=read(source/'results.json')
    if snapshot['wallet_address'].lower()!=wallet['address_key'] or snapshot.get('pipeline',{}).get('phase')!='holdings':
        raise ValueError('Refresh this wallet across all networks before analyzing sell routes.')
    raw=read(source/'onchain-summary.json')
    if raw['wallet'].lower()!=wallet['address_key']:raise ValueError('Saved holdings wallet mismatch.')
    atomic(folder/'onchain-summary.json',raw)
    atomic(folder/'market-prices.json',read(source/'market-prices.json'))
    discovered=[]
    for evidence in source.glob('discovery-*.json'):
        row=read(evidence)
        if row.get('wallet','').lower()!=wallet['address_key']:raise ValueError('Saved discovery wallet mismatch.')
        atomic(folder/evidence.name,row);discovered.append(row)
    return discovered


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


def dex_fetch(t, folder, deadline=None, attempt_limit=None):
    chain=DEX.get(t['chain_id'])
    if not chain or t.get('token_type')=='ERC1155':
        return {'chain_id':t['chain_id'],'token_address':t['token_address'],'response':[], 'observed_at':None, 'status':'outside_dex_indexer_scope'}
    name=f"dex-{t['chain_id']}-{t['token_address'].lower()}.json"
    old={}
    if (folder/name).exists():
        old=read(folder/name)
        if isinstance(old.get('response'),list):return old
        if attempt_limit and old.get('attempts',1)>=attempt_limit:return {**old,'status':'unavailable'}
    if deadline is not None and time.monotonic()>=deadline:
        return {'chain_id':t['chain_id'],'token_address':t['token_address'],'response':[], 'observed_at':None,'status':'pending'}
    url='https://api.dexscreener.com/token-pairs/v1/'+chain+'/'+t['token_address']
    response=fetch(url,deadline=deadline)
    if deadline is not None and time.monotonic()>=deadline and not attempt_limit:
        return {'chain_id':t['chain_id'],'token_address':t['token_address'],'response':[], 'observed_at':None,'status':'pending'}
    row={'chain_id':t['chain_id'],'token_address':t['token_address'],'source':url,'observed_at':h.now(),'response':response}
    if attempt_limit:
        row['attempts']=old.get('attempts',0)+1
        if isinstance(response,dict) and response.get('research_pending'):row['status']='pending' if row['attempts']<attempt_limit else 'unavailable'
    atomic(folder/name,row)
    return row


def continuation_checkpoint(folder, discovered, market_pending):
    """Persist substantive progress, excluding timestamps and repeated failures."""
    progress={};pending=[]
    for discovery in discovered:
        for source in discovery_sources(discovery):
            if not source.get('complete') and source.get('discovery_status') in ('history_pending','throttled'):pending.append(source)
        progress['discovery-'+str(discovery['chain_id'])]={
            'contracts':sorted(t['address'].lower() for t in discovery.get('tokens',[])),
            'id0_contracts':sorted(t['address'].lower() for t in discovery.get('mintclub_id0_discovery',{}).get('tokens',[])),
            'sources':[{k:s.get(k) for k in ('provider','complete','history_window','pagination')} for s in discovery_sources(discovery)]}
    for pattern in ('balance-checkpoint-*.json','registry-checkpoint-*.json','market-checkpoint-*.json','reserve-checkpoint-*.json','cashout-checkpoint-*.json','route-market-checkpoint-*.json'):
        for path in sorted(folder.glob(pattern)):
            saved=read(path)
            progress[path.name]={k:saved[k] for k in ('balances','entries','next_index','requests','completed_pools','nodes','mintclub_membership','facts','asset_reviews') if k in saved}
            if 'pool_attempts' in saved:progress[path.name]['pools_attempted']=sorted(saved['pool_attempts'])
    # Only successful evidence counts. Strip observation timestamps recursively
    # so a failed retry cannot disguise a stalled frontier as new work.
    def stable(value):
        if isinstance(value,dict):return {k:stable(v) for k,v in value.items() if k not in ('observed_at','started_at','rpc_routes','balance_observed_at','error','failures')}
        if isinstance(value,list):return [stable(v) for v in value]
        return value
    encoded=json.dumps(stable(progress),sort_keys=True,separators=(',',':')).encode()
    waiting=not market_pending and pending and all(s.get('discovery_status')=='throttled' for s in pending)
    deadline=min((s.get('retry_not_before',0) for s in pending),default=0) if waiting else 0
    value={'fingerprint':hashlib.sha256(encoded).hexdigest(),'not_before':max(0,int(deadline))}
    atomic(folder/'continuation.json',value)
    return value


def retain_price_evidence(current, previous):
    """Retain dated estimates on missing reads, never over contrary evidence."""
    from decimal import Decimal, InvalidOperation
    def usable(row):
        from datetime import datetime
        try:return row.get('quality')=='estimated' and datetime.fromisoformat(row['observed_at'].replace('Z','+00:00')).tzinfo is not None and Decimal(str(row.get('usd'))).is_finite() and Decimal(str(row['usd']))>=0
        except (InvalidOperation,KeyError,TypeError,ValueError,AttributeError):return False
    rows={(p['chain_id'],p['address'].lower()):p for p in current.get('tokens',[])}
    for p in previous.get('tokens',[]):
        key=(p['chain_id'],p['address'].lower());fresh=rows.get(key,{})
        if not usable(p) or fresh.get('usd') is not None or fresh.get('quality') in ('unfunded','unreliable'):continue
        rows[key]={**p,'retained_from_previous':True,'latest_price_status':'unavailable'}
    return {**current,'tokens':list(rows.values())}


def finish(wallet, folder, networks, discovered, *, holdings_source=None):
    deadline=time.monotonic()+180
    market_scope='representative_v1'
    previous_prices=read(folder/'market-prices.json') if (folder/'market-prices.json').exists() else {}
    checkpoint_folder=folder
    raw=read(folder/'onchain-summary.json')
    research_pending=not holdings_source and (any(s.get('discovery_status') in ('history_pending','throttled') for d in discovered for s in discovery_sources(d)) or any(c.get('research_pending') and not c.get('continuation_stalled') for c in raw['chains']))
    tokens=[t for c in raw['chains'] for t in c['tokens']]
    for n in networks:
        if n['environment']=='mainnet':event('onchain_progress',operation='asset_inventory',chain_id=n['chain_id'],total=sum(t['chain_id']==n['chain_id'] for t in tokens))
    # A slow general pool scan must not consume the entire publication slice.
    # Expand funded burns and recover missing verified-member quotes first.
    early=[t for t in tokens if (t.get('mintclub') or {}).get('funded') or t.get('mintclub_membership_status')=='verified']
    if early:
        atomic(folder/'cashout-input.json',{'wallet':wallet['address'],'networks':networks,'tokens':early,'market_chain_names':DEX,'market_scope':market_scope,'market_budget_ms':45000,'cashout_root_only':True})
        run_node('liquidate',folder/'cashout-input.json',folder/'liquidation-verified.json')
        enriched=read(folder/'liquidation-verified.json')['tokens']
        by_asset={(t['chain_id'],t['token_address'].lower(),t['token_type']):t for t in enriched}
        tokens=[by_asset.get((t['chain_id'],t['token_address'].lower(),t['token_type']),t) for t in tokens]
    event('dex_discovery', tokens=len(tokens))
    discovery_deadline=min(deadline-25,time.monotonic()+30)
    with ThreadPoolExecutor(max_workers=5) as executor:
        responses=[]
        for response in executor.map(lambda t:dex_fetch(t,folder,discovery_deadline,attempt_limit=2),tokens):
            responses.append(response);event('onchain_progress',operation='market_discovery',checked=len(responses),total=len(tokens))
    for t,r in zip(tokens,responses):
        if isinstance(r['response'],list):
            t['dex_pools']=[pool_row(p,r.get('observed_at')) for p in r['response'] if p.get('chainId')==DEX.get(t['chain_id']) and
                            t['token_address'].lower() in {p['baseToken']['address'].lower(),p['quoteToken']['address'].lower()}]
            t['dex_discovery_status']='queried' if r.get('status') is None else r['status']
        else:
            t['dex_discovery_status']='provider_error'
    atomic(folder/'dex-input.json',{'wallet':wallet['address'],'networks':networks,'tokens':tokens,'market_scope':market_scope,'market_budget_ms':max(0,min(60000,int((deadline-time.monotonic()-45)*1000)))})
    run_node('dex',folder/'dex-input.json',folder/'dex-verified.json')
    verified=read(folder/'dex-verified.json');tokens=verified['tokens'];market_pending=verified.get('market_pending',False)
    market_pending=market_pending or any(r.get('status')=='pending' for r in responses)
    if time.monotonic()<deadline-25:
        atomic(folder/'cashout-input.json',{'wallet':wallet['address'],'networks':networks,'tokens':tokens,'market_chain_names':DEX,'market_scope':market_scope,
            'market_budget_ms':max(0,int((deadline-time.monotonic()-25)*1000))})
        run_node('liquidate',folder/'cashout-input.json',folder/'liquidation-verified.json')
        liquidation=read(folder/'liquidation-verified.json');tokens=liquidation['tokens'];market_pending=market_pending or liquidation['market_pending']
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
             'rpc_routes':c.get('rpc_routes',[]),
             'head_age_seconds':c.get('head_age_seconds'),'head_status':c.get('head_status'),
             'general_erc20_discovery':'indexer_checked' if d['complete'] else 'incomplete',
             'indexer_source':d['source'],'indexer_pages':len(d['pages']),'indexer_complete':d['complete'],
             'discovery_status':d.get('discovery_status','checked' if d['complete'] else 'incomplete'),
             'discovery_provider':d.get('provider'), 'history_window':d.get('history_window'), 'recent_window':d.get('recent_window'), 'discovery_filters':d.get('filters'),
            'discovery_sources':d.get('sources',[]),'discovery_completion_scope':d.get('completion_scope'),'complete_inventory_guaranteed':False,
             'candidate_balance_errors':len(c.get('balance_errors',[])),
             'positive_erc20_count_discovered':sum(t['chain_id']==n['chain_id'] and t['token_type']=='ERC20' for t in tokens),
             'mintclub_inventory_scan':None,'mintclub_registry_scan':c.get('registry_scan'),
             'inventory_policy':c.get('inventory_policy','full_registry'),'mintclub_wallet_discovery':id0_coverage(d),
             'mintclub_membership_scan':c.get('mintclub_membership_scan'),'candidate_scan':c.get('candidate_scan'),'notes':[]}
        if not d['complete']:row['notes'].append('General token discovery incomplete. See discovery evidence; this is not proof of no holdings.')
        if c.get('inventory_policy')=='wallet_candidates_v1':
            row['notes'].append('Mint Club candidates come from wallet transfer history and prior positive identities. Full registry enumeration is not requested and exhaustive holdings remain unknown.')
            if not d.get('mintclub_id0_discovery',{}).get('complete'):row['notes'].append('Mint Club ID0 transfer discovery is unavailable or unfinished. This is not proof of no holdings.')
        elif not c.get('registry_scan',{}).get('complete'):row['notes'].append('Mint Club registry scan incomplete. Unchecked balances remain unknown.')
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
    if time.monotonic()>=deadline:native_market={'evidence':[],'prices':{},'images':{}}
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
    # Quote-side prices value actual route outputs, not the input token's spot
    # price. Reuse one observed reference per output asset across held tokens.
    for token in tokens:
        for pool in token.get('dex_pools',[]):
            quote=pool.get('cashout_quote') or {}
            if quote.get('status')=='quoted':
                address=quote['output_address']
                reserve_candidates.setdefault((token['chain_id'],address.lower()),{'chain_id':token['chain_id'],'token_address':address,'token_type':'ERC20'})
        for quote in token.get('liquidation_routes',[]):
            address=quote['output_address']
            reserve_candidates.setdefault((token['chain_id'],address.lower()),{'chain_id':token['chain_id'],'token_address':address,'token_type':'ERC20'})
    from cashout import TERMINAL_ASSETS
    reserve_candidates=dict(sorted(reserve_candidates.items(),key=lambda item:item[0] not in TERMINAL_ASSETS))
    with ThreadPoolExecutor(max_workers=5) as executor:
        reserve_rows=list(executor.map(lambda t:dex_fetch(t,folder,deadline,attempt_limit=2),reserve_candidates.values()))
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
            'Mint Club wallet candidate mode verifies bond membership before ID0 balances and does not enumerate the full registry. Full inventory mode separately enumerates reachable bond assets. Neither completed provider pages nor a finite route search proves exhaustive holdings or cash-out coverage. Deposits and stakes are outside direct wallet balances.',
            'Market review selects one supported indexed pool or a funded curve route per asset. Other factories, pools, custom fee tiers and unindexed venues remain unsearched. A representative quote is not a best-price guarantee.',
            'DEX TVL and curve reserves describe the entire pool or curve. Spot wallet values are estimates, distinct from executable cash-out value.',
            'Full-wallet burn quotes subtract the recorded creator royalty and exclude gas. Nested reserve backing overlaps and must not be summed as independent cash reserves.',
            'Testnet assets are excluded from USD totals. Missing prices stay unknown.'],
        'actions':{'paid_provider_calls':None,'provider_billing':'Not determined; provider allowance can be consumed.','signatures':0,'approvals':0,'swaps':0,'transfers':0,'rpc_read_only':True},
        'pipeline':{'version':2,'entrypoint':'wallet.py','market_scope':market_scope,'resumable':True,'market_pending':market_pending,'registry_cache':'Shared append-only asset identity cache. Wallet balances are not reused between wallets.'},
        'evidence_files':[f.name for f in sorted(folder.glob('*.json')) if f.name not in ('results.json','market-prices.json')]}
    if holdings_source:result['pipeline'].update(phase='sell',holdings_snapshot=holdings_source)
    atomic(folder/'results.json',result)
    prices=[]
    for t in tokens:
        p=dex_price(t,None)
        if p:prices.append({'chain_id':t['chain_id'],'address':t['token_address'],**p})
    atomic(folder/'market-prices.json',{'observed_at':result['compiled_at'],'wallet_address':wallet['address'],'balance_refresh':not bool(holdings_source),
        'native_usd':{k.removesuffix('_USD'):{'usd':float(p['value']),'observed_at':p.get('observed_at'),
            'source':p.get('source'),'asset_id':p.get('asset_id'),'basis':p.get('basis','Market index')} for k,p in refs.items()},
        'tokens':prices+reserve_prices,'note':'DEX and reserve prices observed during this run. Curve spot prices use recorded on-chain state. Unknown prices remain null.'})
    atomic(folder/'market-prices.json',refresh_metadata(result,read(folder/'market-prices.json'),folder,native_images=native_market['images']))
    atomic(folder/'market-prices.json',retain_price_evidence(read(folder/'market-prices.json'),previous_prices))
    from cashout import annotate
    annotate(result,read(folder/'market-prices.json'))
    for n in networks:
        if n['environment']!='mainnet':continue
        held=[t for t in tokens if t['chain_id']==n['chain_id']]
        checked=sum(t.get('asset_review',{}).get('status') in ('quoted','unknown') for t in held)
        quoted=sum(t.get('asset_review',{}).get('status')=='quoted' for t in held)
        event('onchain_progress',operation='asset_review',chain_id=n['chain_id'],total=len(held),checked=checked,quoted=quoted,unknown=checked-quoted)
    result['evidence_files']=[f.name for f in sorted(folder.glob('*.json')) if f.name not in ('results.json','market-prices.json')]
    atomic(folder/'results.json',result)
    report(result,folder)
    if market_pending or research_pending:
        continuation_checkpoint(checkpoint_folder,[] if holdings_source else discovered,market_pending)
        result['pipeline']['market_pending']=market_pending
        result['pipeline']['research_pending']=research_pending
        result['status']='completed_with_coverage_gaps'
        index=1
        while (checkpoint_folder/f'market-initial-{index:04d}').exists():index+=1
        previous_folder=folder;folder=checkpoint_folder/f'market-initial-{index:04d}';folder.mkdir(parents=True)
        atomic(folder/'market-prices.json',read(previous_folder/'market-prices.json'))
        result['evidence_files']=['market-prices.json']
        result['limitations'].append('Research has saved unfinished work. Recorded balances and completed checks remain available. Pending discovery ranges and market checks are not verified absent. Background jobs continue automatically unless cancelled or stalled.')
        atomic(folder/'results.json',result);report(result,folder);publish_snapshot(wallet,folder,result)
        event('first_evidence',snapshot=str(folder.relative_to(ROOT)))
        event('market_paused' if market_pending else 'research_paused')
        if market_pending:raise MarketPause('Market verification paused at its time budget. Saved checks are ready for continuation.')
        raise ResearchPause('Discovery has saved unfinished ranges. Saved checks are ready for continuation.')
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
        p.add_argument('--phase',choices=('holdings','sell','baseline','enrichment','full'),default='holdings')
        p.add_argument('--holdings-snapshot',help='Immutable holdings source for sell-route analysis.')
        p.add_argument('--inventory',choices=('market','full'),help='Full registry for holdings; market retains an explicitly requested legacy candidate scope. A resume retains its saved scope.')
    args=parser.parse_args()
    from kira_config import require_alchemy
    require_alchemy()
    # Serialize shared registry and cache writers for the entire run.
    with (os.fdopen(int(os.environ['KIRA_ANALYSIS_FD']), 'a') if os.environ.get('KIRA_ANALYSIS_FD') else (ROOT/'.analysis.lock').open('a')) as lock:
        try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:raise SystemExit('Another wallet analysis is running. Resume after it finishes.')
        read(ROOT/'session.json');registry=read(ROOT/'wallets.json');registered=read(ROOT/'networks.json')['networks']
        candidates=read(ASSETS/'sources/rpc-candidates.json')
        from chain_lifecycle import retired
        networks=[{**n,**next((c for c in candidates if c['chain_id']==n['chain_id']),{})} for n in registered if not retired(n['chain_id'])]
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
        manifest=None
        if args.resume:
            folder=(ROOT/args.resume).resolve()
            if not folder.is_relative_to(ROOT/'snapshots'):raise ValueError('Resume path must be within snapshots/.')
            manifest=read(folder/'run.json')
            if manifest['wallet_address'].lower()!=wallet['address_key']:raise ValueError('Resume wallet mismatch.')
            relative=str(folder.relative_to(ROOT))
            published=any(w.get('latest_snapshot',{}).get('directory')==relative for w in registry['wallets']) or any(r.get('snapshot')==relative for r in registry.get('research_runs',[]))
            if manifest.get('completed_at') or published:raise ValueError('Published snapshots are immutable. Use refresh without --resume for a new analysis.')
            policy=inventory_policy(args.inventory,manifest)
        else:
            policy=inventory_policy('full' if args.phase in ('holdings','baseline','sell') else args.inventory)
            if os.environ.get('KIRA_JOB_SNAPSHOT'):
                folder=(ROOT/os.environ['KIRA_JOB_SNAPSHOT']).resolve()
                if not folder.is_relative_to(ROOT/'snapshots'):raise ValueError('Job path must be within snapshots/.')
            else:
                slug=re.sub(r'[^A-Za-z0-9_-]+','-',wallet['tags'][0] if wallet['tags'] else wallet['address_key']).strip('-')
                folder=ROOT/'snapshots'/slug/(time.strftime('%Y-%m-%dT%H%M%S')+'-'+wallet['address_key'][2:10])
            folder.mkdir(parents=True,exist_ok=bool(os.environ.get('KIRA_JOB_SNAPSHOT')))
        relative=str(folder.relative_to(ROOT))
        atomic(folder/'run.json',{'wallet_address':wallet['address'],'tags':wallet['tags'],'inventory_policy':policy,**({'holdings_snapshot':args.holdings_snapshot or (manifest or {}).get('holdings_snapshot')} if args.phase=='sell' else {}),'started_or_resumed_at':h.now(),'status':'running'})
        event('registered',wallet=wallet['address'],tags=wallet['tags'],snapshot=str(folder.relative_to(ROOT)))
        try:
            if args.phase in ('holdings','baseline'):
                source_check(networks,folder)
                result=research_holdings(wallet,folder,networks)
            elif args.phase=='sell':
                source=args.holdings_snapshot or (manifest or {}).get('holdings_snapshot')
                if not source:raise ValueError('Sell-route analysis requires a saved holdings source.')
                discovered=saved_holdings(wallet,source,folder)
                result=finish(wallet,folder,networks,discovered,holdings_source=source)
            else:
                source_check(networks,folder)
                phase_networks=networks
                known=read(ASSETS/'sources/known-tokens.json')['tokens']
                # Earlier positive identities are candidates, never reused balances.
                prior=prior_candidates(wallet)
                market=policy=='wallet_candidates_v1'
                def acquire(n):
                    row=discover(wallet['address'],n,folder,budget=45 if market else 60,continue_only=bool(args.resume))
                    if market:row['mintclub_id0_discovery']=discover_mintclub_id0(wallet['address'],n,folder,continue_only=bool(args.resume))
                    return row
                if market:
                    discovered=acquire_candidate_slices(wallet['address'],phase_networks,folder,policy,acquire,prior,known)
                else:
                    with ThreadPoolExecutor(max_workers=5) as executor:discovered=list(executor.map(acquire,phase_networks))
                    atomic(folder/'scan-input.json',candidate_input(wallet['address'],phase_networks,policy,discovered,prior,known))
                event('discovery',complete_chains=sum(d['complete'] for d in discovered),candidates=sum(len(d['tokens']) for d in discovered))
                if not market:run_node('scan',folder/'scan-input.json',folder)
                result=finish(wallet,folder,networks,discovered)
            publish_snapshot(wallet,folder,result)
            atomic(folder/'run.json',{'wallet_address':wallet['address'],'tags':wallet['tags'],'inventory_policy':policy,'completed_at':h.now(),'status':result['status']})
            event('published',snapshot=relative,counts=result['counts'],status=result['status'],viewer='http://127.0.0.1:8765')
        except Exception as error:
            atomic(folder/'run.json',{'wallet_address':wallet['address'],'tags':wallet['tags'],'inventory_policy':policy,**({'holdings_snapshot':args.holdings_snapshot or (manifest or {}).get('holdings_snapshot')} if args.phase=='sell' else {}),'failed_at':h.now(),'status':'failed','error':h.redact(str(error))})
            event('market_paused' if isinstance(error,MarketPause) else 'research_paused' if isinstance(error,ResearchPause) else 'failed',error=h.redact(str(error)),resume=str(folder.relative_to(ROOT)))
            raise SystemExit(1)


if __name__=='__main__':
    main()
