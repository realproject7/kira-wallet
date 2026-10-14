"""Keyless transfer candidates, with saved fixed windows and no balance inference."""
import hashlib
import json
import math
import re
import threading
import time
from public_discovery import fetch_bounded

# Added routes were admitted with keyless block and transfer response probes.
# Provider support, including Robinhood's keyless tier, remains best effort.
CHAINS={1,8453,10,42161,137,56,130,33139,4663,11155111,84532,43113}
# Individually admitted keyless ERC1155 first-page access and shape on 2026-10-13.
# Only ID0 candidates are retained; bond membership and balances are independent.
ERC1155_CHAINS={1,10,56,130,137,4663,8453,33139,42161,43113,84532,11155111}
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
        if _cooldown>now:return {'error':{'code':'throttled','retry_after':math.ceil(_cooldown-now)}}
        delay=max(0,_next-now)
        if delay>=end-now:return {'error':{'code':'deadline'}}
        if delay:time.sleep(delay)
        _next=time.monotonic()+2
        headers={'MCP-Protocol-Version':'2025-03-26'}
        if not _session:
            initialized=fetch_bounded(ENDPOINT,max(0,min(8,end-time.monotonic())),{'jsonrpc':'2.0','id':0,'method':'initialize',
                'params':{'protocolVersion':'2025-03-26','capabilities':{},'clientInfo':{'name':'KiraWallet','version':'1'}}},headers=headers,envelope=True)
            pause_quota(initialized)
            if isinstance(initialized,dict) and initialized.get('error',{}).get('http_status')==429:return initialized
            try:
                session=initialized['session'];result=decode(initialized['body'])
                if not isinstance(session,str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,192}',session) or not isinstance(result,dict) or not isinstance(result.get('result'),dict) or result['result'].get('protocolVersion')!='2025-03-26':raise ValueError('Invalid session')
            except (KeyError,TypeError,ValueError):return {'error':{'code':'initialize_failed'}}
            _session=session
            headers['Mcp-Session-Id']=session
            notification=fetch_bounded(ENDPOINT,max(0,min(8,end-time.monotonic())),{'jsonrpc':'2.0','method':'notifications/initialized'},headers=headers,envelope=True)
            pause_quota(notification)
            if isinstance(notification,dict) and notification.get('error',{}).get('http_status')==429:return notification
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
    if isinstance(error,dict) and error.get('http_status')==429:
        retry=error.get('retry_after')
        _cooldown=time.monotonic()+max(60,min(3600,retry) if type(retry) is int else 60)


class BudgetEnded(ValueError):
    """This invocation cannot fit another call in its shared provider lane."""


class RetryLater(ValueError):
    def __init__(self, seconds):
        super().__init__('Provider quota interval')
        self.retry_not_before=int(time.time())+max(60,min(3600,seconds) if type(seconds) is int else 60)


def call(name, arguments, deadline, request=fetch):
    payload={'jsonrpc':'2.0','id':1,'method':'tools/call','params':{'name':name,'arguments':arguments}}
    response=request(payload,max(0,deadline-time.monotonic()))
    error=response.get('error') if isinstance(response,dict) else None
    if isinstance(error,dict) and error.get('code')=='deadline':raise BudgetEnded('Discovery time budget reached')
    if isinstance(error,dict) and (error.get('http_status')==429 or error.get('code')=='throttled'):
        raise RetryLater(error.get('retry_after'))
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


def valid_range(window, *, pending=False):
    if (not isinstance(window,dict) or not all(type(window.get(k)) is int and window[k]>=0 for k in ('startblock','endblock'))
            or window['startblock']>window['endblock']):return False
    if not pending:return True
    if type(window.get('page')) is not int or not 1<=window['page']<=101:return False
    if window['page']>1 and (type(window.get('last_block')) is not int or not window['startblock']<=window['last_block']<=window['endblock']):return False
    return (isinstance(window.get('seen_page_hashes',[]),list)
            and len(window.get('seen_page_hashes',[]))<=100
            and all(isinstance(digest,str) and re.fullmatch(r'[0-9a-f]{64}',digest) for digest in window.get('seen_page_hashes',[])))


def provider_for(standard):
    if standard not in ('erc20','erc1155'):raise ValueError('Unsupported candidate standard')
    return 'etherscan_keyless' if standard=='erc20' else 'etherscan_keyless_erc1155_id0'


