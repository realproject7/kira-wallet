"""Scoped wallet research for in-app agents. No shell, secrets or signing tools."""
from contextlib import nullcontext
from decimal import Decimal, InvalidOperation
import json
from pathlib import Path
from kira_jobs import JobStore, JobError, fields

CATALOG = [
    {'name':'records_read','arguments':{'reads':'List of 0 to 32 declared read tools, each with name and arguments.'},'description':'Declare and execute the complete requested read plan, including every requested source. Includes one receipt per read. An empty plan is for greetings or action-only requests. Read tools only; never queues research.'},
    {'name':'portfolio_read','arguments':{},'description':'Read approved wallet summaries and coverage. Includes a bounded first holdings page; use wallet_read for more.'},
    {'name':'wallet_read','arguments':{'wallet':'registered address or exact name'},'optional_arguments':{'offset':'nonnegative integer, default 0','limit':'integer 1 to 100, default 100'},'description':'Read a compact holdings page of one approved wallet. Follow next_offset until null for the complete recorded inventory. Use token_read for curve, market and exit details.'},
    {'name':'holdings_query','arguments':{'mode':'search, rank or aggregate'},'optional_arguments':{'query':'Token symbol, name, exact contract or native. Required for search. Use one query per token.','wallet':'Optional registered wallet name or address; omit for every approved wallet.','chain_id':'Optional positive chain ID','environment':'mainnet (default), testnet or all','group_by':'asset (default: sum priced positions by chain and contract) or position','minimum_value_usd':'Optional nonnegative USD minimum per position; unknowns excluded and counted.','offset':'nonnegative integer, default 0','limit':'integer 1 to 25, default 10'},'description':'Search names, rank top N or aggregate the ENTIRE approved saved inventory on the host. No inventory pagination or jobs needed. Returns exact counts, values, ambiguity and bounded detailed matches. Use search for symbol-only questions, rank for top-N questions and aggregate for counts or sums.'},
    {'name':'token_read','arguments':{'chain_id':'positive integer','address':'contract address or native'},'optional_arguments':{'minimum_value_usd':'Nonnegative USD number or decimal string. Filter by recorded mainnet value; unknowns stay separate.'},'description':'Read this asset across ALL approved wallets in one request, including saved native observations. Use the optional minimum for value-threshold questions and the exact returned position_count. No wallet inventory pagination is needed.'},
    {'name':'snapshots_list','arguments':{'wallet':'registered address or exact name'},'description':'List past saved analyses for an approved wallet.'},
    {'name':'snapshot_read','arguments':{'snapshot_id':'saved snapshot ID'},'optional_arguments':{'offset':'nonnegative integer, default 0','limit':'integer 1 to 100, default 20'},'description':'Read a compact page of historical evidence for an approved wallet.'},
    {'name':'snapshots_compare','arguments':{'before':'saved snapshot ID','after':'saved snapshot ID'},'optional_arguments':{'offset':'nonnegative integer, default 0','limit':'integer 1 to 100, default 20'},'description':'Compare a page of recorded positions of the same approved wallet.'},
    {'name':'job_list','arguments':{},'description':'Read research jobs only for approved wallets.'},
    {'name':'job_read','arguments':{'job_id':'job UUID'},'description':'Read a scoped research job, its real status and receipts.'},
    {'name':'holdings_refresh','arguments':{'wallet':'registered address or exact name'},'description':'Queue a new holdings analysis through configured providers. Saved analyses remain intact.'},
    {'name':'prices_refresh','arguments':{'wallet':'registered address or exact name'},'description':'Queue a price update without changing recorded balances.'},
]

def compare_curve_states(positions):
    from decimal import Decimal, InvalidOperation
    names=('reserve_token','reserve_balance','current_supply','price_for_next_mint_in_reserve_token','burn_royalty_bps')
    comparisons=[]
    for previous,current in zip(positions,positions[1:]):
        left=previous['asset'].get('curve_state') or {};right=current['asset'].get('curve_state') or {}
        missing=[name for name in names if left.get(name) is None or right.get(name) is None]
        changed=[]
        for name in names:
            if name in missing:continue
            a,b=left[name],right[name]
            try:
                equal=str(a).lower()==str(b).lower() if name=='reserve_token' else Decimal(str(a))==Decimal(str(b))
            except InvalidOperation:missing.append(name);continue
            if not equal:changed.append(name)
        comparisons.append({'wallets':[previous['wallet'],current['wallet']],
            'status':'unknown' if missing else 'different_recorded_state' if changed else 'same_recorded_state',
            'changed_fields':changed,'missing_fields':missing})
    return {'comparisons':comparisons,'note':'Compare equivalent curve fields for this chain and contract only. Blocks and observation times identify evidence; they are not curve changes. Different full-wallet burn outputs can reflect different quantities. Same recorded state does not prove there were no intervening changes.'}

