"""Portable CLI lifecycle for the local Kira research engine."""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import time
import urllib.request
import uuid

ASSETS=Path(__file__).resolve().parent

def atomic(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    temporary=path.with_suffix(path.suffix+'.tmp')
    with temporary.open('w') as file:json.dump(value,file,indent=2);file.write('\n')
    temporary.chmod(0o600);temporary.replace(path)

def initialize(root):
    root.mkdir(parents=True,exist_ok=True,mode=0o700)
    for name,value in [('wallets.json',{'schema_version':1,'wallets':[],'tag_history':[],'research_runs':[]}),
                       ('session.json',{'schema_version':1,'scope':'Direct holdings; mainnet USD only; read-only research.'})]:
        if not (root/name).exists():atomic(root/name,value)
    if not (root/'networks.json').exists():shutil.copyfile(ASSETS/'networks.json',root/'networks.json')
    from kira_config import config_path,default_config
    if not config_path().exists():atomic(config_path(),default_config())

def health(port):
    try:
        with urllib.request.urlopen(f'http://127.0.0.1:{port}/api/health',timeout=1) as response:return json.load(response)
    except (OSError,ValueError):return None

def record(root):
    try:return json.loads((root/'viewer-process.json').read_text())
    except (OSError,ValueError):return None

def live_record(root):
    item=record(root)
    if item and (health(item['port']) or {}).get('instance')==item['instance']:return item
    return None

def start(root,port,controls=False):
    if item:=live_record(root):
        if controls and not health(item['port']).get('controls'):raise ValueError('The running viewer is read-only. Stop it and start with --controls.')
        print(json.dumps({'status':'running','url':f"http://127.0.0.1:{item['port']}"}));return
    if health(port):raise ValueError('Port belongs to another Kira data directory. Choose --port.')
    instance=str(uuid.uuid4());env={**os.environ,'KIRA_INSTANCE_ID':instance}
    with (root/'viewer.log').open('ab') as log:
        child=subprocess.Popen([sys.executable,str(ASSETS/'viewer/server.py'),'--port',str(port)]+(['--controls'] if controls else []),
            env=env,stdout=log,stderr=log,start_new_session=True)
    for _ in range(50):
        if child.poll() is not None:raise ValueError('Viewer could not start. Check the private viewer.log or choose another port.')
        if (health(port) or {}).get('instance')==instance:
            atomic(root/'viewer-process.json',{'pid':child.pid,'port':port,'instance':instance})
            print(json.dumps({'status':'running','url':f'http://127.0.0.1:{port}'}));return
        time.sleep(.1)
    child.terminate();raise ValueError('Viewer startup timed out.')

def stop(root):
    item=live_record(root)
    if not item:print(json.dumps({'status':'stopped'}));return
    # Match both the live service and the OS process before sending a signal.
    result=subprocess.run(['ps','-p',str(item['pid']),'-o','command='],capture_output=True,text=True)
    if str(ASSETS/'viewer/server.py') not in result.stdout:raise ValueError('Viewer process identity changed; stop was refused.')
    os.kill(item['pid'],signal.SIGTERM)
    for _ in range(30):
        if not health(item['port']):break
        time.sleep(.1)
    if health(item['port']):raise ValueError('Viewer has not stopped yet.')
    (root/'viewer-process.json').unlink(missing_ok=True)
    print(json.dumps({'status':'stopped'}))

def doctor(args,root):
    from kira_config import load_config,secret_values,endpoints
    cfg=load_config();values=secret_values(cfg)
    networks=json.loads((ASSETS/'sources/rpc-candidates.json').read_text())
    result={'python':sys.version.split()[0],'node':subprocess.check_output(['node','--version'],text=True).strip(),
        'rpc_mode':cfg['rpc']['mode'],'public_fallback':cfg['rpc']['allow_public_fallback'],
        'discovery':cfg['discovery']['provider'],
        'discovery_key_available':bool(values.get(cfg['discovery']['key_env'])),
        'general_erc20_coverage':'limited unless an indexer is configured and succeeds',
        'platform_verified':'macOS','probes':[],'rpc_calls':0}
    if args.live:
        import research
        if args.budget<1 or args.budget>200:raise ValueError('Live probe budget must be between 1 and 200 method calls.')
        try:chain_ids=[int(cid) for cid in args.chains.split(',')]
        except ValueError:raise ValueError('Expected comma-separated numeric chain IDs.') from None
        if any(cid not in {n['chain_id'] for n in networks} for cid in chain_ids):raise ValueError('Unknown probe chain ID.')
        remaining=args.budget
        def call(url,method,params):
            nonlocal remaining
            if remaining<=0:raise ValueError('RPC probe budget exhausted.')
            remaining-=1;result['rpc_calls']+=1
            response=research.rpc(url,method,params)
            if not isinstance(response,dict) or 'result' not in response or response.get('error') or response.get('transport_error'):
                raise ValueError('RPC method failed or rate limited; endpoint stopped.')
            return response['result']
        for cid in dict.fromkeys(chain_ids):
            network=next(n for n in networks if n['chain_id']==cid)
            probe={'chain_id':cid,'status':'unavailable','attempts':[]}
            for index,url in enumerate(endpoints(network,cfg)[:3]):
                if remaining<2:break
                attempt={'endpoint_index':index,'identity':False,'pinned_read':False,'multicall_code':False,'historical_read':False}
                try:
                    if int(call(url,'eth_chainId',[]),16)!=cid:raise ValueError('Wrong chain ID; endpoint rejected.')
                    attempt['identity']=True
                    block=call(url,'eth_blockNumber',[]);attempt['block']=int(block,16)
                    if remaining<3:raise ValueError('Insufficient budget for contract capability probes.')
                    address=network['mintclub_bond_address']
                    attempt['pinned_read']=call(url,'eth_getCode',[address,block])!='0x'
                    attempt['multicall_code']=call(url,'eth_getCode',['0xcA11bde05977b3631167028862bE2a173976CA11',block])!='0x'
                    previous=hex(max(0,int(block,16)-100))
                    attempt['historical_read']=call(url,'eth_getCode',[address,previous])!='0x'
                    probe['status']='available' if all(attempt[k] for k in ['identity','pinned_read','multicall_code','historical_read']) else 'limited'
                    probe['attempts'].append(attempt);break
                except ValueError as error:
                    attempt['error']=str(error);probe['attempts'].append(attempt)
            result['probes'].append(probe)
    print(json.dumps(result,indent=2))
    return 2 if args.live and any(p['status']!='available' for p in result['probes']) else 0

def sample(root):
    registry=json.loads((root/'wallets.json').read_text())
    if registry['wallets']:raise ValueError('Demo requires an empty, separate data directory.')
    address='0x0000000000000000000000000000000000000001';contract='0x0000000000000000000000000000000000000002'
    folder='snapshots/demo/initial';stamp='2026-10-03T00:00:00Z'
    snapshot={'schema_version':1,'wallet_address':address,'tags':['Demo wallet'],'compiled_at':stamp,'status':'completed_with_coverage_gaps',
        'counts':{},'coverage':[{'chain_id':8453,'name':'Base','environment':'mainnet','native_symbol':'ETH','native_balance':'0',
        'general_erc20_discovery':'incomplete','rpc_status':'available'}],
        'tokens':[{'chain_id':8453,'network':'base','token_address':contract,'token_type':'ERC20','symbol':'DEMO','name':'Sample token',
        'wallet_balance':'100','decimals':18,'mintclub':None,'dex_pools':[],
        'indexer_price_references':[{'currency':'usd','value':'1.25','lastUpdatedAt':stamp}]}]}
    atomic(root/folder/'results.json',snapshot)
    atomic(root/folder/'market-prices.json',{'observed_at':stamp,'tokens':[{'chain_id':8453,'address':contract,'usd':1.25,'basis':'Demo fixture','quality':'estimated'}]})
    atomic(root/'wallets.json',{'schema_version':1,'demo':True,'wallets':[{'address':address,'address_key':address,'tags':['Demo wallet'],
        'latest_snapshot':{'directory':folder,'result':folder+'/results.json'}}]})

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-dir',default=os.environ.get('KIRA_DATA_DIR',str(Path.home()/'.local/share/kira-wallet')))
    sub=parser.add_subparsers(dest='command',required=True)
    sub.add_parser('init');s=sub.add_parser('start');s.add_argument('--port',type=int,default=8787);s.add_argument('--controls',action='store_true')
    sub.add_parser('stop');sub.add_parser('status');sub.add_parser('wallets')
    sub.add_parser('tools')
    d=sub.add_parser('doctor');d.add_argument('--live',action='store_true');d.add_argument('--chains',default='1,8453,81457');d.add_argument('--budget',type=int,default=30)
    demo=sub.add_parser('demo');demo.add_argument('--port',type=int,default=8790)
    add=sub.add_parser('add');add.add_argument('address');add.add_argument('--tag',required=True);add.add_argument('--resume')
    refresh=sub.add_parser('refresh');refresh.add_argument('wallet');refresh.add_argument('--resume')
    prices=sub.add_parser('prices');prices.add_argument('wallet')
    for mutation in (add,refresh,prices):mutation.add_argument('--idempotency-key');mutation.add_argument('--enqueue',action='store_true')
    jobs=sub.add_parser('jobs');jobsub=jobs.add_subparsers(dest='action',required=True)
    jobsub.add_parser('list');jobsub.add_parser('run')
    for action in ('read','resume','cancel'):
        item=jobsub.add_parser(action);item.add_argument('job_id');item.add_argument('--idempotency-key')
    config=sub.add_parser('config');configsub=config.add_subparsers(dest='setting',required=True)
    configsub.add_parser('show')
    imp=configsub.add_parser('import-env');imp.add_argument('--file',required=True);imp.add_argument('--key-env',default='ALCHEMY_API_KEY')
    rpc=sub.add_parser('rpc');rpcsub=rpc.add_subparsers(dest='setting',required=True)
    rpcsub.add_parser('public')
    custom=rpcsub.add_parser('set');custom.add_argument('--chain',type=int,required=True);custom.add_argument('--url-env',required=True);custom.add_argument('--public-fallback',action='store_true')
    discovery=sub.add_parser('discovery');discovery.add_argument('provider',choices=['none','alchemy']);discovery.add_argument('--key-env',default='ALCHEMY_API_KEY');discovery.add_argument('--explorers',action='store_true')
    args=parser.parse_args();root=Path(args.data_dir).expanduser().resolve();os.environ['KIRA_DATA_DIR']=str(root)
    if sys.version_info<(3,11):raise ValueError('Python 3.11 or newer is required.')
    if os.name!='posix':raise ValueError('This development build requires a POSIX host. macOS is verified.')
    if args.command=='tools':
        from kira_tools import serve
        serve(root);return 0
    if getattr(args,'resume',None) and (args.enqueue or args.idempotency_key):raise ValueError('Legacy snapshot resume cannot enqueue or use an idempotency key. Use jobs resume for durable jobs.')
    root.mkdir(parents=True,exist_ok=True,mode=0o700)
    operation_lock=None
    if args.command in ('init','demo','rpc','discovery') or args.command=='config' and args.setting!='show':
        import fcntl
        operation_lock=(root/'.analysis.lock').open('a')
        try:fcntl.flock(operation_lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:raise ValueError('An analysis or configuration writer is active. Retry after it finishes.') from None
    if args.command in ('start','stop','demo'):
        import fcntl
        viewer_lock=(root/'.viewer.lock').open('a')
        try:fcntl.flock(viewer_lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:raise ValueError('Another viewer lifecycle operation is active.') from None
    initialize(root)
    from kira_config import load_config,config_path,redact
    try:
        if args.command=='init':print(json.dumps({'status':'initialized','rpc_mode':load_config()['rpc']['mode']}))
        elif args.command=='start':start(root,args.port,args.controls)
        elif args.command=='stop':stop(root)
        elif args.command=='status':
            item=live_record(root);print(json.dumps({'status':'running' if item else 'stopped','url':f"http://127.0.0.1:{item['port']}" if item else None}))
        elif args.command=='doctor':return doctor(args,root)
        elif args.command=='wallets':print(json.dumps(json.loads((root/'wallets.json').read_text())['wallets'],indent=2))
        elif args.command=='demo':sample(root);start(root,args.port)
        elif args.command=='jobs':
            from kira_jobs import JobStore
            store=JobStore(root)
            if args.action=='list':result=store.list()
            elif args.action=='read':result=store.get(args.job_id)
            elif args.action=='run':store.launch();result={'status':'worker_started'}
            else:
                result=store.submit({'schema_version':1,'operation':'job.'+args.action,'input':{'job_id':args.job_id},'idempotency_key':args.idempotency_key or str(uuid.uuid4())})
                if args.action=='resume':store.launch()
            print(json.dumps(result,indent=2))
        elif args.command in ('rpc','discovery','config'):
            cfg=load_config()
            if args.command=='config' and args.setting=='show':
                safe={key:cfg[key] for key in ['schema_version','rpc','discovery']};safe['secret_file_configured']=bool(cfg.get('secret_env_file'))
                print(json.dumps(safe,indent=2));return 0
            if args.command=='config':
                file=Path(args.file).expanduser().resolve()
                if not file.is_file():raise ValueError('Secret environment file does not exist.')
                from wallet import ALCHEMY
                cfg['secret_env_file']=str(file);cfg['discovery']={'provider':'alchemy','key_env':args.key_env,'explorers':True}
                cfg['rpc']={'mode':'custom','allow_public_fallback':True,
                    'chains':{str(cid):{'url_env':args.key_env,'alchemy_network':name} for cid,name in ALCHEMY.items()}}
            elif args.command=='discovery':cfg['discovery']={'provider':args.provider,'key_env':args.key_env,'explorers':args.explorers}
            elif args.setting=='public':cfg['rpc']['mode']='public'
            else:cfg['rpc'].update(mode='custom',allow_public_fallback=args.public_fallback);cfg['rpc']['chains'][str(args.chain)]={'url_env':args.url_env}
            # Validate before replacing the user's working configuration.
            import kira_config
            previous=kira_config.config_path
            temporary=root/'.kira.validate.json';atomic(temporary,cfg)
            try:
                kira_config.config_path=lambda:temporary;kira_config.load_config()
            finally:kira_config.config_path=previous;temporary.unlink(missing_ok=True)
            atomic(config_path(),cfg);print(json.dumps({'status':'configuration_saved'}))
        else:
            if os.name!='posix':raise ValueError('Analysis currently requires a POSIX host for file locking. macOS is verified.')
            if not getattr(args,'resume',None):
                from kira_jobs import JobStore
                store=JobStore(root)
                result=store.submit({'schema_version':1,'operation':{'add':'wallet.add','refresh':'wallet.refresh','prices':'prices.refresh'}[args.command],
                    'input':{'address':args.address,'tag':args.tag} if args.command=='add' else {'wallet':args.wallet},'idempotency_key':args.idempotency_key or str(uuid.uuid4())})
                print(json.dumps(result),flush=True)
                if args.enqueue:store.launch();return 0
                store.worker();result=store.get(result['job_id']);print(json.dumps(result))
                return 0 if result['state'] in ('succeeded','partial') else 1
            if args.command=='prices':command=[sys.executable,str(ASSETS/'viewer/refresh_prices.py'),'--wallet',args.wallet]
            else:
                command=[sys.executable,str(ASSETS/'wallet.py'),args.command,args.address if args.command=='add' else args.wallet]
                if args.command=='add':command+=['--tag',args.tag]
                if args.resume:command+=['--resume',args.resume]
            return subprocess.run(command).returncode
    except (ValueError,OSError) as error:
        print(redact(error),file=sys.stderr);return 1
    return 0

if __name__=='__main__':
    try:sys.exit(main())
    except (ValueError,OSError) as error:
        from kira_config import redact
        print(redact(error),file=sys.stderr);sys.exit(1)
