"""Local OWS public-descriptor connection and human-submitted encrypted creation."""
from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import threading
import uuid
from kira_jobs import JobError, JobStore, atomic, fields, identifier

class OwsStore:
    def __init__(self, root, vault=None, runner=None):
        self.root=Path(root).resolve();self.vault=Path(vault or os.environ.get('KIRA_OWS_VAULT',str(Path.home()/'.ows'))).expanduser().resolve()
        self.runner=runner or self.bridge;self.lock=threading.RLock();self.session=self.root/'.kira-ows-session.json'
        self.receipts=self.root/'.kira-ows-requests'

    def bridge(self, request):
        node=shutil.which('node')
        if not node:raise JobError('ows_unavailable','Install Node.js and the optional OWS SDK to connect a local wallet.')
        env={key:os.environ[key] for key in ('HOME','PATH','TMPDIR','SYSTEMROOT') if key in os.environ}
        try:
            result=subprocess.run([node,str(Path(__file__).with_name('ows_bridge.cjs'))],input=json.dumps(request),capture_output=True,text=True,timeout=60,env=env)
            if result.returncode or len(result.stdout)>1_000_000:raise ValueError()
            value=json.loads(result.stdout)
            if value.get('error'):raise ValueError()
            return value
        except (OSError,ValueError,subprocess.TimeoutExpired):
            raise JobError('ows_unavailable','The local OWS SDK is unavailable or could not finish. Keep using a browser wallet or a public address. Check the local OWS installation before retrying.') from None

    def descriptors(self):
        result=self.runner({'action':'list','vault':str(self.vault)})
        if not isinstance(result.get('wallets'),list):raise JobError('ows_unavailable','No valid OWS descriptors were returned.')
        return [self.public(w) for w in result['wallets']][:200]

    def public(self, value):
        if not isinstance(value,dict) or not isinstance(value.get('id'),str) or len(value['id'])>100 or not isinstance(value.get('name'),str) or not isinstance(value.get('accounts'),list):
            raise JobError('ows_invalid','The OWS wallet descriptor is invalid.')
        accounts=[{'chain_id':a['chain_id'],'address':a['address']} for a in value['accounts'] if isinstance(a,dict) and isinstance(a.get('chain_id'),str) and re.fullmatch(r'eip155:[1-9][0-9]*',a['chain_id']) and isinstance(a.get('address'),str) and re.fullmatch(r'0x[0-9a-fA-F]{40}',a['address'])]
        return {'id':value['id'],'name':value['name'][:120],'created_at':value.get('created_at'),'accounts':accounts}

    def status(self):
        try:wallets=self.descriptors();available=True;note='Only public EVM accounts are linked. Signing stays in your OWS wallet.'
        except JobError:wallets=[];available=False;note='OWS is optional. Install @open-wallet-standard/core 1.4.3 to use a local vault wallet.'
        connection=None
        if self.session.is_file():
            try:connection=json.loads(self.session.read_text())
            except (ValueError,OSError):pass
        return {'available':available,'wallets':wallets,'connection':connection,'note':note}

    @contextmanager
    def owner_lock(self):
        with self.lock:
            self.vault.mkdir(parents=True,exist_ok=True,mode=0o700)
            with (self.vault/'.kira-create.lock').open('a') as lock:
                fcntl.flock(lock,fcntl.LOCK_EX);yield

    def disconnect(self):
        with self.lock:atomic(self.session,None);self.session.chmod(0o600)
        return {'connection':None}

    def submit(self, request, create=False):
        fields(request,['name','passphrase','tag','idempotency_key'] if create else ['wallet_id','tag','idempotency_key'])
        key=identifier(request['idempotency_key']);tag=request['tag']
        if not isinstance(tag,str) or not tag.strip() or len(tag)>200:raise JobError('invalid_tag','Give this wallet a name.')
        if create:
            if not isinstance(request['name'],str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9 ._-]{1,63}',request['name']):raise JobError('invalid_name','Use 2 to 64 letters, numbers, spaces, periods, underscores or hyphens for the OWS name.')
            if not isinstance(request['passphrase'],str) or not 12<=len(request['passphrase'].strip())<=1024:raise JobError('passphrase_required','Use an encryption passphrase of at least 12 characters.')
        elif not isinstance(request['wallet_id'],str) or len(request['wallet_id'])>100:raise JobError('invalid_wallet','Choose a local OWS wallet.')
        public={k:request[k] for k in request if k!='passphrase'};fingerprint=hashlib.sha256(json.dumps([create,public],sort_keys=True).encode()).hexdigest()
        with self.owner_lock():
            self.receipts.mkdir(parents=True,exist_ok=True,mode=0o700);path=self.receipts/(key+'.json')
            receipt=json.loads(path.read_text()) if path.is_file() else None
            if receipt and receipt['request_hash']!=fingerprint:raise JobError('idempotency_conflict','This wallet request ID was already used for another wallet.')
            if not receipt:
                receipt={'request_hash':fingerprint,'phase':'reserved','sdk_name':request['name'][:54]+'-'+key if create else None}
                atomic(path,receipt);path.chmod(0o600)
            recovered='wallet' in receipt
            if 'wallet' in receipt:wallet=self.public(receipt['wallet'])
            elif create:
                shared_dir=self.vault/'.kira-requests';shared_dir.mkdir(mode=0o700,exist_ok=True)
                shared_path=shared_dir/(key+'.json')
                shared=json.loads(shared_path.read_text()) if shared_path.is_file() else None
                if shared and shared['request_hash']!=fingerprint:
                    raise JobError('idempotency_conflict','This creation request belongs to another wallet.')
                if not shared:
                    if any(w['name']==receipt['sdk_name'] for w in self.descriptors()):
                        raise JobError('ows_name_conflict','A wallet already uses this creation identity. Choose an existing wallet instead.')
                    shared={'request_hash':fingerprint,'sdk_name':receipt['sdk_name'],'attempted':False}
                recovering=shared['attempted'];shared['attempted']=True;atomic(shared_path,shared)
                # Never put the passphrase in a receipt, argv, job or conversation.
                result=self.runner({'action':'create','vault':str(self.vault),'name':receipt['sdk_name'],'passphrase':request['passphrase'],'allow_recovery':recovering})
                recovered=result.get('recovered',False)
                wallet=self.public(result['wallet']);receipt.update(wallet=wallet,phase='created');atomic(path,receipt)
            else:
                wallet=next((w for w in self.descriptors() if w['id']==request['wallet_id']),None)
                if wallet is None:raise JobError('wallet_missing','This local OWS wallet is no longer available.')
                receipt.update(wallet=wallet,phase='selected');atomic(path,receipt)
            if not wallet['accounts']:raise JobError('unsupported_wallet','This OWS wallet has no EVM account. Kira currently researches EVM wallets.')
            address=wallet['accounts'][0]['address'];store=JobStore(self.root)
            registered=next((w for w in json.loads((self.root/'wallets.json').read_text())['wallets'] if w['address_key']==address.lower()),None)
            job=None
            if not registered:
                job=store.submit({'schema_version':1,'operation':'wallet.add','input':{'address':address,'tag':tag},'idempotency_key':str(uuid.uuid5(uuid.UUID(key),'ows-register'))})
                if job['state']=='queued':store.launch()
            connection={'source':'ows','wallet_id':wallet['id'],'name':wallet['name'],'address':address,'tag':(registered.get('tags') or [tag])[0] if registered else tag}
            atomic(self.session,connection);self.session.chmod(0o600)
            receipt.update(phase='connected',connection=connection,job_id=job['job_id'] if job else receipt.get('job_id'))
            atomic(path,receipt)
            note='The prior wallet creation was recovered. Its original encryption passphrase is unchanged.' if create and recovered else 'The public account is linked. Your encrypted OWS keys remain in the vault.'
            return {'connection':connection,'job_id':receipt.get('job_id'),'created':create and not recovered,'recovered':create and recovered,'note':note}
