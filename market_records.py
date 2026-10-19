"""Market identity and public routes. Pool existence never establishes a price."""
import json
from pathlib import Path
import re
from urllib.parse import quote, urlsplit

NETWORKS={n['chain_id']:n['network'] for n in json.loads((Path(__file__).parent/'networks.json').read_text())['networks']}


def mintclub_url(chain_id, symbol, token_type='ERC20'):
    slug=NETWORKS.get(chain_id)
    if not slug or not isinstance(symbol,str) or not symbol or len(symbol)>256 or symbol in ('.','..') or re.match(r'^0x[0-9a-fA-F]{8,}$',symbol) or any(ord(c)<32 for c in symbol):return None
    if token_type not in ('ERC20','ERC1155'):return None
    return 'https://mint.club/'+('nft' if token_type=='ERC1155' else 'token')+'/'+slug+'/'+quote(symbol,safe='')


def canonical_source(source, token):
    """Repair this token's old route only, leaving other source evidence intact."""
    if not isinstance(source,str):return source
    try:parsed=urlsplit(source)
    except ValueError:return source
    if parsed.scheme not in ('http','https') or parsed.hostname!='mint.club':return source
    parts=parsed.path.split('/')
    if len(parts)!=4 or parts[1] not in ('token','nft'):return source
    from urllib.parse import unquote
    if unquote(parts[3]).casefold() not in {str(token.get('token_address','')).casefold(),str(token.get('symbol','')).casefold()}:return source
    return mintclub_url(token.get('chain_id'),token.get('symbol'),token.get('token_type','ERC20')) or source


def canonical_token(token):
    mint=token.get('mintclub')
    if not mint:return token
    return {**token,'mintclub':{**mint,'source_url':mintclub_url(token.get('chain_id'),token.get('symbol'),token.get('token_type','ERC20')) or mint.get('source_url')}}


def pool_row(pair, observed):
    pool=pair['pairAddress']
    return {'pool':pool,'pool_kind':'pool_id' if re.fullmatch(r'0x[0-9a-fA-F]{64}',pool) else 'address',
            'venue':pair['dexId'],'version_labels':pair.get('labels') or [],'fee_bps':pair.get('fee_bps'),
            'paired_tokens':[pair['baseToken'],pair['quoteToken']],'reported_liquidity':pair.get('liquidity'),
            'reported_volume_24h_usd':(pair.get('volume') or {}).get('h24'),'reported_price_usd':pair.get('priceUsd'),
            'observed_at':observed,'source_url':pair['url'],'rpc_verification':None,'factory_measurement':None}


def pool_identity(pool):
    venue=str(pool.get('venue','')).lower()
    venue='uniswap' if 'uniswap' in venue else 'aerodrome' if 'aerodrome' in venue else venue
    return venue,str(pool.get('pool') or pool.get('source_url') or '').lower()


def merge_pools(*groups):
    rows={}
    for group in groups:
        for pool in group:
            key=pool_identity(pool)
            previous=rows.get(key,{})
            # Factory-only evidence augments identity without replacing a dated
            # indexer's liquidity/price observation with a fresh empty row.
            metadata_only=pool.get('reported_liquidity') is None and pool.get('reported_price_usd') is None
            merged={**previous,**pool} if not previous or not metadata_only else {**pool,**previous}
            for field in ('factory_discovery','rpc_verification','factory_measurement','fee_bps','pool_kind'):
                if pool.get(field) is not None:merged[field]=pool[field]
            if 'version_labels' in previous or 'version_labels' in pool:merged['version_labels']=list(dict.fromkeys(previous.get('version_labels',[])+pool.get('version_labels',[])))
            rows[key]=merged
    return list(rows.values())


def collected_markets(records, chains, wanted=None, previous=()):
    """Index either pair member within its chain, unioning all observed venues."""
    inverse={slug:cid for cid,slug in chains.items()}
    rows={row['id']:{**row,'pools':merge_pools(row.get('pools',[]))} for row in previous}
    for record in records:
        response=record.get('response')
        pairs=response if isinstance(response,list) else (response.get('pairs') or []) if isinstance(response,dict) else []
        for pair in pairs:
            try:
                cid=inverse[pair['chainId']];pool=pool_row(pair,record.get('observed_at'))
                for coin in (pair['baseToken'],pair['quoteToken']):
                    address=coin['address'].lower()
                    if not re.fullmatch(r'0x[0-9a-f]{40}',address) or wanted is not None and (cid,address) not in wanted:continue
                    identity=f'{cid}:{address}'
                    rows[identity]={'id':identity,'pools':merge_pools(rows.get(identity,{}).get('pools',[]),[pool])}
            except (KeyError,TypeError,AttributeError,ValueError):continue
    return list(rows.values())
