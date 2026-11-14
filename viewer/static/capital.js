'use strict';
// Saved-data views share one local, paged request. No browser provider requests.
const CapitalUI=(()=>{
 const painted=new WeakMap();
 let scopeKey='',signature='',offset=0,epoch=0,page=null,loading=false,loadError='',positionsOpen=false,coverageOpen=false,platformFilter=null;
 const grouped=value=>new Intl.NumberFormat('en-US').format(value);
 const chainName=id=>state?.details?.networks?.find(n=>n.id===id)?.name||'Chain '+id;
 const walletIcon='<svg class="ui-icon" viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="M4 6h14a2 2 0 0 1 2 2v11H4a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h13v2M20 10h-5v5h5"/></svg>';
 const icon=g=>g.logo?`<img class="platform-icon" src="${escapeHTML(g.logo)}" alt="" width="28" height="28">`:`<span class="platform-icon platform-wallet-icon">${walletIcon}</span>`;
 function scope(){
  const folder=typeof FolderUI!=='undefined'?FolderUI.id:null,params=new URLSearchParams({limit:'25',offset:String(offset)});
  if(folder)params.set('folder_id',folder);
  if(platformFilter)params.set('platform',platformFilter);
  if(selectedView==='wallet')params.set('wallet',selectedWallet);
  if(selectedView==='token')params.set('token_id',selectedToken);
  if(selectedView==='network')params.set('chain_id',String(selectedNetwork));
  return {key:[selectedView,folder,selectedWallet,selectedToken,selectedNetwork].join('|'),params};
 }
 function allocationFallback(){
  if(selectedView==='wallet')return currentWallet()?.capital_allocation;
  if(selectedView==='token')return routeData.token?.capital_allocation;
  if(selectedView==='network')return routeData.network?.capital_allocation;
  return (typeof FolderUI!=='undefined'?FolderUI.view():null)?.dashboard.capital_allocation||state?.dashboard.capital_allocation;
 }
 function render(){
  if(!state||!['home','wallet','token','network'].includes(selectedView))return;
  const target=$(selectedView==='home'?'home-view':selectedView==='wallet'?'wallet-view':'detail-view');
  if(!target||target.hidden)return;
  const current=scope();if(current.key!==scopeKey){scopeKey=current.key;signature='';offset=0;page=null;loadError='';positionsOpen=['wallet','token'].includes(selectedView);coverageOpen=false;platformFilter=null;current.params.delete('platform');current.params.set('offset','0');}
  let host=target.querySelector('.capital-panel');
  // The allocation belongs to the summary card: one total, then where it sits.
  if(!host){host=document.createElement('section');host.className='capital-panel';host.setAttribute('aria-label','Allocation');const anchor=target.querySelector('.hero');if(!anchor)return;anchor.append(host);}
  const allocation=page?.allocation||allocationFallback();
  if(!allocation){host.hidden=true;return;}
  const groups=allocation.groups||[],partial=allocation.wallets_checked<allocation.wallet_count||allocation.coverage_gap_count;
  const positive=groups.filter(g=>g.percent>0),comparable=positive.length>1||allocation.position_count>0;
  // A token held only in wallets has nothing to compare. Keep its page quiet.
  if(selectedView==='token'&&!comparable){host.hidden=true;return;}
  host.hidden=false;
  let x=0;
  const bar=positive.length?`<svg class="capital-bar" viewBox="0 0 1000 14" preserveAspectRatio="none" role="img" aria-label="${escapeHTML(positive.map(g=>g.name+' '+g.percent.toFixed(1)+'%').join(', '))}">${positive.map(g=>{const width=Math.max(0,Math.min(100,g.percent))*10,start=x;x+=width;return `<rect x="${start}" y="0" width="${width}" height="14" fill="${escapeHTML(g.color)}" stroke="white" stroke-width="2"><title>${escapeHTML(g.name)}: ${g.percent.toFixed(1)}%</title></rect>`;}).join('')}</svg>`:'<div class="capital-bar capital-bar-empty" aria-label="No priced allocation saved"></div>';
  const rows=groups.map(g=>{
    const detail=(g.position_count?g.position_count+' saved '+(g.position_count===1?'position':'positions'):g.id==='mintclub'?'Bonding-curve tokens':'Direct holdings')+(g.unpriced_count?' · '+g.unpriced_count+' unpriced':'');
    const body=`<svg class="alloc-swatch" viewBox="0 0 10 10" aria-hidden="true"><rect width="10" height="10" rx="3" fill="${escapeHTML(g.color)}"/></svg>${icon(g)}<span class="alloc-name">${escapeHTML(g.name)}${g.position_count?`<small>${g.position_count}</small>`:''}</span><span class="alloc-value">${money(g.value_usd)}</span><span class="alloc-pct">${g.percent==null?'—':g.percent.toFixed(1)+'%'}</span>`;
    return `<li title="${escapeHTML(detail)}">${g.position_count?`<button type="button" class="alloc-item capital-platform-pick" data-platform="${escapeHTML(g.id)}" aria-pressed="${platformFilter===g.id}">${body}</button>`:`<span class="alloc-item">${body}</span>`}</li>`;
  }).join('');
  const currentWallets=selectedView==='wallet'?[currentWallet()]:((typeof FolderUI!=='undefined'?FolderUI.view():null)||state).wallets;
  const keys=new Set(currentWallets.filter(Boolean).map(w=>w.key));
  const scanJobs=typeof jobList!=='undefined'?jobList:typeof activeJobs!=='undefined'?activeJobs:[];
  const running=scanJobs.some(j=>j.operation==='positions.refresh'&&['queued','running'].includes(j.state)&&keys.has(j.input.wallet));
  const refreshLabel=running?'Platform scans in progress':allocation.latest_observed_at?'Refresh positions':'Find platform positions';
  // Scans cover a wallet or the whole portfolio, so they are offered there only.
  const actionable=['home','wallet'].includes(selectedView)&&localSession?.controls&&!state.demo;
  const fresh=allocation.latest_observed_at?'Positions '+stamp(allocation.latest_observed_at):allocation.wallets_checked?'No platform positions recorded':'Platform positions not scanned';
  const chips=(allocation.wallets_checked<allocation.wallet_count?`<span class="chip warn">${allocation.wallets_checked}/${allocation.wallet_count} wallets checked</span>`:'')+(allocation.unpriced_count?`<span class="chip" title="Unpriced assets are excluded. An unknown value is not zero.">${grouped(allocation.unpriced_count)} unpriced</span>`:'')+(allocation.retained_count?`<span class="chip warn" title="Earlier observations kept because the latest check failed.">${grouped(allocation.retained_count)} retained</span>`:'');
  const about='<details class="info-tip"><summary aria-label="About this allocation"></summary><div class="info-pop"><p>Percentages use known recorded value. Each claim counts once. Unpriced assets, debt, unclaimed rewards and exit costs are excluded. Sell-out estimates cover wallet tokens only.</p><p>'+allocation.wallets_checked+' of '+allocation.wallet_count+' wallets checked'+(partial?'. Coverage is incomplete.':'.')+'</p></div></details>';
  const count=page?.matched_count??allocation.position_count;
  const positions=positionRows(page?.positions||[],groups);
  const gapCount=selectedView!=='token'&&page?.coverage_gaps?.length?page.coverage_gap_count:0;
  const gaps=gapCount&&coverageOpen?`<div class="capital-coverage" id="capital-coverage"><p>Saved-claim refresh keeps broad pool discovery separate. Find new positions checks for new deposits.</p><ul>${page.coverage_gaps.slice(0,12).map(c=>`<li><strong>${escapeHTML(c.wallet_name)} · ${escapeHTML(chainName(c.chain_id))}</strong><span>${escapeHTML(c.message||'This source is not fully checked.')}</span></li>`).join('')}</ul>${page.coverage_gap_count>12?'<p>Showing 12 source gaps. The agent can inspect bounded position records for more detail.</p>':''}</div>`:'';
  const markup=`${comparable?bar+'<ul class="capital-legend">'+rows+'</ul>':''}<div class="capital-footer"><div class="alloc-fresh"><span class="alloc-dot" data-state="${partial?'partial':'complete'}" aria-hidden="true"></span><span>${escapeHTML(fresh)}</span>${about}</div>${chips}${gapCount?`<button type="button" class="chip warn capital-gaps" aria-expanded="${coverageOpen}" aria-controls="capital-coverage">${grouped(gapCount)} coverage gaps</button>`:''}${actionable?`<div class="capital-refresh-actions"><button type="button" class="quiet-button capital-refresh" ${running?'disabled':''}>${refreshLabel}</button>${allocation.latest_observed_at?`<button type="button" class="text-button capital-discover" ${running?'disabled':''}>Find new</button>`:''}</div>`:''}</div><div class="capital-action-status" role="status" aria-live="polite">${escapeHTML(loadError)}${loadError?'<button type="button" class="text-button capital-retry">Retry saved view</button>':''}</div>${count||loading&&!page?`<details class="capital-positions" ${positionsOpen?'open':''}><summary>Positions <span class="count-badge">${grouped(count)}</span>${platformFilter?'<span class="chip">'+escapeHTML(groups.find(g=>g.id===platformFilter)?.name||platformFilter)+'</span>':''}</summary>${platformFilter?'<button type="button" class="text-button capital-clear-platform">Show all platforms</button>':''}${positions?'<ul class="capital-position-list">'+positions+'</ul>':`<p class="capital-empty">${loading?'Loading saved positions…':'No positions recorded in this view. Incomplete checks remain unknown.'}</p>`}<div class="capital-pages" ${!page||page.matched_count<=page.positions.length&&!offset?'hidden':''}><span>${offset+1}–${offset+(page?.positions.length||0)} of ${page?.matched_count||0}</span><button type="button" class="icon-button capital-prev" aria-label="Previous positions" ${!offset||loading?'disabled':''}>‹</button><button type="button" class="icon-button capital-next" aria-label="More positions" ${!page||page.next_offset===null||loading?'disabled':''}>›</button></div></details>`:''}${gaps}`;
  if(painted.get(host)===markup){if(!document.hidden&&signature!==state.data_revision+'|'+current.params.toString()&&!loading)load();return;}
  host.innerHTML=markup;painted.set(host,markup);
  for(const button of host.querySelectorAll('[data-platform]'))button.addEventListener('click',()=>{platformFilter=platformFilter===button.dataset.platform?null:button.dataset.platform;positionsOpen=true;offset=0;load(true);});
  host.querySelector('.capital-clear-platform')?.addEventListener('click',()=>{platformFilter=null;offset=0;load(true);});
  host.querySelector('.capital-positions')?.addEventListener('toggle',event=>{positionsOpen=event.target.open;});
  host.querySelector('.capital-retry')?.addEventListener('click',()=>load(true));
  host.querySelector('.capital-gaps')?.addEventListener('click',()=>{toggleCoverage();host.querySelector('.capital-gaps')?.focus({preventScroll:true});});
  host.querySelector('.capital-refresh')?.addEventListener('click',()=>refresh(!allocation.latest_observed_at));
  host.querySelector('.capital-discover')?.addEventListener('click',()=>refresh(true));
  host.querySelector('.capital-prev')?.addEventListener('click',()=>{offset=Math.max(0,offset-25);load(true);});
  host.querySelector('.capital-next')?.addEventListener('click',()=>{if(page?.next_offset!=null){offset=page.next_offset;load(true);}});
  if(!document.hidden&&signature!==state.data_revision+'|'+current.params.toString()&&!loading)load();
 }
 function toggleCoverage(){coverageOpen=!coverageOpen;render();}
 function positionRows(positions,groups){
  return positions.map(p=>{
   const platform=groups.find(g=>g.id===p.platform)||p.platform_info||{name:p.platform},pair=p.assets.map(a=>a.symbol).join(' / ');
   const priced=p.assets.map(a=>a.price?.observed_at).filter(Boolean).sort()[0];
   const note=(p.exit_note||'Recorded principal; gas excluded.')+(priced?' Saved prices '+stamp(priced)+'.':'')+' Observed '+stamp(p.observed_at)+'.';
   const flags=(p.custody_platform?'<span class="chip">Staked</span>':'')+(p.retained?'<span class="chip warn" title="Earlier observation kept because the latest check failed.">Retained</span>':'')+(p.included_in_totals===false?'<span class="chip">Not in totals</span>':'');
   return `<li class="capital-position" title="${escapeHTML(note)}"><span class="pos-main">${icon(platform)}<span class="pos-label"><strong>${escapeHTML(pair||p.label)}</strong><small>${escapeHTML(platform.name)}${p.version?' · '+escapeHTML(p.version):''}</small></span>${flags}</span><span class="pos-assets">${p.assets.map(a=>`<a href="${tokenHref(p.chain_id+':'+a.address)}">${escapeHTML(quantity(a.amount))} ${escapeHTML(a.symbol)}</a>`).join('<span aria-hidden="true">+</span>')}</span><span class="pos-where">${selectedView==='wallet'?'':`<a href="${FolderUI.path('wallet/'+p.wallet)}">${escapeHTML(p.wallet_name)}</a>`}<small>${escapeHTML(chainName(p.chain_id))}</small></span><strong class="pos-value">${money(p.value_usd)}</strong><a class="pos-source" href="${safeURL(p.source_url)}" target="_blank" rel="noopener noreferrer" aria-label="View source for ${escapeHTML(pair||p.label)}" title="View source">↗</a></li>`;
  }).join('');
 }
 async function load(force=false){
  const current=scope(),requested=current.key,version=state.data_revision+'|'+current.params.toString();
  if(loading&&!force||!force&&signature===version)return;
  const ticket=++epoch;loading=true;
  try{const response=await localAPI('/api/positions?'+current.params);if(ticket!==epoch||requested!==scope().key)return;if(response.data_revision&&response.data_revision!==state.data_revision){signature=version;page=null;await poll();return;}page=response;signature=version;loadError='';}
  catch(error){if(ticket===epoch){signature=version;loadError=error.message;}}
  finally{if(ticket===epoch){loading=false;render();}}
 }
 async function refresh(discover){
  const button=document.querySelector('.capital-panel .capital-refresh');if(!button)return;
  button.disabled=true;const status=button.closest('.capital-panel').querySelector('.capital-action-status');
  try{
   if(setupReadiness?.discovery_key_available!==true){await openDataConnections();return;}
   const folder=typeof FolderUI!=='undefined'?FolderUI.id:null;
   const receipt=selectedView==='wallet'?await submitOperation('positions.refresh',{wallet:selectedWallet,...(discover?{discover:true}:{})}):await submitOperation('portfolio.positionsRefresh',{...(folder?{folder_id:folder}:{}),...(discover?{discover:true}:{})});
   const count=receipt.jobs?.length??1;status.textContent=count+' wallet '+(count===1?'scan':'scans')+' queued. Follow Activity.';
  }catch(error){status.textContent=error.message;}
  finally{button.disabled=false;}
 }
 return {render};
})();
