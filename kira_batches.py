"""Durable portfolio admission plans using the existing per-wallet job queue."""
import json
from kira_jobs import JobError, atomic, digest, fields

OPERATIONS = {'portfolio.refresh', 'portfolio.analyzeSell', 'portfolio.positionsRefresh'}


def submit_batch(store, request):
    fields(request, ['schema_version', 'operation', 'input', 'idempotency_key'])
    if type(request['schema_version']) is not int or request['schema_version'] != 1:
        raise JobError('unsupported_version', 'Expected request schema version 1.')
    operation = request['operation']
    if operation not in OPERATIONS:
        raise JobError('unsupported_operation', 'Choose a portfolio research action.')
    value=request['input']
    if not isinstance(value,dict) or set(value)-{'folder_id','discover'} or 'folder_id' in value and not isinstance(value['folder_id'],str):
        raise JobError('invalid_input','Use an optional saved folder ID for portfolio research.')
    if 'discover' in value and (operation!='portfolio.positionsRefresh' or type(value['discover']) is not bool):raise JobError('invalid_input','Use a boolean discovery mode only for platform scans.')
    key = request['idempotency_key']
    if not isinstance(key, str) or not 8 <= len(key) <= 200:
        raise JobError('invalid_key', 'Supply an idempotency key of 8 to 200 characters.')
    batch_id = digest(key)
    fingerprint = digest({'operation': operation, 'input': value})
    path = store.jobs / 'batches' / (batch_id + '.json')
    with store.locked():
        from kira_folders import key_used, catalog, members
        if key_used(store.root,batch_id) or (store.root / '.token-actions' / (batch_id + '.json')).exists() or (store.jobs / 'requests' / (batch_id + '.json')).exists() or any(j['key_hash']==batch_id or batch_id in (j.get('control_receipts') or {}) for j in store.summaries()):
            raise JobError('idempotency_conflict', 'This request key already belongs to another operation.')
        if path.exists():
            plan = json.loads(path.read_text())
            if plan['request_hash'] != fingerprint:
                raise JobError('idempotency_conflict', 'This request key already belongs to another operation.')
        else:
            store.require_connection()
            wallets = json.loads((store.root / 'wallets.json').read_text())['wallets']
            wallets = members(catalog(store.root,wallets),wallets,value.get('folder_id'))
            jobs = store.summaries()
            from sell_analysis import analysis_index, assess
            analyses=analysis_index(store.root) if operation=='portfolio.analyzeSell' else {}
            items, skipped = [], []
            for wallet in wallets:
                address = wallet['address_key']
                related = [j for j in jobs if (j['input'].get('wallet') or j['input'].get('address') or '').lower() == address]
                reason = None
                if operation == 'portfolio.positionsRefresh':
                    # The shared writer runs holdings first. Admit every registration,
                    # including a wallet whose newer holdings are still being collected.
                    # Per-job admission coalesces a scan covering the requested mode.
                    items.append({'wallet':address,'operation':'positions.refresh','input':{'wallet':address,**({'discover':value['discover']} if 'discover' in value else {})}})
                elif any(j['state'] in ('queued', 'running') and j['operation'] in ('wallet.add', 'wallet.refresh', 'prices.refresh') for j in related):
                    reason = 'already_running'
                elif operation == 'portfolio.refresh':
                    blocked=next((j for j in related if j['job_id']==wallet.get('research_generation')
                        and j.get('analysis_phase')=='baseline' and j['state']=='failed' and not j.get('result')
                        and any(e.get('code')=='network_scope_changed' for e in j.get('errors',[]))),None)
                    items.append({'wallet':address,'operation':'job.resume','input':{'job_id':blocked['job_id']}} if blocked else
                                 {'wallet': address, 'operation': 'wallet.refresh', 'input': {'wallet': address}})
                else:
                    baseline = next((j for j in related if j['job_id'] == wallet.get('research_generation')), None)
                    if baseline is None:
                        baseline = max((j for j in related if j.get('analysis_phase') == 'baseline'), key=lambda j: j['created_at'], default=None)
                    if not baseline or baseline.get('scan_policy') != 'alchemy_inventory_v1' or baseline['state'] not in ('succeeded', 'partial') or not baseline.get('result'):
                        reason = 'holdings_refresh_required'
                    else:
                        child = next((j for j in related if j.get('parent_job_id') == baseline['job_id']), None)
                        analysis=assess(store.root,wallet,analyses,snapshot_id=baseline['result']['snapshot_id'])
                        if analysis['status']=='current':
                            reason = 'unchanged_holdings'
                        elif analysis['status']=='unverified':
                            reason = 'holdings_unverified'
                        elif child and child['state'] in ('succeeded', 'partial'):
                            reason = 'already_analyzed'
                        elif child:
                            items.append({'wallet': address, 'operation': 'job.resume', 'input': {'job_id': child['job_id']}})
                        else:
                            items.append({'wallet': address, 'operation': 'job.deepen', 'input': {'job_id': baseline['job_id']}})
                if reason: skipped.append({'wallet': address, 'reason': reason})
            plan = {'schema_version': 1, 'batch_id': batch_id, 'operation': operation,
                    'request_hash': fingerprint, 'wallet_count': len(wallets), 'items': items, 'skipped': skipped}
            if 'folder_id' in value:plan['folder_id']=value['folder_id']
            atomic(path, plan)
    admitted, errors, skipped = [], [], list(plan['skipped'])
    for item in plan['items']:
        try:
            job = store.submit({'schema_version': 1, 'operation': item['operation'], 'input': item['input'],
                                'idempotency_key': 'batch:' + digest({'batch': batch_id, 'wallet': item['wallet']})}, skip_active=operation!='portfolio.positionsRefresh')
            admitted.append({'job_id': job['job_id'], 'state': job['state'], 'wallet': item['wallet'], 'operation': job['operation']})
        except JobError as error:
            if error.code=='already_running':skipped.append({'wallet':item['wallet'],'reason':'already_running'})
            else:errors.append({'wallet': item['wallet'], 'code': error.code, 'message': str(error)})
    return {'schema_version': 1, 'batch_id': batch_id, 'operation': operation, 'wallet_count': plan['wallet_count'],
            **({'folder_id':plan['folder_id']} if 'folder_id' in plan else {}),
            'jobs': admitted, 'skipped': skipped, 'errors': errors,
            'note': 'Per-wallet job receipts. Research runs sequentially; inspect Activity for completion.'}
