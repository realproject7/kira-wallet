"""One local application contract for CLI, optional MCP and browser controls."""
from __future__ import annotations
import json
from pathlib import Path
import time
import uuid
from kira_jobs import JobStore, JobError, atomic, fields, STATE_FILTERS
from kira_state import StateCache, page, page_bounds
from kira_research_tools import ResearchTools, CATALOG

STRING={'type':'string','minLength':1,'maxLength':500}
INTEGER={'type':'integer','minimum':0}
FOLDER_NAME={'type':'string','minLength':1,'maxLength':80}
FOLDER_ID={'type':'string','minLength':1,'maxLength':32,'description':'Saved folder ID or unfiled. Use folders_list to read IDs and metadata revision.'}
WALLET_ADDRESS={'type':'string','minLength':42,'maxLength':42,'pattern':'^0x[0-9a-fA-F]{40}$'}
READ_TOOLS=[]
for row in CATALOG:
    if row['name'] in ('records_read','holdings_refresh','prices_refresh'):continue
    properties={}
    for name,description in {**row['arguments'],**row.get('optional_arguments',{})}.items():
        schema={'type':'integer','minimum':1 if name in ('chain_id','limit') else 0} if name in ('chain_id','offset','limit') else dict(STRING)
        if name=='minimum_value_usd':schema={'type':['string','number']}
        if name=='limit':schema['maximum']=25 if row['name']=='holdings_query' else 100
        if row['name']=='snapshots_list' and name=='kind':schema['enum']=['holdings','prices','all']
        properties[name]={**schema,'description':description}
    if row['name'] in ('portfolio_read','job_list','snapshots_list'):
        properties.update(offset=INTEGER,limit={'type':'integer','minimum':1,'maximum':100})
    if row['name']=='portfolio_read':properties['folder_id']={**FOLDER_ID,'description':'Optional folder ID or unfiled. Omit for all registered wallets.'}
    summary=row['description']
    if row['name']=='job_list':
        summary='Read a newest-first page of durable jobs with scoped status counts. Filter by state, registered wallet or search across saved history.'
        properties.update(state={'type':'string','enum':list(STATE_FILTERS),'description':'Default all. Groups: active (queued, running), succeeded (succeeded, partial), attention (interrupted, failed). The other values match one exact state.'},
                          wallet={**STRING,'description':'registered address or exact name'})
        properties['query']={'type':'string','maxLength':200,'description':'Search wallet names, addresses, task type or job ID before pagination.'}
    READ_TOOLS.append({'name':row['name'],'description':summary,
        'inputSchema':{'type':'object','properties':properties,'required':list(row['arguments']),'additionalProperties':False},
        'annotations':{'readOnlyHint':True,'destructiveHint':False,'idempotentHint':True,'openWorldHint':False}})


def tool(name,description,properties=None,required=None,write=False):
    properties=properties or {}
    return {'name':name,'description':description,
        'inputSchema':{'type':'object','properties':properties,'required':list(properties) if required is None else required,'additionalProperties':False},
        'annotations':{'readOnlyHint':not write,'destructiveHint':False,'idempotentHint':True,'openWorldHint':write}}


READ_TOOLS += [tool('network_read','Read saved network allocation and coverage.',{'chain_id':{'type':'integer','minimum':1}}),
               tool('folders_list','List saved folders and registered wallet membership. No research is started.'),
               tool('folder_overview','Read cached portfolio, sell-estimate and network statistics for a saved folder.',{'folder_id':FOLDER_ID}),
               tool('workspace_status','Read local readiness, capabilities, saved-data revisions and active jobs.'),
               tool('settings_read','Read configuration references without credential values.'),
               tool('ui_context','Read the wallet, token or network selected in the local web app.')]
MUTATIONS={
    'portfolio_holdings_refresh':('portfolio.refresh',{'folder_id':FOLDER_ID}),
    'portfolio_sell_routes_analyze':('portfolio.analyzeSell',{'folder_id':FOLDER_ID}),
    'settings_h402':('settings.h402',{'enabled':{'type':'boolean'}}),
    'wallet_add':('wallet.add',{'address':STRING,'tag':STRING}),
    'wallet_tags':('wallet.setTags',{'wallet':STRING,'tags':{'type':'array','items':STRING,'minItems':1,'maxItems':20}}),
    'holdings_refresh':('wallet.refresh',{'wallet':STRING}),
    'prices_refresh':('prices.refresh',{'wallet':STRING}),
    'job_cancel':('job.cancel',{'job_id':STRING}),
    'job_resume':('job.resume',{'job_id':STRING}),
    'job_deepen':('job.deepen',{'job_id':STRING}),
    'settings_rpc':('settings.rpc',{'mode':{'type':'string','enum':['public','custom']},'chains':{'type':'array','maxItems':30,'items':{'type':'object','properties':{'chain_id':{'type':'integer','minimum':1},'url_env':STRING},'required':['chain_id','url_env'],'additionalProperties':False}},'allow_public_fallback':{'type':'boolean'},'priority':{'type':'string','enum':['public_first','custom_first']}}),
    'settings_discovery':('settings.discovery',{'provider':STRING,'key_env':STRING,'explorers':{'type':'boolean'}}),
    'settings_provider':('settings.provider',{'provider':STRING,'key_env':STRING}),
}
TOKEN_ACTIONS={'token_policy':('token.policy',{'chain_id':{'type':'integer','minimum':1},'address':STRING,'mode':{'type':'string','enum':['auto','include','exclude']}}),
               'token_risk_check':('token.riskCheck',{'chain_id':{'type':'integer','minimum':1},'address':STRING})}
