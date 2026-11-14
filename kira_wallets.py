"""Recoverable registration removal. Saved research and keys are never deleted."""
from copy import deepcopy
import json
from pathlib import Path
import re
from kira_jobs import JobError, atomic, digest, fields, now

OPERATIONS={'wallet.remove','wallet.restore'}


def management(registry):
    active=[(w['address_key'],w.get('tags',[])) for w in registry.get('wallets',[])]
    removed=registry.get('removed_wallets',{})
    return {'revision':digest({'active':active,'removed':sorted((k,v['removed_at']) for k,v in removed.items())}),
            'removed_count':len(removed)}


def key_used(root,key_hash):
    path=Path(root)
    if (path/'.wallet-actions'/(key_hash+'.json')).exists():return True
    registry=json.loads((path/'wallets.json').read_text())
    return (registry.get('wallet_last_action') or {}).get('key_hash')==key_hash


def removed_page(root,offset=0,limit=50,query=''):
    from kira_state import page
    if not isinstance(query,str) or len(query)>200:raise JobError('invalid_query','Search with up to 200 characters.')
    registry=json.loads((Path(root)/'wallets.json').read_text());text=query.strip().casefold();rows=[]
    for key,record in registry.get('removed_wallets',{}).items():
        w=record['wallet'];name=(w.get('tags') or [w['address']])[0]
        if text and not any(text in str(v).casefold() for v in [key,w['address'],*w.get('tags',[])]):continue
        rows.append({'key':key,'address':w['address'],'name':name,'tags':w.get('tags',[]),'removed_at':record['removed_at']})
    rows.sort(key=lambda w:(w['removed_at'],w['key']),reverse=True)
    return {**management(registry),**page(rows,offset,limit,key='wallets')}


def action(store,request):
    """Called under the job admission lock; one registry commit holds recovery."""
    fields(request,['schema_version','operation','input','idempotency_key'])
    if type(request['schema_version']) is not int or request['schema_version']!=1:raise JobError('unsupported_version','Expected request schema version 1.')
    operation=request['operation'];args=request['input'];key=request['idempotency_key']
    if operation not in OPERATIONS:raise JobError('unsupported_operation','Choose remove or restore.')
    fields(args,['wallets','expected_revision'])
    if not isinstance(key,str) or not 8<=len(key)<=200:raise JobError('invalid_key','Supply an idempotency key of 8 to 200 characters.')
    values=args['wallets']
    if not isinstance(values,list) or not 1<=len(values)<=1000 or any(not isinstance(w,str) or not re.fullmatch(r'0x[0-9a-fA-F]{40}',w) for w in values):
        raise JobError('invalid_wallets','Choose 1 to 1,000 registered wallet addresses.')
    keys=[w.lower() for w in values];targets=set(keys)
    if len(set(keys))!=len(keys):raise JobError('invalid_wallets','Choose each wallet once.')
    key_hash=digest(key);fingerprint=digest({'operation':operation,'input':args});root=store.root
    from wallet import registry_locked
    with registry_locked(root):
        registry=json.loads((root/'wallets.json').read_text())
        prior=registry.get('wallet_last_action')
        if prior:
            target=root/'.wallet-actions'/(prior['key_hash']+'.json')
            if not target.exists():atomic(target,{k:v for k,v in prior.items() if k!='key_hash'})
        receipt=root/'.wallet-actions'/(key_hash+'.json')
        if receipt.exists():
            old=json.loads(receipt.read_text())
            if old['request_hash']!=fingerprint:raise JobError('idempotency_conflict','This key belongs to a different wallet action.')
            return old['result']
        from kira_folders import load
        if (load(root).get('last_action') or {}).get('key_hash')==key_hash or any((root/folder/(key_hash+'.json')).exists() for folder in ('.folder-actions','.token-actions','jobs/requests','jobs/batches')) or any(j['key_hash']==key_hash or key_hash in (j.get('control_receipts') or {}) for j in store.summaries()):
            raise JobError('idempotency_conflict','This key belongs to another operation.')
        if args['expected_revision']!=management(registry)['revision']:
            raise JobError('wallet_conflict','Wallets changed elsewhere. Reload the list and review your selection.')
        current={w['address_key']:w for w in registry['wallets']};removed=registry.setdefault('removed_wallets',{})
        if operation=='wallet.restore' and targets&current.keys():raise JobError('wallet_exists','Some selected wallets are already registered. Reload the list.')
        source=current if operation=='wallet.remove' else removed
        if set(keys)-source.keys():raise JobError('wallet_not_found','Some selected wallets are no longer in this list. Reload and select again.')
        active=[j for j in store.summaries() if j['state'] in ('queued','running') and (j['input'].get('wallet') or j['input'].get('address','')).lower() in targets]
        if active:raise JobError('wallet_busy',str(len({(j['input'].get('wallet') or j['input'].get('address')).lower() for j in active}))+' selected wallets have work in progress. Pause their scans in Activity, then try again.')
        if operation=='wallet.remove':
            stamp=now()
            for index,w in enumerate(registry['wallets']):
                if w['address_key'] in targets:removed[w['address_key']]={'wallet':deepcopy(w),'position':index,'removed_at':stamp}
            registry['wallets']=[w for w in registry['wallets'] if w['address_key'] not in targets]
        else:
            for record in sorted((removed.pop(k) for k in keys),key=lambda r:r['position']):
                registry['wallets'].insert(min(record['position'],len(registry['wallets'])),record['wallet'])
        result={'schema_version':1,'completed':True,'operation':operation,'wallet_count':len(keys),**management(registry)}
        registry['wallet_last_action']={'key_hash':key_hash,'request_hash':fingerprint,'result':result}
        atomic(root/'wallets.json',registry)
        atomic(receipt,{'request_hash':fingerprint,'result':result})
        return result
