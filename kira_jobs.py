"""Versioned private job service shared by CLI and loopback controls."""
from __future__ import annotations
from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import selectors
import signal
import subprocess
import sys
import tempfile
import time
from typing import Literal, TypedDict, NotRequired
import uuid

ASSETS = Path(__file__).resolve().parent

def signal_process_group(pgid, sig):
    try:os.killpg(pgid,sig)
    except ProcessLookupError:return
    except PermissionError:
        # macOS can return EPERM for an already exited process group. Only
        # dismiss it after proving no live member can continue writing.
        status=subprocess.run(['ps','-axo','pgid=,stat='],capture_output=True,text=True,timeout=3)
        rows=[line.split() for line in status.stdout.splitlines() if line.strip()]
        valid=bool(rows) and all(len(row)==2 and re.fullmatch(r'\d+',row[0]) and re.fullmatch(r'[DRISTUWZX][<NnLs+ElWXV]*',row[1]) for row in rows)
        if status.returncode or not valid or any(int(row[0])==pgid and not row[1].startswith('Z') for row in rows):raise

State = Literal['queued', 'running', 'interrupted', 'succeeded', 'partial', 'failed', 'cancelled']
Operation = Literal['wallet.add','wallet.refresh','prices.refresh','wallet.setTags','settings.rpc','settings.discovery','settings.provider','settings.importEnv']
TERMINAL = {'succeeded', 'partial', 'failed', 'cancelled', 'interrupted'}
ADDRESS = re.compile(r'0x[0-9a-fA-F]{40}')

class Request(TypedDict):
    schema_version: int
    operation: str
    input: dict
    idempotency_key: str

class AddInput(TypedDict):
    address: str
    tag: str

class WalletInput(TypedDict):
    wallet: str

class TagsInput(WalletInput):
    tags: list[str]

class Job(TypedDict):
    schema_version: int
    job_id: str
    operation: Operation
    input: AddInput | WalletInput | TagsInput | dict
    state: State
    attempt: int
    sequence: int
    result: dict | None
    previous_result: dict | None
    key_hash: str
    request_hash: str
    raw_hash: str
    created_at: str
    updated_at: str
    started_at: NotRequired[str]
    cancel_requested: bool
    checkpoint: str
    stage: str
    events: list[dict]
    errors: list[dict]
    chains: dict
    control_receipts: NotRequired[dict[str,str]]
    control_raw: NotRequired[dict[str,str]]
    provider_configuration: NotRequired[dict]

class JobError(ValueError):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code

def now():
    return datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')

