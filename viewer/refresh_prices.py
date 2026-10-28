"""Refresh price references and bounded direct-sale quotes for registered snapshots."""
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
import argparse
import fcntl
import json
import os
import subprocess
import sys
import time

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import research as h
from model import dex_price, within, number
from curve_pricing import enrich, resolve, index_prices
from native_assets import market_metadata
from market_records import collected_markets, canonical_token
from chain_lifecycle import retired
from token_images import refresh_catalog
from wallet import DEX as DEX_CHAINS, retain_price_evidence, event

def price_stage(phase, **counts):
 event('price_refresh',phase=phase,**counts)

def fetch_market_prices(requests):
 # Report completed requests without waiting behind a slow first response.
 # Keep input order for the existing price-selection policy.
 price_stage('markets',checked=0,total=len(requests))
 fetched=[None]*len(requests);last_progress=time.monotonic()
 def get(url):return {'source':url,'observed_at':h.now(),'response':h.fetch(url)}
 with ThreadPoolExecutor(max_workers=5) as executor:
  futures={executor.submit(get,url):index for index,url in enumerate(requests)}
  for checked,future in enumerate(as_completed(futures),1):
   fetched[futures[future]]=future.result()
   if checked==len(requests) or time.monotonic()-last_progress>=1:
    price_stage('markets',checked=checked,total=len(requests));last_progress=time.monotonic()
 return fetched

