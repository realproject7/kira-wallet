'use strict';
// Saved-data views share one local, paged request. No browser provider requests.
const CapitalUI=(()=>{
 const painted=new WeakMap();
 let scopeKey='',signature='',offset=0,epoch=0,page=null,loading=false,loadError='',positionsOpen=false,platformFilter=null;
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
  if(!state||!['home','wallet','token','network','tokens'].includes(selectedView))return;
  const target=$(selectedView==='home'?'home-view':selectedView==='wallet'?'wallet-view':selectedView==='tokens'?'tokens-view':'detail-view');
  if(!target||target.hidden)return;
  const current=scope();if(current.key!==scopeKey){scopeKey=current.key;signature='';offset=0;page=null;loadError='';positionsOpen=['wallet','token'].includes(selectedView);platformFilter=null;current.params.delete('platform');current.params.set('offset','0');}
  let host=target.querySelector('.capital-panel');
  if(!host){host=document.createElement('section');host.className='capital-panel';const anchor=target.querySelector('.detail-metrics,#home-summary,.portfolio-summary,.token-page-heading');if(!anchor)return;anchor.insertAdjacentElement('afterend',host);}
  const allocation=page?.allocation||allocationFallback();
  if(!allocation){host.hidden=true;return;}host.hidden=false;
  const groups=allocation.groups||[],total=allocation.known_value_usd,partial=allocation.wallets_checked<allocation.wallet_count||allocation.coverage_gap_count;
  const positive=groups.filter(g=>g.percent>0);
  let x=0;
  const bar=positive.length?`<svg class="capital-bar" viewBox="0 0 1000 22" preserveAspectRatio="none" role="img" aria-label="${escapeHTML(positive.map(g=>g.name+' '+g.percent.toFixed(1)+'%').join(', '))}">${positive.map(g=>{const width=Math.max(0,Math.min(100,g.percent))*10,start=x;x+=width;return `<rect x="${start}" y="0" width="${width}" height="22" fill="${escapeHTML(g.color)}" stroke="white" stroke-width="2"><title>${escapeHTML(g.name)}: ${g.percent.toFixed(1)}%</title></rect>`;}).join('')}</svg>`:'<div class="capital-bar capital-bar-empty" aria-label="No priced allocation saved"></div>';
  const rows=groups.map(g=>`<li>${g.position_count?`<button type="button" class="capital-platform-pick" data-platform="${escapeHTML(g.id)}" aria-pressed="${platformFilter===g.id}">`:''}${icon(g)}<span class="capital-platform-name">${escapeHTML(g.name)}<small>${g.position_count?g.position_count+' saved '+(g.position_count===1?'position':'positions'):g.id==='mintclub'?'Bonding-curve tokens':'Direct holdings'}${g.unpriced_count?' · '+g.unpriced_count+' unpriced':''}</small></span><span class="capital-platform-value">${money(g.value_usd)}<small>${g.percent==null?'Unpriced':g.percent.toFixed(1)+'%'}</small></span>${g.position_count?'</button>':''}</li>`).join('');
  const currentWallets=selectedView==='wallet'?[currentWallet()]:((typeof FolderUI!=='undefined'?FolderUI.view():null)||state).wallets;
  const keys=new Set(currentWallets.filter(Boolean).map(w=>w.key));
  const running=typeof activeJobs!=='undefined'&&activeJobs.some(j=>j.operation==='positions.refresh'&&['queued','running'].includes(j.state)&&keys.has(j.input.wallet));
  const refreshLabel=running?'Platform scans in progress':allocation.latest_observed_at?'Refresh positions':'Find platform positions';
  const markup=`<div class="capital-heading"><div><h2>Where your assets are</h2><p>Wallet tokens and platform positions${selectedView==='token'?' for this token':''}</p></div><div class="capital-total"><strong>${money(total)}</strong><span>Known value · NAV</span></div></div>${bar}<ul class="capital-legend">${rows}</ul><div class="capital-footer"><span>${allocation.wallets_checked}/${allocation.wallet_count} wallets checked${partial?' · Coverage incomplete':''}${allocation.latest_observed_at?' · Updated '+stamp(allocation.latest_observed_at):''}${allocation.unpriced_count?' · '+allocation.unpriced_count+' unpriced':''}${allocation.retained_count?' · '+allocation.retained_count+' retained results':''}</span>${localSession?.controls&&!state.demo?`<div class="capital-refresh-actions"><button type="button" class="quiet-button capital-refresh" ${running?'disabled':''}>${refreshLabel}</button>${allocation.latest_observed_at?`<button type="button" class="text-button capital-discover" ${running?'disabled':''}>Find new positions</button>`:''}</div>`:''}</div><p class="capital-basis">Percentages use known recorded value. Each claim counts once. Unpriced assets, debt, unclaimed rewards and exit costs are excluded. Sell-out estimates cover wallet tokens only.</p><div class="capital-action-status" role="status" aria-live="polite">${escapeHTML(loadError)}${loadError?'<button type="button" class="text-button capital-retry">Retry saved view</button>':''}</div><details class="capital-positions" ${positionsOpen?'open':''}><summary>Platform positions <span>${page?.matched_count??allocation.position_count}${platformFilter?' · '+escapeHTML(groups.find(g=>g.id===platformFilter)?.name||platformFilter):''}</span></summary>${platformFilter?'<button type="button" class="text-button capital-clear-platform">Show all platforms</button>':''}<div class="capital-position-list">${positionRows(page?.positions||[],groups)||`<p class="capital-empty">${loading?'Loading saved positions…':allocation.wallets_checked?'No positions recorded in this view. Incomplete checks remain unknown.':'Find LP, vault and staking positions with a read-only scan. Saved results will appear here.'}</p>`}</div><div class="capital-pages" ${!page?.matched_count?'hidden':''}><span>${offset+1}–${offset+(page?.positions.length||0)} of ${page?.matched_count||0}</span><button type="button" class="quiet-button capital-prev" ${!offset||loading?'disabled':''}>Previous</button><button type="button" class="quiet-button capital-next" ${!page||page.next_offset===null||loading?'disabled':''}>Next</button></div></details>${page?.coverage_gaps?.length?`<details class="capital-coverage"><summary>Coverage & sources · ${page.coverage_gap_count} gaps</summary><p>Saved-claim refresh keeps broad pool discovery separate. Find new positions checks for new deposits.</p><ul>${page.coverage_gaps.slice(0,12).map(c=>`<li><strong>${escapeHTML(c.wallet_name)} · ${escapeHTML(chainName(c.chain_id))}</strong><span>${escapeHTML(c.message||'This source is not fully checked.')}</span></li>`).join('')}</ul>${page.coverage_gap_count>12?'<p>Showing 12 source gaps. The agent can inspect bounded position records for more detail.</p>':''}</details>`:''}`;
  if(painted.get(host)===markup){if(!document.hidden&&signature!==state.data_revision+'|'+current.params.toString()&&!loading)load();return;}
  host.innerHTML=markup;painted.set(host,markup);
  for(const button of host.querySelectorAll('[data-platform]'))button.addEventListener('click',()=>{platformFilter=button.dataset.platform;positionsOpen=true;offset=0;load(true);});
  host.querySelector('.capital-clear-platform')?.addEventListener('click',()=>{platformFilter=null;offset=0;load(true);});
  host.querySelector('.capital-positions').addEventListener('toggle',event=>{positionsOpen=event.target.open;});
  host.querySelector('.capital-retry')?.addEventListener('click',()=>load(true));
  host.querySelector('.capital-refresh')?.addEventListener('click',()=>refresh(!allocation.latest_observed_at));
  host.querySelector('.capital-discover')?.addEventListener('click',()=>refresh(true));
  host.querySelector('.capital-prev')?.addEventListener('click',()=>{offset=Math.max(0,offset-25);load(true);});
  host.querySelector('.capital-next')?.addEventListener('click',()=>{if(page?.next_offset!=null){offset=page.next_offset;load(true);}});
  if(!document.hidden&&signature!==state.data_revision+'|'+current.params.toString()&&!loading)load();
 }
 function positionRows(positions,groups){
  return positions.map(p=>{
   const platform=groups.find(g=>g.id===p.platform)||{name:p.platform},pair=p.assets.map(a=>a.symbol).join(' / ');
   return `<article class="capital-position"><div class="capital-position-title">${icon(platform)}<span><strong>${escapeHTML(pair||p.label)}</strong><small>${escapeHTML(platform.name)} · ${escapeHTML(p.version||'')} ${p.custody_platform?'· Staked':''}${p.retained?' · Retained observation':''}${p.included_in_totals===false?' · Excluded from totals':''}</small></span><strong>${money(p.value_usd)}</strong></div><div class="capital-position-assets">${p.assets.map(a=>`<a href="${tokenHref(p.chain_id+':'+a.address)}">${escapeHTML(quantity(a.amount))} ${escapeHTML(a.symbol)}</a>`).join('<span>+</span>')}</div><div class="capital-position-meta"><a href="${FolderUI.path('wallet/'+p.wallet)}">${escapeHTML(p.wallet_name)}</a><span>${escapeHTML(chainName(p.chain_id))} · ${stamp(p.observed_at)}</span><a href="${safeURL(p.source_url)}" target="_blank" rel="noopener noreferrer">View source ↗</a></div><p>${escapeHTML(p.exit_note||'Recorded principal; gas excluded.')} ${p.assets.some(a=>a.price?.observed_at)?'Saved prices '+stamp(p.assets.map(a=>a.price?.observed_at).filter(Boolean).sort()[0])+'.':''}</p></article>`;
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
   const count=receipt.jobs?.length??1;status.textContent=count+' wallet '+(count===1?'scan':'scans')+' queued. Results appear as each bounded pass is saved. Follow Activity.';
  }catch(error){status.textContent=error.message;}
  finally{button.disabled=false;}
 }
 return {render};
})();
