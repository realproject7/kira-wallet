'use strict';

const KiraPnl = (() => {
  const day = raw => new Date(raw).toLocaleDateString('en-US',{month:'short',day:'numeric',year:'numeric',timeZone:'UTC'});
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

  function dateRange(from,to) {
    if(from===to)return day(from);
    if(day(from)!==day(to))return day(from)+' to '+day(to);
    const utcTime=value=>new Date(value).toISOString().slice(11,19);
    return day(from)+' · '+utcTime(from)+' to '+utcTime(to)+' UTC';
  }
  function amount(raw) {
    return '<span class="pnl-number ' + tone(raw) + '">' + escapeHTML(signed(raw)) + '</span>';
  }

  function listValue(asset) {
    const value = asset.pnl?.unrealized;
    if (asset.environment !== 'mainnet' || asset.included_in_totals === false || value == null) return '';
    const when = asset.pnl?.as_of ? ' · ' + dateRange(asset.pnl.as_of,asset.pnl.latest_as_of || asset.pnl.as_of) : '';
    return '<span class="pnl-inline" title="' + escapeHTML('Unrealized P&L' + when) + '">Unrealized ' + amount(value) + '</span>';
  }

  const axisMoney = new Intl.NumberFormat('en-US', {
    style:'currency', currency:'USD', notation:'compact', maximumSignificantDigits:3
  });

  // All three steps share a dollar scale, including zero and any negative balance.
  function waterfall(title, steps) {
    const values=steps.flatMap(step=>[step.start,step.end]);
    const min=Math.min(0,...values), max=Math.max(0,...values);
    const target=(max-min)/3 || 1;
    const magnitude=10 ** Math.floor(Math.log10(target));
    const interval=[1,2,2.5,5,10].find(n=>n*magnitude>=target)*magnitude;
    const low=Math.floor(min/interval), high=Math.ceil(max/interval);
    const position=value=>high===low?50:100*(value/interval-low)/(high-low);
    const rules=[];
    for(let n=low;n<=high;n++){
      rules.push(`<div class="pnl-rule${n===0?' pnl-zero':''}" data-pnl-y="${position(n*interval)}"><span>${escapeHTML(axisMoney.format(n*interval))}</span></div>`);
    }
    const bars=steps.map((step,index)=>{
      const a=position(step.start), b=position(step.end);
      const connector=index===steps.length-1?'':`<i class="pnl-connector" data-pnl-y="${b}"></i>`;
      return `<div class="pnl-column">${connector}<i class="pnl-block ${step.style}" data-pnl-y="${Math.min(a,b)}" data-pnl-height="${Math.abs(b-a)}"></i></div>`;
    }).join('');
    const legend=steps.map(step=>`<div><dt>${escapeHTML(step.label)}</dt><dd>${step.signed?amount(step.raw):escapeHTML(money(Number(step.raw)))}</dd></div>`).join('');
    return `<figure class="pnl-chart"><figcaption>${title}<span>USD</span></figcaption><div class="pnl-plot" aria-hidden="true">${rules.join('')}<div class="pnl-columns">${bars}</div></div><dl class="pnl-key">${legend}</dl></figure>`;
  }

  function paintChart(node) {
    for(const mark of node.querySelectorAll('[data-pnl-y]')){
      mark.style.bottom=mark.dataset.pnlY+'%';
      if(mark.dataset.pnlHeight!==undefined)mark.style.height=mark.dataset.pnlHeight+'%';
    }
  }

  function capitalChart(p) {
    const capital=p.capital_in_usd, returned=p.value_and_withdrawals_usd;
    if(capital==null || returned==null || p.pnl_usd==null)return '';
    const start=Number(capital), end=Number(returned);
    return waterfall('Capital movement',[
      {label:Number(p.opening_usd)?'Opening + deposits':'Deposits',start:0,end:start,raw:capital,style:'pnl-base'},
      {label:'Net P&L',start,end,raw:p.pnl_usd,signed:true,style:'pnl-change '+tone(p.pnl_usd)},
      {label:Number(p.withdrawals_usd)?'Value + withdrawals':'Portfolio value',start:0,end,raw:returned,style:'pnl-total'}
    ]);
  }

  function tradingChart(p) {
    const realized=Number(p.realized), total=Number(p.total);
    return waterfall('Trading breakdown',[
      {label:'Realized',start:0,end:realized,raw:p.realized,signed:true,style:'pnl-base '+tone(p.realized)},
      {label:'Unrealized',start:realized,end:total,raw:p.unrealized,signed:true,style:'pnl-change '+tone(p.unrealized)},
      {label:'Total P&L',start:0,end:total,raw:p.total,signed:true,style:'pnl-total '+tone(p.total)}
    ]);
  }

  function capitalChange(p) {
    if(p.pnl_usd==null || !(Number(p.capital_in_usd)>0))return '';
    const percent=Number(p.pnl_usd)/Number(p.capital_in_usd)*100;
    const digits=percent && Math.abs(percent)<.01?'&lt;0.01':Math.abs(percent).toLocaleString('en-US',{maximumFractionDigits:2});
    const sign=percent>0?'+':percent<0?'−':'';
    return `<div class="pnl-relative"><span class="pnl-chip ${tone(p.pnl_usd)}">${sign}${digits}%</span><span>of capital in</span></div>`;
  }

  function disclosure(content, {title, opened=false}={}) {
    const label=title?'<span class="pnl-compact-title">'+escapeHTML(title)+'</span><span class="pnl-status">Pending</span><span class="pnl-details-label">Details</span>':'Calculation details';
    return '<details class="pnl-disclosure'+(title?' pnl-disclosure-compact':'')+'"'+(opened?' open':'')+'><summary>'+label+'</summary><div class="pnl-details-body">'+content+'</div></details>';
  }

  function tokenPanel(token) {
    if (token.environment !== 'mainnet') return '';
    const p=token.pnl, rows=token.pnl_assets || [];
    if (!p || !rows.length || token.included_in_totals === false) return '';
    const pending=p.total==null;
    const coverage=rows.length+(rows.length===1?' wallet':' wallets')+' with returns';
    const issues=[];
    if(p.missing_holders)issues.push('Awaiting analysis for '+p.missing_holders+(p.missing_holders===1?' holder':' holders'));
    if(p.valuation_dates_aligned===false)issues.push('Wallet reports have different valuation cutoffs');
    if(pending && !issues.length)issues.push('Some wallet returns are incomplete');
    const dates='Valued '+dateRange(p.as_of,p.latest_as_of);
    const details='<p class="pnl-caption">'+escapeHTML([coverage,dates,...issues].join(' · '))+'</p>';
    const summary=pending?disclosure(details,{title:'Trading P&L'}):
      '<div class="pnl-layout"><div class="pnl-lead"><h2>Trading P&amp;L</h2><strong class="pnl-amount">'+amount(p.total)+
      '</strong><span class="pnl-caption">'+escapeHTML(coverage)+'</span></div>'+tradingChart(p)+'</div>';
    return '<section class="pnl-panel pnl-token-detail'+(pending?' pnl-compact-panel':'')+'" aria-label="Token performance">'+summary+
      '<div class="pnl-section-head"><h3>By wallet</h3><span>'+escapeHTML(dates)+'</span></div>'+assetTable(rows,token.id,true)+'</section>';
  }

  function assetTable(rows, scope, token=false, total=rows?.length||0) {
    if (!rows?.length) return '';
    const limit=limits.get(scope)||tableLimit;
    const head=token?'Wallet':'Token';
    const cells=rows.slice(0,limit).map(r=>{
      const title=token?r.wallet:r.symbol;
      const secondary=token?day(r.as_of):networkName(r.chain_id)+' · '+(r.asset==='native'?'Native':shortAddress(r.asset.split('#')[0])+(r.asset.includes('#')?' #'+r.asset.split('#')[1]:''));
      const result=v=>v==null?'—':amount(v);
      const label=!token?'<a href="'+escapeHTML(tokenHref(r.chain_id+':'+r.asset))+'">'+escapeHTML(title)+'</a>':escapeHTML(title);
      const observed=r.quantity==null?'—':quantity(r.quantity);
      return '<tr><th scope="row"><strong>'+label+'</strong><small>'+escapeHTML(secondary)+'</small></th>'+
        '<td data-label="Quantity">'+observed+'</td><td data-label="Avg. cost">'+(r.average_cost==null?'—':unitPrice(Number(r.average_cost)))+
        '</td><td data-label="Realized">'+result(r.realized)+'</td><td data-label="Unrealized">'+result(r.unrealized)+'</td></tr>';
    }).join('');
    const more=total>limit?'<button type="button" class="text-button" data-pnl-more="'+escapeHTML(scope)+'">Show more ('+(total-limit)+')</button>':'';
    return '<div class="pnl-scroll"><table class="pnl-table" aria-label="Token cost and returns"><thead><tr><th>'+head+'</th><th>Quantity</th><th>Avg. cost</th><th>Realized</th><th>Unrealized</th></tr></thead><tbody>'+cells+'</tbody></table></div>'+more;
  }

  function render(id, result, scope, rows, visible) {
    const node=document.getElementById(id);
    node.hidden=!visible;
    if (!visible) return;
    node.classList.toggle('pnl-compact-panel',result?.pnl_usd==null);
    let rowCount=rows?.length||0;
    if (id==='wallet-pnl' && rows) {
      const revision=routeData.wallet?.data_revision;
      if(walletPage?.scope!==scope || walletPage.revision!==revision){
        walletPage={scope,revision,rows:[...rows]};
        limits.delete(scope);
      }
      rows=walletPage.rows;
      rowCount=routeData.wallet?.pnl_asset_count??rows.length;
    }
    const opened=node.dataset.scope===scope && node.querySelector('.pnl-disclosure')?.open;
    node.dataset.scope=scope;
    const action='<button type="button" class="quiet-button pnl-copy" data-pnl-copy="'+escapeHTML(scope)+'">Copy agent request</button>';
    if (!result) {
      node.innerHTML=disclosure('<p class="pnl-caption">Ask your agent to trace deposits and trades for this scope.</p>'+action,{title:'Profit & loss',opened});
      return;
    }
    const p=result;
    const title=p.first_deposit?'P&L since first deposit':'P&L since tracking began';
    const at=dateRange(p.as_of,p.latest_as_of);
    const networks=p.chain_ids.map(networkName).join(', ');
    const coverage=p.analyzed_wallets+' of '+p.wallet_count+(p.wallet_count===1?' wallet':' wallets')+' · '+networks;
    const issues=[];
    if(p.analyzed_wallets<p.wallet_count)issues.push('Wallet research missing');
    if(p.missing_chain_count)issues.push('Missing chain reports: '+p.missing_chain_ids.map(networkName).join(', '));
    if(p.behind_chain_count)issues.push('Holdings were observed after the P&L cutoff');
    if(p.valuation_dates_aligned===false)issues.push('Reports have different valuation cutoffs');
    if(p.partial_chains)issues.push('Transaction history incomplete');
    if(p.unclassified_count)issues.push(p.unclassified_count+' unclassified transactions');
    if(p.pending_bridges)issues.push('Bridge transfer awaiting its other leg');
    if(p.balance_gaps)issues.push(p.balance_gaps+' unmatched balances');
    if(p.unmatched_transfers)issues.push('Internal transfers need matching');
    if(p.value_usd==null||p.deposits_usd==null||p.withdrawals_usd==null||p.opening_usd==null)issues.push('USD valuation incomplete');
    const opening=p.first_deposit?'':metric('Opening value',p.opening_usd);
    const chains=id==='wallet-pnl' && p.pnl_usd==null ? (routeData.wallet?.pnl_chains || []).filter(r=>r.pnl_usd!=null) : [];
    const breakdown=chains.length?'<div class="pnl-section-head"><h3>By network</h3></div><dl class="pnl-components">'+chains.map(r=>
      '<div><dt>'+escapeHTML(networkName(r.chain_id))+' · '+escapeHTML(day(r.as_of))+'</dt><dd>'+amount(r.pnl_usd)+'</dd></div>').join('')+'</dl>':'';
    const pending=p.pnl_usd==null;
    const details='<div class="pnl-foot"><span>'+escapeHTML(coverage)+'</span><span>Valued '+escapeHTML(at)+'</span></div>'+
      (pending?'<p class="pnl-caption">From '+escapeHTML(day(p.started_at))+'</p>':'')+
      (issues.length?'<p class="pnl-caption">'+escapeHTML(issues.join(' · '))+'</p>':'')+
      '<dl class="pnl-metrics">'+metric('Analyzed value',p.value_usd)+metric('Reported deposits',p.deposits_usd)+metric('Reported withdrawals',p.withdrawals_usd)+opening+'</dl>'+breakdown+action;
    node.innerHTML=(pending?'':'<div class="pnl-layout"><div class="pnl-lead"><h2>'+title+'</h2><strong class="pnl-amount">'+amount(p.pnl_usd)+'</strong>'+capitalChange(p)+'<span class="pnl-caption">From '+escapeHTML(day(p.started_at))+'</span></div>'+capitalChart(p)+'</div>')+
      disclosure(details,{title:pending?title:undefined,opened})+
      (rows?.length?'<div class="pnl-section-head"><h3>Token performance</h3><span>'+rowCount+(rowCount===1?' token':' tokens')+'</span></div>'+assetTable(rows,scope,false,rowCount):'');
    paintChart(node);
  }

  document.addEventListener('click',async event=>{
    const more=event.target.closest('[data-pnl-more]');
    if(more){
      const scope=more.dataset.pnlMore;
      if(selectedView==='wallet' && walletPage?.scope===scope){
        const current=walletPage;
        more.disabled=true;
        try {
          const page=await readAPI(queryPath('/api/pnl',{wallet:scope,offset:current.rows.length,limit:tableLimit,pnl_view:'performance'}));
          if(current!==walletPage || selectedView!=='wallet' || scope!==selectedWallet)return;
          if(page.data_revision!==current.revision){await loadRoute(true);return;}
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
  return {render,tokenPanel,listValue,amount,paintChart};
})();
