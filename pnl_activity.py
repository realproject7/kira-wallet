"""Explicit, bounded Alchemy evidence collection for the external research agent."""
from datetime import datetime, timedelta, timezone
import fcntl
import hashlib
import json
import re
import time

from kira_jobs import JobError, atomic, now
from kira_pnl import HASH, N, S, asset_id, date, encode, mainnet, require

ARGS={'wallet':S,'chain_id':N,'from_block':N,'to_block':N,'block_hash':S,
      'direction':{'type':'string','enum':['incoming','outgoing']},'include_internal':{'type':'boolean'},
      'page_key':S,'renew_cursor':{'type':'boolean'},'daily_budget_cu':N}
REQUIRED=['wallet','chain_id','from_block','to_block','block_hash','direction','daily_budget_cu']
PAGE_CU=120

def fetch(root, address, args):
    from wallet import ALCHEMY
    mainnet(root,args['chain_id'])
    network=ALCHEMY.get(args['chain_id'])
    require(network and type(args['from_block']) is int and 0<=args['from_block']<=args['to_block']<=N['maximum'],
            'Choose an Alchemy-supported mainnet and an ordered, finalized block range.')
    require(re.fullmatch(HASH,args['block_hash']) and args['direction'] in ('incoming','outgoing'),'Supply the closing block hash and transfer direction.')
    require('page_key' not in args or re.fullmatch(r'[A-Za-z0-9_-]{1,200}',args['page_key']), 'Use the returned page key.')
    categories=['external','erc20','erc721','erc1155']
    if args.get('include_internal'):categories.append('internal')
    params={'fromBlock':hex(args['from_block']),'toBlock':hex(args['to_block']),
            ('toAddress' if args['direction']=='incoming' else 'fromAddress'):address,'category':categories,
            'withMetadata':True,'maxCount':hex(50),'order':'asc','excludeZeroValue':False}
    if args.get('page_key'):params['pageKey']=args['page_key']
    request={'jsonrpc':'2.0','id':1,'method':'alchemy_getAssetTransfers','params':[params]}
    return collect(root,network,request,PAGE_CU,args['daily_budget_cu'],args['block_hash'].lower(),args.get('renew_cursor',False))


KINDS=['finalized_block','block','receipt','balance','historical_price']
REFERENCE={'wallet':S,'chain_id':N,'kind':{'type':'string','enum':KINDS},'daily_budget_cu':N,
           'block_number':N,'block_hash':S,'tx_hash':S,'asset':S,'hour_end':S}

