'use strict';
(function (root) {
  const pageSize = 50;
  function catalog(tokens, filters = {}) {
    const search = (filters.search || '').trim().toLowerCase();
    const rows = tokens.filter(t => (filters.testnets || t.environment !== 'testnet')
      && (!filters.network || filters.network === 'all' || String(t.chain_id) === String(filters.network))
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
  const coverageGap = chain => chain.head_status==='stale'||['retired','retirement_reported'].includes(chain.lifecycle?.status)||!chain.complete||rpcGap(chain)||chain.candidate_deferred>0||chain.market_pending||chain.market_errors>0;
  function networkEmpty(network, recordedCount) {
    if(recordedCount)return {title:'No tokens match these filters',message:'Lower the minimum value or clear your search to see recorded holdings.',activity:false};
    const rows=network.wallets||[];
    if(!rows.length||rows.some(r=>['Research pending','Awaiting analysis','Not researched'].includes(r.coverage)))return {title:'Research is pending on this network',message:'No holdings have been recorded here yet. Check Activity for progress or resume saved work. Missing records do not mean zero holdings.',activity:true};
    if(rows.some(r=>r.coverage!=='Researched'))return {title:'No holdings recorded; coverage is incomplete',message:'Some checks could not establish holdings on this network. Review Activity and retry holdings when ready. Missing records remain unknown.',activity:true};
    return {title:'No positive holdings recorded',message:'The completed checks found no positive holdings. Coverage can still omit tokens. Refresh holdings to check again.',activity:false};
  }
  function discoveryNotice(wallet, readiness = null) {
    const lifecycle=(wallet?.chains||[]).filter(c=>c.environment==='mainnet'&&['retired','retirement_reported'].includes(c.lifecycle?.status));
    const other=(wallet?.chains||[]).filter(c=>c.environment==='mainnet'&&!lifecycle.includes(c));
    if(lifecycle.length&&other.some(coverageGap)){
      const notice=coverageNotice({...wallet,chains:other},readiness);
      if(notice)notice.message+=' '+lifecycle.map(c=>c.name+': '+(c.lifecycle.status==='retired'?'retired records are historical and excluded from current value; another provider cannot restart the network.':'retirement is reported without a verified official closure notice; changing provider is not a verified remedy.')).join(' ');
      return notice;
    }
    return coverageNotice(wallet,readiness);
  }
  function coverageNotice(wallet, readiness = null) {
    const chains=(wallet?.chains||[]).filter(c=>c.environment==='mainnet');
    const gaps=chains.filter(coverageGap);
    if(!wallet?.analysed_at||!gaps.length)return null;
    const retired=chains.filter(c=>c.lifecycle?.status==='retired');
    const reported=chains.filter(c=>c.lifecycle?.status==='retirement_reported');
    if(retired.length)return {title:'Retired network records are archived',message:retired.map(c=>c.name).join(', ')+': retained balances are historical and excluded from current value. Review the official notice and last observation in network coverage. Connecting another provider cannot restart a retired network.',action:'none',settings:false};
    const missing=chains.some(c=>!c.complete);
    const disabled=(readiness?.public_discovery===false&&readiness?.discovery_provider==='none'&&chains.every(c=>!c.complete))||(!readiness&&chains.every(c=>c.discovery_status==='disabled'));
    const noKey=readiness?.discovery_configured&&!readiness.discovery_key_available;
    const rpc=chains.filter(rpcGap);
    if(chains.some(c=>c.market_pending))return {title:'Balances saved; market checks paused',message:'Recorded balances and completed registry checks are available. Remaining market verification reached its time budget. Resume the job in Activity to continue saved checks. Pending markets are not verified absent, and missing prices remain unknown.',action:'none',settings:false};
    if(rpc.length){
      const connection=missing&&(disabled||noKey);
      return {title:'Some balances could not be checked',
        message:'On-chain checks did not finish on '+rpc.length+(rpc.length===1?' network.':' networks.')+' Missing balances are unknown, so this portfolio is partial. Wait a moment, then retry holdings. '+(readiness?.discovery_key_available?'Review your Alchemy connection if errors continue. Public and custom providers can both have outages or limits.':'We recommend connecting Alchemy for backup RPC reads and broader token coverage on supported networks.')+(connection?' Other ERC20 holdings may also be missing.':''),
        action:'refresh',settings:true,rpcIssues:true,refreshLabel:'Retry holdings',settingsLabel:readiness?.discovery_key_available?'Review Alchemy connection':'Set up Alchemy'};
    }
    if(reported.length)return {title:'Network retirement was reported',message:reported.map(c=>c.name).join(', ')+': a shutdown was reported, but no verified official closure notice is recorded. Saved balances remain dated evidence. RPC failure alone cannot establish closure, and Alchemy is not a verified recovery path. Check network coverage before retrying.',action:'none',settings:false};
    if(chains.some(c=>c.head_status==='stale'))return {title:'A provider returned an old block head',message:'These balances use a dated block observation. A stale head does not prove the network has shut down. Review the recorded block and time, then retry later or review your data connection.',action:'refresh',settings:true,settingsLabel:'Review data connection'};
    if(chains.some(c=>c.market_errors>0))return {title:'Some market checks did not complete',message:'Recorded holdings remain available. Some pool reads failed, so missing market and price details remain unknown. Retry holdings. If this continues, review your data connection and its RPC access.',action:'refresh',settings:true,settingsLabel:'Review data connection'};
    if(chains.some(c=>c.discovery_status==='history_pending'))return {title:'Free token history is still being checked',message:'Kira found token candidates without a key and verifies their balances with RPC. The saved transfer-history window is unfinished. Refresh holdings to continue from its saved page. Known balances remain available; transfer records do not prove current holdings. Alchemy is optional for a broader initial inventory.',action:'refresh',refreshLabel:'Continue free discovery',settings:true,settingsLabel:'Review optional connection'};
    if(!disabled&&!noKey&&chains.some(c=>c.rpc_pending||c.registry_phase==='deferred'))return {title:'First results are available',message:'This initial report has recorded balances. Other networks, remaining token candidates, the full Mint Club registry and markets need detailed research. Check Activity for progress or to resume stopped work. You can also refresh holdings. Missing holdings and prices remain unknown. Alchemy is optional for broader coverage.',action:'none',settings:true,settingsLabel:'Review optional connection'};
    if(missing&&disabled)return {title:'Some tokens may be missing',message:'Free research checks native balances, selected common tokens and Mint Club assets, with keyless token discovery on supported networks. Public RPC cannot list all wallet tokens. We recommend Alchemy for broader token coverage on supported networks. Connect it, then refresh holdings. Missing tokens are not zero balances.',action:'settings',settingsLabel:'Set up Alchemy'};
    if(missing&&noKey)return {title:'Token discovery needs a connection',message:'The local Alchemy key is unavailable. Follow the setup guide, check the key, then refresh holdings. Other tokens may be missing from this partial portfolio.',action:'settings',settingsLabel:'Set up Alchemy'};
    if(missing&&readiness?.discovery_key_available&&chains.some(c=>['disabled','missing_credential'].includes(c.discovery_status)))return {title:'Refresh holdings to discover other tokens',message:'Your discovery connection is now available. This saved analysis predates it and remains partial until you refresh holdings.',action:'refresh'};
    const unsupported=gaps.every(c=>c.discovery_status==='unsupported');
    return {title:unsupported?'Some networks have limited token coverage':'Your portfolio is partial',message:unsupported?'Broader token discovery is unavailable on these networks. An Alchemy connection cannot cover every network or token. Available balances remain visible; missing holdings remain unknown.':'Some token discovery did not complete. Other holdings may be missing. '+(readiness?.discovery_key_available?'Retry holdings, then check your Alchemy app access, networks and usage limits if this continues.':'Free research remains available. Optional Alchemy can broaden token coverage on supported networks; connect it and refresh holdings if you need more coverage.'),action:readiness?.discovery_key_available?'refresh':'settings',settings:true,settingsLabel:readiness?.discovery_key_available?'Review Alchemy connection':'Set up Alchemy'};
  }
  function jobPresentation(job, now = Date.now(), connected = true) {
    const labels = { queued: 'Queued', running: 'Running', succeeded: 'Completed', partial: 'Saved with gaps', interrupted: 'Interrupted', failed: 'Failed', cancelled: 'Stopped' };
    const start = job.state === 'queued' ? job.updated_at || job.created_at : job.started_at || job.created_at;
    const end = active(job) ? now : Date.parse(job.updated_at);
    const elapsed = Math.max(0, Math.floor((end - Date.parse(start)) / 1000));
    const last = job.events?.at(-1)?.observed_at || job.updated_at;
    const quiet = job.state === 'running' && now - Date.parse(last) > 60000;
    return {
      label: job.cancel_requested && active(job) ? 'Stopping' : labels[job.state] || 'Unknown',
      active: active(job), spinner: connected && job.state === 'running', quiet,
      elapsed: Number.isFinite(elapsed) ? elapsed : null,
      timerLabel: job.state === 'queued' ? 'Waiting' : job.started_at ? job.attempt>1?'Attempt elapsed':'Elapsed' : 'Since request',
      freshness: !connected ? 'Connection lost. Last recorded state shown.' : quiet ? 'Awaiting a new stage update. Still marked running.' : '',
    };
  }
  const progressUnits={balances:'balances',registry:'registry entries',metadata:'metadata reads',curves:'curve reads',reserves:'reserve records',mintclub_membership:'membership checks',
    history:'history pages',market_discovery:'token market lookups',factory_queries:'factory queries',pool_checks:'pool checks',cashout_routes:'held assets'};
  function jobProgress(job, now=Date.now(), connected=true) {
    const last=job.events?.at(-1),counts=last?.counts||{},context=last?.context||{},unit=progressUnits[context.operation];
    const known=context.operation!=='reserves'&&Number.isSafeInteger(counts.total)&&counts.total>0&&Number.isSafeInteger(counts.checked)&&counts.checked<=counts.total;
    const checked=Number.isSafeInteger(counts.checked)&&counts.checked>=0?counts.checked:null;
    const count=unit&&checked!=null?(known?checked+' / '+counts.total+' '+unit:checked+' '+unit+' checked')+(context.operation==='history'?' including saved work':''):'';
    const waiting=job.state==='queued'&&job.continuation?.not_before*1000>now;
    let eta=waiting?'Provider retry in '+duration(Math.ceil(job.continuation.not_before-now/1000)):'Overall remaining time is unknown.';
    if(job.state==='running'&&connected&&!job.cancel_requested&&known&&checked<counts.total&&context.attempt===job.attempt&&now-Date.parse(last.observed_at)<=20000){
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
    return {count,eta,saved,totalElapsed:Number.isFinite(age)?age:null};
  }
  function duration(seconds) {
    if (seconds == null) return 'Unknown';
    const h = Math.floor(seconds / 3600), m = Math.floor(seconds % 3600 / 60), s = seconds % 60;
    return (h ? h + 'h ' : '') + m + 'm ' + s + 's';
  }
  const api = { catalog, pageSize, active, jobPresentation, jobProgress, duration, discoveryNotice, coverageGap, networkEmpty };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else root.KiraView = api;
})(typeof globalThis !== 'undefined' ? globalThis : this);