def valid_state(state, address, chain_id, standard='erc20'):
    provider=provider_for(standard)
    if (not isinstance(state,dict) or type(state.get('schema_version')) is not int or state['schema_version'] not in (1,2)
            or state.get('wallet')!=address.lower() or type(state.get('chain_id')) is not int or state['chain_id']!=chain_id
            or state.get('provider','etherscan_keyless')!=provider or state.get('standard','erc20')!=standard or not valid_range(state)
            or type(state.get('complete')) is not bool or not isinstance(state.get('contracts'),list)
            or not all(isinstance(a,str) and ADDRESS.fullmatch(a) for a in state['contracts'])):return False
    if state.get('history_strategy','linear_pages_v1') not in ('linear_pages_v1','balanced_ranges_v1'):return False
    if type(state.get('page_size',100)) is not int or state.get('page_size',100) not in (100,1000):return False
    if 'retry_not_before' in state and (type(state['retry_not_before']) is not int or state['retry_not_before']<0):return False
    if state['schema_version']==1:
        return (standard=='erc20' and type(state.get('page')) is int and 1<=state['page']<=101
                and all(k not in state or type(state[k]) is int and state[k]>=0 for k in ('records','started_at'))
                and (state['complete'] or valid_range(state,pending=True)))
    if not all(type(state.get(k)) is int and state[k]>=0 for k in ('records','started_at','pages_checked')):return False
    ranges=[]
    for field in ('pending_ranges','completed_ranges','blocked_ranges'):
        if not isinstance(state.get(field),list):return False
        for window in state[field]:
            if not valid_range(window,pending=field=='pending_ranges'):return False
            if field=='pending_ranges' and 'seen_page_hashes' not in window:return False
            if field=='blocked_ranges' and window.get('reason')!='single_block_page_limit':return False
            ranges.append(window)
    # A checkpoint must cover the whole pinned window exactly once. Never turn
    # lost work, overlapping ranges or a truncated manifest into completion.
    next_block=state['startblock']
    for window in sorted(ranges,key=lambda w:w['startblock']):
        if window['startblock']!=next_block:return False
        next_block=window['endblock']+1
    return (next_block==state['endblock']+1
            and state['complete']==(not state['pending_ranges'] and not state['blocked_ranges']))


def migrate(state):
    current=json.loads(json.dumps(state))
    if current['schema_version']==2:return current
    window={k:current[k] for k in ('startblock','endblock')}
    pending={**window,'page':current['page'],'seen_page_hashes':[]}
    if current.get('last_block') is not None:pending['last_block']=current['last_block']
    if isinstance(current.get('previous_page_hash'),str) and re.fullmatch(r'[0-9a-f]{64}',current['previous_page_hash']):
        pending['seen_page_hashes']=[current['previous_page_hash']]
    return {'schema_version':2,'provider':'etherscan_keyless','wallet':current['wallet'],'chain_id':current['chain_id'],**window,
            'contracts':sorted(set(a.lower() for a in current['contracts'])),'complete':current['complete'],
            'records':current.get('records',0),'started_at':current.get('started_at',int(time.time())),
            'pages_checked':current['page']-1,'pending_ranges':[] if current['complete'] else [pending],
            'completed_ranges':[window] if current['complete'] else [],'blocked_ranges':[]}


def finish_range(current, window):
    ranges=sorted(current['completed_ranges']+[{'startblock':window['startblock'],'endblock':window['endblock']}],key=lambda w:w['startblock'])
    merged=[]
    for item in ranges:
        if merged and item['startblock']==merged[-1]['endblock']+1:merged[-1]['endblock']=item['endblock']
        else:merged.append(item)
    current['completed_ranges']=merged


def split_limit(current, *, balanced=False):
    window=current['pending_ranges'].pop(0)
    lo,hi=window['startblock'],window['endblock']
    if lo==hi:
        current['blocked_ranges'].append({'startblock':lo,'endblock':hi,'reason':'single_block_page_limit'})
        return
    mid=(lo+hi)//2
    # Inclusive, disjoint ranges. Re-reading the limited parent is intentional;
    # contract identities are a set and every child must finish independently.
    older={'startblock':lo,'endblock':mid,'page':1,'seen_page_hashes':[]}
    newer={'startblock':mid+1,'endblock':hi,'page':1,'seen_page_hashes':[]}
    if balanced:current['pending_ranges'].extend([older,newer])
    else:current['pending_ranges'][0:0]=[newer,older]