MUTATIONS.update(TOKEN_ACTIONS)
FOLDER_ACTIONS={
    'folder_create':('folder.create',{'name':FOLDER_NAME,'expected_revision':INTEGER}),
    'folder_rename':('folder.rename',{'folder_id':FOLDER_ID,'name':FOLDER_NAME,'expected_revision':INTEGER}),
    'folder_delete':('folder.delete',{'folder_id':FOLDER_ID,'expected_revision':INTEGER}),
    'folder_assign':('folder.assign',{'folder_id':FOLDER_ID,'wallets':{'type':'array','items':WALLET_ADDRESS,'minItems':1,'maxItems':1000},'expected_revision':INTEGER}),
    'folder_set_members':('folder.setMembers',{'folder_id':FOLDER_ID,'wallets':{'type':'array','items':WALLET_ADDRESS,'maxItems':1000},'expected_revision':INTEGER})}
MUTATIONS.update(FOLDER_ACTIONS)
WALLET_ACTIONS={name:(operation,{'wallets':{'type':'array','items':WALLET_ADDRESS,'minItems':1,'maxItems':1000},'expected_revision':{'type':'string','pattern':'^[0-9a-f]{64}$'}})
                for name,operation in [('wallets_remove','wallet.remove'),('wallets_restore','wallet.restore')]}
MUTATIONS.update(WALLET_ACTIONS)
READ_TOOLS.append(tool('wallets_removed','Read a bounded page of removed registrations and the wallet revision. Names and saved research can be restored without providers.',
                       {'offset':INTEGER,'limit':{'type':'integer','minimum':1,'maximum':100},'query':{'type':'string','maxLength':200}},required=[]))
WRITE_TOOLS=[tool(name,'Submit '+operation+' as a durable local job. Returns a receipt, not a completed result.',
    {**props,'idempotency_key':{'type':'string','minLength':8,'maxLength':200}},required=[k for k in props if k not in ('priority','explorers') and not (name.startswith('portfolio_') and k=='folder_id') and not (k=='expected_revision' and name not in ('folder_set_members',*WALLET_ACTIONS))]+['idempotency_key'],write=True)
    for name,(operation,props) in MUTATIONS.items()]

for descriptor in WRITE_TOOLS:
    if descriptor['name'] in WALLET_ACTIONS:
        descriptor['description']='Immediately remove or restore 1 to 1,000 selected registrations. Removed wallets leave portfolio totals. Saved research, names, folders and keys remain available for restoration. Read wallets_removed for expected_revision; active research must be paused first. No provider work or worker launch.'
        descriptor['annotations'].update(openWorldHint=False,destructiveHint=descriptor['name']=='wallets_remove')
    if descriptor['name'] in FOLDER_ACTIONS:
        descriptor['description']='Apply '+FOLDER_ACTIONS[descriptor['name']][0]+' immediately to local organization metadata. Wallet names, snapshots and keys are preserved. One folder per wallet; unfiled removes membership. setMembers replaces that folder membership; expected_revision prevents stale form overwrites. No research or worker launch.'
        descriptor['annotations']['openWorldHint']=False
        descriptor['annotations']['destructiveHint']=descriptor['name']=='folder_delete'
    if descriptor['name']=='wallet_tags':
        descriptor['description']='Save exact wallet names immediately without waiting for research. Returns a durable job receipt; inspect its state for completion. Prior snapshots retain their original names.'
    if descriptor['name'] in TOKEN_ACTIONS:
        descriptor['description']='Apply a durable local token valuation preference immediately across every registered wallet.' if descriptor['name']=='token_policy' else 'Explicitly query GoPlus for a recorded token contract and save dated risk observations. Sends only chain and contract identity. No transaction, simulation or safety guarantee. Runs immediately; saved reads never call providers.'
    if descriptor['name'].startswith('portfolio_'):
        descriptor['description']='Queue research for all registered wallets or one explicit folder using existing per-wallet jobs. Folder membership is captured at admission; retries retain that target set. Returns a durable batch receipt with jobs, skipped wallets and errors. Inspect each job for completion.'

