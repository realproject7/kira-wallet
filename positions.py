"""Saved, read-only protocol claims and non-overlapping capital allocation.

Amounts are principal/NAV observations, never executable sell estimates.
Opening a view only reads the last published records.
"""
from decimal import Decimal, InvalidOperation, localcontext
import json
from pathlib import Path

PLATFORMS = {
    'wallet': ('Wallet tokens', '#8a7aaf', None, None),
    'lptoken': ('lpTOKEN.fun', '#df6249', 'lptoken.png', 'https://lptoken.fun'),
    'factory': ('Hunt Factory', '#7da660', 'factory.jpg', 'https://hunt.town/factory'),
    'aeromax': ('Aeromax', '#dabb52', 'aeromax.png', 'https://aeromax.fun'),
    'uniswap': ('Uniswap', '#ef5da8', 'uniswap.svg', 'https://app.uniswap.org/portfolio'),
    'aerodrome': ('Aerodrome', '#4a8de6', 'aerodrome.svg', 'https://aero.xyz'),
    'pancakeswap': ('PancakeSwap', '#42b9b3', 'pancakeswap.png', 'https://pancakeswap.finance'),
    'mintclub': ('Mint Club', '#4baf8b', 'mintclub.png', 'https://mint.club'),
    'mintclub-staking': ('Mint Club Staking', '#30876c', 'mintclub.png', 'https://mint.club/staking'),
}


def decimal(value):
    if isinstance(value, bool) or value is None:return None
    try:
        n=Decimal(str(value))
        return n if n.is_finite() and n>=0 and n<Decimal('1e80') else None
    except (InvalidOperation, ValueError):return None


def prices(wallets):
    result={}
    for wallet in wallets:
        for a in wallet.get('assets',[]):
            p=a.get('price') or {};value=decimal(p.get('usd'))
            from asset_policy import included
            if a.get('environment')!='mainnet' or not included(a) or value is None or not p.get('observed_at') or not p.get('source'):continue
            if p.get('quality')!='estimated' or p.get('retained_from_previous'):continue
            key=a['id'];prior=result.get(key)
            if prior is None or p['observed_at']>prior['observed_at']:result[key]=dict(p)
    return result


def valued(row, price_map):
    row=dict(row);assets=[]
    for asset in row.get('assets',[]):
        asset=dict(asset);p=price_map.get(str(row['chain_id'])+':'+asset['address'].lower());amount=decimal(asset.get('amount'))
        value=decimal((p or {}).get('usd'))
        asset.update(price=p,value_usd=0.0 if amount==0 else float(amount*value) if amount is not None and value is not None else None)
        assets.append(asset)
    row['assets']=assets
    row['value_usd']=sum(a['value_usd'] for a in assets) if assets and all(a['value_usd'] is not None for a in assets) else None
    row['known_component_value_usd']=sum(a['value_usd'] for a in assets if a['value_usd'] is not None)
    return row


def attach(root, wallets):
    """One bounded read per published wallet; no historical-file scans or RPC."""
    root=Path(root);path=root/'positions/index.json'
    index=json.loads(path.read_text()) if path.is_file() else {'wallets':{}}
    price_map=prices(wallets)
    for wallet in wallets:
        reference=index.get('wallets',{}).get(wallet['key']);saved=None
        if reference:
            candidate=(root/reference['path']).resolve()
            if candidate.is_relative_to((root/'snapshots/jobs').resolve()) and (candidate.name=='positions.json' or __import__('re').fullmatch(r'positions-[0-9]{5,}\.json',candidate.name)):
                try:saved=json.loads(candidate.read_text())
                except (OSError,ValueError):pass
        if saved and saved.get('wallet')==wallet['key'] and saved.get('schema_version')==1:
            wallet['positions']=[valued(p,price_map) for p in saved.get('positions',[]) if p.get('platform') in PLATFORMS][:5000]
            wallet['position_coverage']=saved.get('coverage',[])
            wallet['positions_observed_at']=saved.get('observed_at')
            wallet['positions_scan_status']=saved.get('status')
        else:
            wallet.update(positions=[],position_coverage=[],positions_observed_at=None,positions_scan_status='not_checked')
        wallet['capital_allocation']=allocation([wallet])


