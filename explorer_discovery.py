"""Opt-in, best-effort hosted explorer pages. RPC verifies all balances."""
import json
import re
from urllib.parse import urlencode
from public_discovery import discover_pages, fetch_page

# These official hosts answered the keyless paginated endpoint during admission.
# Hosted per-instance APIs are deprecated upstream; do not promise availability.
HOSTS={109:'https://shibariumscan.io',7560:'https://cyberscan.co',
       177:'https://explorer.hsk.xyz',157:'https://puppyscan.shib.io'}
CHAINS=set(HOSTS)
DOCS='https://docs.blockscout.com/devs/apis'


def cursor_params(value):
    if (not isinstance(value,dict) or not value or len(value)>16
            or any(not isinstance(k,str) or not re.fullmatch(r'[a-z_]{1,64}',k)
                   or type(v) not in (str,int,float) or len(str(v))>256 for k,v in value.items())
            or 'type' in value and value['type']!='ERC-20'):
        raise ValueError('Invalid explorer pagination parameters')
    return value


def discover(address,chain_id,*,fetch=fetch_page,budget=25,max_pages=20,state=None,save=lambda value:None,continue_only=False):
    if chain_id not in HOSTS:
        return {'chain_id':chain_id,'provider':'explorer','source':DOCS,'tokens':[],'native':[],
                'pages':[],'complete':False,'discovery_status':'unsupported','error':None}
    base=HOSTS[chain_id]+'/api/v2/addresses/'+address+'/tokens'
    def page_url(cursor):
        params=cursor_params(json.loads(cursor)) if cursor else {}
        return base+'?'+urlencode({**params,'type':'ERC-20'})
    def normalized(url,timeout):
        data=fetch(url,timeout)
        if (not isinstance(data,dict) or not isinstance(data.get('items'),list)
                or 'next_page_params' not in data):return data if isinstance(data,dict) and data.get('error') else {}
        items=[]
        for item in data['items']:
            meta=item.get('token') if isinstance(item,dict) else None
            if not isinstance(meta,dict) or meta.get('type')!='ERC-20':items.append(None);continue
            decimals=meta.get('decimals')
            decimals=int(decimals) if isinstance(decimals,str) and re.fullmatch(r'\d{1,3}',decimals) else decimals
            items.append({'chainId':chain_id,'tokenAddress':meta.get('address_hash'),'tokenQuantity':item.get('value'),
                          'tokenName':meta.get('name'),'tokenSymbol':meta.get('symbol'),'tokenDecimals':decimals})
        cursor=data['next_page_params']
        if cursor is not None:
            try:cursor=json.dumps(cursor_params(cursor),sort_keys=True,separators=(',',':'),allow_nan=False)
            except (ValueError,TypeError):cursor=False  # Shared validator preserves candidates without advancing.
        return {'items':items,'link':{'nextToken':cursor}}
    row=discover_pages(address,chain_id,provider='explorer',source=base,page_url=page_url,fetch=normalized,
        budget=budget,max_pages=max_pages,state=state,save=save,continue_only=continue_only)
    row['availability']='Best effort hosted API; per-instance endpoints are deprecated upstream.'
    return row