DATA_SCOPE = {
    'inventory': 'Recorded direct holdings on configured EVM networks; coverage may be partial.',
    'includes': ['native_balances', 'discovered_token_balances', 'price_references', 'saved_history'],
    'not_established': ['complete_defi_positions', 'liabilities', 'perp_positions', 'prediction_market_positions', 'deployable_capital', 'complete_net_worth'],
    'freshness': 'Read balance, price and quote timestamps and coverage in each result. Missing is unknown, not zero.',
    'analysis': 'The host agent supplies external research, code execution and interpretation. Saved reads never refresh providers.'
}


def describe_tools(name=None):
    """Expose the exact CLI/MCP contract without initializing a workspace."""
    tools=READ_TOOLS+WRITE_TOOLS
    if name is not None:
        selected=next((row for row in tools if row['name']==name),None)
        if selected is None:raise JobError('unsupported_tool','Unknown tool. Run kira describe --json for available tools.')
        return selected
    return {'schema_version':1,'tools':tools,'note':'CLI calls support reads and writes. MCP exposes reads by default; writes require --allow-writes.'}


def validate(arguments,schema):
    if not isinstance(arguments,dict) or set(schema['required'])-set(arguments) or set(arguments)-set(schema['properties']):
        raise JobError('invalid_input','Unexpected or missing tool arguments.')
    kinds={'string':str,'integer':int,'number':(int,float),'boolean':bool,'array':list,'object':dict}
    for name,value in arguments.items():
        field=schema['properties'][name];types=field['type'] if isinstance(field['type'],list) else [field['type']]
        if not any((type(value) in kinds[k] if isinstance(kinds[k],tuple) else type(value) is kinds[k]) for k in types):
            raise JobError('invalid_input','Invalid argument type: '+name)
        if 'enum' in field and value not in field['enum']:
            raise JobError('invalid_input','Choose '+name+' from: '+', '.join(map(str,field['enum']))+'.')
        if isinstance(value,str) and (len(value)>field.get('maxLength',500) or len(value)<field.get('minLength',0)):
            raise JobError('invalid_input','Use a bounded identifier: '+name)
        if type(value) in (int,float) and (value<field.get('minimum',value) or value>field.get('maximum',value)):
            raise JobError('invalid_input','Argument is outside its range: '+name)


