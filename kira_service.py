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
    summary=row['description']
    if row['name']=='job_list':
        summary='Read a newest-first page of durable jobs. Optionally filter by state or registered wallet.'
        properties.update(state={'type':'string','enum':list(STATE_FILTERS),'description':'Default all. Groups: active (queued, running), succeeded (succeeded, partial), attention (interrupted, failed). The other values match one exact state.'},
                          wallet={**STRING,'description':'registered address or exact name'})
    READ_TOOLS.append({'name':row['name'],'description':summary,
        'inputSchema':{'type':'object','properties':properties,'required':list(row['arguments']),'additionalProperties':False},
        'annotations':{'readOnlyHint':True,'destructiveHint':False,'idempotentHint':True,'openWorldHint':False}})


def tool(name,description,properties=None,required=None,write=False):
    properties=properties or {}
    return {'name':name,'description':description,
        'inputSchema':{'type':'object','properties':properties,'required':list(properties) if required is None else required,'additionalProperties':False},
        'annotations':{'readOnlyHint':not write,'destructiveHint':False,'idempotentHint':True,'openWorldHint':write}}


READ_TOOLS += [tool('network_read','Read saved network allocation and coverage.',{'chain_id':{'type':'integer','minimum':1}}),
               tool('workspace_status','Read local readiness, capabilities, saved-data revisions and active jobs.'),
               tool('settings_read','Read configuration references without credential values.'),
               tool('ui_context','Read the wallet, token or network selected in the local web app.')]
MUTATIONS={
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
WRITE_TOOLS=[tool(name,'Submit '+operation+' as a durable local job. Returns a receipt, not a completed result.',
    {**props,'idempotency_key':{'type':'string','minLength':8,'maxLength':200}},required=[k for k in props if k not in ('priority','explorers')]+['idempotency_key'],write=True)
    for name,(operation,props) in MUTATIONS.items()]


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
        config=load_config()
        networks=json.loads((Path(__file__).resolve().parent/'sources/rpc-candidates.json').read_text())
        return {**{k:config[k] for k in ('schema_version','rpc','discovery')},
                'rpc_networks':[{'chain_id':n['chain_id'],'name':n.get('name',str(n['chain_id']))} for n in networks]}

    def status(self):
        return {'schema_version':1,'data_revision':self.views.data_revision(),**self.jobs.status()}

    def submit(self,request,*,launch=True):
        registry=json.loads((self.root/'wallets.json').read_text())
        operation=request.get('operation') if isinstance(request,dict) else None
        if registry.get('demo'):
            if operation in ('job.resume','job.deepen') and isinstance(request.get('input'),dict):
                operation=self.jobs.get(request['input'].get('job_id'))['operation']
            if operation in ('wallet.add','wallet.refresh','prices.refresh'):
                raise JobError('demo_read_only','Sample portfolios never contact research providers.')
        result=self.jobs.submit(request)
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
            from kira_config import public_status
            return {**self.status(),'research_connection':public_status(self.root),
                    'capabilities':{'headless':True,'manual_refresh':True,'web_controls':True,'model_runtime':False}}
        if name=='settings_read':return self.settings()
        if name=='ui_context':
            try:return json.loads((self.root/'.ui-context.json').read_text())
            except FileNotFoundError:return {'view':None,'note':'No web selection has been recorded.'}
        if name=='network_read':return self.views.network(arguments['chain_id'])
        if name=='job_list':return self.jobs.page(**arguments)
        if name=='job_read':return self.jobs.get(arguments['job_id'])
        if name=='portfolio_read':
            state=self.views.refresh();offset=arguments.get('offset',0);limit=arguments.get('limit',100)
            from kira_records import wallet_facts, recorded_valuation
            rows=wallet_facts([{**w,'recorded_valuation':recorded_valuation(w['assets']),'assets':[]} for w in state['wallets']])
            return {'schema_version':1,'dashboard':state['dashboard'],**page(rows,offset,limit,key='wallets'),
                    'data_revision':self.views.revision,'note':'Saved summaries only. Use wallet_read for holdings pages and holdings_query for search, ranking and aggregates.'}
        if name=='snapshots_list':
            return page(self.jobs.snapshots(arguments['wallet'],arguments.get('kind','holdings')),arguments.get('offset',0),arguments.get('limit',100),key='snapshots')
        return self.records.call(name,arguments,str(uuid.uuid4()))

    def select(self,value):
        if not isinstance(value,dict) or set(value)-{'view','wallet','token','chain_id'}:raise JobError('invalid_context','Expected a web selection.')
        for key,item in value.items():
            if item is not None and (type(item) is not int if key=='chain_id' else not isinstance(item,str) or len(item)>200):
                raise JobError('invalid_context','Use bounded selection identifiers.')
        if value.get('wallet'):self.jobs.wallet(value['wallet'])
        if value.get('token'):
            try:chain,address=value['token'].split(':',1);self.views.token(int(chain),address)
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
