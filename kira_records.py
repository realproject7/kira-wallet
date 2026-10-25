"""Recorded financial facts shared by CLI, local tools and web controls."""
import json
import re
from pathlib import Path
from kira_jobs import JobError

def read_receipt(name, arguments, result, delivered=True):
    receipt={'name':name,'arguments':arguments,'status':'completed' if delivered and not (isinstance(result,dict) and result.get('error')) else 'failed'}
    if name=='portfolio_read' and isinstance(result,dict) and isinstance(result.get('wallets'),list):
        receipt['wallet_pages']=[read_receipt('inventory_page',{'wallet':w['address'],'offset':w.get('offset',0)},w,receipt['status']=='completed') for w in result['wallets']]
    if name=='snapshot_read' and isinstance(result,dict) and isinstance(result.get('wallets'),list) and len(result['wallets'])==1:
        receipt['snapshot_id']=result.get('snapshot_id')
        result=result['wallets'][0]
    if isinstance(result,dict):
        for key in ('offset','next_offset','asset_count','position_count','snapshot_id','query_scope'):
            if key in result:receipt[key]=result[key]
        for key in ('assets','positions'):
            if isinstance(result.get(key),list):receipt['page_end']=result.get('offset',0)+len(result[key])
    return receipt

def read_completion(message, receipts, tools):
    """Validate declared plans and literal requests against delivered receipts."""
    ranking=re.search(r'\btop[- ]*(\d+|one|two|three|four|five|ten)\b|상위\s*(\d+|다섯|열)',message,re.I)
    requested_rank=None
    if ranking:
        raw=next(v for v in ranking.groups() if v).lower()
        requested_rank=int(raw) if raw.isdigit() else {'one':1,'two':2,'three':3,'four':4,'five':5,'ten':10,'다섯':5,'열':10}[raw]
    names=set(re.findall(r'\b(?:holdings_query|portfolio_read|wallet_read|snapshot_read|snapshots_compare|token_read|job_read|job_list|snapshots_list)\b',message))
    literal_names=names.copy()
    decoder=json.JSONDecoder();requested=[]
    for match in re.finditer(r'\{',message):
        try:value,_=decoder.raw_decode(message[match.start():])
        except ValueError:continue
        if isinstance(value,dict) and value.get('name',value.get('kira_tool')) in names and isinstance(value.get('arguments'),dict):
            requested.append((value.get('name',value.get('kira_tool')),value['arguments']))
    for receipt in receipts:
        plan=receipt.get('arguments')
        if receipt['name']=='records_read' and isinstance(plan,dict) and isinstance(plan.get('reads'),list):
            for read in plan['reads']:
                if isinstance(read,dict) and isinstance(read.get('name'),str) and isinstance(read.get('arguments'),dict):
                    names.add(read['name']);requested.append((read['name'],read['arguments']))
    if not requested_rank and (not names or not requested and not re.search(r'\b(?:read|call|run|use|execute)\b|읽|호출|실행|수행|\+',message,re.I)):return None
    expanded=[]
    for receipt in receipts:
        expanded.extend(receipt.get('reads',[]) if receipt['name']=='records_read' else [receipt])
    expanded.extend(page for r in list(expanded) for page in r.get('wallet_pages',[]))
    completed=[r for r in expanded if r['status']=='completed']
    missing=[name for name in sorted(names) if not any(r['name']==name for r in completed)]
    if tools and 'wallet_read' in literal_names:
        context,approved=tools.allowed()
        wallets=context['wallets']
        selected=wallets if re.search(r'\b(?:all|each|every)\b|모든|각각|전부',message,re.I) else [w for w in wallets if w['address'].lower() in message.lower() or any(tag.lower() in message.lower() for tag in w['tags'])]
        actual=set()
        for receipt in completed:
            if receipt['name']=='wallet_read':
                try:actual.add(tools.wallet(receipt['arguments']['wallet'],approved))
                except JobError:pass
        missing.extend('wallet_read '+w['name'] for w in selected if w['address'].lower() not in actual)
    if 'snapshot_read' in names:
        snapshot_requested=set(re.findall(r'snapshots/[A-Za-z0-9_./-]+',message))
        actual={r['arguments'].get('snapshot_id') for r in completed if r['name']=='snapshot_read'}
        missing.extend('snapshot_read '+identity for identity in sorted(snapshot_requested-actual))
    # Literal JSON read plans are checked by argument, including chain identity.
    # This is a bounded parser, not a claim to understand every natural request.
    from kira_research_tools import CATALOG
    specifications={row['name']:row for row in CATALOG}
    specifications['inventory_page']={'arguments':{'wallet':None},'optional_arguments':{'offset':None}}
    def matches(name,wanted,receipt):
        if receipt['name']!=name:return False
        if not isinstance(wanted,dict) or not isinstance(receipt.get('arguments'),dict):return False
        spec=specifications.get(name)
        if spec is None:return False
        required=set(spec['arguments']);allowed=required|set(spec.get('optional_arguments',{}))
        if any(not required<=set(args) or set(args)-allowed for args in (wanted,receipt['arguments'])):return False
        defaults={'offset':0,'limit':100 if name=='wallet_read' else 20} if name in ('wallet_read','snapshot_read','snapshots_compare') else {}
        if name=='inventory_page':defaults={'offset':0}
        wanted={**defaults,**wanted};actual={**defaults,**receipt.get('arguments',{})}
        if set(wanted)!=set(actual):return False
        for key,value in wanted.items():
            other=actual.get(key)
            if key=='minimum_value_usd':
                from decimal import Decimal, InvalidOperation
                try:
                    left,right=Decimal(str(value)),Decimal(str(other))
                    if not left.is_finite() or not right.is_finite() or left!=right:return False
                except InvalidOperation:return False
                continue
            if key=='wallet' and tools:
                try:
                    _,approved=tools.allowed();value=tools.wallet(value,approved);other=tools.wallet(other,approved)
                except JobError:return False
            if isinstance(value,str) and key in ('address','wallet'):value=value.lower();other=other.lower() if isinstance(other,str) else other
            if type(value) is not type(other) or value!=other:return False
        return True
    # A delivered retry fulfils the same request. Keep failed attempts in the
    # original receipts, but do not call a recovered request incomplete.
    failed=[{'name':r['name'],'arguments':r.get('arguments',{})} for r in expanded
            if r['status']=='failed' and r['name']!='inventory_page'
            and not any(matches(r['name'],r.get('arguments',{}),ok) for ok in completed)]
    missing.extend(name+' '+json.dumps(args,sort_keys=True) for name,args in requested if not any(matches(name,args,r) for r in completed))
    if 'token_read' in names and not any(name=='token_read' for name,_ in requested):
        addresses=set(re.findall(r'0x[0-9a-fA-F]{40}',message))
        chains={int(value) for value in re.findall(r'\bchain(?:_id)?\s*[:=]?\s*(\d+)\b',message,re.I)}
        for address in addresses:
            relevant=[r for r in completed if r['name']=='token_read' and str(r['arguments'].get('address','')).lower()==address.lower()]
            if not relevant:missing.append('token_read '+address)
            for chain in chains:
                if not any(r['arguments'].get('chain_id')==chain for r in relevant):missing.append('token_read '+str(chain)+':'+address)
    unread=[]
    exhaustive=bool(re.search(r'\b(?:complete|full)\s+inventory\b|\ball\s+(?:holdings|assets|positions)\b|전체\s*(?:보유|자산|목록)',message,re.I))
    groups={}
    for r in expanded:
        if r['name'] not in ('wallet_read','snapshot_read','snapshots_compare','inventory_page','holdings_query'):continue
        if r['name']=='holdings_query' and (r.get('query_scope') or {}).get('mode')!='search':continue
        if not isinstance(r.get('arguments'),dict):continue
        if r['status']=='failed' and any(matches(r['name'],r.get('arguments',{}),ok) for ok in completed):continue
        if r['name']=='inventory_page' and not exhaustive:continue
        identity={k:v for k,v in r['arguments'].items() if k not in ('offset','limit')}
        if 'wallet' in identity and tools:
            try:identity['wallet']=tools.wallet(identity['wallet'],tools.allowed()[1])
            except JobError:pass
        name='wallet_read' if r['name']=='inventory_page' else r['name']
        groups.setdefault((name,json.dumps(identity,sort_keys=True),r.get('snapshot_id')),[]).append(r)
    for (name,identity,snapshot),pages in groups.items():
        offset=0;seen=set();finished=False
        while offset not in seen:
            seen.add(offset);page=next((r for r in pages if r['status']=='completed' and r['arguments'].get('offset',0)==offset and 'next_offset' in r),None)
            if not page:break
            if page['next_offset'] is None:finished=True;break
            if type(page['next_offset']) is not int or page['next_offset']<=offset:break
            offset=page['next_offset']
        if not finished and (exhaustive or any(r.get('next_offset') is not None for r in pages)):
            unread.append({'name':name,'arguments':{**json.loads(identity),'offset':offset},'snapshot_id':snapshot})
    if requested_rank:
        from decimal import Decimal
        ranked=[r for r in completed if r['name']=='holdings_query' and (r.get('query_scope') or {}).get('mode')=='rank']
        rank_pages={};approved_wallets=None
        for r in ranked:
            q=r['query_scope']
            if not q.get('full_inventory_scanned') or not q.get('complete'):continue
            identity={'environment':'mainnet','group_by':'asset','query':'',
                      **{k:v for k,v in r['arguments'].items() if k not in ('offset','limit')}}
            identity['query']=identity['query'].strip().casefold()
            if 'minimum_value_usd' in identity:identity['minimum_value_usd']=Decimal(str(identity['minimum_value_usd']))
            if 'wallet' in identity and tools:
                try:
                    if approved_wallets is None:approved_wallets=tools.allowed()[1]
                    identity['wallet']=tools.wallet(identity['wallet'],approved_wallets)
                except JobError:continue
            rank_pages.setdefault((tuple(sorted(identity.items())),q['result_count']),[]).append(q)
        rank_complete=False
        for (_,available),pages in rank_pages.items():
            covered=0
            for page in sorted(pages,key=lambda q:q['offset']):
                if page['offset']>covered:break
                covered=max(covered,page['offset']+page['returned_count'])
            if covered>=min(requested_rank,available):rank_complete=True;break
        if not rank_complete:
            missing.append('holdings_query rank for the requested top '+str(requested_rank))
    for r in completed:
        q=r.get('query_scope')
        if q and not q.get('complete'):missing.append('holdings_query result detail was truncated')
    missing.extend('holdings_query has unread matching records' for r in unread if r['name']=='holdings_query')
    if exhaustive:missing.extend(r['name']+' unread offset '+str(r['arguments']['offset']) for r in unread)
    return {'status':'partial' if missing or failed else 'complete','missing':list(dict.fromkeys(missing)),'failed':failed,'unread_pages':unread,'completed_reads':sum(r['name']!='inventory_page' for r in completed)}

