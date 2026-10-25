"""Recorded financial facts shared by CLI, local tools and web controls."""
import json
import re
from pathlib import Path
from kira_jobs import JobError

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