def atomic(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, name = tempfile.mkstemp(prefix='.', suffix='.tmp', dir=path.parent)
    try:
        with os.fdopen(fd, 'w') as stream:
            json.dump(value, stream, indent=2, ensure_ascii=False, allow_nan=False)
            stream.write('\n'); stream.flush(); os.fsync(stream.fileno())
        os.replace(name, path)
        directory = os.open(path.parent, os.O_RDONLY)
        try: os.fsync(directory)
        finally: os.close(directory)
    finally:
        if os.path.exists(name): os.unlink(name)

def read(path):
    return json.loads(Path(path).read_text())

def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()

def fields(value, required):
    if not isinstance(value, dict) or set(value) != set(required):
        raise JobError('invalid_input', 'Unexpected or missing operation fields.')

def identifier(value):
    if not isinstance(value, str): raise JobError('invalid_id', 'Expected a job ID.')
    try:
        if str(uuid.UUID(value)) != value: raise ValueError()
    except ValueError: raise JobError('invalid_id', 'Expected a canonical job ID.') from None
    return value

class JobStore:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.jobs = self.root / 'jobs'
        self.jobs.mkdir(parents=True, exist_ok=True, mode=0o700)

    @contextmanager
    def locked(self):
        with (self.root / '.jobs.lock').open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            yield

    def get(self, job_id):
        path = self.jobs / (identifier(job_id) + '.json')
        if not path.exists(): raise JobError('not_found', 'Job was not found.')
        job = read(path)
        if not isinstance(job,dict) or type(job.get('schema_version')) is not int or job.get('schema_version') != 1: raise JobError('unsupported_version', 'Unsupported persisted job version.')
        required={'schema_version','job_id','operation','input','state','attempt','sequence','result','previous_result','key_hash','request_hash','created_at','updated_at','cancel_requested','checkpoint','stage','events','errors','chains'}
        optional={'raw_hash','control_receipts','control_raw','provider_configuration','started_at','analysis_phase','parent_job_id','continuation_id'}
        if required-set(job) or set(job)-required-optional or job['job_id']!=job_id or job['checkpoint']!='snapshots/jobs/'+job_id or not isinstance(job['operation'],str) or job['operation'] not in {'wallet.add','wallet.refresh','prices.refresh','wallet.setTags','settings.rpc','settings.discovery','settings.provider','settings.importEnv'} or not isinstance(job['state'],str) or job['state'] not in TERMINAL|{'queued','running'} or any(type(job[k]) is not int or job[k]<0 for k in ('attempt','sequence')) or type(job['cancel_requested']) is not bool or not isinstance(job['input'],dict) or any(not isinstance(job[k],list) for k in ('events','errors')) or not isinstance(job['chains'],dict):
            raise JobError('invalid_envelope','Persisted job validation failed. Preserve the file for recovery.')
        names={'wallet.add':['address','tag'],'wallet.refresh':['wallet'],'prices.refresh':['wallet'],'wallet.setTags':['wallet','tags'],
            'settings.rpc':['mode','chains','allow_public_fallback'],'settings.discovery':['provider','key_env'],'settings.provider':['provider','key_env'],'settings.importEnv':['import_id','key_env']}[job['operation']]
        if job['operation']=='settings.rpc' and 'priority' in job['input']:names=names+['priority']
        fields(job['input'],names)
        if 'analysis_phase' in job and job['analysis_phase'] not in ('baseline','enrichment'):raise JobError('invalid_envelope','Invalid analysis phase.')
        for field in ('parent_job_id','continuation_id'):
            if field in job:identifier(job[field])
        wallet=job['input'].get('wallet') or job['input'].get('address')
        if wallet is not None and (not isinstance(wallet,str) or not ADDRESS.fullmatch(wallet)):raise JobError('invalid_envelope','Persisted wallet identity is invalid.')
        return job

    def list(self):
        with self.locked():
            return sorted((self.get(p.stem) for p in self.jobs.glob('*.json')), key=lambda j: j['created_at'], reverse=True)

    def save(self, job):
        job['sequence'] += 1; job['updated_at'] = now()
        atomic(self.jobs / (job['job_id'] + '.json'), job)
        return job

    def wallet(self, selector):
        if not isinstance(selector, str) or not selector or len(selector) > 200:
            raise JobError('invalid_wallet', 'Expected a registered address or exact tag.')
        wallets = read(self.root / 'wallets.json')['wallets']
        matches = [w for w in wallets if w['address_key'] == selector.lower() or selector in w['tags']]
        if not matches:
            raise JobError('wallet_not_registered', 'No registered wallet matches this address or name. A new wallet may still be queued for registration. Check Activity.')
        if len(matches) != 1:
            raise JobError('wallet_not_unique', 'More than one registered wallet has this name. Choose its exact public address.')
        return matches[0]

    def normalize(self, operation, value):
        if operation == 'settings.importEnv':
            fields(value,['import_id','key_env'])
            identifier(value['import_id'])
            if not isinstance(value['key_env'],str) or not re.fullmatch(r'[A-Z_][A-Z0-9_]{0,99}',value['key_env']):
                raise JobError('invalid_settings','Use a local credential reference.')
            self.import_reference(value)
            return value.copy()
        if operation == 'settings.provider':
            fields(value,['provider','key_env'])
            if value['provider'] not in ('public','alchemy') or not isinstance(value['key_env'],str) or not re.fullmatch(r'[A-Z_][A-Z0-9_]{0,99}',value['key_env']):
                raise JobError('invalid_settings','Choose a data provider and a local credential reference.')
            return value.copy()
        if operation == 'settings.rpc':
            fields(value,['mode','chains','allow_public_fallback']+(['priority'] if isinstance(value,dict) and 'priority' in value else []))
            if value.get('priority','public_first') not in ('public_first','custom_first'):
                raise JobError('invalid_settings','Choose a valid RPC priority.')
            if value['mode'] not in ('public','custom') or type(value['allow_public_fallback']) is not bool or not isinstance(value['chains'],list) or len(value['chains'])>30:
                raise JobError('invalid_settings','Choose a valid RPC mode and credential references.')
            available={n['chain_id'] for n in read(ASSETS/'sources/rpc-candidates.json')}
            chains={}
            for chain in value['chains']:
                fields(chain,['chain_id','url_env'])
                if type(chain['chain_id']) is not int or chain['chain_id'] not in available or not isinstance(chain['url_env'],str) or not re.fullmatch(r'[A-Z_][A-Z0-9_]{0,99}',chain['url_env']) or str(chain['chain_id']) in chains:
                    raise JobError('invalid_settings','Use a known chain and a unique environment variable reference.')
                chains[str(chain['chain_id'])]={'url_env':chain['url_env']}
            if value['mode']=='custom' and not chains:raise JobError('invalid_settings','Custom RPC requires at least one endpoint reference.')
            return {'mode':value['mode'],'chains':chains,'allow_public_fallback':value['allow_public_fallback'],**({'priority':value['priority']} if 'priority' in value else {})}
        if operation == 'settings.discovery':
            fields(value,['provider','key_env'])
            if value['provider'] not in ('none','alchemy') or not isinstance(value['key_env'],str) or not re.fullmatch(r'[A-Z_][A-Z0-9_]{0,99}',value['key_env']):raise JobError('invalid_settings','Use a supported indexer and environment variable reference.')
            return value.copy()
        if operation == 'wallet.add':
            fields(value, ['address', 'tag'])
            if not isinstance(value['address'], str) or not ADDRESS.fullmatch(value['address']):
                raise JobError('invalid_address', 'Expected a 20-byte EVM address.')
            if not isinstance(value['tag'], str) or not value['tag'].strip() or len(value['tag']) > 200 or any(ord(c) < 32 for c in value['tag']):
                raise JobError('invalid_tag', 'Supply an exact non-empty wallet tag, up to 200 characters.')
            # Validate mixed-case checksums with the existing engine contract.
            from wallet import validate_address
            address = validate_address(value['address'])
            return {'address': address, 'tag': value['tag']}
        if operation in {'wallet.refresh', 'prices.refresh', 'wallet.setTags'}:
            fields(value, ['wallet', 'tags'] if operation == 'wallet.setTags' else ['wallet'])
            wallet = self.wallet(value['wallet'])
            if operation == 'prices.refresh' and not wallet.get('latest_snapshot'):
                raise JobError('no_snapshot', 'Analyse this wallet before refreshing prices.')
            result = {'wallet': wallet['address_key']}
            if operation == 'wallet.setTags':
                tags = value['tags']
                if not isinstance(tags, list) or not 1 <= len(tags) <= 20 or any(not isinstance(t, str) or not t.strip() or len(t) > 200 or any(ord(c) < 32 for c in t) for t in tags) or len(set(tags)) != len(tags):
                    raise JobError('invalid_tags', 'Supply 1 to 20 unique exact non-empty tags.')
                result['tags'] = tags
            return result
        if operation in {'job.resume', 'job.cancel'}:
            fields(value, ['job_id']); identifier(value['job_id'])
            return value.copy()
        raise JobError('unsupported_operation', 'Unsupported job operation.')

    def import_reference(self, value):
        file=self.root/'.config-imports'/(identifier(value['import_id'])+'.json')
        if not file.is_file() or file.is_symlink() or file.resolve().parent != (self.root/'.config-imports').resolve():
            raise JobError('invalid_import','Run kira config import-env locally to create a connection request.')
        record=read(file)
        if record.get('key_env')!=value['key_env'] or not isinstance(record.get('file'),str) or not Path(record['file']).is_file():
            raise JobError('invalid_import','The local environment file is no longer available. Run kira config import-env again.')
        return record['file']

    def queue_import(self, file, key_env):
        if not isinstance(key_env,str) or not re.fullmatch(r'[A-Z_][A-Z0-9_]{0,99}',key_env):
            raise JobError('invalid_settings','Use a local credential reference.')
        file=Path(file).expanduser().resolve()
        if not file.is_file():raise JobError('invalid_import','Secret environment file does not exist.')
        identity=str(uuid.uuid4())
        # Only the reference stays in this private record. The browser job has no
        # file path or credential value, and the existing writer stays exclusive.
        atomic(self.root/'.config-imports'/(identity+'.json'),{'file':str(file),'key_env':key_env})
        return self.submit({'schema_version':1,'operation':'settings.importEnv','input':{'import_id':identity,'key_env':key_env},'idempotency_key':identity})

    def admit_wallet(self, job):
        if job['operation'] not in ('wallet.add','wallet.refresh'):return job
        from wallet import register, registry_locked
        with registry_locked(self.root):
            registry=read(self.root/'wallets.json')
            admissions=registry.setdefault('wallet_admissions',{})
            address=job['input'].get('address') or job['input'].get('wallet')
            entry=next((w for w in registry['wallets'] if w['address_key']==address.lower()),None)
            if job['job_id'] not in admissions:
                legacy_done=not job.get('analysis_phase') and (job['state']!='queued' or job['attempt']>0) and entry is not None
                if job['operation']=='wallet.add' and not legacy_done:
                    entry=register(registry,address,job['input']['tag'])
                if job.get('analysis_phase')=='baseline':entry['research_generation']=job['job_id']
                admissions[job['job_id']]=address.lower()
                atomic(self.root/'wallets.json',registry)
            elif entry is None and job['operation']=='wallet.add':
                register(registry,address,job['input']['tag'])
                atomic(self.root/'wallets.json',registry)
        return job

    def submit(self, request, *, phase='baseline', parent=None):
        fields(request, ['schema_version', 'operation', 'input', 'idempotency_key'])
        if type(request['schema_version']) is not int or request['schema_version'] != 1:
            raise JobError('unsupported_version', 'Expected request schema version 1.')
        key = request['idempotency_key']
        if not isinstance(key, str) or not 8 <= len(key) <= 200:
            raise JobError('invalid_key', 'Supply an idempotency key of 8 to 200 characters.')
        with self.locked():
            operation = request['operation']
            if not isinstance(operation,str):raise JobError('unsupported_operation','Expected a typed operation name.')
            key_hash = digest(key); receipt = self.jobs / 'requests' / (key_hash + '.json')
            raw_hash=digest({'operation':operation,'input':request['input']})
            if receipt.exists() and read(receipt).get('raw_hash')==raw_hash:return self.admit_wallet(self.get(read(receipt)['job_id']))
            for p in self.jobs.glob('*.json'):
                saved=self.get(p.stem)
                if saved.get('control_raw',{}).get(key_hash)==raw_hash or saved['key_hash']==key_hash and saved.get('raw_hash')==raw_hash:
                    fingerprint=saved.get('control_receipts',{}).get(key_hash,saved['request_hash'])
                    atomic(receipt,{'schema_version':1,'request_hash':fingerprint,'raw_hash':raw_hash,'job_id':saved['job_id']})
                    return self.admit_wallet(saved)
            value = self.normalize(operation, request['input'])
            fingerprint = digest({'operation': operation, 'input': value})
            if receipt.exists():
                old = read(receipt)
                if old['request_hash'] != fingerprint: raise JobError('idempotency_conflict', 'This request key already belongs to another operation.')
                return self.admit_wallet(self.get(old['job_id']))
            # Recover an envelope committed before its request receipt.
            existing = next((j for p in self.jobs.glob('*.json') if (j := self.get(p.stem))['key_hash'] == key_hash or key_hash in j.get('control_receipts',{})), None)
            if existing:
                recorded=existing.get('control_receipts',{}).get(key_hash,existing['request_hash'])
                if recorded != fingerprint: raise JobError('idempotency_conflict', 'This request key already belongs to another operation.')
                job = existing
            elif operation in {'job.resume', 'job.cancel'}:
                job = self.get(value['job_id'])
                if operation == 'job.resume':
                    if job['state'] not in {'interrupted', 'failed', 'cancelled'}:
                        raise JobError('not_resumable', 'Only interrupted, failed or cancelled jobs can resume.')
                    job.update(state='queued', cancel_requested=False, errors=[])
                elif job['state'] == 'queued': job.update(state='cancelled', cancel_requested=True)
                elif job['state'] == 'running': job['cancel_requested'] = True
                job.setdefault('control_receipts',{})[key_hash]=fingerprint
                job.setdefault('control_raw',{})[key_hash]=raw_hash
                self.save(job)
            else:
                previous = None
                if operation=='wallet.add':
                    existing_wallet=next((w for w in read(self.root/'wallets.json')['wallets'] if w['address_key']==value['address'].lower()),None)
                    if existing_wallet:previous=existing_wallet.get('latest_snapshot')
                if operation in {'wallet.refresh','prices.refresh','wallet.setTags'}:
                    previous = self.wallet(value['wallet']).get('latest_snapshot')
                job_id = str(uuid.uuid4())
                job = {'schema_version': 1, 'job_id': job_id, 'operation': operation, 'input': value,
                    'key_hash': key_hash, 'request_hash': fingerprint,'raw_hash':raw_hash, 'state': 'queued', 'attempt': 0,
                    'created_at': now(), 'updated_at': now(), 'sequence': 0, 'cancel_requested': False,
                    'stage': 'queued', 'events': [], 'checkpoint': 'snapshots/jobs/' + job_id,
                    'result': None, 'previous_result': previous, 'errors': [],'chains':{}}
                if operation in ('wallet.add','wallet.refresh'):job['analysis_phase']=phase
                if parent:job['parent_job_id']=parent
                self.save(job)
            self.admit_wallet(job)
            atomic(receipt, {'schema_version': 1, 'request_hash': fingerprint,'raw_hash':raw_hash, 'job_id': job['job_id']})
            return job

    def snapshot(self, snapshot_id):
        if not isinstance(snapshot_id, str) or not snapshot_id.startswith('snapshots/'):
            raise JobError('invalid_snapshot', 'Expected a saved snapshot ID.')
        path = (self.root / snapshot_id).resolve()
        if not path.is_relative_to((self.root / 'snapshots').resolve()) or '..' in Path(snapshot_id).parts:
            raise JobError('invalid_snapshot', 'Snapshot ID is outside saved evidence.')
        if not (path / 'results.json').is_file(): raise JobError('not_found', 'Snapshot was not found.')
        result = read(path / 'results.json')
        # Public readers receive financial facts, never arbitrary raw provider files.
        from kira_config import redact
        def safe(value, key=''):
            if 'error' in key.lower() and value: return {'code': 'provider_error', 'message': 'Recorded provider read failed.'}
            if isinstance(value, dict): return {k: safe(v,k) for k,v in value.items()}
            if isinstance(value, list): return [safe(v,key) for v in value]
            if isinstance(value,str) and ('http://' in value or 'https://' in value):
                from urllib.parse import urlparse
                parsed=urlparse(value)
                if parsed.scheme=='https' and not parsed.username and not parsed.password and parsed.hostname in {'mint.club','dexscreener.com','basescan.org','etherscan.io','blastscan.io','www.alchemy.com'} and not parsed.query:return value
                return redact(value)
            return value
        return safe(result)

    def compare(self, before, after):
        from decimal import Decimal, InvalidOperation, localcontext
        old, new = self.snapshot(before), self.snapshot(after)
        if old['wallet_address'].lower() != new['wallet_address'].lower():raise JobError('wallet_mismatch','Choose snapshots from the same wallet.')
        def positions(snapshot):
            return {(t['chain_id'],t['token_address'].lower(),t.get('token_id')):t for t in snapshot.get('tokens',[])}
        left,right=positions(old),positions(new);changes=[]
        for identity in sorted(left.keys() | right.keys(),key=str):
            a,b=left.get(identity),right.get(identity);delta=None
            if a is not None and b is not None and a.get('wallet_balance') is not None and b.get('wallet_balance') is not None:
                try:
                    with localcontext() as context:
                        context.prec=100;delta=str(Decimal(b['wallet_balance'])-Decimal(a['wallet_balance']))
                except InvalidOperation:pass
            changes.append({'chain_id':identity[0],'address':identity[1],'token_id':identity[2],
                'symbol':(b or a).get('symbol'),'before_balance':a.get('wallet_balance') if a else None,
                'after_balance':b.get('wallet_balance') if b else None,'balance_delta':delta,
                'presence':'both' if a and b else 'new_record' if b else 'absent_record',
                'price_references_changed':(a or {}).get('indexer_price_references')!=(b or {}).get('indexer_price_references'),
                'valuation_method_changed':bool((a or {}).get('mintclub'))!=bool((b or {}).get('mintclub'))})
        return {'schema_version':1,'before':before,'after':after,'wallet':new['wallet_address'],
            'coverage_changed':old.get('coverage')!=new.get('coverage'),'price_references_changed':old.get('price_references')!=new.get('price_references'),
            'positions':changes,'note':'Absent records are unknown, not zero. Price overlays have separate observations and are not balance changes. Coverage changes compare full evidence, including observation times and blocks; this alone does not prove the set of checked networks changed. Positions compare direct token records. Read both snapshots to compare native balances.'}

    def snapshots(self, wallet):
        key = self.wallet(wallet)['address_key']
        paths = {w['latest_snapshot']['directory'] for w in read(self.root / 'wallets.json')['wallets'] if w['address_key'] == key and w.get('latest_snapshot')}
        for run in read(self.root / 'wallets.json').get('research_runs', []):
            if run['address_key'] == key: paths.add(run['snapshot'])
        return sorted([{'snapshot_id': p, 'compiled_at': self.snapshot(p).get('compiled_at'), 'status': self.snapshot(p).get('status')} for p in paths],key=lambda r:r['compiled_at'] or '')

    def publication(self, job):
        if job['operation'].startswith('settings.') or job['operation']=='wallet.setTags':
            receipt=self.jobs/'results'/(job['job_id']+'.json')
            return read(receipt) if receipt.exists() else None
        folder = self.root / job['checkpoint']
        if job['operation'] == 'prices.refresh':
            receipt = folder / 'price-publication.json'
            if not receipt.exists():
                if not (folder/'prices.json').exists():return None
                saved=read(folder/'prices.json')
                if not saved.get('snapshot_id'):return None
                atomic(receipt,{'schema_version':1,'snapshot_id':saved['snapshot_id'],'overlay':str((folder/'prices.json').relative_to(self.root)),
                    'projection':saved['snapshot_id']+'/market-prices.json','status':saved['job_result_status']})
            item = read(receipt)
            overlay = (self.root / item['overlay']).resolve(); projection = (self.root / item['projection']).resolve()
            base = (self.root / 'snapshots').resolve()
            if not overlay.is_relative_to(base) or not projection.is_relative_to(base): raise JobError('invalid_snapshot', 'Invalid price receipt.')
            # Reconciliation only while the worker owns the portfolio writer lock.
            previous = read(projection) if projection.exists() else {}
            value = read(overlay)
            if (previous.get('observed_at') or '') <= value['observed_at']: atomic(projection, value)
            return {'snapshot_id': item['snapshot_id'], 'overlay': item['overlay'], 'status': item['status']}
        manifest = folder / 'run.json'
        if not manifest.exists() or not (folder / 'results.json').exists(): return None
        result = read(folder / 'results.json')
        if result.get('wallet_address', '').lower() != (job['input'].get('wallet') or job['input'].get('address')).lower(): return None
        registry = read(self.root / 'wallets.json')
        published = any(w.get('latest_snapshot', {}).get('directory') == job['checkpoint'] for w in registry['wallets']) or any(r.get('snapshot') == job['checkpoint'] for r in registry.get('research_runs', []))
        if not published: return None
        return {'snapshot_id': job['checkpoint'], 'status': result['status']}

    def recover(self):
        with self.locked():
            for path in self.jobs.glob('*.json'):
                job = self.get(path.stem)
                if job['state'] != 'running': continue
                receipt = self.publication(job)
                if receipt:
                    job.update(result=receipt, state='partial' if receipt['status'] != 'completed' else 'succeeded', stage='published')
                elif job['cancel_requested']:job.update(state='cancelled',stage='stopped',errors=[{'code':'cancelled','message':'Job stopped at your request. Saved evidence is available to resume.'}])
                else: job.update(state='interrupted', stage='interrupted', errors=[{'code': 'interrupted', 'message': 'Worker stopped. Saved evidence is available for an explicit resume.'}])
                self.save(job)

    def event(self, job_id, event):
        allowed = {'registered', 'discovery', 'chain', 'onchain_progress', 'first_evidence', 'dex_discovery', 'market_paused', 'token_images', 'published', 'failed'}
        if event.get('stage') not in allowed: return
        with self.locked():
            job = self.get(job_id)
            counts = {k: v for k, v in event.items() if k in {'complete_chains', 'candidates', 'tokens','chain_id','registry','checked','held','block_number','total'} and type(v) is int and v >= 0}
            job['stage'] = event['stage']
            if event['stage']=='chain' and type(event.get('chain_id')) is int:
                block=event.get('block_number');block=str(block) if type(block) is int and block>=0 else block
                job.setdefault('chains',{})[str(event['chain_id'])]={'block_number':block if isinstance(block,str) and re.fullmatch(r'\d+',block) else None,
                    'endpoint_index':event.get('endpoint_index') if type(event.get('endpoint_index')) is int else None,
                    'status':event.get('status') if event.get('status') in ('complete','partial','unavailable') else 'unknown'}
            job['events'].append({'stage': event['stage'], 'observed_at': now(), 'counts': counts})
            if event['stage']=='onchain_progress' and event.get('operation') in ('balances','registry','metadata','curves','markets','reserves'):
                job['events'][-1]['context']={'operation':event['operation'],'chain_id':counts.get('chain_id')}
            if event['stage']=='first_evidence' and isinstance(event.get('snapshot'),str) and (event['snapshot']==job['checkpoint']+'/initial' or re.fullmatch(re.escape(job['checkpoint'])+r'/market-initial-[0-9]{4}',event['snapshot'])):
                saved=self.snapshot(event['snapshot'])
                wallet=job['input'].get('wallet') or job['input'].get('address')
                if saved.get('wallet_address','').lower()==wallet.lower():job['result']={'snapshot_id':event['snapshot'],'status':saved['status'],'phase':'initial'}
            if event['stage']=='chain' and type(event.get('chain_id')) is int:job['events'][-1]['context']={'chain_id':event['chain_id'],**job['chains'][str(event['chain_id'])]}
            job['events'] = job['events'][-100:]
            self.save(job)

    def set_tags(self, job):
        from wallet import registry_locked
        with registry_locked(self.root):
            registry = read(self.root / 'wallets.json')
            wallet = next(w for w in registry['wallets'] if w['address_key'] == job['input']['wallet'])
            old = wallet['tags']; tags = job['input']['tags']
            for tag in set(old) ^ set(tags):
                registry.setdefault('tag_history', []).append({'address_key': wallet['address_key'], 'tag': tag,
                    'action': 'add' if tag in tags else 'remove', 'observed_at': now(), 'source': 'operator'})
            wallet['tags'] = tags; atomic(self.root / 'wallets.json', registry)
        return {'wallet': wallet['address_key'], 'tags': tags, 'status': 'completed'}

    def continue_research(self):
        """A durable continuation of the admitted analysis, behind initial reports."""
        for parent in self.list():
            if parent.get('analysis_phase')!='baseline' or parent['state'] not in ('succeeded','partial') or parent.get('cancel_requested') or parent.get('continuation_id'):continue
            result=parent.get('result')
            if not result or not result.get('snapshot_id'):continue
            saved=self.snapshot(result['snapshot_id'])
            if saved.get('pipeline',{}).get('phase')!='baseline':continue
            wallet=parent['input'].get('address') or parent['input'].get('wallet')
            child=self.submit({'schema_version':1,'operation':'wallet.refresh','input':{'wallet':wallet},'idempotency_key':'enrichment:'+parent['job_id']},phase='enrichment',parent=parent['job_id'])
            with self.locked():
                parent=self.get(parent['job_id']);parent['continuation_id']=child['job_id'];self.save(parent)

    def engine_command(self, job):
        if job['operation'] == 'prices.refresh':
            command = [sys.executable, str(ASSETS / 'viewer/refresh_prices.py'), '--wallet', job['input']['wallet']]
        else:
            add = job['operation'] == 'wallet.add'
            command = [sys.executable, str(ASSETS / 'wallet.py'), 'add' if add else 'refresh', job['input']['address'] if add else job['input']['wallet']]
            if add: command += ['--tag', job['input']['tag']]
            command += ['--phase',job.get('analysis_phase','enrichment')]
            if (self.root / job['checkpoint'] / 'run.json').exists(): command += ['--resume', job['checkpoint']]
        return command

    def execute(self, job, lease, writer):
        saved=self.publication(job)
        if saved:return saved
        if job['operation'] == 'wallet.setTags':
            result=self.set_tags(job);atomic(self.jobs/'results'/(job['job_id']+'.json'),result);return result
        if job['operation'].startswith('settings.'):
            from kira_config import config_path,load_config
            config=load_config()
            if job['operation']=='settings.importEnv':
                from kira_config import provider_config,secret_values
                config=provider_config(config,'alchemy',job['input']['key_env'])
                config['secret_env_file']=self.import_reference(job['input']);config['discovery']['explorers']=True
                if not secret_values(config).get(job['input']['key_env']):
                    raise JobError('connection_key_missing','The local file does not contain the selected Alchemy key. Check the file and run import-env again. Existing settings are unchanged.')
            elif job['operation']=='settings.rpc':
                updated={**job['input'],'chains':{key:dict(row) for key,row in job['input']['chains'].items()}}
                updated.setdefault('priority',config['rpc'].get('priority','public_first'))
                for key,row in updated['chains'].items():
                    previous=config['rpc']['chains'].get(key,{})
                    if row['url_env']==previous.get('url_env') and previous.get('alchemy_network'):row['alchemy_network']=previous['alchemy_network']
                config['rpc']=updated
            elif job['operation']=='settings.discovery':config['discovery']={**config['discovery'],**job['input']}
            else:
                from kira_config import provider_config,secret_values
                config=provider_config(config,**job['input'])
                if job['input']['provider']=='alchemy' and not secret_values(config).get(job['input']['key_env']):
                    raise JobError('connection_key_missing','Kira cannot find the local Alchemy key. Follow the connection guide, then retry. Existing settings are unchanged.')
            atomic(config_path(),config)
            result={'status':'completed','setting':job['operation']};atomic(self.jobs/'results'/(job['job_id']+'.json'),result);return result
        env = {**os.environ, 'KIRA_DATA_DIR': str(self.root), 'KIRA_JOB_ID': job['job_id'], 'KIRA_JOB_SNAPSHOT': job['checkpoint'], 'KIRA_ANALYSIS_FD': str(writer.fileno()), 'PYTHONUNBUFFERED': '1', 'KIRA_RESEARCH_GENERATION':job.get('parent_job_id',job['job_id'])}
        command=self.engine_command(job)
        child = subprocess.Popen(command, env=env, cwd=ASSETS, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            start_new_session=True, pass_fds=(lease.fileno(), writer.fileno()))
        selector = selectors.DefaultSelector(); selector.register(child.stdout, selectors.EVENT_READ)
        buffer = b''; cancelled = False; stopped = False; yielded = False; next_check = 0
        def stop_child():
            nonlocal stopped
            if stopped:return
            stopped=True
            signal_process_group(child.pid, signal.SIGTERM)
            if child.poll() is None:
                try: child.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    signal_process_group(child.pid, signal.SIGKILL)
                    child.wait()
            # A failed engine leader can leave a Node descendant in its group.
            signal_process_group(child.pid,signal.SIGKILL)
        try:
            while child.poll() is None:
                if self.get(job['job_id'])['cancel_requested']:
                    cancelled = True; stop_child(); break
                if job.get('analysis_phase')=='enrichment' and time.monotonic()>=next_check:
                    next_check=time.monotonic()+2
                    if any(j['state']=='queued' and (j.get('analysis_phase')=='baseline' or j['operation']=='prices.refresh' or j['operation'].startswith('settings.')) for j in self.list()):
                        yielded=True;stop_child();break
                for key, _ in selector.select(.2):
                    chunk = os.read(key.fileobj.fileno(), 65536)
                    if not chunk: selector.unregister(key.fileobj); continue
                    buffer += chunk
                    while b'\n' in buffer:
                        line, buffer = buffer.split(b'\n', 1)
                        try: self.event(job['job_id'], json.loads(line))
                        except (ValueError, TypeError): pass
                    if len(buffer) > 65536: buffer = b''
            stop_child()
            while selector.select(0):
                key=selector.select(0)[0][0];chunk=os.read(key.fileobj.fileno(),65536)
                if not chunk:selector.unregister(key.fileobj);continue
                buffer+=chunk
                while b'\n' in buffer:
                    line,buffer=buffer.split(b'\n',1)
                    try:self.event(job['job_id'],json.loads(line))
                    except (ValueError,TypeError):pass
                if len(buffer)>65536:buffer=b''
            receipt = self.publication(job)
            if receipt: return receipt
            if cancelled or self.get(job['job_id'])['cancel_requested']: raise JobError('cancelled', 'Job stopped. Previous published results and saved evidence were preserved.')
            if yielded:raise JobError('yielded','Detailed research yielded to a short operation. Saved checkpoints are retained and detailed research resumes automatically.')
            if self.get(job['job_id'])['stage']=='market_paused':raise JobError('market_budget','Balances are saved. Market verification reached its time budget. Resume this job in Activity to continue saved checks. Pending pools are not verified absent.')
            raise JobError('engine_failed', 'Analysis stopped before publication. Check connection settings and resume saved evidence.')
        finally:
            stop_child(); selector.close(); child.stdout.close()

    def worker(self):
        with (self.root / '.job-worker.lock').open('a') as lease:
            fcntl.flock(lease, fcntl.LOCK_EX)
            # Do not reconcile or claim work while a legacy engine/config writer is live.
            with (self.root / '.analysis.lock').open('a') as writer:
                fcntl.flock(writer, fcntl.LOCK_EX)
                self.recover()
                self.continue_research()
            while True:
                writer = (self.root / '.analysis.lock').open('a')
                fcntl.flock(writer, fcntl.LOCK_EX)
                with self.locked():
                    queued = sorted((self.get(p.stem) for p in self.jobs.glob('*.json')), key=lambda j: (j.get('analysis_phase')=='enrichment',j['created_at']))
                    job = next((j for j in queued if j['state'] == 'queued'), None)
                    if not job:writer.close();return
                    if job.get('analysis_phase')=='enrichment':
                        entry=self.wallet(job['input']['wallet'])
                        if entry.get('research_generation') not in (None,job.get('parent_job_id')):
                            job.update(state='cancelled',stage='stopped',errors=[{'code':'superseded','message':'Newer holdings research replaced this detailed run. Earlier evidence is preserved.'}]);self.save(job);writer.close();continue
                    from kira_config import load_config
                    config=load_config()
                    job['provider_configuration']={'rpc_mode':config['rpc']['mode'],'discovery_provider':config['discovery']['provider'],
                        'public_fallback':config['rpc']['allow_public_fallback'],'endpoint_refs':{cid:row['url_env'] for cid,row in config['rpc']['chains'].items()}}
                    job.update(state='running', stage='starting', started_at=now(), attempt=job['attempt'] + 1, errors=[]); self.save(job)
                try:
                    result = self.execute(job, lease, writer)
                    with self.locked():
                        job = self.get(job['job_id']); job.update(result=result, state='succeeded' if result['status'] == 'completed' else 'partial', stage='published'); self.save(job)
                    self.continue_research()
                except JobError as error:
                    with self.locked():
                        job = self.get(job['job_id'])
                        if error.code=='yielded':job.update(state='queued',stage='queued',errors=[])
                        elif error.code=='market_budget':job.update(state='interrupted',stage='market_paused',errors=[{'code':error.code,'message':str(error)}])
                        else:job.update(state='cancelled' if error.code == 'cancelled' else 'failed', stage='stopped', errors=[{'code': error.code, 'message': str(error)}])
                        self.save(job)
                except (Exception, KeyboardInterrupt):
                    with self.locked():
                        job = self.get(job['job_id'])
                        try:saved=self.publication(job)
                        except (ValueError,OSError):saved=None
                        if saved:job.update(result=saved,state='succeeded' if saved['status']=='completed' else 'partial',stage='published',errors=[])
                        elif job['cancel_requested']:job.update(state='cancelled',stage='stopped',errors=[{'code':'cancelled','message':'Job stopped at your request. Resume saved evidence explicitly.'}])
                        else:job.update(state='interrupted', stage='interrupted', errors=[{'code': 'interrupted', 'message': 'Worker stopped. Resume saved evidence explicitly.'}])
                        self.save(job)
                    return
                finally: writer.close()

    def launch(self):
        # Logs never contain raw engine output or credentials.
        with (self.root / 'jobs-worker.log').open('ab') as log:
            subprocess.Popen([sys.executable, str(ASSETS / 'kira_jobs.py'), '--worker', str(self.root)],
                stdout=log, stderr=log, start_new_session=True, env=os.environ.copy())

if __name__ == '__main__':
    if len(sys.argv) == 3 and sys.argv[1] == '--worker':
        signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(KeyboardInterrupt()))
        JobStore(sys.argv[2]).worker()
