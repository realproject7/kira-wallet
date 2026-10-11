"""Keyless transfer candidates, with saved fixed windows and no balance inference."""
import hashlib
import json
import re
import threading
import time
from public_discovery import fetch_bounded

CHAINS={1,8453,10,42161,137,56}
ENDPOINT='https://mcp-keyless.etherscan.io/mcp'
DOCS='https://docs.etherscan.io/build-with-ai/mcp'
ADDRESS=re.compile(r'0x[0-9a-fA-F]{40}')
_lock=threading.Lock()
_next=0.0
_cooldown=0.0
_session=None


def decode(body):
    try:return json.loads(body)
    except ValueError:
        events=[line[5:].strip() for line in body.splitlines() if line.startswith('data:')]
        if len(events)!=1:raise ValueError('Invalid event response')
        return json.loads(events[0])


def fetch(body, timeout):
    """One shared conservative lane. A quota response pauses, never evades limits."""
    global _next,_cooldown,_session
    end=time.monotonic()+timeout
    if not _lock.acquire(timeout=max(0,timeout)):return {'error':{'code':'deadline'}}
    try:
        now=time.monotonic()
        if _cooldown>now:return {'error':{'code':'throttled'}}
        delay=max(0,_next-now)
        if delay>=end-now:return {'error':{'code':'deadline'}}
        if delay:time.sleep(delay)
        _next=time.monotonic()+2
        headers={'MCP-Protocol-Version':'2025-03-26'}
        if not _session:
            initialized=fetch_bounded(ENDPOINT,max(0,min(8,end-time.monotonic())),{'jsonrpc':'2.0','id':0,'method':'initialize',
                'params':{'protocolVersion':'2025-03-26','capabilities':{},'clientInfo':{'name':'KiraWallet','version':'1'}}},headers=headers,envelope=True)
            pause_quota(initialized)
            try:
                session=initialized['session'];result=decode(initialized['body'])
                if not isinstance(session,str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,192}',session) or not isinstance(result,dict) or not isinstance(result.get('result'),dict) or result['result'].get('protocolVersion')!='2025-03-26':raise ValueError('Invalid session')
            except (KeyError,TypeError,ValueError):return {'error':{'code':'initialize_failed'}}
            _session=session
            headers['Mcp-Session-Id']=session
            notification=fetch_bounded(ENDPOINT,max(0,min(8,end-time.monotonic())),{'jsonrpc':'2.0','method':'notifications/initialized'},headers=headers,envelope=True)
            pause_quota(notification)
            if notification.get('http_status') not in (200,202,204):_session=None;return {'error':{'code':'initialize_failed'}}
        headers['Mcp-Session-Id']=_session
        _next=time.monotonic()+2
        response=fetch_bounded(ENDPOINT,max(0,min(8,end-time.monotonic())),body,headers=headers,envelope=True)
        error=response.get('error',{}) if isinstance(response,dict) else {}
        pause_quota(response)
        if error.get('http_status') in (400,404):_session=None
        if error:return response
        try:return decode(response['body'])
        except (KeyError,ValueError,TypeError):return {'error':{'code':'invalid_response'}}
    finally:_lock.release()


def pause_quota(response):
    global _cooldown
    error=response.get('error',{}) if isinstance(response,dict) else {}
    if error.get('http_status')==429:_cooldown=time.monotonic()+max(60,error.get('retry_after') or 0)


def call(name, arguments, deadline, request=fetch):
    payload={'jsonrpc':'2.0','id':1,'method':'tools/call','params':{'name':name,'arguments':arguments}}
    response=request(payload,max(0,deadline-time.monotonic()))
    if not isinstance(response,dict) or response.get('id')!=1 or response.get('error'):raise ValueError('Provider unavailable')
    result=response.get('result',{})
    if not isinstance(result,dict) or result.get('isError'):raise ValueError('Tool unavailable')
    content=result.get('content')
    if not isinstance(content,list) or len(content)!=1 or not isinstance(content[0],dict) or content[0].get('type')!='text' or not isinstance(content[0].get('text'),str):raise ValueError('Invalid tool result')
    data=json.loads(content[0]['text'])
    if not isinstance(data,dict):raise ValueError('Invalid provider result')
    # No-transactions is a valid empty list. NOTOK text is never an empty wallet.
    if data.get('ok') is not True or data.get('status') not in ('1','0') or data.get('status')=='0' and data.get('result')!=[]:
        raise ValueError('Provider could not establish discovery')
    return data['result']


def valid_state(state, address, chain_id):
    if not isinstance(state,dict) or state.get('schema_version')!=1 or state.get('wallet')!=address.lower() or state.get('chain_id')!=chain_id:return False
    if not all(type(state.get(k)) is int and state[k]>=0 for k in ('startblock','endblock','page')) or not 1<=state['page']<=101 or state['startblock']>state['endblock']:return False
    if not state.get('complete') and state['page']>1 and (type(state.get('last_block')) is not int or not state['startblock']<=state['last_block']<=state['endblock']):return False
    return isinstance(state.get('contracts'),list) and len(state['contracts'])<=10000 and all(isinstance(a,str) and ADDRESS.fullmatch(a) for a in state['contracts']) and type(state.get('complete')) is bool