def admit(transfers, address, startblock, endblock, contracts, standard='erc20', page_size=100):
    provider_for(standard)
    if page_size not in (100,1000) or not isinstance(transfers,list) or len(transfers)>page_size:raise ValueError('Invalid transfer page')
    contracts=set(contracts);previous=None
    for transfer in transfers:
        if not isinstance(transfer,dict):raise ValueError('Invalid transfer')
        contract=transfer.get('contractAddress');block=transfer.get('blockNumber')
        if not isinstance(contract,str) or not ADDRESS.fullmatch(contract) or not isinstance(block,str) or not re.fullmatch(r'\d{1,16}',block):raise ValueError('Invalid identity')
        block=int(block)
        if not startblock<=block<=endblock or previous is not None and block>previous:raise ValueError('Invalid page window')
        if not any(isinstance(transfer.get(side),str) and transfer[side].lower()==address.lower() for side in ('from','to')):raise ValueError('Foreign wallet record')
        previous=block
        if standard=='erc1155':
            token_id=transfer.get('tokenID')
            if not isinstance(token_id,str) or not re.fullmatch(r'0|[1-9][0-9]{0,77}',token_id) or int(token_id)>=2**256:
                raise ValueError('Invalid ERC1155 token ID')
            if token_id!='0':continue
        contracts.add(contract.lower())
    return sorted(contracts)


