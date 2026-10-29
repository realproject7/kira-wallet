"""Portable CLI lifecycle for the local Kira research engine."""
from __future__ import annotations
import argparse
import json
import os
import re
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
        status=health(item['port']) or {}
        if status.get('api_version')!=2:
            raise ValueError('An earlier Kira viewer is running. Run kira stop, then kira start to load this version. Saved records and research jobs are preserved.')
        if bool(status.get('controls')) != controls:
            mode='local controls' if controls else 'read-only mode'
            command='kira start' if controls else 'kira start --read-only'
            raise ValueError(f'The running app uses a different mode. Run kira stop, then {command} to use {mode}.')
        url=f"http://127.0.0.1:{item['port']}"
        print(json.dumps({'status':'running','url':url}));return url
    if health(port):raise ValueError('Port belongs to another Kira data directory. Choose --port.')
    instance=str(uuid.uuid4());env={**os.environ,'KIRA_INSTANCE_ID':instance}
    with (root/'viewer.log').open('ab') as log:
        child=subprocess.Popen([sys.executable,str(ASSETS/'viewer/server.py'),'--port',str(port)]+(['--controls'] if controls else []),
            env=env,stdout=log,stderr=log,start_new_session=True)
    for _ in range(50):
        if child.poll() is not None:raise ValueError('Viewer could not start. Check the private viewer.log or choose another port.')
        if (health(port) or {}).get('instance')==instance:
            atomic(root/'viewer-process.json',{'pid':child.pid,'port':port,'instance':instance})
            url=f'http://127.0.0.1:{port}'
            print(json.dumps({'status':'running','url':url}));return url
        time.sleep(.1)
    child.terminate()
    try:child.wait(timeout=3)
    except subprocess.TimeoutExpired:child.kill();child.wait(timeout=3)
    raise ValueError('Viewer startup timed out.')

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

def connect_alchemy(root):
    """Only the operator types the key, at a hidden terminal prompt."""
    import getpass
    from kira_jobs import JobStore
    if not sys.stdin.isatty():raise ValueError('Run kira connect alchemy in an interactive terminal. The API key is entered privately there.')
    key=getpass.getpass('Alchemy API key (hidden): ').strip()
    if not key or len(key)>512 or not re.fullmatch(r'[A-Za-z0-9_-]+',key):raise ValueError('Enter the app API key, without an endpoint URL.')
    directory=root/'.secrets';directory.mkdir(mode=0o700,exist_ok=True)
    if directory.is_symlink():raise ValueError('The private key directory must not be a symlink.')
    import tempfile
    fd,name=tempfile.mkstemp(prefix='alchemy-',suffix='.env',dir=directory)
    with os.fdopen(fd,'w') as stream:
        stream.write('ALCHEMY_API_KEY='+key+'\n');stream.flush();os.fsync(stream.fileno())
    store=JobStore(root);job=store.queue_import(name,'ALCHEMY_API_KEY');store.launch()
    print(json.dumps({'status':'configuration_queued','job_id':job['job_id'],'note':'Your key is stored privately on this computer. Return to Kira and check the connection.'}))