class Application:
    def __init__(self,root):
        self.root=Path(root).resolve();self.jobs=JobStore(self.root);self.views=StateCache(self.root)
        self.records=ResearchTools(self.root,{'scope':'portfolio','wallet':None,'wallet_tools':True,'external':True})

    def settings(self):
        from kira_config import load_config
        from kira_integrations import h402_status
        config=load_config()
        networks=json.loads((Path(__file__).resolve().parent/'sources/rpc-candidates.json').read_text())
        return {**{k:config[k] for k in ('schema_version','rpc','discovery')},
                'rpc_networks':[{'chain_id':n['chain_id'],'name':n.get('name',str(n['chain_id']))} for n in networks],
                'integrations':{'h402':h402_status(config)}}

    def status(self):
        return {'schema_version':1,'data_revision':self.views.data_revision(),**self.jobs.status()}

    def submit(self,request,*,launch=True):
        registry=json.loads((self.root/'wallets.json').read_text())
        operation=request.get('operation') if isinstance(request,dict) else None
        if operation in ('wallet.remove','wallet.restore'):
            from kira_wallets import action
            with self.jobs.locked():return action(self.jobs,request)
        if operation in {row[0] for row in FOLDER_ACTIONS.values()}:
            from kira_folders import action
            with self.jobs.locked():return action(self.jobs,request)
        if operation in ('token.policy','token.riskCheck'):
            if registry.get('demo') and operation=='token.riskCheck':raise JobError('demo_read_only','Sample portfolios never contact risk providers.')
            fields(request,['schema_version','operation','input','idempotency_key'])
            value=request['input']
            fields(value,['chain_id','address','mode'] if operation=='token.policy' else ['chain_id','address'])
            self.views.token(value.get('chain_id'),value.get('address'))
            from asset_policy import action
            with self.jobs.locked():return action(self.root,request)
        if registry.get('demo'):
            if operation in ('job.resume','job.deepen') and isinstance(request.get('input'),dict):
                operation=self.jobs.get(request['input'].get('job_id'))['operation']
            if operation in ('wallet.add','wallet.refresh','prices.refresh','portfolio.refresh','portfolio.analyzeSell'):
                raise JobError('demo_read_only','Sample portfolios never contact research providers.')
        if operation in ('portfolio.refresh','portfolio.analyzeSell'):
            from kira_batches import submit_batch
            result=submit_batch(self.jobs,request)
            if launch and any(j['state']=='queued' for j in result['jobs']):self.jobs.launch()
            return result
        result=self.jobs.submit(request)
        if operation=='wallet.setTags':
            self.jobs.finish_tag_edits()
            result=self.jobs.get(result['job_id'])
        if launch and result['state']=='queued':self.jobs.launch()
        return result

    def call(self,name,arguments=None,*,allow_write=False):
        arguments={} if arguments is None else arguments
        descriptor=next((row for row in READ_TOOLS+(WRITE_TOOLS if allow_write else []) if row['name']==name),None)
        if descriptor is None:raise JobError('unsupported_tool','Choose a declared local Kira tool.')
        validate(arguments,descriptor['inputSchema'])
        if name in MUTATIONS:
            args=dict(arguments);key=args.pop('idempotency_key')
            return self.submit({'schema_version':1,'operation':MUTATIONS[name][0],'input':args,'idempotency_key':key})
        if name=='workspace_status':
            from kira_config import public_status,load_config
            from kira_integrations import h402_status
            return {**self.status(),'research_connection':public_status(self.root),
                    'data_scope':DATA_SCOPE,'tool_catalog_command':'kira describe --json',
                    'integrations':{'h402':h402_status(load_config())},
                    'capabilities':{'headless':True,'manual_refresh':True,'web_controls':True,'model_runtime':False}}
        if name=='settings_read':return self.settings()
        if name=='wallets_removed':
            from kira_wallets import removed_page
            return removed_page(self.root,**arguments)
        if name=='folders_list':
            from kira_folders import catalog
            return catalog(self.root)
        if name=='folder_overview':return self.views.overview(arguments['folder_id'])
        if name=='ui_context':
            try:return json.loads((self.root/'.ui-context.json').read_text())
            except FileNotFoundError:return {'view':None,'note':'No web selection has been recorded.'}
        if name=='network_read':return self.views.network(arguments['chain_id'])
        if name=='job_list':return self.jobs.page(**arguments)
        if name=='job_read':return self.jobs.get(arguments['job_id'])
        if name=='portfolio_read':
            state=self.views.scoped(arguments.get('folder_id'));offset=arguments.get('offset',0);limit=arguments.get('limit',100)
            from kira_records import wallet_facts, recorded_valuation
            rows=wallet_facts([{**w,'recorded_valuation':recorded_valuation(w['assets']),'assets':[]} for w in state['wallets']])
            return {'schema_version':1,'dashboard':state['dashboard'],**page(rows,offset,limit,key='wallets'),
                    'data_revision':self.views.revision,'note':'Saved summaries only. Use wallet_read for holdings pages and holdings_query for search, ranking and aggregates.'}
        if name=='snapshots_list':
            return page(self.jobs.snapshots(arguments['wallet'],arguments.get('kind','holdings')),arguments.get('offset',0),arguments.get('limit',100),key='snapshots')
        return self.records.call(name,arguments,str(uuid.uuid4()))

    def select(self,value):
        if not isinstance(value,dict) or set(value)-{'view','wallet','token','chain_id','folder_id'}:raise JobError('invalid_context','Expected a web selection.')
        for key,item in value.items():
            if item is not None and (type(item) is not int if key=='chain_id' else not isinstance(item,str) or len(item)>200):
                raise JobError('invalid_context','Use bounded selection identifiers.')
        if value.get('wallet'):self.jobs.wallet(value['wallet'])
        if value.get('folder_id'):
            from kira_folders import catalog,members
            members(catalog(self.root),[],value['folder_id'])
        if value.get('token'):
            try:chain,address=value['token'].split(':',1);self.views.token(int(chain),address,folder_id=value.get('folder_id'))
            except (ValueError,AttributeError):raise JobError('invalid_context','Use a recorded token identity.') from None
        result={'schema_version':1,**value,'data_revision':self.views.data_revision()}
        atomic(self.root/'.ui-context.json',result)
        return result

    def wait(self,job_id,timeout=30):
        if type(timeout) not in (int,float) or not 0<=timeout<=120:raise JobError('invalid_timeout','Use a timeout from 0 to 120 seconds.')
        end=time.monotonic()+timeout
        while True:
            job=self.jobs.get(job_id)
            if job['state'] not in ('queued','running'):return {'completed':True,'job':job}
            if time.monotonic()>=end:return {'completed':False,'job':job}
            time.sleep(min(.25,max(0,end-time.monotonic())))
