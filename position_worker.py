"""One resumable position slice, launched under the existing research writer lease."""
import argparse
from copy import deepcopy
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from kira_config import ASSETS, data_root
from kira_jobs import atomic, digest, now


def previous(root, address):
    index=root/'positions/index.json'
    index=json.loads(index.read_text()) if index.is_file() else {'schema_version':1,'wallets':{}}
    ref=index['wallets'].get(address);saved=None
    if ref:
        path=(root/ref['path']).resolve()
        if not path.is_relative_to((root/'snapshots/jobs').resolve()):raise ValueError('Invalid saved positions reference')
        saved=json.loads(path.read_text())
    return index,saved


def prepare(root, job):
    address=job['input']['wallet'];registry=json.loads((root/'wallets.json').read_text())
    wallet=next(w for w in registry['wallets'] if w['address_key']==address)
    latest=wallet.get('latest_snapshot') or {};tokens={}
    if latest.get('result'):
        path=(root/latest['result']).resolve()
        if not path.is_relative_to((root/'snapshots').resolve()):raise ValueError('Invalid holdings reference')
        snapshot=json.loads(path.read_text())
        for t in snapshot.get('tokens',[]):
            a=t.get('token_address');cid=t.get('chain_id')
            if isinstance(a,str) and re.fullmatch(r'0x[0-9a-fA-F]{40}',a) and t.get('token_type')!='ERC1155':
                tokens[(cid,a.lower())]={'chain_id':cid,'address':a,'symbol':t.get('symbol','')}
    _,old=previous(root,address)
    for p in (old or {}).get('positions',[]):
        if (p.get('receipt') or {}).get('custody')=='wallet' and p['receipt'].get('standard')!='ERC1155':
            a=p['receipt']['address'];tokens[(p['chain_id'],a)]={'chain_id':p['chain_id'],'address':a,'symbol':'LP'}
    networks=json.loads((root/'networks.json').read_text())['networks']
    # Configured mainnets are checked even when the wallet has no loose tokens.
    from native_assets import NATIVE_ASSETS
    native={cid:(row[0],18) for cid,row in NATIVE_ASSETS.items()}
    native.update({5042:('USDC',6),99901:('HYPE',18),57073:('ETH',18)})
    return {'wallet':address,'networks':[{**n,'native_symbol':native.get(n['chain_id'],('Unknown',None))[0],'native_decimals':native.get(n['chain_id'],('Unknown',None))[1]} for n in networks if n['environment']=='mainnet'],
            'tokens':list(tokens.values()),'discover':job['input'].get('discover',True),
            'known_positions':[{k:p.get(k) for k in ('id','scope','chain_id','platform','protocol','version','manager','token_id','pool','factory','gauge','farm','pool_id')} for p in (old or {}).get('positions',[])],
            'max_reads':48,'budget_ms':25000}


def projection(state, old, *, completed, job):
    positions=deepcopy(state['positions']);coverage=deepcopy(state['coverage'])
    pending={t['scope'] for t in state['tasks'][state['cursor']:]}
    for scope in pending:
        coverage.setdefault(scope,{'id':scope,'chain_id':int(scope.split(':')[0]),'errors':0})['status']='pending'
    for p in (old or {}).get('positions',[]):
        scope=p['scope']
        if p['id'] not in positions and (not completed or coverage.get(scope,{}).get('status')!='checked'):
            positions[p['id']]={**p,'retained':True}
    rows=list(positions.values());rows.sort(key=lambda p:p['id'])
    return {'schema_version':1,'wallet':state['wallet'],'job_id':job['job_id'],'requested_at':job['created_at'],
            'observed_at':now(),'status':'in_progress' if not completed else 'partial' if any(c['status']!='checked' for c in coverage.values()) else 'checked',
            'positions':rows,'coverage':list(coverage.values()),'blocks':state['blocks'],
            'collection':{'tasks_checked':state['cursor'],'tasks_total':len(state['tasks']),'slice_rpc_batches':state.get('last_slice_reads',0),'concurrent_requests':1,'max_multicall_contracts':32},
            'discovery_mode':'full' if job['input'].get('discover',True) else 'known',
            'scope_note':'Known principal/NAV only. Third-party custodians, liabilities, unclaimed rewards and exit costs are outside this inventory.'}


def publish(root, job, state):
    from wallet import registry_locked
    completed=state.get('complete') is True;folder=root/job['checkpoint'];address=job['input']['wallet']
    with registry_locked(root):
        registry=json.loads((root/'wallets.json').read_text())
        if not any(w['address_key']==address for w in registry['wallets']):raise ValueError('Wallet registration was removed')
        index,old=previous(root,address)
        if old and old.get('requested_at','')>job['created_at']:raise ValueError('Newer position research is already published')
        saved=projection(state,old,completed=completed,job=job)
        target=folder/('positions.json' if completed else 'positions-'+str(job['attempt']).zfill(5)+'.json')
        atomic(target,saved)
        index['wallets'][address]={'path':str(target.relative_to(root)),'job_id':job['job_id'],'observed_at':saved['observed_at']}
        atomic(root/'positions/index.json',index)
        if completed:
            result={'status':'completed' if saved['status']=='checked' else 'partial','positions_snapshot':str(target.relative_to(root)),
                    'position_count':len(saved['positions']),'coverage_gaps':sum(c['status']!='checked' for c in saved['coverage'])}
            atomic(folder/'positions-publication.json',result)
        return saved


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--wallet',required=True);args=parser.parse_args()
    root=data_root();job_id=os.environ['KIRA_JOB_ID'];job=json.loads((root/'jobs'/(job_id+'.json')).read_text())
    if args.wallet!=job['input']['wallet'] or job['operation']!='positions.refresh':raise ValueError('Invalid position request')
    folder=root/job['checkpoint'];folder.mkdir(parents=True,exist_ok=True)
    input_file=folder/'positions-input.json';checkpoint=folder/'positions-checkpoint.json'
    if not input_file.is_file():atomic(input_file,prepare(root,job))
    command=['node',str(ASSETS/'position-reader.cjs'),str(input_file),str(checkpoint),str(root/'cache/positions-shared.json')]
    try:
        result=subprocess.run(command,cwd=ASSETS,timeout=50)
        if result.returncode:raise ValueError('Position reader stopped before saving a slice')
    except subprocess.TimeoutExpired:
        if not checkpoint.is_file():raise ValueError('Position source timed out before saving evidence') from None
    if not checkpoint.is_file():raise ValueError('Position reader stopped before saving a slice')
    state=json.loads(checkpoint.read_text());publish(root,job,state)
    if not state.get('complete'):
        atomic(folder/'continuation.json',{'fingerprint':digest({'cursor':state['cursor'],'tasks':len(state['tasks']),'positions':len(state['positions']),'blocks':state['blocks']}),'not_before':0})
        print(json.dumps({'stage':'research_paused'}),flush=True)


if __name__=='__main__':main()