class ResearchTools:
    def __init__(self, root, config, guard=None):
        self.root=Path(root).resolve();self.config=config;self.store=JobStore(self.root)
        self.guard=guard or nullcontext;self.started={}

    def allowed(self):
        if self.config['scope']=='none' or not self.config.get('wallet_tools'):
            raise JobError('wallet_access_off','Wallet research access is off. Enable it in model settings.')
        from kira_agent import projection
        current=projection(self.root,self.config)
        return current, {w['address'].lower() for w in current['wallets']}

    def wallet(self, selector, approved):
        key=self.store.wallet(selector)['address_key']
        if key not in approved:raise JobError('wallet_scope','This wallet is outside the current conversation scope.')
        return key

    def snapshot(self, identity, approved, offset=0, limit=20):
        # Only published historical analyses listed for this scope may be read.
        visible={row['snapshot_id'] for key in approved for row in self.store.snapshots(key)}
        if identity not in visible:raise JobError('snapshot_scope','This analysis is outside the current conversation scope.')
        result=self.store.snapshot(identity)
        if result.get('wallet_address','').lower() not in approved:raise JobError('snapshot_scope','This analysis does not belong to the approved wallet.')
        from kira_agent import wallet_facts, compact_wallet_facts, recorded_valuation
        from model import project_wallet
        entry=self.store.wallet(result['wallet_address'])
        entry={**entry,'latest_snapshot':{'directory':identity}}
        wallet=project_wallet(entry,result,self.root);count=len(wallet['assets'])
        wallet['recorded_valuation']=recorded_valuation(wallet['assets'])
        wallet['assets']=wallet['assets'][offset:offset+limit]
        rows=compact_wallet_facts(wallet_facts([wallet],pool_budget=0))
        rows[0].update(asset_count=count,assets_omitted=count-len(wallet['assets']),offset=offset,
                       next_offset=offset+len(wallet['assets']) if offset+len(wallet['assets'])<count else None)
        return {'snapshot_id':identity,'wallets':rows,'note':'Historical recorded evidence. Prices and balances retain their observation times; curve backing is not executable cash. Follow next_offset for more holdings.'}

    def job(self, job, approved):
        if job['operation'] not in ('wallet.add','wallet.refresh','prices.refresh'):
            raise JobError('job_scope','Only approved wallet research jobs are available.')
        selector=job['input'].get('wallet') or job['input'].get('address')
        wallet=self.wallet(selector,approved)
        return {'wallet':wallet,**{key:job.get(key) for key in ('job_id','operation','state','stage','created_at','updated_at','checkpoint','result','chains','analysis_phase','parent_job_id','continuation_id','events')}}

    def call(self, name, arguments, key):
        if name=='records_read':
            if not isinstance(arguments,dict):raise JobError('invalid_tool','Expected a read plan.')
            fields(arguments,['reads']);reads=arguments['reads']
            if not isinstance(reads,list) or not 0<=len(reads)<=32:raise JobError('invalid_tool','Use at most 32 read requests.')
            allowed={'holdings_query','portfolio_read','wallet_read','token_read','snapshots_list','snapshot_read','snapshots_compare','job_list','job_read'}
            for read in reads:
                if not isinstance(read,dict):raise JobError('invalid_tool','Expected read requests.')
                fields(read,['name','arguments'])
                if read['name'] not in allowed:raise JobError('invalid_tool','Read plans accept declared read tools only.')
            results=[]
            for read in reads:
                try:result=self.call(read['name'],read['arguments'],key)
                except JobError as error:
                    if error.code=='cancelled':raise
                    result={'error':{'code':error.code,'message':str(error)}}
                results.append({**read,'status':'failed' if isinstance(result,dict) and result.get('error') else 'completed','result':result})
            response={'requested_reads':len(reads),'completed_reads':sum(read['status']=='completed' for read in results),
                      'completion':'complete' if all(read['status']=='completed' for read in results) else 'partial','reads':results}
            token_reads=[r for r in results if r['name']=='token_read' and r['status']=='completed']
            if token_reads:
                response['position_count']=len({(p['wallet'],r['result']['identity']) for r in token_reads for p in r['result']['positions']})
                response['position_count_scope']='Exact distinct wallet/chain/asset matches returned by completed token reads, after their filters. Use this count verbatim; failed reads remain unresolved.'
            return response
        tool=next((row for row in CATALOG if row['name']==name),None)
        if tool is None:raise JobError('unsupported_tool','Choose a declared wallet research tool.')
        if not isinstance(arguments,dict):raise JobError('invalid_tool','Expected declared tool arguments.')
        fields({k:v for k,v in arguments.items() if k not in tool.get('optional_arguments',{})},list(tool['arguments']))
        for field,value in arguments.items():
            if field=='minimum_value_usd':
                try:
                    if type(value) not in (str,int,float) or len(str(value))>80:raise ValueError()
                    minimum=Decimal(str(value))
                    if not minimum.is_finite() or minimum<0:raise ValueError()
                except (InvalidOperation,ValueError):raise JobError('invalid_tool','Use a finite nonnegative USD minimum.') from None
            elif field in ('offset','limit'):
                if type(value) is not int or value<0 or field=='limit' and not 1<=value<=100:
                    raise JobError('invalid_tool','Use a nonnegative offset and a limit from 1 to 100.')
            elif field=='chain_id':
                if type(value) is not int or value<1:raise JobError('invalid_tool','Expected a positive chain ID.')
            elif not isinstance(value,str) or not value or len(value)>500:
                raise JobError('invalid_tool','Expected a bounded recorded identifier.')
        context,approved=self.allowed()
        if name=='holdings_query':
            from kira_agent import scoped_wallets
            from holdings_query import query_holdings
            wallets=scoped_wallets(self.root,self.config)
            if 'wallet' in arguments:
                selected=self.wallet(arguments['wallet'],approved)
                wallets=[w for w in wallets if w['key']==selected]
            return query_holdings(wallets,arguments)
        if name=='portfolio_read':return context
        if name=='wallet_read':
            wallet=self.wallet(arguments['wallet'],approved)
            from kira_agent import projection
            page=projection(self.root,self.config,wallet_key=wallet,offset=arguments.get('offset',0),limit=arguments.get('limit',100),inventory=True)
            return {**page['wallets'][0],'note':page['note'],'research_connection':page['research_connection']}
        if name=='token_read':
            from kira_jobs import ADDRESS
            address=arguments['address'].lower()
            if address!='native' and not ADDRESS.fullmatch(address):raise JobError('invalid_token','Expected native or a 20-byte contract address.')
            identity=str(arguments['chain_id'])+':'+address
            from kira_agent import projection
            specific=projection(self.root,self.config,token_id=identity)
            positions=[{'wallet':row['address'],'snapshot_id':row.get('snapshot_id'),'asset':asset} for row in specific['wallets'] for asset in row['assets']]
            total=len(positions)
            outside=sum(p['asset'].get('environment')!='mainnet' or p['asset'].get('archived') for p in positions)
            unpriced=sum(p['asset'].get('environment')=='mainnet' and not p['asset'].get('archived') and p['asset'].get('value_usd') is None for p in positions)
            if 'minimum_value_usd' in arguments:
                positions=[p for p in positions if p['asset'].get('environment')=='mainnet' and not p['asset'].get('archived')
                           and p['asset'].get('value_usd') is not None and Decimal(str(p['asset']['value_usd']))>=minimum]
            return {'identity':identity,'positions':positions,'position_count':len(positions),'unfiltered_position_count':total,
                    'unpriced_position_count':unpriced,'outside_usd_scope_count':outside,'curve_comparison':compare_curve_states(positions),
                    'note':'An absent record is unknown, not a verified zero holding.'}
        if name=='snapshots_list':return self.store.snapshots(self.wallet(arguments['wallet'],approved))
        if name=='snapshot_read':return self.snapshot(arguments['snapshot_id'],approved,arguments.get('offset',0),arguments.get('limit',20))
        if name=='snapshots_compare':
            self.snapshot(arguments['before'],approved);self.snapshot(arguments['after'],approved)
            result=self.store.compare(arguments['before'],arguments['after'])
            count=len(result['positions']);offset=arguments.get('offset',0);limit=arguments.get('limit',20)
            result['positions']=result['positions'][offset:offset+limit]
            result.update(position_count=count,offset=offset,next_offset=offset+len(result['positions']) if offset+len(result['positions'])<count else None)
            return result
        if name=='job_list':
            rows=[]
            for job in self.store.list():
                try:rows.append(self.job(job,approved))
                except JobError:continue
            return rows[:50]
        if name=='job_read':return self.job(self.store.get(arguments['job_id']),approved)
        wallet=self.wallet(arguments['wallet'],approved)
        signature=(name,wallet)
        with self.guard():
            # Recheck scope immediately before admission. Duplicate requests within
            # the same turn reuse a durable job rather than starting more research.
            _,approved=self.allowed();self.wallet(wallet,approved)
            if signature not in self.started:
                if json.loads((self.root/'wallets.json').read_text()).get('demo'):
                    raise JobError('demo_read_only','Sample portfolios never contact research providers.')
                job=self.store.submit({'schema_version':1,'operation':'wallet.refresh' if name=='holdings_refresh' else 'prices.refresh',
                    'input':{'wallet':wallet},'idempotency_key':key})
                self.started[signature]=job['job_id']
                if job['state']=='queued':self.store.launch()
            job=self.store.get(self.started[signature])
        return {**self.job(job,approved),'note':'Only succeeded or partial with a publication receipt proves a saved result. Queued/running work is not finished. Research jobs are managed in Activity and survive chat cancellation.'}
