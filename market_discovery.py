"""Supplement indexed markets with official Uniswap records and read-only factories."""
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import re
import subprocess
import time
from market_records import collected_markets, merge_pools

UNISWAP='https://interface.gateway.uniswap.org/v1/graphql'
CHAINS={1:'ETHEREUM',8453:'BASE',10:'OPTIMISM',42161:'ARBITRUM',137:'POLYGON',56:'BNB',43114:'AVALANCHE',81457:'BLAST',130:'UNICHAIN',7777777:'ZORA',4663:'ROBINHOOD'}
SLUGS={cid:name.lower() for cid,name in CHAINS.items()}
SLUGS[56]='bsc'


def uniswap_query(tokens, cursors=None):
    cursors=cursors or {};fields=[];aliases={}
    for i,t in enumerate(tokens):
        cid=t['chain_id'];address=t['token_address'].lower()
        if cid not in CHAINS or not re.fullmatch(r'0x[0-9a-f]{40}',address):continue
        for version,field,identifier in (('v2','topV2Pairs','address'),('v3','topV3Pools','address'),('v4','topV4Pools','poolId')):
            key=f'{cid}:{address}:{version}'
            if key in cursors and cursors[key] is None:continue
            alias=f't{i}_{version}';aliases[alias]=(cid,address,version,key)
            cursor=',tvlCursor:'+str(cursors[key]) if key in cursors else ''
            fields.append(f'{alias}:{field}(chain:{CHAINS[cid]},first:50,tokenFilter:"{address}"{cursor})'+'{'+identifier+' feeTier totalLiquidity{value currency} token0{address symbol} token1{address symbol}}' if version!='v2' else f'{alias}:{field}(chain:{CHAINS[cid]},first:50,tokenFilter:"{address}"{cursor})'+'{address totalLiquidity{value currency} token0{address symbol} token1{address symbol}}')
    return {'query':'query KiraMarkets {'+' '.join(fields)+'}'},aliases


def uniswap_records(response, aliases, observed):
    pairs=[];status={};cursors={}
    data=response.get('data') or {} if isinstance(response,dict) else {}
    for alias,(cid,address,version,key) in aliases.items():
        rows=data.get(alias)
        status[key]='checked' if isinstance(rows,list) else 'unavailable'
        if not isinstance(rows,list):cursors[key]=None;continue
        for row in rows:
            pool=row.get('poolId') if version=='v4' else row.get('address')
            coins=[row.get('token0'),row.get('token1')]
            if not isinstance(pool,str) or not re.fullmatch(r'0x[0-9a-fA-F]{'+('64' if version=='v4' else '40')+r'}',pool) or not all(isinstance(c,dict) for c in coins):continue
            coins=[{**c,'address':c.get('address') or '0x'+'0'*40} for c in coins]
            if address not in {c['address'].lower() for c in coins}:continue
            liquidity=row.get('totalLiquidity') or {};value=liquidity.get('value') if liquidity.get('currency')=='USD' else None
            pairs.append({'chainId':SLUGS[cid],'pairAddress':pool,'dexId':'uniswap','labels':[version],
                'baseToken':coins[0],'quoteToken':coins[1],'liquidity':{'usd':value} if value is not None else None,
                'fee_bps':row['feeTier']/100 if isinstance(row.get('feeTier'),(int,float)) else None,
                'url':'https://app.uniswap.org/explore/pools/'+('bnb' if cid==56 else SLUGS[cid])+'/'+pool})
        cursor=(rows[-1].get('totalLiquidity') or {}).get('value') if len(rows)>=50 else None
        cursors[key]=cursor if isinstance(cursor,(int,float)) and cursor>=0 else None
        if len(rows)>=50:status[key]='partial'
    return {'source':UNISWAP,'observed_at':observed,'response':pairs,'query_status':status,'provider_response':response},cursors


