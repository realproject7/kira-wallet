"""Refresh price references for registered snapshots. Agent CLI, never a viewer action."""
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import argparse
import fcntl
import json
import os
import subprocess
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import research as h
from model import dex_price, within
from curve_pricing import enrich
DEX_CHAINS={1:'ethereum',8453:'base',10:'optimism',42161:'arbitrum',137:'polygon',56:'bsc',43114:'avalanche',81457:'blast',130:'unichain',7777777:'zora',33139:'apechain',177:'hashkey',8217:'kaia',7560:'cyber',109:'shibarium',4663:'robinhood'}

parser=argparse.ArgumentParser();parser.add_argument('--wallet',help='Registered wallet address or tag. Omit to refresh all registered snapshots.')
args=parser.parse_args()
analysis_lock=os.fdopen(int(os.environ['KIRA_ANALYSIS_FD']), 'a') if os.environ.get('KIRA_ANALYSIS_FD') else (h.ROOT/'.analysis.lock').open('a')
try:fcntl.flock(analysis_lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
except BlockingIOError:raise SystemExit('Another wallet or price analysis is running. Retry after it finishes.')
registry=json.loads((h.ROOT/'wallets.json').read_text())
selected=[w for w in registry['wallets'] if w.get('latest_snapshot') and (not args.wallet or args.wallet.lower()==w['address_key'] or args.wallet in w['tags'])]
if not selected:raise SystemExit('No analysed registered wallet matches this selection.')

for w in selected:
 folder=within(h.ROOT,w['latest_snapshot']['directory']);path=within(h.ROOT,w['latest_snapshot']['result']);snapshot=json.loads(path.read_text())
 pools={}
 for t in snapshot['tokens']:
  chain=DEX_CHAINS.get(t['chain_id'])
  if chain:
   pools.setdefault(chain,set()).update(p['pool'] for p in t['dex_pools'])
 requests=[]
 for chain,addresses in pools.items():
  addresses=sorted(addresses)
  requests += ['https://api.dexscreener.com/latest/dex/pairs/'+chain+'/'+','.join(addresses[i:i+25]) for i in range(0,len(addresses),25)]
 reserves={(t['chain_id'],m['reserve_token']):m['reserve_symbol'] for t in snapshot['tokens'] if (m:=t.get('mintclub'))}
 # Every wallet needs an independent ETH reference, even without a WETH-backed curve.
 reserves[(8453,'0x4200000000000000000000000000000000000006')]='WETH'
 for (chain_id,address),symbol in reserves.items():
  chain=DEX_CHAINS.get(chain_id)
  if chain:requests.append('https://api.dexscreener.com/token-pairs/v1/'+chain+'/'+address)
 def get(url):return {'source':url,'observed_at':h.now(),'response':h.fetch(url)}
 fetched=list(ThreadPoolExecutor(max_workers=5).map(get,requests))
 pairs=[]
 for r in fetched:
  response=r['response'];pairs.extend(response if isinstance(response,list) else response.get('pairs') or [])
 prices=[]
 for t in snapshot['tokens']:
  candidates=[p for p in pairs if p['chainId']==DEX_CHAINS.get(t['chain_id']) and p['baseToken']['address'].lower()==t['token_address'].lower()]
  shadow={**t,'dex_pools':[{'reported_price_usd':p.get('priceUsd'),'paired_tokens':[p['baseToken'],p['quoteToken']],
             'reported_liquidity':p.get('liquidity'),'source_url':p['url']} for p in candidates], 'indexer_price_references':[]}
  p=dex_price(shadow,h.now())
  if p:prices.append({'chain_id':t['chain_id'],'address':t['token_address'],**p})
 for (chain_id,address),symbol in reserves.items():
  options=[p for p in pairs if p['chainId']==DEX_CHAINS.get(chain_id) and p['baseToken']['address'].lower()==address.lower() and p.get('priceUsd') and p.get('liquidity',{}).get('usd',0)>0]
  if options:
   shadow={'token_address':address,'dex_pools':[{'reported_price_usd':p.get('priceUsd'),'paired_tokens':[p['baseToken'],p['quoteToken']],'reported_liquidity':p.get('liquidity'),'source_url':p['url']} for p in options]}
   p=dex_price(shadow,h.now())
   if p:prices.append({'chain_id':chain_id,'address':address,**p,'reserve_symbol':symbol})
 node=subprocess.run(['node',str(Path(__file__).with_name('refresh-curve-prices.cjs')),str(path)],capture_output=True,text=True,timeout=60)
 rpc=json.loads(node.stdout)
 if node.returncode!=0:raise SystemExit('Curve refresh failed: '+h.redact(rpc))
 by_address={(p['chain_id'],p['address'].lower()):p for p in prices}
 eth=next((p['usd'] for p in prices if p.get('chain_id')==8453 and p['address'].lower()=='0x4200000000000000000000000000000000000006' and p.get('usd') is not None),None)
 if eth is None:raise SystemExit('ETH price refresh failed. Previous market cache preserved.')
 for p in rpc['tokens']:
  key=(p['chain_id'],p['address'].lower())
  if 'error' in p:continue
  if p.get('price_in_weth') is not None:p['usd']=p['price_in_weth']*eth;p['quality']='estimated'
  # Keep a valid DEX quote as the market price; retain current curve spot metadata.
  if key in by_address and by_address[key].get('usd') is not None and p['basis']=='Curve spot':
   by_address[key].update({k:v for k,v in p.items() if k.startswith('curve_') or k in ['reserve_symbol','block_number']})
  else:by_address[key]=p
 native_prices={k.removesuffix('_USD'):{'usd':float(p['value']),'observed_at':p.get('observed_at')} for k,p in snapshot.get('price_references',{}).items() if p.get('value') is not None}
 previous=folder/'market-prices.json'
 if previous.exists():native_prices.update(json.loads(previous.read_text()).get('native_usd',{}))
 native_prices['ETH']={'usd':eth,'observed_at':h.now()}
 output={'observed_at':h.now(),'wallet_address':w['address'],'balance_refresh':False,
         'native_usd':native_prices,'tokens':list(by_address.values()),
         'source_requests':fetched,'rpc_price_state':rpc,
         'note':'Prices only. Balances and research coverage remain at their recorded analysis time.'}
 destination=folder/'market-prices.json';temporary=destination.with_suffix('.json.tmp')
 output=enrich(snapshot,output,folder)
 if os.environ.get('KIRA_JOB_SNAPSHOT'):
  from kira_jobs import atomic
  job_folder=(h.ROOT/os.environ['KIRA_JOB_SNAPSHOT']).resolve()
  if not job_folder.is_relative_to(h.ROOT/'snapshots'):raise ValueError('Job path must be within snapshots/.')
  overlay=job_folder/'prices.json'
  output['snapshot_id']=w['latest_snapshot']['directory']
  output['job_result_status']='completed_with_coverage_gaps' if rpc.get('errors') or any('error' in p for p in rpc['tokens']) or any(isinstance(r['response'],dict) and 'transport_error' in r['response'] for r in fetched) else 'completed'
  atomic(overlay,output)
  atomic(job_folder/'price-publication.json',{'schema_version':1,'snapshot_id':w['latest_snapshot']['directory'],
      'overlay':str(overlay.relative_to(h.ROOT)),'projection':str(destination.relative_to(h.ROOT)),
      'status':output['job_result_status']})
 temporary.write_text(json.dumps(output,indent=2)+'\n');os.replace(temporary,destination)
 print(json.dumps({'wallet':w['address'],'tag':w['tags'],'price_records':len(output['tokens']),'observed_at':output['observed_at'],'errors':sum(isinstance(r['response'],dict) and 'transport_error' in r['response'] for r in fetched)}))