def scoped_wallets(root,config):
    import sys
    sys.path.insert(0,str(Path(__file__).resolve().parent/'viewer'))
    from model import load_state
    state,_,_ = load_state(root, include_details=False, encode=False)
    wallets = state['wallets']
    if config['scope'] == 'wallet':
        wallets = [w for w in wallets if w['key'] == config['wallet']]
        if len(wallets) != 1: raise JobError('wallet_missing','The approved wallet is no longer registered. Review your context settings.')
    return wallets

def projection(root, config, *, token_id=None, limit=12, offset=0, wallet_key=None, inventory=False):
    if config['scope'] == 'none': return {'scope':'none','note':'No automatic wallet context supplied.'}
    wallets=scoped_wallets(root,config)
    wallets=[{**w,'recorded_valuation':recorded_valuation(w['assets'])} for w in wallets]
    if token_id is not None:
        wallets=[{**wallet,'assets':[a for a in wallet['assets'] if a['id']==token_id]} for wallet in wallets]
    if wallet_key is not None: wallets=[w for w in wallets if w['key']==wallet_key]
    counts=[len(w['assets']) for w in wallets]
    if token_id is None:
        wallets=[{**w,'assets':w['assets'][offset:offset+limit]} for w in wallets]
    rows=wallet_facts(wallets,pool_budget=40_000 if token_id else 0)
    if token_id is None and (inventory or any(count>limit for count in counts)):
        rows=compact_wallet_facts(rows)
    for row,count in zip(rows,counts):
        row.update(asset_count=count,assets_omitted=count-len(row['assets']),offset=offset,
                   next_offset=offset+len(row['assets']) if token_id is None and offset+len(row['assets'])<count else None)
    result = {'scope':config['scope'],'wallets':rows,'note':'Recorded direct holdings. Missing data is unknown. Mainnet priced totals exclude unpriced amounts and testnets. Exit quotes are independent historical full-balance burn outputs after royalty, before gas. Do not sum them, infer live execution, or convert output tokens at spot prices into cash-out value. pools_omitted counts bounded market detail; token_read can retrieve a specific approved token.'}
    from kira_config import public_status
    result['research_connection']=public_status(root)
    size=len(json.dumps(result,ensure_ascii=False).encode())
    if size > 240_000:
        # Preserve this holdings page and every approved wallet. Market links and
        # detailed burn evidence can be read separately without blocking chat.
        result['wallets']=compact_wallet_facts(rows)
        result['detail_level']='holdings'
        result['note']+=' This compact inventory is a holdings page. Asset id is chain_id:contract_address, or chain_id:native for native assets; chain names and environments are in each wallet\'s chains. Market links, pools, exit quotes and curve reserves are deferred. Use wallet_read for more holdings and token_read for detailed evidence before making market or exit claims. If wallet tools are off, these details are unavailable in this conversation.'
        if len(json.dumps(result,ensure_ascii=False).encode()) > 240_000:
            raise JobError('context_too_large','This portfolio exceeds the context limit. Choose one wallet or ask with no automatic context.')
        return result
    return result