def allocation(wallets, *, token_id=None, chain_id=None):
    """Exclusive groups. A wrapper and its underlying assets never add twice."""
    from asset_policy import included
    groups={};unknown=0;stale=0;positions_count=0;observations=[];checked=0
    def add(platform,value,position=False):
        nonlocal unknown
        if value is None:unknown+=1
        item=groups.setdefault(platform,{'id':platform,'value_usd':Decimal(0),'position_count':0,'unpriced_count':0})
        if position:item['position_count']+=1
        if value is None:item['unpriced_count']+=1
        else:item['value_usd']+=Decimal(str(value))
    with localcontext() as ctx:
        ctx.prec=100
        for wallet in wallets:
            checked+=wallet.get('positions_scan_status') in ('checked','partial')
            observations.extend([wallet['positions_observed_at']] if wallet.get('positions_observed_at') else [])
            rows=[p for p in wallet.get('positions',[]) if chain_id is None or p['chain_id']==chain_id]
            receipts={str(p['chain_id'])+':'+p['receipt']['address'].lower() for p in rows if p.get('receipt') and p['receipt'].get('custody')=='wallet'}
            seen=set()
            for p in rows:
                if p['id'] in seen:continue
                seen.add(p['id'])
                receipt_matches=token_id is not None and str(p['chain_id'])+':'+(p.get('receipt') or {}).get('address','').lower()==token_id
                components=[a for a in p['assets'] if token_id is None or receipt_matches or str(p['chain_id'])+':'+a['address'].lower()==token_id]
                if not components:continue
                # Token view contains only this underlying's share of the claim.
                value=p.get('value_usd') if token_id is None or receipt_matches else (sum(a['value_usd'] for a in components) if all(a.get('value_usd') is not None for a in components) else None)
                positions_count+=1;stale+=bool(p.get('retained'))
                add(p['platform'],value,True)
            for a in wallet.get('assets',[]):
                if a.get('environment')!='mainnet' or not included(a) or a['id'] in receipts:continue
                if token_id is not None and a['id']!=token_id or chain_id is not None and a['chain_id']!=chain_id:continue
                platform='mintclub' if a.get('curve_reserve') else 'wallet'
                add(platform,a.get('value_usd'))
        total=sum(g['value_usd'] for g in groups.values())
        rows=[]
        for platform,g in sorted(groups.items(),key=lambda pair:(-pair[1]['value_usd'],pair[0])):
            name,color,logo,url=PLATFORMS[platform]
            rows.append({**g,'name':name,'color':color,'logo':'/venues/'+logo if logo else None,'url':url,
                         'value_usd':float(g['value_usd']) if g['value_usd'] or not g['unpriced_count'] else None,
                         'percent':float(g['value_usd']/total*100) if total else None})
        return {'groups':rows,'known_value_usd':float(total) if total or groups and not unknown else None,
                'unpriced_count':unknown,'retained_count':stale,'position_count':positions_count,
                'wallets_checked':checked,'wallet_count':len(wallets),'oldest_observed_at':min(observations,default=None),
                'coverage_gap_count':sum(c.get('status')!='checked' for w in wallets for c in w.get('position_coverage',[])),
                'latest_observed_at':max(observations,default=None),'basis':'Known recorded assets; principal/NAV, not sell-out value.',
                'complete_net_worth':False}


def read_positions(root, wallets, offset=0, limit=50, *, token_id=None,chain_id=None,platform=None):
    from kira_state import page
    rows=[]
    for w in wallets:
        for p in w.get('positions',[]):
            if platform is not None and p['platform']!=platform:continue
            if chain_id is not None and p['chain_id']!=chain_id:continue
            if token_id and str(p['chain_id'])+':'+(p.get('receipt') or {}).get('address','').lower()!=token_id and not any(str(p['chain_id'])+':'+a['address'].lower()==token_id for a in p['assets']):continue
            rows.append({**p,'wallet':w['key'],'wallet_name':w['name']})
    rows.sort(key=lambda p:(p.get('value_usd') is None,-(p.get('value_usd') or 0),p['id'],p['wallet']))
    gaps=[{**c,'wallet':w['key'],'wallet_name':w['name']} for w in wallets for c in w.get('position_coverage',[]) if c.get('status')!='checked' and (chain_id is None or c.get('chain_id')==chain_id)]
    return {**page(rows,offset,limit,key='positions'),'coverage_gaps':gaps[:100],'coverage_gap_count':len(gaps),'platform_filter':platform,'allocation':allocation(wallets,token_id=token_id,chain_id=chain_id),
            'allocation_scope':'Selected wallet/folder/token/network, before the platform list filter.'}