def reference(root, address, args):
    from native_assets import NATIVE_ASSETS
    from wallet import ALCHEMY
    mainnet(root,args['chain_id'])
    network=ALCHEMY.get(args['chain_id'])
    require(network,'This network has no configured Alchemy route.')
    common={'wallet','chain_id','kind','daily_budget_cu'}
    kind=args['kind']
    options={'finalized_block':set(),'block':{'block_number'},'receipt':{'tx_hash','block_hash'},
             'balance':{'block_hash','asset'},'historical_price':{'asset','hour_end'}}
    require(kind in options and set(args)==common|options[kind],'Supply the inputs for the selected evidence kind.')
    cache_scope=''
    if kind in ('finalized_block','block'):
        # Refresh the shared head at most once per minute. Historical lookups can recheck a reorg.
        method='eth_getBlockByNumber'
        params=['finalized' if kind=='finalized_block' else hex(args['block_number']),False]
        cache_scope=str(int(time.time()//60))
        cu=20
    elif kind=='receipt':
        require(re.fullmatch(HASH,args['tx_hash']), 'Choose a transaction on the finalized chain.')
        require(re.fullmatch(HASH,args['block_hash']),'Choose the transaction’s finalized block hash.')
        cache_scope=args['block_hash'].lower()
        method,params,cu='eth_getTransactionReceipt',[args['tx_hash'].lower()],20
    elif kind=='balance':
        require(re.fullmatch(HASH,args['block_hash']),'Choose a finalized block hash.')
        block={'blockHash':args['block_hash'].lower(),'requireCanonical':True}
        asset=asset_id(args['asset'])
        require('#' not in asset,'Use protocol evidence for NFT-backed positions.')
        if asset=='native':method,params,cu='eth_getBalance',[address,block],20
        else:
            method,cu='eth_call',26
            params=[{'to':asset,'data':'0x70a08231'+address[2:].rjust(64,'0')},block]
    else:
        asset=asset_id(args['asset'])
        require('#' not in asset,'Position claims need an independent NAV observation.')
        end=datetime.fromisoformat(date(args['hour_end']))
        require(not (end.minute or end.second or end.microsecond),'Supply a completed UTC hour ending on the hour.')
        identity={'network':network,'address':asset}
        if asset=='native':
            native=NATIVE_ASSETS.get(args['chain_id'])
            require(native,'There is no supported native USD identity on this chain.')
            identity={'symbol':native[0]}
        request={**identity,'startTime':(end-timedelta(hours=1)).isoformat(),'endTime':end.isoformat(),'interval':'5m'}
        return collect(root,network,request,40,args['daily_budget_cu'])
    return collect(root,network,{'jsonrpc':'2.0','id':1,'method':method,'params':params},cu,args['daily_budget_cu'],cache_scope)


def collect(root,network,request,cu,budget,cache_scope='',renew=False):
    from kira_config import load_config, secret_values
    from kira_usage import append
    from public_discovery import fetch_bounded
    method=request.get('method','tokens/historical')
    key=hashlib.sha256(encode([network,cache_scope,request]).encode()).hexdigest()
    folder=root/'pnl'/'activity'
    folder.mkdir(mode=0o700,parents=True,exist_ok=True)
    page=folder/(key+'.json')
    # Only this small lane is serialized; ordinary wallet jobs do not take this lock.
    with (folder/'.lock').open('a') as lock:
        try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:raise JobError('pnl_busy','Another PnL page is being fetched. Retry shortly.') from None
        if page.exists() and not renew:
            return {**json.loads(page.read_text()),'cached':True,'cu':0}
        with (root/'.job-worker.lock').open('a') as worker:
            try:fcntl.flock(worker,fcntl.LOCK_SH|fcntl.LOCK_NB)
            except BlockingIOError:raise JobError('pnl_busy','Wallet research is running. Resume this PnL page afterward.') from None
        today=now()[:10]
        meter=folder/(today+'.json')
        used=json.loads(meter.read_text()) if meter.exists() else {'cu':0,'retry_at':0}
        require(used['cu']+cu<=budget,'The workspace PnL page budget for this UTC day is exhausted.')
        require(time.time()>=used['retry_at'],'The PnL provider lane is cooling down. Resume from the saved cursor.')
        config=load_config()
        secret=secret_values(config).get(config['discovery']['key_env'])
        require(config['discovery']['provider']=='alchemy' and secret,'Connect Alchemy to collect new PnL activity.')
        # Reserve before transmission; a crash cannot give a second process the same allowance.
        used.update(cu=used['cu']+cu,retry_at=time.time()+1)
        atomic(meter,used)
        price=method=='tokens/historical'
        url=('https://api.g.alchemy.com/prices/v1/'+secret+'/tokens/historical' if price
             else 'https://'+network+'.g.alchemy.com/v2/'+secret)
        result=fetch_bounded(url,12,request)
        error=result.get('error') if isinstance(result,dict) else None
        error=error if isinstance(error,dict) else {}
        if error.get('http_status') in (403,429):
            used.update(cu=used['cu']-cu,retry_at=time.time()+(error.get('retry_after') or 15))
            atomic(meter,used)
        elif not price:  # fetch_bounded already records calls to the Prices API.
            append({'at':now(),'source':'pnl','job':None,'batch':None,'cu':cu,'requests':1,'methods':{method:[1,cu]}},root)
        body=(result if price else result.get('result')) if isinstance(result,dict) else None
        if body is None or error:
            raise JobError('pnl_provider','Evidence unavailable. Check the network, cursor, block and provider cooldown.')
        if method=='alchemy_getAssetTransfers':
            require(isinstance(body,dict) and isinstance(body.get('transfers'),list),'Invalid transfer response.')
            payload={'transfers':body['transfers'],'next_page_key':body.get('pageKey'),'categories':request['params'][0]['category']}
        elif method=='eth_getTransactionReceipt':
            require(isinstance(body,dict) and str(body.get('blockHash','')).lower()==cache_scope
                    and str(body.get('transactionHash','')).lower()==request['params'][0],'Receipt and finalized block do not match.')
            payload={'result':body}
        elif method=='eth_getBlockByNumber':
            require(isinstance(body,dict) and all(k in body for k in ('number','hash','timestamp')),'Missing finalized block.')
            payload={k:body[k] for k in ('number','hash','timestamp')}
        elif price:
            require(body.get('currency','').lower()=='usd' and isinstance(body.get('data'),list),'Missing USD observations.')
            payload={'currency':'usd','prices':body['data']}
        else:
            payload={'result':body}
        atomic(page,payload)
        return {**payload,'cached':False,'cu':cu}