parser=argparse.ArgumentParser();parser.add_argument('--wallet',help='Registered wallet address or tag. Omit to refresh all registered snapshots.')
args=parser.parse_args()
from kira_config import require_alchemy
require_alchemy()
analysis_lock=os.fdopen(int(os.environ['KIRA_ANALYSIS_FD']), 'a') if os.environ.get('KIRA_ANALYSIS_FD') else (h.ROOT/'.analysis.lock').open('a')
try:fcntl.flock(analysis_lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
except BlockingIOError:raise SystemExit('Another wallet or price analysis is running. Retry after it finishes.')
registry=json.loads((h.ROOT/'wallets.json').read_text())
selected=[w for w in registry['wallets'] if w.get('latest_snapshot') and (not args.wallet or args.wallet.lower()==w['address_key'] or args.wallet in w['tags'])]
if not selected:raise SystemExit('No analysed registered wallet matches this selection.')

for w in selected:
 folder=within(h.ROOT,w['latest_snapshot']['directory']);path=within(h.ROOT,w['latest_snapshot']['result']);snapshot=json.loads(path.read_text())
 snapshot={**snapshot,'tokens':[canonical_token(t) for t in snapshot['tokens'] if not retired(t['chain_id'])],
           'coverage':[c for c in snapshot.get('coverage',[]) if not retired(c['chain_id'])]}
 price_stage('native')
 native_market=market_metadata(snapshot.get('coverage',[]))
 import uuid
 evidence_folder=folder/'price-evidence'/uuid.uuid4().hex
 if os.environ.get('KIRA_JOB_SNAPSHOT'):
  evidence_folder=(h.ROOT/os.environ['KIRA_JOB_SNAPSHOT']).resolve()
  if not evidence_folder.is_relative_to((h.ROOT/'snapshots').resolve()):raise ValueError('Job path must be within snapshots/.')
 if native_market['evidence']:h.save(evidence_folder/'native-market.json',native_market['evidence'])
 pools={}
 for t in snapshot['tokens']:
  chain=DEX_CHAINS.get(t['chain_id'])
  if chain:
   pools.setdefault(chain,set()).update(p['pool'] for p in t['dex_pools'])
 requests=[]
 for chain_id,chain in DEX_CHAINS.items():
  addresses=sorted({t['token_address'].lower() for t in snapshot['tokens'] if t['chain_id']==chain_id and t.get('token_type')!='ERC1155'})
  requests += ['https://api.dexscreener.com/tokens/v1/'+chain+'/'+','.join(addresses[i:i+30]) for i in range(0,len(addresses),30)]
 for chain,addresses in pools.items():
  addresses=sorted(addresses)
  requests += ['https://api.dexscreener.com/latest/dex/pairs/'+chain+'/'+','.join(addresses[i:i+25]) for i in range(0,len(addresses),25)]
 reserves={(t['chain_id'],m['reserve_token']):m['reserve_symbol'] for t in snapshot['tokens'] if (m:=t.get('mintclub'))}
 # Every wallet needs an independent ETH reference, even without a WETH-backed curve.
 reserves[(8453,'0x4200000000000000000000000000000000000006')]='WETH'
 for (chain_id,address),symbol in reserves.items():
  chain=DEX_CHAINS.get(chain_id)
  if chain:requests.append('https://api.dexscreener.com/token-pairs/v1/'+chain+'/'+address)
 fetched=fetch_market_prices(requests)
 pairs=[]
 for r in fetched:
  response=r['response'];pairs.extend(response if isinstance(response,list) else (response.get('pairs') or []) if isinstance(response,dict) else [])
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
 priced={(p['chain_id'],p['address'].lower()) for p in prices}
 mainnets={c['chain_id'] for c in snapshot.get('coverage',[]) if c.get('environment')=='mainnet'}
 price_stage('index')
 indexed=index_prices([(t['chain_id'],t['token_address']) for t in snapshot['tokens']
                       if t['chain_id'] in mainnets and t.get('token_type','ERC20')=='ERC20' and not t.get('mintclub')
                       and (t['chain_id'],t['token_address'].lower()) not in priced],evidence_folder)
 prices.extend(indexed['tokens'])
 curve_input=evidence_folder/'curve-refresh-input.json';h.save(curve_input,snapshot)
 price_stage('curves')
 try:node=subprocess.run(['node',str(Path(__file__).with_name('refresh-curve-prices.cjs')),str(curve_input)],capture_output=True,text=True,timeout=180)
 except subprocess.TimeoutExpired:rpc={'tokens':[],'errors':[{'code':'curve_budget','message':'Fresh curve checks reached their bound. Previous usable quotes are retained.'}]}
 else:
  rpc=json.loads(node.stdout)
  if node.returncode!=0:raise SystemExit('Curve refresh failed: '+h.redact(rpc))
 by_address={(p['chain_id'],p['address'].lower()):p for p in prices}
 # Preserve the established Base WETH market reference. Native metadata fills gaps.
 eth_reference=next((p for p in prices if p.get('chain_id')==8453 and p['address'].lower()=='0x4200000000000000000000000000000000000006' and p.get('usd') is not None),None)
 eth=eth_reference['usd'] if eth_reference else None
 fresh_native=dict(native_market['prices'])
 if eth is not None:fresh_native['ETH_USD']={'value':eth,'observed_at':eth_reference.get('observed_at'),'source':eth_reference.get('source'),'basis':'DEX market'}
 else:eth=fresh_native.get('ETH_USD',{}).get('value')
 if not native_market['prices'] and not prices:raise SystemExit('Price refresh failed. Previous market cache preserved.')
 for p in rpc['tokens']:
  key=(p['chain_id'],p['address'].lower())
  if 'error' in p:continue
  if p.get('price_in_weth') is not None:p['usd']=p['price_in_weth']*eth if eth is not None else None;p['quality']='estimated'
  # Keep a valid DEX quote as the market price; retain current curve spot metadata.
  if key in by_address and by_address[key].get('usd') is not None and p['basis']=='Curve spot':
   by_address[key].update({k:v for k,v in p.items() if k.startswith('curve_') or k in ['reserve_symbol','block_number']})
  else:
   if p['basis']=='Curve spot' and number(p.get('curve_reserve'))==0:p={**p,'usd':None,'quality':'unfunded'}
   by_address[key]=p
 native_prices={k.removesuffix('_USD'):{'usd':float(p['value']),'observed_at':p.get('observed_at'),'source':p.get('source'),'basis':p.get('basis','Market index')} for k,p in snapshot.get('price_references',{}).items() if p.get('value') is not None}
 previous=folder/'market-prices.json'
 previous_market=json.loads(previous.read_text()) if previous.exists() else {}
 native_prices.update(previous_market.get('native_usd',{}))
 for key,row in fresh_native.items():
  native_prices[key.removesuffix('_USD')]={**row,'usd':row['value']};native_prices[key.removesuffix('_USD')].pop('value')
 output={'observed_at':h.now(),'wallet_address':w['address'],'balance_refresh':False,
         'native_usd':native_prices,'tokens':list(by_address.values()),'markets':collected_markets(fetched,DEX_CHAINS,previous=previous_market.get('markets',[])),
         'source_requests':fetched,'rpc_price_state':rpc,
         'note':'Prices and bounded sale estimates. Portfolio balances and research coverage remain at their recorded analysis time.'}
 from market_discovery import discover
 from market_records import merge_pools
 price_stage('discovery')
 supplemental=discover(snapshot,evidence_folder)
 merged={row['id']:row for row in output['markets']}
 for row in supplemental['markets']:
  merged[row['id']]={'id':row['id'],'pools':merge_pools(merged.get(row['id'],{}).get('pools',[]),row['pools'])}
 output['markets']=list(merged.values());output['market_discovery_status']=supplemental['status']
 destination=folder/'market-prices.json';temporary=destination.with_suffix('.json.tmp')
 # Reuse the fresh batched curve observations before traversing missing reserves.
 # These are price facts, never fresh wallet balances.
 graph=[{'chain_id':p['chain_id'],'address':p['address'],'is_curve':True,
         'price_in_reserve':p['curve_price_in_reserve'],'curve_reserve':p['curve_reserve'],
         'reserve_token':p['reserve_token'],'reserve_symbol':p['reserve_symbol'],
         'funded':p['funded'],'source':p.get('source'),'observed_at':p.get('observed_at'),'block_number':p.get('block_number')}
        for p in rpc['tokens'] if p.get('basis')=='Curve spot' and p.get('reserve_token') and type(p.get('funded')) is bool and p.get('curve_price_in_reserve') is not None]
 resolved={(p['chain_id'],p['address'].lower()):p for p in output['tokens']}
 for p in resolve(graph,output['tokens']):resolved[(p['chain_id'],p['address'].lower())]=p
 output['tokens']=list(resolved.values())
 missing=[t for t in snapshot['tokens'] if t.get('mintclub') and resolved.get((t['chain_id'],t['token_address'].lower()),{}).get('usd') is None
          and resolved.get((t['chain_id'],t['token_address'].lower()),{}).get('quality') not in ('unfunded','unreliable')]
 if missing:
  price_stage('reserves')
  from wallet import MarketPause
  try:output=enrich({**snapshot,'tokens':missing},output,evidence_folder)
  except MarketPause:
   output['reserve_price_status']='partial'
   graph_file=evidence_folder/'reserve-graph.json'
   if graph_file.exists():
    partial={(p['chain_id'],p['address'].lower()):p for p in output['tokens']}
    for p in resolve(json.loads(graph_file.read_text()).get('tokens',[]),output['tokens']):partial[(p['chain_id'],p['address'].lower())]=p
    output['tokens']=list(partial.values())
 # Preserve historical quotes on a provider gap, after fresh reserve derivation.
 # Fresh unfunded/unreliable evidence must invalidate an old estimate.
 output=retain_price_evidence(output,previous_market)
 retained=sum(bool(p.get('retained_from_previous')) for p in output['tokens'])
 output['retained_price_records']=retained
 if retained:output['note']+=f' {retained} token price references retain their earlier observation times because fresh USD was unavailable.'
 from sell_quotes import enrich as enrich_sell_quotes
 price_stage('quotes')
 output=enrich_sell_quotes(snapshot,output,evidence_folder/'sell-quotes',previous=previous_market)
 price_stage('artwork')
 try:refresh_catalog([snapshot],h.ROOT,native_images=native_market['images'],market_metadata=fetched)
 except (OSError,ValueError):output['image_refresh_status']='unavailable'
 from kira_jobs import atomic
 job_folder=evidence_folder.resolve()
 if not job_folder.is_relative_to((h.ROOT/'snapshots').resolve()):raise ValueError('Job path must be within snapshots/.')
 overlay=job_folder/'prices.json'
 output['snapshot_id']=w['latest_snapshot']['directory']
 missing_native=any(c.get('environment')=='mainnet' and float(c.get('native_balance') or 0)>0 and c.get('native_symbol')+'_USD' not in fresh_native for c in snapshot.get('coverage',[]))
 # Name each gap so a partial price job explains itself.
 output['job_result_gaps']=[name for name,found in (
     ('market_discovery_partial',output.get('market_discovery_status')=='partial'),
     ('native_price_missing',missing_native),
     ('earlier_prices_retained',bool(retained)),
     ('index_price_missing',indexed['status']=='partial'),
     ('reserve_pricing_partial',output.get('reserve_price_status')=='partial' or bool((output.get('reserve_price_graph') or {}).get('errors'))),
     ('curve_reads_incomplete',bool(rpc.get('errors')) or any('error' in p for p in rpc['tokens'])),
     ('provider_request_failed',any(isinstance(r['response'],dict) and 'transport_error' in r['response'] for r in fetched))) if found]
 output['job_result_status']='completed_with_coverage_gaps' if output['job_result_gaps'] else 'completed'
 price_stage('saving')
 atomic(overlay,output)
 if os.environ.get('KIRA_JOB_SNAPSHOT'):atomic(job_folder/'price-publication.json',{'schema_version':1,'snapshot_id':w['latest_snapshot']['directory'],
     'overlay':str(overlay.relative_to(h.ROOT)),'projection':str(destination.relative_to(h.ROOT)),
     'status':output['job_result_status']})
 temporary.write_text(json.dumps(output,indent=2)+'\n');os.replace(temporary,destination)
 print(json.dumps({'wallet':w['address'],'tag':w['tags'],'price_records':len(output['tokens']),'observed_at':output['observed_at'],'errors':sum(isinstance(r['response'],dict) and 'transport_error' in r['response'] for r in fetched)}))