def finish_configuration(store,job,*,enqueue=False):
    """Use the same job executor in a terminal, without waiting on an active writer."""
    import fcntl
    with (store.root/'.analysis.lock').open('a') as writer:
        try:fcntl.flock(writer,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:enqueue=True
    if enqueue:
        store.launch()
        print(json.dumps({'status':'configuration_queued','job_id':job['job_id']}))
        return 0
    store.worker();job=store.get(job['job_id'])
    if job['state']!='succeeded':
        from kira_jobs import JobError
        error=(job.get('errors') or [{'code':'configuration_failed','message':'Configuration was not applied.'}])[0]
        raise JobError(error['code'],error['message'])
    print(json.dumps({'status':'configuration_saved','job_id':job['job_id']}))
    return 0

def main():
    parser=argparse.ArgumentParser(prog='kira',description=__doc__)
    parser.add_argument('--version',action='version',version=json.loads((ASSETS/'package.json').read_text())['version'])
    parser.add_argument('--json',action='store_true',help='Return structured output; research commands enqueue without waiting.')
    parser.add_argument('--data-dir',default=os.environ.get('KIRA_DATA_DIR',str(Path.home()/'.local/share/kira-wallet')),help='Workspace directory. Accepted before or after the subcommand.')
    sub=parser.add_subparsers(dest='command',required=True)
    sub.add_parser('init',help='Create or check the data directory without changing records.');s=sub.add_parser('start',help='Open the local app.');s.add_argument('--port',type=int,default=8787)
    mode=s.add_mutually_exclusive_group()
    mode.add_argument('--read-only',dest='controls',action='store_false',help='View recorded holdings without local browser actions.')
    mode.add_argument('--controls',dest='controls',action='store_true',help=argparse.SUPPRESS)
    s.set_defaults(controls=True)
    s.add_argument('--no-open',action='store_true',help='Print the local app URL without opening a browser.')
    setup=sub.add_parser('setup',help='Open the local app at first-run setup.');setup.add_argument('--port',type=int,default=8787);setup.add_argument('--no-open',action='store_true')
    sub.add_parser('stop',help='Stop the local app.');sub.add_parser('status',help='Show whether the local app is running.');sub.add_parser('info',help='Show version, data directory, readiness and active jobs.')
    wallets=sub.add_parser('wallets',help='List wallets or change their names.');walletsub=wallets.add_subparsers(dest='wallet_action')
    tags=walletsub.add_parser('tags');tags.add_argument('wallet');tags.add_argument('--tag',action='append',required=True);tags.add_argument('--idempotency-key')
    tools=sub.add_parser('tools',help='Serve Kira tools over MCP stdio.');tools.add_argument('--allow-writes',action='store_true')
    call=sub.add_parser('call',help='Run one Kira tool with JSON arguments.');call.add_argument('tool');call.add_argument('--arguments',default='{}')
    sub.add_parser('skill',help='Print the agent instructions.')
    describe=sub.add_parser('describe',help='List tool schemas or describe one tool without starting research.');describe.add_argument('tool',nargs='?')
    integrations=sub.add_parser('integrations',help='Check optional h402 tools or save the workspace preference.');integrations.add_argument('integration',nargs='?',choices=['h402'])
    choice=integrations.add_mutually_exclusive_group();choice.add_argument('--enable',action='store_true');choice.add_argument('--disable',action='store_true')
    integrations.add_argument('--idempotency-key')
    ui=sub.add_parser('ui',help="Read the app's last recorded selection.");ui.add_argument('action',choices=['context'])
    archive=sub.add_parser('archive',help='Read earlier conversations and generated files.');archive.add_argument('action',choices=['list','read','workspaces','files','export']);archive.add_argument('conversation',nargs='?');archive.add_argument('--path');archive.add_argument('--output')
    connection=sub.add_parser('connect',help='Enter an Alchemy key at a hidden local prompt.');connection.add_argument('provider',choices=['alchemy'])
    d=sub.add_parser('doctor',help='Check RPC settings, optionally with live probes.');d.add_argument('--live',action='store_true');d.add_argument('--chains',default='1,8453,81457');d.add_argument('--budget',type=int,default=30)
    demo=sub.add_parser('demo',help='Open a sample portfolio.');demo.add_argument('--port',type=int,default=8790)
    add=sub.add_parser('add',help='Register a public wallet and run its first holdings lookup.');add.add_argument('address');add.add_argument('--tag',required=True);add.add_argument('--resume')
    refresh=sub.add_parser('refresh',help='Run a new holdings lookup for a wallet.');refresh.add_argument('wallet');refresh.add_argument('--resume')
    prices=sub.add_parser('prices',help='Refresh prices without changing balances.');prices.add_argument('wallet')
    for mutation in (add,refresh,prices):mutation.add_argument('--idempotency-key');mutation.add_argument('--enqueue',action='store_true')
    jobs=sub.add_parser('jobs',help='List, follow and control durable jobs.');jobsub=jobs.add_subparsers(dest='action',required=True)
    jobsub.add_parser('list');jobsub.add_parser('run')
    wait=jobsub.add_parser('wait');wait.add_argument('job_id');wait.add_argument('--timeout',type=float,default=30)
    for action in ('read','resume','cancel','deepen'):
        item=jobsub.add_parser(action);item.add_argument('job_id');item.add_argument('--idempotency-key')
    config=sub.add_parser('config',help='Show settings or import a key file reference.');configsub=config.add_subparsers(dest='setting',required=True)
    configsub.add_parser('show')
    imp=configsub.add_parser('import-env');imp.add_argument('--file',required=True);imp.add_argument('--key-env',default='ALCHEMY_API_KEY')
    rpc=sub.add_parser('rpc',help='Choose public or custom RPC references.');rpcsub=rpc.add_subparsers(dest='setting',required=True)
    rpcsub.add_parser('public')
    custom=rpcsub.add_parser('set');custom.add_argument('--chain',type=int,required=True);custom.add_argument('--url-env',required=True);custom.add_argument('--priority',choices=['public_first','custom_first']);fallback=custom.add_mutually_exclusive_group();fallback.add_argument('--public-fallback',action='store_true',default=None);fallback.add_argument('--custom-only',dest='public_fallback',action='store_false')
    discovery=sub.add_parser('discovery',help='Choose the token discovery provider.');discovery.add_argument('provider',choices=['none','alchemy']);discovery.add_argument('--key-env',default='ALCHEMY_API_KEY');discovery.add_argument('--explorers',action='store_true')
    argv=sys.argv[1:]
    # Global switches work before or after a subcommand.
    if '--json' in argv:argv=['--json']+[a for a in argv if a!='--json']
    for index,item in enumerate(argv):
        if item=='--data-dir' and index+1<len(argv):argv=argv[index:index+2]+argv[:index]+argv[index+2:];break
        if item.startswith('--data-dir='):argv=[item]+argv[:index]+argv[index+1:];break
    args=parser.parse_args(argv);root=Path(args.data_dir).expanduser().resolve();os.environ['KIRA_DATA_DIR']=str(root)
    if sys.version_info<(3,11):raise ValueError('Python 3.11 or newer is required.')
    if os.name!='posix':raise ValueError('This development build requires a POSIX host. macOS is verified.')
    if args.command=='describe':
        from kira_service import describe_tools
        try:result=describe_tools(args.tool)
        except ValueError as error:
            if args.json:print(json.dumps({'error':{'code':getattr(error,'code','invalid_request'),'message':str(error)}}))
            else:print(str(error),file=sys.stderr)
            return 1
        print(json.dumps(result,allow_nan=False));return 0
    if args.command=='tools':
        from kira_tools import serve
        initialize(root)
        serve(root,allow_write=args.allow_writes);return 0
    if getattr(args,'resume',None) and (args.enqueue or args.idempotency_key):raise ValueError('Legacy snapshot resume cannot enqueue or use an idempotency key. Use jobs resume for durable jobs.')
    root.mkdir(parents=True,exist_ok=True,mode=0o700)
    operation_lock=None;viewer_lock=None
    if args.command in ('init','demo'):
        import fcntl
        operation_lock=(root/'.analysis.lock').open('a')
        try:fcntl.flock(operation_lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:
            operation_lock.close()
            if args.command=='config' and args.setting=='import-env':
                from kira_jobs import JobStore
                store=JobStore(root);job=store.queue_import(args.file,args.key_env);store.launch()
                print(json.dumps({'status':'configuration_queued','job_id':job['job_id'],
                    'note':'Connection setup is queued in Activity. Detailed research will pause safely, apply the connection, then resume. Recheck the connection after this job finishes.'}))
                return 0
            raise ValueError('An analysis or configuration writer is active. Check Activity and stop or wait for the active job before retrying.') from None
    if args.command in ('start','stop','demo','setup'):
        import fcntl
        viewer_lock=(root/'.viewer.lock').open('a')
        try:fcntl.flock(viewer_lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:raise ValueError('Another viewer lifecycle operation is active.') from None
    from kira_config import load_config,config_path,redact
    try:
        initialize(root)
        from kira_service import Application
        app=Application(root)
        if args.command=='connect':connect_alchemy(root)
        elif args.command=='info':
            print(json.dumps({'version':json.loads((ASSETS/'package.json').read_text())['version'],
                'data_dir':str(root),**app.call('workspace_status'), 'ui':live_record(root) is not None,
                'skill':str(ASSETS/'skills/kira-wallet/SKILL.md')},allow_nan=False))
        elif args.command=='call':
            try:value=json.loads(args.arguments,parse_constant=lambda _:(_ for _ in ()).throw(ValueError()))
            except ValueError:raise ValueError('Expected JSON tool arguments.') from None
            print(json.dumps(app.call(args.tool,value,allow_write=True),allow_nan=False))
        elif args.command=='skill':print((ASSETS/'skills/kira-wallet/SKILL.md').read_text())
        elif args.command=='integrations':
            if args.enable or args.disable:
                if args.integration!='h402':raise ValueError('Choose h402 when enabling or disabling an integration.')
                result=app.call('settings_h402',{'enabled':args.enable,'idempotency_key':args.idempotency_key or str(uuid.uuid4())},allow_write=True)
            else:
                from kira_integrations import h402_status
                result={'h402':h402_status(load_config())}
            print(json.dumps(result,allow_nan=False))
        elif args.command=='ui':print(json.dumps(app.call('ui_context')))
        elif args.command=='archive':
            from kira_archive import conversations,conversation_read,workspace_list,artifacts,read_artifact
            if args.action=='list':result=conversations(root)
            elif args.action=='workspaces':result=workspace_list(root)
            elif not args.conversation:raise ValueError('Choose a saved conversation or workspace ID.')
            elif args.action=='read':result=conversation_read(root,args.conversation)
            elif args.action=='files':result=artifacts(root,args.conversation)
            else:
                if not args.path or not args.output:raise ValueError('Use --path and --output to export a historical generated file.')
                body=read_artifact(root,args.conversation,args.path)
                with Path(args.output).expanduser().open('xb') as file:file.write(body)
                result={'status':'exported','size':len(body)}
            print(json.dumps(result))
        elif args.command=='init':print(json.dumps({'status':'initialized','rpc_mode':load_config()['rpc']['mode']}))
        elif args.command=='start':
            url=start(root,args.port,args.controls)
            if not args.no_open:
                import webbrowser
                webbrowser.open(url)
        elif args.command=='setup':
            import contextlib,io
            with contextlib.redirect_stdout(io.StringIO()):url=start(root,args.port,True)+'/?setup=1'
            if not args.no_open:
                import webbrowser
                webbrowser.open(url)
            print(json.dumps({'setup_url':url,'note':'Connect Alchemy, then add a public wallet. Use your agent session or the web controls.'}))
        elif args.command=='stop':stop(root)
        elif args.command=='status':
            item=live_record(root);print(json.dumps({'status':'running' if item else 'stopped','url':f"http://127.0.0.1:{item['port']}" if item else None}))
        elif args.command=='doctor':return doctor(args,root)
        elif args.command=='wallets':
            if args.wallet_action=='tags':result=app.submit({'schema_version':1,'operation':'wallet.setTags','input':{'wallet':args.wallet,'tags':args.tag},'idempotency_key':args.idempotency_key or str(uuid.uuid4())})
            else:result=json.loads((root/'wallets.json').read_text())['wallets']
            print(json.dumps(result,indent=2))
        elif args.command=='demo':sample(root);start(root,args.port)
        elif args.command=='jobs':
            from kira_jobs import JobStore
            store=JobStore(root)
            if args.action=='list':result=store.page()
            elif args.action=='read':result=store.get(args.job_id)
            elif args.action=='wait':result=app.wait(args.job_id,args.timeout)
            elif args.action=='run':store.launch();result={'status':'worker_started'}
            else:
                result=app.submit({'schema_version':1,'operation':'job.'+args.action,'input':{'job_id':args.job_id},'idempotency_key':args.idempotency_key or str(uuid.uuid4())})
            print(json.dumps(result,indent=2))
        elif args.command in ('rpc','discovery','config'):
            cfg=load_config()
            if args.command=='config' and args.setting=='show':
                safe={key:cfg[key] for key in ['schema_version','rpc','discovery']};safe['secret_file_configured']=bool(cfg.get('secret_env_file'))
                print(json.dumps(safe,indent=2));return 0
            if args.command=='config':
                job=app.jobs.queue_import(args.file,args.key_env)
                return finish_configuration(app.jobs,job,enqueue=args.json)
            elif args.command=='discovery':
                operation='settings.discovery';value={'provider':args.provider,'key_env':args.key_env,'explorers':args.explorers}
            else:
                rpc=cfg['rpc'];chains=dict(rpc['chains'])
                if args.setting=='set':chains[str(args.chain)]={'url_env':args.url_env}
                operation='settings.rpc';value={'mode':'public' if args.setting=='public' else 'custom',
                    'chains':[{'chain_id':int(cid),'url_env':row['url_env']} for cid,row in chains.items()],
                    'allow_public_fallback':rpc['allow_public_fallback'] if args.setting=='public' or args.public_fallback is None else args.public_fallback,
                    'priority':getattr(args,'priority',None) or rpc.get('priority','public_first')}
            result=app.submit({'schema_version':1,'operation':operation,'input':value,'idempotency_key':str(uuid.uuid4())},launch=False)
            return finish_configuration(app.jobs,result,enqueue=args.json)
        else:
            if os.name!='posix':raise ValueError('Analysis currently requires a POSIX host for file locking. macOS is verified.')
            if not getattr(args,'resume',None):
                from kira_jobs import JobStore
                store=JobStore(root)
                result=app.submit({'schema_version':1,'operation':{'add':'wallet.add','refresh':'wallet.refresh','prices':'prices.refresh'}[args.command],
                    'input':{'address':args.address,'tag':args.tag} if args.command=='add' else {'wallet':args.wallet},'idempotency_key':args.idempotency_key or str(uuid.uuid4())},launch=args.enqueue or args.json)
                print(json.dumps(result),flush=True)
                if args.enqueue or args.json:return 0
                store.worker();result=store.get(result['job_id']);print(json.dumps(result))
                return 0 if result['state'] in ('succeeded','partial') else 1
            if args.command=='prices':command=[sys.executable,str(ASSETS/'viewer/refresh_prices.py'),'--wallet',args.wallet]
            else:
                command=[sys.executable,str(ASSETS/'wallet.py'),args.command,args.address if args.command=='add' else args.wallet]
                if args.command=='add':command+=['--tag',args.tag]
                if args.resume:command+=['--resume',args.resume]
            return subprocess.run(command).returncode
    except (ValueError,OSError) as error:
        message=redact(error)
        if args.json:print(json.dumps({'error':{'code':getattr(error,'code','invalid_request'),'message':message}}))
        else:print(message,file=sys.stderr)
        return 1
    finally:
        if viewer_lock:viewer_lock.close()
        if operation_lock:operation_lock.close()
    return 0

if __name__=='__main__':
    try:sys.exit(main())
    except (ValueError,OSError) as error:
        from kira_config import redact
        print(redact(error),file=sys.stderr);sys.exit(1)