def compact_wallet_facts(rows):
    asset_fields=('id','chain_id','address','display_identity','symbol','name','environment','balance','is_native','value_usd','historical_value_usd','balance_observed_at','price','pools','pools_recorded','pools_omitted','exit_quote_recorded','archived')
    return [{**row,'assets':[{key:asset[key] for key in asset_fields if key in asset and
                           (asset[key] is not None or key in ('address','value_usd','price'))}
                          for asset in row['assets']]} for row in rows]

def recorded_valuation(assets):
    """Explicit disjoint categories over the full recorded inventory, before paging."""
    from decimal import Decimal, InvalidOperation, localcontext
    groups={'native':[], 'mintclub':[], 'other_tokens':[]}
    unpriced=0
    for asset in assets:
        if asset.get('environment')!='mainnet' or asset.get('archived'):continue
        try:value=Decimal(str(asset.get('value_usd')))
        except InvalidOperation:unpriced+=1;continue
        if not value.is_finite() or value<0:unpriced+=1;continue
        category='native' if asset.get('is_native') else 'mintclub' if asset.get('curve_state') or asset.get('exit_route')=='mintclub_burn' else 'other_tokens'
        groups[category].append((value,(asset.get('price') or {}).get('observed_at')))
    def summarize(rows):
        times=[time for _,time in rows if time]
        with localcontext() as context:
            context.prec=100
            value=format(sum((value for value,_ in rows),Decimal(0)),'f') if rows else None
        return {'estimated_value_usd':value,'priced_position_count':len(rows),
                'price_observed_at':{'from':min(times,default=None),'to':max(times,default=None)},
                'price_time_unknown_count':sum(time is None for _,time in rows)}
    return {'scope':'Full recorded mainnet inventory, before pagination. Categories are disjoint.',
            'all_priced_positions':summarize([row for rows in groups.values() for row in rows]),
            'categories':{name:summarize(rows) for name,rows in groups.items()},'unpriced_mainnet_count':unpriced,
            'interpretation':'Estimated recorded priced subset at separate observation times. Not a floor on current wealth or realizable proceeds. Missing values remain unknown; indicative prices are not executable quotes.'}

