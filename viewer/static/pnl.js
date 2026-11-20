'use strict';

const KiraPnl = (() => {
  const day = raw => new Date(raw).toLocaleDateString('en-US',{month:'short',day:'numeric',year:'numeric'});
  function signed(raw) {
    if (raw == null) return 'Pending';
    const value = Number(raw);
    if (value && Math.abs(value) < .01) return (value > 0 ? '+' : '−') + '< $0.01';
    return (value > 0 ? '+' : '') + money(value);
  }
  const tone = raw => raw == null ? '' : Number(raw)>0?'pnl-gain':Number(raw)<0?'pnl-loss':'';
  const metric = (label,value) => '<div><dt>'+escapeHTML(label)+'</dt><dd>'+money(value==null?null:Number(value))+'</dd></div>';
  const tableLimit = 20;
  const limits = new Map();
  let walletPage=null;

  const dateRange = (from,to) => day(from) === day(to) ? day(from) : day(from) + ' to ' + day(to);
  function amount(raw) {
    return '<span class="pnl-number ' + tone(raw) + '">' + escapeHTML(signed(raw)) + '</span>';
  }

  function listValue(asset) {
    if (asset.environment !== 'mainnet') return '';
    const value = asset.pnl?.unrealized;
    const when = asset.pnl?.as_of ? ' · ' + dateRange(asset.pnl.as_of,asset.pnl.latest_as_of || asset.pnl.as_of) : '';
    return '<span class="pnl-inline" title="' + escapeHTML('Unrealized P&L' + when) + '">Unrealized ' +
      (value == null ? '—' : amount(value)) + '</span>';
  }

  function bar(label,value,max,variant) {
    return '<div class="pnl-bar '+variant+'"><div><span>'+label+'</span><strong>'+money(Number(value))+
      '</strong></div><progress aria-hidden="true" max="'+max+'" value="'+Number(value)+'"></progress></div>';
  }

  function capitalChart(p) {
    if (p.pnl_usd == null) return '';
    const capital=p.capital_in_usd, returned=p.value_and_withdrawals_usd;
    if (capital == null || returned == null) return '';
    const max=Math.max(Number(capital),Number(returned)) || 1;
    return '<div class="pnl-chart" role="group" aria-label="Capital comparison">'+
      bar(Number(p.opening_usd) ? 'Opening value + deposits' : 'Deposits',capital,max,'pnl-basis')+
      bar(Number(p.withdrawals_usd) ? 'Value + withdrawals' : 'Portfolio value',returned,max,tone(p.pnl_usd))+'</div>';
  }

  function component(label,value,max) {
    const scale = value == null ? '' : '<div class="pnl-axis" aria-hidden="true"><progress class="pnl-negative" max="'+max+'" value="'+
      Math.max(0,-Number(value))+'"></progress><progress max="'+max+'" value="'+Math.max(0,Number(value))+'"></progress></div>';
    return '<div class="pnl-component"><div><span>'+label+'</span>'+amount(value)+'</div>'+scale+'</div>';
  }

  function tokenPanel(token) {
    if (token.environment !== 'mainnet') return '';
    const p=token.pnl, rows=token.pnl_assets || [];
    if (!p) return '<section class="pnl-panel pnl-empty"><div><h2>Token performance</h2><p>No P&amp;L analysis saved for this token in this scope.</p></div></section>';
    const max=Math.max(Math.abs(Number(p.realized)),Math.abs(Number(p.unrealized))) || 1;
    const coverage=p.reporting_wallets+(p.reporting_wallets === 1 ? ' reporting wallet' : ' reporting wallets');
    const missing=p.missing_holders ? '<p class="pnl-notice">Awaiting analysis for '+p.missing_holders+(p.missing_holders === 1 ? ' holder.' : ' holders.')+'</p>' : '';
    const summary='<div class="pnl-layout"><div class="pnl-lead"><h2>Trading P&amp;L</h2><strong class="pnl-amount">'+amount(p.total)+
      '</strong><span class="pnl-caption">'+escapeHTML(coverage)+'</span></div><div class="pnl-chart" role="group" aria-label="Trading P&amp;L components">'+
      component('Realized',p.realized,max)+component('Unrealized',p.unrealized,max)+'</div></div>';
    return '<section class="pnl-panel pnl-token-detail" aria-label="Token performance">'+summary+missing+
      '<div class="pnl-section-head"><h3>By wallet</h3><span>Valued '+escapeHTML(dateRange(p.as_of,p.latest_as_of))+'</span></div>'+
      assetTable(rows,token.id,true)+'</section>';
  }

  function assetTable(rows, scope, token=false, total=rows?.length||0) {
    if (!rows?.length) return '';
    const limit=limits.get(scope)||tableLimit;
    const head=token?'Wallet':'Token';
    const cells=rows.slice(0,limit).map(r=>{
      const title=token?r.wallet:r.symbol;
      const secondary=token?day(r.as_of):networkName(r.chain_id)+' · '+(r.asset==='native'?'Native':shortAddress(r.asset.split('#')[0])+(r.asset.includes('#')?' #'+r.asset.split('#')[1]:''));
      const result=v=>v==null?'—':amount(v);
      return '<tr><th scope="row"><strong>'+escapeHTML(title)+'</strong><small>'+escapeHTML(secondary)+'</small></th>'+
        '<td data-label="Quantity">'+quantity(r.quantity)+'</td><td data-label="Avg. cost">'+(r.average_cost==null?'—':unitPrice(Number(r.average_cost)))+
        '</td><td data-label="Realized">'+result(r.realized)+'</td><td data-label="Unrealized">'+result(r.unrealized)+'</td></tr>';
    }).join('');
    const more=total>limit?'<button type="button" class="text-button" data-pnl-more="'+escapeHTML(scope)+'">Show more ('+(total-limit)+')</button>':'';
    return '<div class="pnl-scroll"><table class="pnl-table" aria-label="Token cost and returns"><thead><tr><th>'+head+'</th><th>Quantity</th><th>Avg. cost</th><th>Realized</th><th>Unrealized</th></tr></thead><tbody>'+cells+'</tbody></table></div>'+more;
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
    const at=dateRange(p.as_of,p.latest_as_of);
    const networks=p.chain_ids.map(networkName).join(', ');
    const coverage=p.analyzed_wallets+' of '+p.wallet_count+(p.wallet_count===1?' wallet':' wallets')+' · '+networks;
    const issues=[];
    if(p.analyzed_wallets<p.wallet_count)issues.push('Wallet research missing');
    if(p.partial_chains)issues.push('Transaction history incomplete');
    if(p.unclassified_count)issues.push(p.unclassified_count+' unclassified transactions');
    if(p.pending_bridges)issues.push('Bridge transfer awaiting its other leg');
    if(p.balance_gaps)issues.push(p.balance_gaps+' unmatched balances');
    if(p.unmatched_transfers)issues.push('Internal transfers need matching');
    if(p.value_usd==null||p.deposits_usd==null||p.withdrawals_usd==null||p.opening_usd==null)issues.push('USD valuation incomplete');
    const opening=p.first_deposit?'':metric('Opening value',p.opening_usd);
    const visual=p.pnl_usd==null?'<div class="pnl-chart pnl-coverage"><span>Wallet analysis</span><strong>'+p.analyzed_wallets+' of '+p.wallet_count+'</strong><progress aria-label="Wallets analyzed" value="'+p.analyzed_wallets+'" max="'+p.wallet_count+'"></progress></div>':capitalChart(p);
    node.innerHTML='<div class="pnl-layout"><div class="pnl-lead"><h2>'+title+'</h2><strong class="pnl-amount">'+amount(p.pnl_usd)+'</strong><span class="pnl-caption">From '+escapeHTML(day(p.started_at))+'</span></div>'+visual+'</div>'+
      (issues.length?'<p class="pnl-notice">'+escapeHTML(issues.join(' · '))+'</p>':'')+
      '<div class="pnl-foot"><span>'+escapeHTML(coverage)+'</span><span>Valued '+escapeHTML(at)+'</span></div>'+
      '<details'+(opened?' open':'')+'><summary>Calculation details</summary><dl class="pnl-metrics">'+metric('Analyzed value',p.value_usd)+metric('Deposits',p.deposits_usd)+metric('Withdrawals',p.withdrawals_usd)+opening+'</dl>'+action+'</details>'+
      (rows?.length?'<div class="pnl-section-head"><h3>Token performance</h3><span>'+rowCount+(rowCount===1?' token':' tokens')+'</span></div>'+assetTable(rows,scope,false,rowCount):'');

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
  return {render,tokenPanel,listValue,amount};
})();