def discover(address, chain_id, *, state=None, save=lambda value:None, request=fetch, budget=25, max_pages=3, continue_only=False, standard='erc20', history_strategy=None, page_size=100):
    provider=provider_for(standard)
    row={'chain_id':chain_id,'source':DOCS,'provider':provider,'standard':standard,'tokens':[],'native':[],
         'pages':[],'complete':False,'discovery_status':'unsupported','error':None,
         'candidate_basis':'ERC20 transfer identities only. RPC verifies balances independently.' if standard=='erc20' else 'ERC1155 ID0 transfer identities only. Mint Club bond membership and wallet balances must be verified independently.',
         'completion_scope':'Validated provider pages within the recorded block ranges only.',
         'complete_inventory_guaranteed':False,
         'filters':{'spam_filter':False,'minimum_value':None,'minimum_liquidity':None}}
    if chain_id not in (CHAINS if standard=='erc20' else ERC1155_CHAINS):return row
    if not isinstance(address,str) or not ADDRESS.fullmatch(address):raise ValueError('Invalid wallet')
    if history_strategy not in (None,'linear_pages_v1','balanced_ranges_v1'):raise ValueError('Unsupported history strategy')
    if type(page_size) is not int or page_size not in (100,1000):raise ValueError('Unsupported transfer page size')
    if state is not None and not valid_state(state,address,chain_id,standard):
        row.update(discovery_status='checkpoint_error',error={'message':'Transfer checkpoint is invalid. Saved evidence was preserved.'})
        return row
    deadline=time.monotonic()+budget
    current=migrate(state) if state is not None else None
    # Existing frontiers keep their exact traversal policy. New wallet runs can
    # explore old ranges early without labelling sampled ranges complete.
    strategy=current.get('history_strategy','linear_pages_v1') if current else history_strategy or 'linear_pages_v1'
    # Changing an offset at page N would skip or repeat a different interval.
    # Older checkpoints retain their original 100-record paging semantics.
    page_size=current.get('page_size',100) if current else page_size
    def height():
        value=call('get_block_by_timestamp',{'chainid':str(chain_id),'timestamp':max(0,int(time.time())-120),'closest':'before'},deadline,request)
        if not isinstance(value,str) or not re.fullmatch(r'\d{1,16}',value):raise ValueError('Invalid window boundary')
        return int(value)
    try:
        if current and current.get('retry_not_before',0)>time.time():
            row.update(discovery_status='throttled',retry_not_before=current['retry_not_before'])
        elif budget<=0 or max_pages<=0:
            row['discovery_status']='history_pending'
        else:
            if current is None or current['complete'] and not continue_only:
                endblock=height();startblock=max(0,current['endblock']-2048) if current else 0
                if current and endblock<current['endblock']:raise ValueError('Indexer height moved backward')
                current={'schema_version':2,'provider':provider,'standard':standard,'history_strategy':strategy,'page_size':page_size,'wallet':address.lower(),'chain_id':chain_id,
                         'startblock':startblock,'endblock':endblock,'contracts':current['contracts'] if current else [],
                         'complete':False,'records':0,'pages_checked':0,'started_at':int(time.time()),
                         'pending_ranges':[{'startblock':startblock,'endblock':endblock,'page':1,'seen_page_hashes':[]}],
                         'completed_ranges':[],'blocked_ranges':[]}
                save(current)
            elif not continue_only and not current['complete']:
                endblock=height()
                if endblock<current['endblock']:raise ValueError('Indexer height moved backward')
                if endblock>current['endblock']:
                    recent={'startblock':current['endblock']+1,'endblock':endblock,'page':1,'seen_page_hashes':[]}
                    current['pending_ranges'].insert(0,recent);current['endblock']=endblock
                    row['recent_window']={k:recent[k] for k in ('startblock','endblock','page')}
                    save(current)
            while current['pending_ranges'] and len(row['pages'])<max_pages and time.monotonic()<deadline:
                window=current['pending_ranges'][0]
                if window['page']>100:
                    split_limit(current,balanced=strategy=='balanced_ranges_v1');save(current);continue
                args={k:window[k] for k in ('startblock','endblock','page')}
                transfers=call('get_token_transfers',{'chainid':str(chain_id),'address':address,'standard':standard,'offset':page_size,'sort':'desc',**args},deadline,request)
                contracts=admit(transfers,address,window['startblock'],window['endblock'],current['contracts'],standard,page_size)
                if transfers and window.get('last_block') is not None and int(transfers[0]['blockNumber'])>window['last_block']:
                    raise ValueError('Transfer pagination moved backward')
                digest=hashlib.sha256(json.dumps(transfers,sort_keys=True).encode()).hexdigest()
                if transfers and digest in window['seen_page_hashes']:raise ValueError('Repeated transfer page')
                current['contracts']=contracts;current['records']+=len(transfers);current['pages_checked']+=1
                if row.get('recent_window',{}).get('startblock')==window['startblock']:
                    row['recent_window'].update(complete=len(transfers)<page_size,records=len(transfers))
                if len(transfers)<page_size:
                    current['pending_ranges'].pop(0);finish_range(current,window)
                else:
                    window.update(page=window['page']+1,last_block=int(transfers[-1]['blockNumber']))
                    window['seen_page_hashes'].append(digest)
                    if window['page']>100 or strategy=='balanced_ranges_v1' and window['page']>3 and window['startblock']<window['endblock']:
                        split_limit(current,balanced=strategy=='balanced_ranges_v1')
                current['complete']=not current['pending_ranges'] and not current['blocked_ranges']
                current.pop('retry_not_before',None)
                save(current);row['pages'].append({**args,'page_size':page_size,'records':len(transfers)})
            row['complete']=current['complete']
            row['discovery_status']='checked' if row['complete'] else 'history_pending' if current['pending_ranges'] else 'source_limited'
    except BudgetEnded:
        row['discovery_status']='history_pending'
    except RetryLater as error:
        row.update(discovery_status='throttled',retry_not_before=error.retry_not_before)
        if current:
            current['retry_not_before']=error.retry_not_before
            try:save(current)
            except (OSError,ValueError):row['discovery_status']='checkpoint_error'
    except OSError:
        row['discovery_status']='checkpoint_error'
    except (ValueError,KeyError,TypeError):
        # Exhausting this invocation's deadline leaves resumable history work.
        # It does not establish provider failure or remove the pending frontier.
        row['discovery_status']='history_pending' if current and current['pending_ranges'] and time.monotonic()>=deadline else 'provider_error'
    if not row['complete']:
        messages={'source_limited':'A single block exceeded the provider page limit. This range remains explicitly unresolved.',
                  'checkpoint_error':'Transfer checkpoint could not be saved. Existing evidence was preserved.',
                  'throttled':'Free transfer discovery is waiting for the provider retry interval.',
                  'provider_error':'Free transfer discovery could not finish. Saved candidates remain usable; retry holdings later.',
                  'history_pending':'Transfer history has saved unfinished ranges. Saved candidates remain usable.'}
        row['error']={'message':messages[row['discovery_status']]}
    if current:
        row['tokens']=[{'chain_id':chain_id,'address':contract,'prices':[],**({'token_type':'ERC1155','token_id':'0','requires_mintclub_membership':True} if standard=='erc1155' else {})} for contract in current['contracts']]
        pending=current['pending_ranges']
        row['history_window']={k:current[k] for k in ('startblock','endblock','records','started_at','pages_checked')}
        row['history_window'].update(page=pending[0]['page'] if pending else 0,complete=row['complete'],
            page_size=page_size,
            pending_ranges=len(pending),completed_ranges=len(current['completed_ranges']),blocked_ranges=len(current['blocked_ranges']),
            pagination_limit_reached=bool(current['blocked_ranges']))
        row['continuation']={'pending':bool(pending),'retry_not_before':current.get('retry_not_before',0),
                             'unresolved_ranges':len(current['blocked_ranges'])}
    return row
