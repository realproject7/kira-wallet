'use strict';

const KiraPnl = (() => {
  const day = raw => new Date(raw).toLocaleDateString('en-US',{month:'short',day:'numeric',year:'numeric'});
  const signed = raw => raw == null ? 'Pending' : (Number(raw)>0?'+':'') + money(Number(raw));
  const tone = raw => raw == null ? '' : Number(raw)>0?'pnl-gain':Number(raw)<0?'pnl-loss':'';
  const metric = (label,value) => '<div><dt>'+escapeHTML(label)+'</dt><dd>'+money(value==null?null:Number(value))+'</dd></div>';
  const tableLimit = 20;
  const limits = new Map();
  let walletPage=null;

  function assetTable(rows, scope, token=false, total=rows?.length||0) {
    if (!rows?.length) return '';
    const limit=limits.get(scope)||tableLimit;
    const head=token?'Wallet':'Token';
    const cells=rows.slice(0,limit).map(r=>{
      const title=token?r.wallet:r.symbol;
      const secondary=token?day(r.as_of):networkName(r.chain_id)+' · '+(r.asset==='native'?'Native':shortAddress(r.asset.split('#')[0])+(r.asset.includes('#')?' #'+r.asset.split('#')[1]:''));
      const usd=v=>v==null?'—':signed(v);
      return '<tr><th scope="row"><strong>'+escapeHTML(title)+'</strong><small>'+escapeHTML(secondary)+'</small></th><td>'+quantity(r.quantity)+'</td><td>'+(r.average_cost==null?'—':unitPrice(Number(r.average_cost)))+'</td><td class="'+tone(r.realized)+'">'+usd(r.realized)+'</td><td class="'+tone(r.unrealized)+'">'+usd(r.unrealized)+'</td></tr>';
    }).join('');
    const more=total>limit?'<button type="button" class="text-button" data-pnl-more="'+escapeHTML(scope)+'">Show more ('+(total-limit)+')</button>':'';
    return '<div class="pnl-scroll" role="region" aria-label="Token cost and returns" tabindex="0"><table class="pnl-table"><thead><tr><th>'+head+'</th><th>Quantity</th><th>Avg. cost</th><th>Realized</th><th>Unrealized</th></tr></thead><tbody>'+cells+'</tbody></table></div>'+more;
  }

  function render(id, result, scope, rows, visible) {
    const node=document.getElementById(id);
    node.hidden=!visible;
    if (!visible) return;
    let rowCount=rows?.length||0;
    if (id==='wallet-pnl' && rows) {
      const revision=routeData.wallet?.data_revision;
      if(walletPage?.scope!==scope || walletPage.revision!==revision){
        walletPage={scope,revision,rows:[...rows]};
        limits.delete(scope);
      }
      rows=walletPage.rows;
      rowCount=routeData.wallet?.pnl_asset_count||rows.length;
    }
    const opened=node.dataset.scope===scope && node.querySelector('details')?.open;
    node.dataset.scope=scope;
    const action='<button type="button" class="quiet-button pnl-copy" data-pnl-copy="'+escapeHTML(scope)+'">Copy agent request</button>';
    if (!result) {
      node.innerHTML='<div class="pnl-empty"><div><h2>Profit &amp; loss</h2><p>Ask your agent to trace deposits and trades for this scope.</p></div>'+action+'</div>';
      return;
    }
    const p=result;
    const title=p.first_deposit?'P&L since first deposit':'P&L since tracking began';
    const at=p.as_of===p.latest_as_of?day(p.as_of):day(p.as_of)+' to '+day(p.latest_as_of);
    const networks=p.chain_ids.map(networkName).join(', ');
    const coverage=p.analyzed_wallets+' of '+p.wallet_count+(p.wallet_count===1?' wallet':' wallets')+' · Analyzed on '+networks;
    const issues=[];
    if(p.analyzed_wallets<p.wallet_count)issues.push('Wallet research missing');
    if(p.partial_chains)issues.push('Transaction history incomplete');
    if(p.unclassified_count)issues.push(p.unclassified_count+' unclassified transactions');
    if(p.pending_bridges)issues.push('Bridge transfer awaiting its other leg');
    if(p.balance_gaps)issues.push(p.balance_gaps+' unmatched balances');
    if(p.unmatched_transfers)issues.push('Internal transfers need matching');
    if(p.value_usd==null||p.deposits_usd==null||p.withdrawals_usd==null||p.opening_usd==null)issues.push('USD valuation incomplete');
    const dates='From '+day(p.started_at)+' · Valued '+at;
    const opening=p.first_deposit?'':metric('Opening value',p.opening_usd);
    node.innerHTML='<div class="pnl-heading"><div><h2>'+title+'</h2><strong class="pnl-amount '+tone(p.pnl_usd)+'">'+signed(p.pnl_usd)+'</strong></div><div class="pnl-meta"><span>'+escapeHTML(coverage)+'</span><span>'+escapeHTML(dates)+'</span></div></div>'+
      (issues.length?'<p class="pnl-notice">'+escapeHTML(issues.join(' · '))+'</p>':'')+
      '<details'+(opened?' open':'')+'><summary>Calculation details</summary><dl class="pnl-metrics">'+metric('Analyzed value',p.value_usd)+metric('Deposits',p.deposits_usd)+metric('Withdrawals',p.withdrawals_usd)+opening+'</dl>'+
      (rows?.length?'<h3>Token performance</h3>'+assetTable(rows,scope,false,rowCount):'')+action+'</details>';
  }

  document.addEventListener('click',async event=>{
    const more=event.target.closest('[data-pnl-more]');
    if(more){
      const scope=more.dataset.pnlMore;
      if(selectedView==='wallet' && walletPage?.scope===scope){
        const current=walletPage;
        more.disabled=true;
        try {
          const page=await readAPI(queryPath('/api/pnl',{wallet:scope,offset:current.rows.length,limit:tableLimit}));
          if(current!==walletPage || selectedView!=='wallet' || scope!==selectedWallet)return;
          const version=rows=>rows.map(r=>r.chain_id+'@'+r.revision).sort().join(',');
          if(version(page.chains)!==version(routeData.wallet?.pnl_chains||[])){await loadRoute(true);return;}
          current.rows.push(...page.assets);
        } catch {
          more.disabled=false;
          more.textContent='Retry loading token performance';
          return;
        }
      }
      limits.set(scope,(limits.get(scope)||tableLimit)+tableLimit);
      if(selectedView==='token')renderDetail();else renderWallet();
      return;
    }
    const button=event.target.closest('[data-pnl-copy]');
    if(!button)return;
    const scope=button.dataset.pnlCopy;
    const target=scope==='all'?'all registered wallets':scope.startsWith('folder/')?'registered wallets in folder '+scope.slice(7):'registered wallet '+scope;
    const request='Update deposit-based USD P&L for '+target+' in Kira. Read kira skill and pnl_read first. Reuse saved evidence, resume after the last finalized block and publish reconciled transactions and balances with pnl_publish. Keep missing coverage explicit.';
    try { await navigator.clipboard.writeText(request); button.textContent='Copied'; }
    catch { window.prompt('Copy this request to your agent',request); }
  });
  return {render,assetTable,signed};
})();
