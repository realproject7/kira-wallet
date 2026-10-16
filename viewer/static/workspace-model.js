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
  const rpcGap = chain => chain.rpc_available===false||chain.registry_complete===false||chain.candidate_balance_errors>0;
  const coverageGap = chain => !chain.complete||rpcGap(chain);
  function discoveryNotice(wallet, readiness = null) {
    const chains=(wallet?.chains||[]).filter(c=>c.environment==='mainnet');
    const gaps=chains.filter(coverageGap);
    if(!wallet?.analysed_at||!gaps.length)return null;
    const missing=chains.some(c=>!c.complete);
    const disabled=(readiness?.discovery_provider==='none'&&chains.every(c=>!c.complete))||(!readiness&&chains.every(c=>c.discovery_status==='disabled'));
    const noKey=readiness?.discovery_configured&&!readiness.discovery_key_available;
    const rpc=chains.filter(rpcGap);
    if(rpc.length){
      const connection=missing&&(disabled||noKey);
      return {title:'Some balances could not be checked',
        message:'On-chain checks did not finish on '+rpc.length+(rpc.length===1?' network.':' networks.')+' Missing balances are unknown, so this portfolio is partial. Wait a moment, then retry holdings. If errors continue, review RPC settings or use a different provider.'+(connection?' Token discovery also needs a connection to find other ERC20 holdings.':''),
        action:'refresh',settings:true,rpcIssues:true,refreshLabel:'Retry holdings',settingsLabel:connection?'Review data connection':'Review RPC settings'};
    }
    if(missing&&disabled)return {title:'Token discovery is off',message:'This analysis checks native balances and Mint Club assets only. Other ERC20 holdings may be missing. Connect a data provider, then refresh holdings.',action:'settings'};
    if(missing&&noKey)return {title:'Token discovery needs a connection',message:'The selected indexer credential is unavailable. Review its connection, then refresh holdings. This portfolio is partial.',action:'settings'};
    if(missing&&readiness?.discovery_key_available&&chains.some(c=>['disabled','missing_credential'].includes(c.discovery_status)))return {title:'Refresh holdings to discover other tokens',message:'Your discovery connection is now available. This saved analysis predates it and remains partial until you refresh holdings.',action:'refresh'};
    return {title:'Your portfolio is partial',message:'Some token discovery or on-chain checks did not complete. Missing holdings remain unknown. Review the network details below before refreshing holdings.',action:readiness?.discovery_key_available?'refresh':'settings'};
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
      timerLabel: job.state === 'queued' ? 'Waiting' : job.started_at ? 'Elapsed' : 'Since request',
      freshness: !connected ? 'Connection lost. Last recorded state shown.' : quiet ? 'Awaiting a new stage update. Still marked running.' : '',
    };
  }
  function duration(seconds) {
    if (seconds == null) return 'Unknown';
    const h = Math.floor(seconds / 3600), m = Math.floor(seconds % 3600 / 60), s = seconds % 60;
    return (h ? h + 'h ' : '') + m + 'm ' + s + 's';
  }
  const api = { catalog, pageSize, active, jobPresentation, duration, discoveryNotice, coverageGap };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else root.KiraView = api;
})(typeof globalThis !== 'undefined' ? globalThis : this);