def fetch_official(url,body,*,deadline):
    import urllib.request
    import urllib.error
    # This public endpoint is the official Pools UI's read API. No API key.
    if time.monotonic()>=deadline:return {'research_pending':True}
    request=urllib.request.Request(UNISWAP,data=json.dumps(body).encode(),headers={
        'Content-Type':'application/json','Origin':'https://app.uniswap.org','User-Agent':'Mozilla/5.0 (compatible; kira-wallet)'})
    try:
        with urllib.request.urlopen(request,timeout=max(0.1,min(20,deadline-time.monotonic()))) as response:
            raw=response.read(4_000_001)
            if len(raw)>4_000_000:return {'transport_error':{'code':'response_limit'}}
            return json.loads(raw)
    except urllib.error.HTTPError as error:return {'transport_error':{'status':error.code}}
    except (OSError,ValueError):return {'transport_error':{'code':'unavailable'}}


def discover(snapshot, folder, *, deadline=None, fetch=None, factories=True):
    """No wallet reads or sale quotes. Missing provider records remain unknown."""
    import wallet
    from chain_lifecycle import retired
    fetch=fetch or fetch_official;deadline=deadline or time.monotonic()+60
    folder=Path(folder);path=folder/'supplemental-markets.json'
    previous=wallet.read(path) if path.exists() else {}
    active={c['chain_id'] for c in snapshot.get('coverage',[]) if c.get('environment')=='mainnet' and not retired(c['chain_id'])}
    # The alternate source covers Mint Club's simultaneous markets. Ordinary
    # ERC20 holdings still receive the default full DexScreener batch lookup.
    tokens=[t for t in snapshot['tokens'] if t.get('mintclub') and t.get('token_type','ERC20')=='ERC20' and t['chain_id'] in active]
    wanted={(t['chain_id'],t['token_address'].lower()) for t in tokens}
    records=[];statuses={};groups=[tokens[i:i+8] for i in range(0,len(tokens),8)]
    def get(group):
        cursors={};seen=set();evidence=[]
        while time.monotonic()<deadline:
            body,aliases=uniswap_query(group,cursors)
            if not aliases:break
            signature=json.dumps(cursors,sort_keys=True)
            if signature in seen:break
            seen.add(signature)
            response=fetch(UNISWAP,body,deadline=deadline)
            record,next_cursors=uniswap_records(response,aliases,wallet.h.now());cursors.update(next_cursors);evidence.append(record)
            if not any(v is not None for v in cursors.values()):break
        return evidence
    with ThreadPoolExecutor(max_workers=2) as executor:
        for evidence in executor.map(get,groups):
            records.extend(evidence)
            for record in evidence:statuses.update(record['query_status'])
    markets=collected_markets(records,SLUGS,wanted,previous.get('markets',[]))
    # Source errors cannot remove earlier observed pools.
    result={'observed_at':wallet.h.now(),'markets':markets,'records':records,'query_status':statuses,
            'scope':'Official indexed pools and bounded common-quote factory checks. Not proof that undiscovered pools do not exist.',
            'status':'partial' if any(v!='checked' for v in statuses.values()) or len(statuses)<3*sum(t['chain_id'] in CHAINS for t in tokens) else 'checked'}
    wallet.atomic(path,result)
    if factories and tokens and time.monotonic()<deadline:
        input_path=folder/'factory-market-input.json';output_path=folder/'factory-markets.json'
        networks=json.loads((Path(__file__).parent/'networks.json').read_text())['networks']
        wallet.atomic(input_path,{'tokens':tokens,'networks':networks,'budget_ms':max(1,int((deadline-time.monotonic())*1000))})
        try:
            process=subprocess.run(['node',str(Path(__file__).with_name('market-discovery.cjs')),str(input_path),str(output_path)],capture_output=True,timeout=max(1,deadline-time.monotonic()+2))
            if process.returncode!=0:result['factory_status']='unavailable'
        except subprocess.TimeoutExpired:result['factory_status']='partial'
        if output_path.exists():
            factory=wallet.read(output_path);by_id={r['id']:r for r in result['markets']}
            for row in factory.get('markets',[]):
                by_id[row['id']]={'id':row['id'],'pools':merge_pools(by_id.get(row['id'],{}).get('pools',[]),row['pools'])}
            result['markets']=list(by_id.values());result['factory_status']=factory['status']
    if result.get('factory_status') in ('partial','unavailable'):result['status']='partial'
    wallet.atomic(path,result)
    return result