def wallet_facts(wallets, *, pool_budget=40_000):
    def pick(value, names): return {k:value.get(k) for k in names}
    rows = []
    for wallet in wallets:
        row = pick(wallet,('address','tags','name','snapshot_id','analysed_at','prices_at','balance_observed_at','known_value_usd','unpriced_count','status'))
        if not wallet.get('analysed_at'): row['known_value_usd']=None
        row['recorded_valuation']=wallet.get('recorded_valuation') or recorded_valuation(wallet['assets'])
        row['chains'] = [pick(c,('id','name','environment','complete','rpc_available','rpc_status','market_pending','market_errors','native_symbol','native_balance','native_observed_at','native_block_number','registry_block_number','discovery_status','registry_complete','registry_phase','rpc_pending','candidate_balance_errors','candidate_deferred','rpc_routes','history_window','discovery_provider','discovery_filters','lifecycle','head_status','head_age_seconds')) for c in wallet['chains']]
        row['coverage_counts']={}
        for environment in ('mainnet','testnet'):
            chains=[c for c in row['chains'] if c['environment']==environment]
            groups={status:[c['id'] for c in chains if (c['rpc_status'] if c['rpc_status'] in ('available','pending','unavailable','retired') else 'unknown')==status] for status in ('available','pending','unavailable','retired','unknown')}
            row['coverage_counts'][environment]={'total':len(chains),'rpc':{status:{'count':len(ids),'chain_ids':ids} for status,ids in groups.items()},
                'discovery_checked':sum(c['complete'] is True for c in chains),'history_pending':sum(c.get('discovery_status')=='history_pending' for c in chains)}
        row['snapshot_price_references'] = wallet.get('snapshot_price_references',{})
        row['assets'] = []
        for asset in wallet['assets']:
            item = pick(asset,('id','chain_id','address','symbol','name','environment','balance','is_native','value_usd','balance_observed_at'))
            address=asset.get('address')
            item['display_identity']=str(asset['chain_id'])+':'+(address[:8]+'…'+address[-6:] if isinstance(address,str) and re.fullmatch(r'0x[0-9a-fA-F]{40}',address) else 'native')
            item['archived']=asset.get('archived',False)
            if item['archived']:item['historical_value_usd']=asset.get('historical_value_usd')
            item['price'] = pick(asset['price'],('usd','basis','quality','observed_at')) if asset.get('price') else None
            item['exit_quote'] = asset.get('exit_quote')
            item['sell_out'] = asset.get('sell_out')
            item['exit_quote_recorded'] = item['exit_quote'] is not None or item['sell_out'] is not None
            item['exit_route'] = asset.get('exit_route')
            item['markets'] = asset.get('links',[])
            pools=asset.get('market_pools',[]);item['pools']=[];item['pools_recorded']=len(pools)
            for pool in pools[:12]:
                fact={**pick(pool,('venue','pool','url','liquidity_usd','price_usd','observed_at','version_labels','fee_bps','pool_kind')),
                      'pair':[pick(coin,('address','symbol')) for coin in pool.get('pair',[])]}
                cost=len(json.dumps(fact,ensure_ascii=False).encode())+2
                if cost>pool_budget:break
                item['pools'].append(fact);pool_budget-=cost
            item['pools_omitted']=len(pools)-len(item['pools'])
            item['curve_reserve'] = asset.get('curve_reserve')
            item['curve_state'] = asset.get('curve_state')
            row['assets'].append(item)
        rows.append(row)
    return rows
