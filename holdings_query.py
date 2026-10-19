"""Bounded results from the complete authorized saved projection, without model paging."""
from decimal import Decimal, localcontext
import json
from kira_jobs import JobError


def query_holdings(wallets, args):
    mode=args['mode'];query=args.get('query','').strip().casefold()
    if mode not in ('search','rank','aggregate'):raise JobError('invalid_tool','Choose search, rank or aggregate.')
    if mode=='search' and not query:raise JobError('invalid_tool','Supply a token symbol, name, contract or native.')
    group_by=args.get('group_by','asset')
    if group_by not in ('asset','position'):raise JobError('invalid_tool','Group by asset or position.')
    environment=args.get('environment','mainnet')
    if environment not in ('mainnet','testnet','all'):raise JobError('invalid_tool','Choose mainnet, testnet or all.')
    limit=args.get('limit',10);offset=args.get('offset',0)
    if limit>25:raise JobError('invalid_tool','Use at most 25 query results; this does not limit the scanned inventory.')
    minimum=Decimal(str(args['minimum_value_usd'])) if 'minimum_value_usd' in args else None
    def eligible(asset):
        return not asset.get('archived') and (environment=='all' or asset.get('environment')==environment) and ('chain_id' not in args or asset['chain_id']==args['chain_id'])
    def exact(asset):
        return query in {str(asset.get('symbol','')).casefold(),str(asset.get('name','')).casefold(),str(asset.get('address','')).casefold()} or query=='native' and asset.get('is_native')
    exact_match=bool(query) and any(eligible(a) and exact(a) for w in wallets for a in w['assets'])
    scanned=0;selected=[];outside=0;unpriced=0
    for wallet in wallets:
        for asset in wallet['assets']:
            scanned+=1
            if 'chain_id' in args and asset['chain_id']!=args['chain_id']:continue
            if query and not (exact(asset) if exact_match else query in str(asset.get('name','')).casefold() or query in str(asset.get('symbol','')).casefold()):continue
            if asset.get('archived') or environment!='all' and asset.get('environment')!=environment:
                outside+=1;continue
            value=asset.get('value_usd') if asset.get('environment')=='mainnet' else None
            if value is None:unpriced+=1
            if minimum is not None and (value is None or Decimal(str(value))<minimum):continue
            selected.append((wallet,asset))
    from kira_agent import recorded_valuation, wallet_facts
    valuation=recorded_valuation([a for _,a in selected])
    groups={}
    for wallet,asset in selected:
        key=asset['id'] if group_by=='asset' else wallet['address'].lower()+':'+asset['id']
        groups.setdefault(key,[]).append((wallet,asset))
    ranked=[]
    for key,positions in groups.items():
        values=[Decimal(str(a['value_usd'])) for _,a in positions if a.get('value_usd') is not None and a.get('environment')=='mainnet']
        with localcontext() as context:
            context.prec=100;total=sum(values,Decimal(0)) if values else None
        ranked.append((key,positions,total))
    if mode=='rank':ranked=[r for r in ranked if r[2] is not None]
    ranked.sort(key=lambda r:(r[2] is None,-r[2] if r[2] is not None else Decimal(0),r[0]))
    page=ranked[offset:offset+limit] if mode!='aggregate' else []
    rows=[];remaining=40000
    for key,positions,total in page:
        facts=[]
        for wallet,asset in positions:
            fact=wallet_facts([{**wallet,'assets':[asset]}],pool_budget=max(0,remaining))[0]['assets'][0]
            remaining-=len(json.dumps(fact.get('pools',[])).encode())
            facts.append({'wallet':wallet['address'],'wallet_name':wallet['name'],'snapshot_id':wallet.get('snapshot_id'),'asset':fact})
        rows.append({'identity':positions[0][1]['id'],'value_usd':format(total,'f') if total is not None else None,
                     'position_count':len(positions),'unpriced_position_count':len(positions)-sum(a.get('value_usd') is not None and a.get('environment')=='mainnet' for _,a in positions),
                     'positions':facts})
    count=len(ranked)
    response={'mode':mode,'match_type':'exact' if exact_match else 'substring' if query else 'all','group_by':group_by,'environment':environment,'scanned_position_count':scanned,
              'matched_position_count':len(selected),'matched_asset_count':len({a['id'] for _,a in selected}),
              'unpriced_position_count':unpriced,'outside_scope_count':outside,'valuation':valuation,
              'result_count':count,'results':rows,'offset':offset,'next_offset':offset+len(rows) if mode!='aggregate' and offset+len(rows)<count else None,
              'ambiguous':mode=='search' and len({a['id'] for _,a in selected})>1,
              'query_scope':{'mode':mode,'full_inventory_scanned':True,'requested_limit':limit,'offset':offset,'result_count':count},
              'note':'Exact query over approved saved holdings, including records beyond the first page. Ranking sums the priced mainnet subset per chain and contract; unknown values remain separate. Not live wealth or sale proceeds. Search may match multiple identities; report the ambiguity rather than guessing. Missing records are unknown.'}
    # Never enlarge the native context to accommodate a pathological result.
    while len(json.dumps(response,ensure_ascii=False).encode())>120000 and rows:
        rows.pop();response['next_offset']=offset+len(rows)
    if mode!='aggregate' and page and not rows:raise JobError('context_limit','This match exceeds the detail limit. Use a wallet filter or token_read.')
    response['query_scope']['returned_count']=len(rows)
    response['query_scope']['complete']=mode=='aggregate' or len(rows)==len(page)
    return response
