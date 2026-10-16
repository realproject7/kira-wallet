"""Scoped wallet research for in-app agents. No shell, secrets or signing tools."""
from contextlib import nullcontext
import json
from pathlib import Path
from kira_jobs import JobStore, JobError, fields

CATALOG = [
    {'name':'portfolio_read','arguments':{},'description':'Read approved wallet summaries and coverage. Includes a bounded first holdings page; use wallet_read for more.'},
    {'name':'wallet_read','arguments':{'wallet':'registered address or exact name'},'optional_arguments':{'offset':'nonnegative integer, default 0','limit':'integer 1 to 100, default 100'},'description':'Read a compact holdings page of one approved wallet. Follow next_offset until null for the complete recorded inventory. Use token_read for curve, market and exit details.'},
    {'name':'token_read','arguments':{'chain_id':'positive integer','address':'contract address or native'},'description':'Read a chain-specific token in the approved wallets.'},
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
        from kira_agent import wallet_facts, compact_wallet_facts
        from model import project_wallet
        entry=self.store.wallet(result['wallet_address'])
        entry={**entry,'latest_snapshot':{'directory':identity}}
        wallet=project_wallet(entry,result,self.root);count=len(wallet['assets'])
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
        tool=next((row for row in CATALOG if row['name']==name),None)
        if tool is None:raise JobError('unsupported_tool','Choose a declared wallet research tool.')
        if not isinstance(arguments,dict):raise JobError('invalid_tool','Expected declared tool arguments.')
        fields({k:v for k,v in arguments.items() if k not in tool.get('optional_arguments',{})},list(tool['arguments']))
        for field,value in arguments.items():
            if field in ('offset','limit'):
                if type(value) is not int or value<0 or field=='limit' and not 1<=value<=100:
                    raise JobError('invalid_tool','Use a nonnegative offset and a limit from 1 to 100.')
            elif field=='chain_id':
                if type(value) is not int or value<1:raise JobError('invalid_tool','Expected a positive chain ID.')
            elif not isinstance(value,str) or not value or len(value)>500:
                raise JobError('invalid_tool','Expected a bounded recorded identifier.')
        context,approved=self.allowed()
        if name=='portfolio_read':return context
        if name=='wallet_read':
            wallet=self.wallet(arguments['wallet'],approved)
            from kira_agent import projection
            page=projection(self.root,self.config,wallet_key=wallet,offset=arguments.get('offset',0),limit=arguments.get('limit',100),inventory=True)
            return {**page['wallets'][0],'note':page['note']}
        if name=='token_read':
            from kira_jobs import ADDRESS
            address=arguments['address'].lower()
            if address!='native' and not ADDRESS.fullmatch(address):raise JobError('invalid_token','Expected native or a 20-byte contract address.')
            identity=str(arguments['chain_id'])+':'+address
            from kira_agent import projection
            specific=projection(self.root,self.config,token_id=identity)
            positions=[{'wallet':row['address'],'snapshot_id':row.get('snapshot_id'),'asset':asset} for row in specific['wallets'] for asset in row['assets']]
            return {'identity':identity,'positions':positions,'curve_comparison':compare_curve_states(positions),
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