def admit(transfers, address, startblock, endblock, contracts):
    if not isinstance(transfers,list) or len(transfers)>100:raise ValueError('Invalid transfer page')
    contracts=set(contracts);previous=None
    for transfer in transfers:
        if not isinstance(transfer,dict):raise ValueError('Invalid transfer')
        contract=transfer.get('contractAddress');block=transfer.get('blockNumber')
        if not isinstance(contract,str) or not ADDRESS.fullmatch(contract) or not isinstance(block,str) or not re.fullmatch(r'\d{1,16}',block):raise ValueError('Invalid identity')
        block=int(block)
        if not startblock<=block<=endblock or previous is not None and block>previous:raise ValueError('Invalid page window')
        if not any(isinstance(transfer.get(side),str) and transfer[side].lower()==address.lower() for side in ('from','to')):raise ValueError('Foreign wallet record')
        previous=block;contracts.add(contract.lower())
    if len(contracts)>10000:raise ValueError('Candidate safety limit')
    return sorted(contracts)


def discover(address, chain_id, *, state=None, save=lambda value:None, request=fetch, budget=25, max_pages=3):
    row={'chain_id':chain_id,'source':DOCS,'provider':'etherscan_keyless', 'tokens':[], 'native':[],
         'pages':[], 'complete':False,'discovery_status':'unsupported','error':None,
         'candidate_basis':'ERC20 transfer identities only. RPC verifies balances independently.',
         'filters':{'spam_filter':False,'minimum_value':None,'minimum_liquidity':None}}
    if chain_id not in CHAINS:return row
    if not isinstance(address,str) or not ADDRESS.fullmatch(address):raise ValueError('Invalid wallet')
    deadline=time.monotonic()+budget
    current=state.copy() if valid_state(state,address,chain_id) else None
    try:
        if not current or current['complete']:
            height=call('get_block_by_timestamp',{'chainid':str(chain_id),'timestamp':max(0,int(time.time())-120),'closest':'before'},deadline,request)
            if not isinstance(height,str) or not re.fullmatch(r'\d{1,16}',height):raise ValueError('Invalid window boundary')
            # Reconcile the last 2,048 blocks of a finished window. The lag is
            # not finality. Deeper reorgs and indexer backfills can still omit IDs.
            endblock=int(height);startblock=max(0,current['endblock']-2048) if current else 0
            if current and endblock<current['endblock']:raise ValueError('Indexer height moved backward')
            current={'schema_version':1,'wallet':address.lower(),'chain_id':chain_id,'startblock':startblock,
                     'endblock':endblock,'page':1,'contracts':current['contracts'][:] if current else [],'complete':False,
                     'previous_page_hash':None,'records':0,'started_at':int(time.time())}
            save(current)
        elif max_pages:
            # Keep finding new receipts while older history is unfinished. A
            # bounded fresh page supplements, never replaces, the saved frontier.
            height=call('get_block_by_timestamp',{'chainid':str(chain_id),'timestamp':max(0,int(time.time())-120),'closest':'before'},deadline,request)
            if not isinstance(height,str) or not re.fullmatch(r'\d{1,16}',height):raise ValueError('Invalid window boundary')
            if int(height)>current['endblock']:
                recent={'startblock':current['endblock']+1,'endblock':int(height),'page':1}
                transfers=call('get_token_transfers',{'chainid':str(chain_id),'address':address,'standard':'erc20','offset':100,'sort':'desc',**recent},deadline,request)
                current['contracts']=admit(transfers,address,recent['startblock'],recent['endblock'],current['contracts']);save(current)
                row['recent_window']={**recent,'complete':len(transfers)<100,'records':len(transfers)}
                row['pages'].append({'page':1,'records':len(transfers),'window':'recent'})
        for _ in range(max(0,max_pages-len(row['pages']))):
            if row['complete'] or current['complete']:break
            if time.monotonic()>=deadline or current['page']>100:break
            args={k:current[k] for k in ('startblock','endblock','page')}
            transfers=call('get_token_transfers',{'chainid':str(chain_id),'address':address,'standard':'erc20','offset':100,'sort':'desc',**args},deadline,request)
            contracts=admit(transfers,address,current['startblock'],current['endblock'],current['contracts'])
            if transfers and current.get('last_block') is not None and int(transfers[0]['blockNumber'])>current['last_block']:raise ValueError('Transfer pagination moved backward')
            digest=hashlib.sha256(json.dumps(transfers,sort_keys=True).encode()).hexdigest()
            if transfers and digest==current.get('previous_page_hash'):raise ValueError('Repeated transfer page')
            current.update(contracts=sorted(contracts),page=current['page']+1,complete=len(transfers)<100,
                           previous_page_hash=digest,records=current.get('records',0)+len(transfers),last_block=int(transfers[-1]['blockNumber']) if transfers else current.get('last_block'))
            save(current);row['pages'].append({'page':args['page'],'records':len(transfers)})
        row['complete']=(row['complete'] or current['complete']) and row.get('recent_window',{}).get('complete',True)
        row['discovery_status']='checked' if row['complete'] else 'history_pending'
        if not row['complete']:row['error']={'message':'Transfer history is unfinished. Saved candidates remain usable. Refresh holdings to continue.'}
    except (ValueError,KeyError,TypeError,OSError):
        row['discovery_status']='provider_error'
        row['error']={'message':'Free transfer discovery could not finish. Saved candidates remain usable; retry holdings later.'}
    if current:
        row['tokens']=[{'chain_id':chain_id,'address':contract,'prices':[]} for contract in current['contracts']]
        row['history_window']={k:current.get(k) for k in ('startblock','endblock','page','complete','records','started_at')}
        row['history_window']['pagination_limit_reached']=current['page']>100 and not current['complete']
    return row
