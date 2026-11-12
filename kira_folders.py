"""Local wallet organization. No holdings, research or credentials are changed."""
from copy import deepcopy
from functools import lru_cache
import json
from pathlib import Path
import re
import uuid
from kira_jobs import JobError, atomic, digest, fields, now

OPERATIONS={'folder.create','folder.rename','folder.delete','folder.assign','folder.setMembers'}


def _name(value):
    if not isinstance(value,str) or not 1<=len(value.strip())<=80 or any(ord(c)<32 for c in value):
        raise JobError('invalid_folder_name','Use a folder name of 1 to 80 characters without control characters.')
    return value.strip()


@lru_cache(maxsize=8)
def _read(path,signature):
    value=json.loads(Path(path).read_text())
    if value.get('schema_version')!=1 or type(value.get('revision')) is not int or not isinstance(value.get('folders'),list) or not isinstance(value.get('assignments'),dict):
        raise JobError('invalid_folders','Saved folder metadata could not be read. Wallet research is preserved.')
    return value


def load(root):
    path=Path(root)/'wallet-folders.json'
    try:stat=path.stat()
    except FileNotFoundError:return {'schema_version':1,'revision':0,'folders':[],'assignments':{}}
    return _read(str(path.resolve()),(stat.st_mtime_ns,stat.st_size,stat.st_ino))


def key_used(root,key_hash):
    return (Path(root)/'.folder-actions'/(key_hash+'.json')).exists() or (load(root).get('last_action') or {}).get('key_hash')==key_hash


def catalog(root,wallets=None):
    saved=load(root)
    if wallets is None:wallets=json.loads((Path(root)/'wallets.json').read_text()).get('wallets',[])
    registered={w.get('key',w.get('address_key')) for w in wallets}
    ids={f['id'] for f in saved['folders']}
    assignments={k:v for k,v in saved['assignments'].items() if k in registered and v in ids}
    counts={key:0 for key in ids}
    for key in assignments.values():counts[key]+=1
    return {'schema_version':1,'revision':saved['revision'],
            'folders':[{**f,'wallet_count':counts[f['id']]} for f in sorted(saved['folders'],key=lambda f:(f['name'].casefold(),f['id']))],
            'assignments':assignments,'unfiled_count':len(registered)-len(assignments)}


def members(saved,wallets,folder_id):
    if folder_id in (None,'all'):return wallets
    if folder_id!='unfiled' and not any(f['id']==folder_id for f in saved['folders']):
        raise JobError('folder_not_found','This folder no longer exists. Choose All wallets or another saved folder.')
    return [w for w in wallets if (saved['assignments'].get(w.get('key',w.get('address_key'))) or 'unfiled')==folder_id]


def action(store,request):
    """Called under the shared operation lock. Commit metadata and recovery together."""
    fields(request,['schema_version','operation','input','idempotency_key'])
    operation=request['operation'];args=request['input'];key=request['idempotency_key']
    if type(request['schema_version']) is not int or request['schema_version']!=1:raise JobError('unsupported_version','Expected request schema version 1.')
    required={'folder.create':['name'],'folder.rename':['folder_id','name'],'folder.delete':['folder_id'],
              'folder.assign':['folder_id','wallets'],'folder.setMembers':['folder_id','wallets','expected_revision']}
    if operation not in required:raise JobError('unsupported_operation','Choose a folder action.')
    if not isinstance(args,dict) or set(args)-set(required[operation])-{'expected_revision'} or set(required[operation])-set(args):
        raise JobError('invalid_input','Unexpected or missing folder arguments.')
    if not isinstance(key,str) or not 8<=len(key)<=200:raise JobError('invalid_key','Supply an idempotency key of 8 to 200 characters.')
    root=store.root;key_hash=digest(key);fingerprint=digest({'operation':operation,'input':args})
    receipt=root/'.folder-actions'/(key_hash+'.json')
    if any((root/folder/(key_hash+'.json')).exists() for folder in ('jobs/requests','jobs/batches','.token-actions')) or any(j['key_hash']==key_hash or key_hash in (j.get('control_receipts') or {}) for j in store.summaries()):
        raise JobError('idempotency_conflict','This request key belongs to another operation.')
    saved=load(root)
    # A state commit carries its receipt. Recover it before a later edit can
    # replace this marker, without replaying an obsolete membership change.
    previous=saved.get('last_action')
    if previous:
        path=root/'.folder-actions'/(previous['key_hash']+'.json')
        if not path.exists():atomic(path,{k:v for k,v in previous.items() if k!='key_hash'})
    if receipt.exists():
        old=json.loads(receipt.read_text())
        if old['request_hash']!=fingerprint:raise JobError('idempotency_conflict','This request key belongs to a different folder action.')
        return old['result']
    expected=args.get('expected_revision')
    if 'expected_revision' in args and (type(expected) is not int or expected!=saved['revision']):
        raise JobError('folder_conflict','Folders changed while this form was open. Reload saved folders, then apply your changes.')
    value=deepcopy(saved);folder_id=args.get('folder_id')
    folder=next((f for f in value['folders'] if f['id']==folder_id),None)
    if operation!='folder.create' and not folder and not (operation=='folder.assign' and folder_id=='unfiled'):
        raise JobError('folder_not_found','Choose an existing folder.')
    if operation in ('folder.create','folder.rename'):
        name=_name(args['name'])
        if name.casefold() in ('all wallets','unfiled') or any(f['name'].casefold()==name.casefold() and f is not folder for f in value['folders']):
            raise JobError('folder_name_exists','A folder with this name already exists. Choose another name.')
        if operation=='folder.create':
            if len(value['folders'])>=200:raise JobError('folder_limit','Up to 200 folders are supported.')
            folder_id=uuid.uuid4().hex;folder={'id':folder_id,'name':name,'created_at':now(),'updated_at':now()};value['folders'].append(folder)
        else:folder.update(name=name,updated_at=now())
    elif operation=='folder.delete':
        value['folders']=[f for f in value['folders'] if f['id']!=folder_id]
        value['assignments']={k:v for k,v in value['assignments'].items() if v!=folder_id}
    else:
        wallets=args['wallets']
        if not isinstance(wallets,list) or len(wallets)>1000 or (operation=='folder.assign' and not wallets) or any(not isinstance(w,str) or not re.fullmatch(r'0x[0-9a-fA-F]{40}',w) for w in wallets):
            raise JobError('invalid_wallets','Choose up to 1,000 registered wallet addresses per action.')
        wallets=[w.lower() for w in wallets]
        registered={w['address_key'] for w in json.loads((root/'wallets.json').read_text())['wallets']}
        if len(set(wallets))!=len(wallets) or set(wallets)-registered:raise JobError('wallet_not_registered','Choose unique wallets already registered in Kira.')
        if operation=='folder.setMembers':value['assignments']={k:v for k,v in value['assignments'].items() if v!=folder_id}
        for wallet in wallets:
            if folder_id=='unfiled':value['assignments'].pop(wallet,None)
            else:value['assignments'][wallet]=folder_id
        if folder:folder['updated_at']=now()
    value['revision']+=1
    result={'schema_version':1,'completed':True,'operation':operation,'folder_id':folder_id,'revision':value['revision']}
    value['last_action']={'key_hash':key_hash,'request_hash':fingerprint,'result':result}
    atomic(root/'wallet-folders.json',value)
    atomic(receipt,{'request_hash':fingerprint,'result':result})
    return result
