'use strict';
(function (root) {
  const pageSize = 50;
  function catalog(tokens, filters = {}) {
    const search = (filters.search || '').trim().toLowerCase();
    const rows = tokens.filter(t => (filters.testnets || t.environment !== 'testnet')
      && (!filters.network || filters.network === 'all' || String(t.chain_id) === String(filters.network))
      && (!(filters.minimum > 0) || (t.environment !== 'testnet' && t.value_usd != null && t.value_usd >= filters.minimum))
      && (filters.pricing !== 'priced' || (t.value_usd != null && !t.unpriced_count))
      && (filters.pricing !== 'unpriced' || t.value_usd == null || t.unpriced_count > 0)
      && (!search || [t.symbol, t.name, t.address || 'native'].some(v => String(v || '').toLowerCase().includes(search))));
    const order = filters.sort || 'value';
    rows.sort((a, b) => (order === 'name' ? String(a.name || a.symbol).localeCompare(String(b.name || b.symbol))
      : order === 'wallets' ? b.wallet_count - a.wallet_count
      : (b.value_usd ?? -Infinity) - (a.value_usd ?? -Infinity)) || String(a.id).localeCompare(String(b.id)));
    const pages = Math.max(1, Math.ceil(rows.length / pageSize));
    const page = Math.min(Math.max(1, filters.page || 1), pages);
    return { rows: rows.slice((page - 1) * pageSize, page * pageSize), count: rows.length, page, pages };
  }
  const active = job => ['queued', 'running'].includes(job.state);
  const rpcGap = chain => chain.lifecycle?.status!=='retired'&&chain.lifecycle?.status!=='retirement_reported'&&((chain.rpc_available===false&&!chain.rpc_pending)||(chain.registry_complete===false&&!chain.rpc_pending&&chain.registry_phase!=='deferred')||chain.candidate_balance_errors>0);
  const coverageGap = chain => chain.lifecycle?.status!=='retired'&&(chain.head_status==='stale'||chain.lifecycle?.status==='retirement_reported'||!chain.complete||rpcGap(chain)||chain.candidate_deferred>0||chain.market_pending||chain.market_errors>0||chain.token_detail_errors>0);
  function networkEmpty(network, recordedCount) {
    if(recordedCount)return {title:'No tokens match these filters',message:'Lower the minimum value or clear your search to see recorded holdings.',activity:false};
    const rows=network.wallets||[];
    if(network.lifecycle?.status==='retired'||(rows.length&&rows.every(r=>r.coverage==='Archived network')))return {title:'Archived network',message:'This network is excluded from new research. Any saved observations remain historical.',activity:false};
    if(!rows.length||rows.some(r=>['Research pending','Awaiting analysis','Not researched'].includes(r.coverage)))return {title:'Research is pending on this network',message:'No holdings have been recorded here yet. Check Activity for progress or resume saved work. Missing records do not mean zero holdings.',activity:true};
    if(rows.some(r=>r.coverage!=='Researched'))return {title:'No holdings recorded; coverage is incomplete',message:'Some checks could not establish holdings on this network. Review Activity and retry holdings when ready. Missing records remain unknown.',activity:true};
    return {title:'No positive holdings recorded',message:'The completed checks found no positive holdings. Coverage can still omit tokens. Refresh holdings to check again.',activity:false};
  }
  function discoveryNotice(wallet, readiness = null) {
    if(!wallet?.analysed_at)return null;
    const chains=(wallet.chains||[]).filter(c=>c.environment==='mainnet'&&c.lifecycle?.status!=='retired');
    const gaps=chains.filter(coverageGap),unavailable=gaps.filter(rpcGap);
    if(readiness&&readiness.discovery_key_available!==true)return {title:'Connect Alchemy to update this portfolio',message:'Your saved holdings are available. Alchemy is required for new token and price lookups.',action:'settings',settingsLabel:'Connect Alchemy'};
    const pending=gaps.length-unavailable.length;
    const summary=(chains.length-gaps.length)+' of '+chains.length+' active networks checked'+(unavailable.length?' · '+unavailable.length+' unavailable':'')+(pending?' · '+pending+' incomplete':'');
    const names=gaps.map(c=>c.name).join(', ');
    const earlier=wallet.lookup_mode!=='all_networks'&&chains.some(c=>c.rpc_pending||c.registry_phase==='deferred');
    return {title:'Network coverage · '+summary,
      message:(earlier?'This earlier scan checked a limited selection. ':names?names+': missing balances and prices remain unknown. ':'Available checks are complete. Coverage can still omit tokens. ')+
        'Refresh all holdings checks every configured active network, balances and markets for this wallet. Saved observations stay available while it runs.',
      action:'refresh',refreshLabel:'Refresh all holdings',settings:false,rpcIssues:unavailable.length>0,gapCount:gaps.length};
  }
  function jobPresentation(job, now = Date.now(), connected = true) {
    const labels = { queued: 'Queued', running: 'Running', succeeded: 'Completed', partial: 'Saved with gaps', interrupted: 'Interrupted', failed: 'Failed', cancelled: 'Stopped' };
    const start = job.state === 'queued' ? job.updated_at || job.created_at : job.started_at || job.created_at;
    const end = active(job) ? now : Date.parse(job.events?.at(-1)?.observed_at || job.updated_at);
    const elapsed = Math.max(0, Math.floor((end - Date.parse(start)) / 1000));
    const last = job.events?.at(-1)?.observed_at || job.updated_at;
    const quiet = job.state === 'running' && now - Date.parse(last) > 60000;
    return {
      label: job.cancel_requested && active(job) ? (job.scan_policy?'Pausing':'Stopping') : job.scan_policy&&job.state==='cancelled'?'Paused':job.scan_policy&&job.analysis_phase==='baseline'&&['partial','succeeded'].includes(job.state)?'Holdings saved':job.scan_policy&&job.analysis_phase==='enrichment'&&['partial','succeeded'].includes(job.state)?'Sell analysis saved':labels[job.state] || 'Unknown',
      active: active(job), spinner: connected && job.state === 'running', quiet,
      elapsed: Number.isFinite(elapsed) ? elapsed : null,
      timerLabel: job.state === 'queued' ? 'Waiting' : job.started_at ? job.attempt>1?(job.scan_policy?'Current pass':'Attempt elapsed'):'Elapsed' : 'Since request',
      freshness: !connected ? 'Connection lost. Last recorded state shown.' : quiet ? 'Awaiting a new stage update. Still marked running.' : '',
    };
  }
  const progressUnits={balances:'balances',registry:'registry entries',metadata:'metadata reads',curves:'curve reads',reserves:'reserve records',mintclub_membership:'membership checks',
    history:'history pages',market_discovery:'token market lookups',factory_queries:'factory queries',pool_checks:'pool checks',cashout_routes:'held assets',asset_review:'assets reviewed'};
  function assetProgress(job) {
    const rows=Object.values(job.asset_progress||{}).filter(p=>p&&typeof p==='object'&&['total','checked','quoted','unknown'].every(k=>Number.isSafeInteger(p[k])&&p[k]>=0)&&p.checked<=p.total&&p.quoted+p.unknown===p.checked);
    if(!rows.length)return null;
    return rows.reduce((sum,p)=>Object.fromEntries(Object.keys(sum).map(k=>[k,sum[k]+p[k]])),{total:0,checked:0,quoted:0,unknown:0});
  }
  function jobProgress(job, now=Date.now(), connected=true) {
    const last=job.events?.at(-1),counts=last?.counts||{},context=last?.context||{},unit=progressUnits[context.operation];
    const known=context.operation!=='reserves'&&Number.isSafeInteger(counts.total)&&counts.total>0&&Number.isSafeInteger(counts.checked)&&counts.checked<=counts.total;
    const checked=Number.isSafeInteger(counts.checked)&&counts.checked>=0?counts.checked:null;
    const currentScope=!active(job)||job.state==='running'&&(context.attempt==null||context.attempt===job.attempt);
    const count=currentScope&&unit&&checked!=null?(known?checked+' / '+counts.total+' '+unit:checked+' '+unit+' checked')+(context.operation==='history'?' including saved work':''):'';
    const waiting=job.state==='queued'&&job.continuation?.not_before*1000>now;
    let eta=waiting?'Next check in '+duration(Math.ceil(job.continuation.not_before-now/1000)):'';
    if(job.state==='running'&&connected&&!job.cancel_requested&&context.operation!=='asset_review'&&known&&checked<counts.total&&context.attempt===job.attempt&&now-Date.parse(last.observed_at)<=20000){
      const samples=[];
      for(const event of job.events||[]){
        const c=event.context||{},n=event.counts||{},time=Date.parse(event.observed_at);
        if(c.operation!==context.operation||c.chain_id!==context.chain_id||c.provider!==context.provider||c.attempt!==job.attempt||n.total!==counts.total)continue;
        if(!Number.isSafeInteger(n.checked)||n.checked<0||n.checked>counts.total||!Number.isFinite(time))continue;
        const previous=samples.at(-1);
        if(previous&&(n.checked<previous.checked||time<=previous.time))samples.length=0;
        if(!samples.length||n.checked>samples.at(-1).checked)samples.push({time,checked:n.checked});
      }
      const recent=samples.slice(-5),span=recent.length?(recent.at(-1).time-recent[0].time)/1000:0;
      if(recent.length>=3&&span>=15){
        const rates=recent.slice(1).map((s,i)=>(s.checked-recent[i].checked)/((s.time-recent[i].time)/1000));
        const slow=Math.min(...rates),fast=Math.max(...rates),remaining=counts.total-checked;
        if(slow>0&&fast/slow<=4){
          const low=Math.max(15,Math.floor(remaining/fast*.75/15)*15),high=Math.max(low+15,Math.ceil(remaining/slow*1.5/15)*15);
          eta='Current step estimate: '+duration(low)+' to '+duration(high)+'. Overall time unknown.';
        }
      }
    }
    if(!active(job))eta='';
    const age=Math.max(0,Math.floor((now-Date.parse(job.created_at))/1000));
    const saved=active(job)&&(job.result||job.previous_result)?'Saved results remain available while research continues. Missing holdings and prices are still unknown.':'';
    return {count,eta,saved,cumulative:context.operation==='asset_review',assets:assetProgress(job),totalElapsed:Number.isFinite(age)?age:null,
      checked:known&&currentScope?checked:null,total:known&&currentScope?counts.total:null,
      lastProgress:job.progress_observed_at||null};
  }
  function researchSession(jobs,wallet,now=Date.now()) {
    const rows=jobs.filter(j=>['wallet.add','wallet.refresh'].includes(j.operation)&&String(j.input?.wallet||j.input?.address||'').toLowerCase()===wallet?.key).sort((a,b)=>b.created_at.localeCompare(a.created_at));
    if(!rows.length)return null;
    const latest=rows[0],base=latest.parent_job_id?rows.find(j=>j.job_id===latest.parent_job_id):latest;
    const deep=latest.analysis_phase==='enrichment'?latest:rows.find(j=>j.parent_job_id===base?.job_id);
    const basic=base?.analysis_phase!=='enrichment'?base:null;
    const job=deep||basic||latest,isDeep=job.analysis_phase==='enrichment';
    const basicReady=!!basic?.result&&['succeeded','partial'].includes(basic.state)||isDeep;
    let mode,title,description,action=null,actionLabel=null;
    const legacy=basic?.scan_policy!=='alchemy_inventory_v1';
    if(active(job)){
      mode=job.cancel_requested?'pausing':job.state==='queued'?'waiting':'running';
      title=job.cancel_requested?'Saving your progress':isDeep?'Analyzing sell routes':'Looking up your holdings';
      description=job.cancel_requested?'Your saved results stay available.':job.state==='queued'?'Queued. Your saved portfolio stays available.':isDeep?'Checking sale and redemption estimates for your saved holdings. Balances are unchanged.':'Checking every configured network, token balances, prices and artwork.';
      action='cancel';actionLabel='Pause';
    }else if(legacy){
      mode='ready';title='Update your holdings';description='Refresh to check every configured network and all token candidates with Alchemy.';action='refresh';actionLabel='Refresh holdings';
    }else if(['cancelled','interrupted','failed'].includes(job.state)){
      mode='paused';title=isDeep?'Sell analysis paused':'Holdings lookup paused';
      description=job.errors?.some(e=>e.code==='no_progress')?'No new evidence was available. Check your connection, then retry.':'Your progress is saved. Resume when ready.';
      if(job.errors?.some(e=>e.code==='superseded')){description='A newer holdings lookup replaced this work.';}
      else{action='resume';actionLabel='Resume';}
    }else if(isDeep){
      mode='saved';title='Sell analysis saved';description='Available estimates are saved. Unavailable routes remain unknown; estimates exclude gas and do not guarantee execution.';
    }else{
      mode='ready';title='Your holdings are ready';description='Balances, prices and artwork are available. Analyze sell routes only if you need sale or redemption estimates.';
      if(basic?.result){action='deepen';actionLabel='Analyze sell routes';}
    }
    return {basic,deep,job,isDeep,basicReady,mode,title,description,action,actionLabel};
  }
  function duration(seconds) {
    if (seconds == null) return 'Unknown';
    const h = Math.floor(seconds / 3600), m = Math.floor(seconds % 3600 / 60), s = seconds % 60;
    return (h ? h + 'h ' : '') + m + 'm ' + s + 's';
  }
  const api = { catalog, pageSize, active, jobPresentation, jobProgress, assetProgress, researchSession, duration, discoveryNotice, coverageGap, networkEmpty };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else root.KiraView = api;
})(typeof globalThis !== 'undefined' ? globalThis : this);
