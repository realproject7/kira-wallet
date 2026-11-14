'use strict';
const $ = id => document.getElementById(id);
const escapeHTML = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
let state = null, selectedWallet = localStorage.getItem('wallet-selection'), selectedView = localStorage.getItem('wallet-view') === 'wallet' ? 'wallet' : 'home', selectedChain = 'all', minimum = 0, etag = null, currentSignature = null, busy = false;
let selectedToken = null, selectedNetwork = null, tokenSearch = '', walletSort='value', networkSort='value', walletStatus='portfolio', networkStatus='portfolio';
if (![0,5,10].includes(minimum)) minimum=0;
const money = value => value == null ? '—' : value > 0 && value < .01 ? '< $0.01' : new Intl.NumberFormat('en-US',{style:'currency',currency:'USD',maximumFractionDigits:2}).format(value);
const unitPrice = value => value == null ? '—' : value === 0 ? '$0.00' : value < .000001 ? '$'+value.toExponential(3) : '$'+new Intl.NumberFormat('en-US',{maximumFractionDigits:value < .01 ? 8 : value < 1 ? 6 : 2}).format(value);
const quantity = raw => raw==null ? '—' : Number(raw)>0&&Number(raw)<.000001 ? Number(raw).toExponential(3) : new Intl.NumberFormat('en-US',{maximumFractionDigits:Number(raw)<1 ? 6 : 3}).format(Number(raw));
const compactQuantity = raw => raw!=null&&Number(raw)>=100000 ? new Intl.NumberFormat('en-US',{notation:'compact',maximumFractionDigits:3}).format(Number(raw)) : quantity(raw);
const shortAddress = address => address.slice(0,6)+'…'+address.slice(-4);
const stamp = raw => raw ? new Date(raw).toLocaleString('en-US',{month:'short',day:'numeric',hour:'2-digit',minute:'2-digit',hour12:false}) : 'Not analysed yet';
const safeURL = raw => {try{const url=new URL(raw,location.origin);return (url.origin===location.origin||url.protocol==='https:') ? url.href : '#';}catch{return '#';}};
const imageHosts = new Set(['mint.club','tokens.1inch.io','coin-images.coingecko.com','fc.hunt.town','mint-club-v2.s3.us-west-2.amazonaws.com','cdn.dexscreener.com','static.alchemyapi.io','s2.coinmarketcap.com']);
const safeImage = raw => {try{const url=new URL(raw);return url.protocol==='https:'&&imageHosts.has(url.hostname)&&!url.username&&!url.password&&(!url.port||url.port==='443') ? url.href : null;}catch{return null;}};
const walletGlyph = '<svg viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="M4 6.5h13a2 2 0 0 1 2 2V18a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V6a2 2 0 0 1 1.4-1.9L15 1.8v4.7"/><path d="M19 10h-4a2 2 0 0 0 0 4h4"/><path d="M15.5 12h.01"/></svg>';

const arrowGlyph = '<svg class="ui-icon" viewBox="0 0 24 24" fill="none" aria-hidden="true" focusable="false"><path d="M7 17 17 7M7 7h10v10"/></svg>';
const infoTip = (label,body) => `<details class="info-tip"><summary aria-label="${escapeHTML(label)}"></summary><div class="info-pop">${body}</div></details>`;
const integer = value => value==null ? '—' : new Intl.NumberFormat('en-US').format(value);
// A wallet's face: a small symmetric pattern drawn from a hash of its whole address, so no two wallets share one glyph.
const walletAvatar = address => {const text=String(address||'').toLowerCase(),bytes=[];let hash=2166136261;for(let round=0;round<17;round++){for(let i=0;i<text.length;i++){hash^=text.charCodeAt(i)+round;hash=Math.imul(hash,16777619);}hash^=round+1;hash=Math.imul(hash,16777619);bytes.push((hash>>>16)&255);}const hue=Math.round(bytes[0]/255*360),ink=(hue+150+bytes[1]%90)%360;let cells='';for(let y=0;y<5;y++)for(let x=0;x<3;x++)if(bytes[2+y*3+x]%2)cells+=`<rect x="${x}" y="${y}" width="1" height="1"/>`+(x<2?`<rect x="${4-x}" y="${y}" width="1" height="1"/>`:'');return `<svg class="wallet-avatar" viewBox="-1 -1 7 7" aria-hidden="true" focusable="false"><rect x="-1" y="-1" width="7" height="7" rx="1.7" fill="hsl(${hue}, 60%, 91%)"/><g fill="hsl(${ink}, 42%, 46%)" shape-rendering="crispEdges">${cells||'<rect x="2" y="2" width="1" height="1"/>'}</g></svg>`;};
// How much of a value an estimate reaches, as a bar with one short label.
const ratioBar = (value,total,label) => value!=null&&total>0 ? `<span class="ratio" title="${escapeHTML(label)}"><progress class="allocation-progress" value="${Math.min(value,total)}" max="${total}" aria-label="${escapeHTML(label)}">${Math.round(Math.min(value,total)/total*100)}%</progress><small>${value/total>0&&value/total<.01?'< 1':Math.round(Math.min(value,total)/total*100)}%</small></span>` : '';
// The estimate covers tokens held in wallets, so that is its base. Platform positions have their own NAV.
const walletTokenValue = (allocation,fallback) => {const groups=(allocation?.groups||[]).filter(g=>['wallet','mintclub'].includes(g.id)&&g.value_usd!=null);return groups.length?groups.reduce((sum,g)=>sum+g.value_usd,0):fallback??null;};
let toastTimeout;
function toast(message,duration=2200){clearTimeout(toastTimeout);$('toast').textContent=message;$('toast').classList.add('show');toastTimeout=setTimeout(()=>$('toast').classList.remove('show'),duration);}
let routeData={},routeLoadedKey=null,routeLoading=false,routeEpoch=0,routeAbort=null;
let walletOffset=0,networkOffset=0,networkSearchTimer;
const routeCache=new Map();
async function readAPI(path,signal){
  const response=await fetch(path,{cache:'no-cache',headers:typeof localSession!=='undefined'&&localSession?.token?{'X-Kira-Session':localSession.token}:{},signal:signal?AbortSignal.any([signal,AbortSignal.timeout(12000)]):AbortSignal.timeout(12000)});
  if(!response.ok)throw Error('Saved research could not be loaded. Retry when the local app is available.');
  return response.json();
}
function queryPath(path,params){const query=new URLSearchParams();for(const [key,value] of Object.entries(params))if(value!==null&&value!==undefined&&value!==''&&(value!=='all'||key==='portfolio_status'))query.set(key,String(value));return path+'?'+query;}
function renderPagination(kind,page,size){
  const container=$(kind+'-pagination');if(!container)return;
  const count=page?.matched_count??0,offset=page?.offset??0;
  container.hidden=count<=size;
  $(kind+'-page').textContent=count?((offset+1)+'–'+Math.min(offset+(page.assets?.length||0),count)+' of '+count):'No matching holdings';
  const previous=$(kind+'-prev')||container.querySelector('[data-page="'+kind+'-prev"]');
  const next=$(kind+'-next')||container.querySelector('[data-page="'+kind+'-next"]');
  previous.disabled=routeLoading||offset===0;next.disabled=routeLoading||page?.next_offset==null;
}
function showRouteStatus(message,retry=false){
  const node=$('route-status');node.hidden=!message;node.textContent=message;
  if(retry){const button=document.createElement('button');button.type='button';button.className='quiet-button';button.textContent='Retry';button.addEventListener('click',()=>loadRoute(true));node.append(button);}
}
function selectedContext(){return {view:selectedView,...(typeof FolderUI!=='undefined'&&FolderUI.id?{folder_id:FolderUI.id}:{}),...(selectedView==='wallet'?{wallet:selectedWallet}:selectedView==='token'?{token:selectedToken,chain_id:Number(selectedToken.split(':')[0])}:selectedView==='network'?{chain_id:selectedNetwork}:{})};}
async function publishUiContext(){
  if(typeof localSession==='undefined'||!localSession?.controls)return;
  try{await localAPI('/api/ui-context',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(selectedContext())});}catch{/* Selection is optional; saved research remains usable. */}
}
async function loadRoute(force=false){
  if(!state?.paged)return;
  const view=selectedView,revision=state.data_revision,epoch=++routeEpoch;
  let requests=[];
  if(view==='home')requests=[queryPath('/api/holdings',{offset:0,limit:5,sort:'value',include_testnets:0})];
  else if(view==='wallet')requests=[queryPath('/api/wallet',{wallet:selectedWallet,offset:walletOffset,limit:100,chain_id:selectedChain,minimum_value_usd:minimum,sort:walletSort,portfolio_status:walletStatus})];
  else if(view==='token'){const [chain_id,address]=selectedToken.split(':');requests=[queryPath('/api/token',{chain_id,address})];}
  else if(view==='network')requests=[queryPath('/api/network',{chain_id:selectedNetwork}),queryPath('/api/holdings',{chain_id:selectedNetwork,offset:networkOffset,limit:100,query:tokenSearch,minimum_value_usd:minimum,include_testnets:1,sort:networkSort,portfolio_status:networkStatus})];
  else if(view==='tokens'){const f=catalogFilters();requests=[queryPath('/api/holdings',{offset:(f.page-1)*50,limit:50,chain_id:f.network,query:f.search,minimum_value_usd:f.minimum,sort:f.sort,pricing:f.pricing,portfolio_status:f.status,include_testnets:f.testnets?1:0})];}
  const folder=typeof FolderUI!=='undefined'?FolderUI.id:null;
  if(folder)requests=requests.map(path=>/^\/api\/(holdings|token|network)\?/.test(path)?path+'&folder_id='+encodeURIComponent(folder):path);
  const overviewIndex=requests.length;
  if(folder)requests.push(queryPath('/api/overview',{folder_id:folder}));
  const key=JSON.stringify([revision,view,requests]);
  if(key===routeLoadedKey&&!force){publishUiContext();return;}
  const focused=document.activeElement?.id?{id:document.activeElement.id,start:document.activeElement.selectionStart,end:document.activeElement.selectionEnd}:null;
  routeAbort?.abort();routeAbort=new AbortController();routeLoadedKey=null;routeLoading=true;routeData={};showRouteStatus(requests.length?'Loading saved research…':'');renderView();
  try{
    let results=!force&&routeCache.get(key);
    if(!results){
      results=await Promise.all(requests.map(path=>readAPI(path,routeAbort.signal)));
      const consistent=rows=>new Set(rows.map(row=>row.data_revision).filter(Boolean)).size<=1;
      if(folder&&!consistent(results)){
        if(epoch!==routeEpoch||revision!==state.data_revision)return;
        results=await Promise.all(requests.map(path=>readAPI(path,routeAbort.signal)));
        if(!consistent(results))throw Error('Saved data changed while this view was loading. Please retry.');
      }
      routeCache.set(key,results);if(routeCache.size>12)routeCache.delete(routeCache.keys().next().value);
    }
    if(epoch!==routeEpoch||revision!==state.data_revision)return;
    if(view==='wallet')routeData={wallet:results[0]};
    else if(view==='token')routeData={token:results[0]};
    else if(view==='network')routeData={network:results[0],page:results[1]};
    else if(view==='tokens'||view==='home')routeData={page:results[0]};
    if(folder){routeData.overview=results[overviewIndex];FolderUI.acceptOverview(routeData.overview);}
    routeLoadedKey=key;routeLoading=false;showRouteStatus('');renderView();
    const field=focused&&$(focused.id);if(field&&!field.disabled){field.focus({preventScroll:true});if(typeof field.setSelectionRange==='function'&&typeof focused.start==='number')field.setSelectionRange(focused.start,focused.end);}
    if(typeof refreshControlState==='function')refreshControlState();
    if(view==='activity'&&typeof loadActivity==='function')await loadActivity();
    if(view==='wallet'&&typeof loadWalletJobs==='function')await loadWalletJobs(selectedWallet);
    publishUiContext();
  }catch(error){if(epoch!==routeEpoch||error.name==='AbortError')return;routeLoading=false;showRouteStatus(error.message,true);renderView();}
}
function currentWallet(){return typeof routeData!=='undefined'&&routeData.wallet?.key===selectedWallet ? routeData.wallet : state?.wallets.find(w=>w.key===selectedWallet);}
const tokenHref = id => (typeof FolderUI!=='undefined'?FolderUI.path('token'):'#/token')+'/'+id.split(':').map(encodeURIComponent).join('/');
const networkHref = id => (typeof FolderUI!=='undefined'?FolderUI.path('network'):'#/network')+'/'+id;
function navigate(hash){if(location.hash===hash)readRoute();else location.hash=hash;}
let routeIdentity=null;
function readRoute(){
  const identity=location.hash||'#/home';
  if(identity!==routeIdentity){selectedChain='all';minimum=0;tokenSearch='';walletOffset=0;networkOffset=0;routeData={};routeLoadedKey=null;if(typeof resetRouteFilters==='function')resetRouteFilters();routeIdentity=identity;}
  let parts=[];try{parts=location.hash.replace(/^#\/?/,'').split('/').map(decodeURIComponent);}catch{}
  if(typeof FolderUI!=='undefined')parts=FolderUI.route(parts);
  if(parts[0]==='wallet'&&/^0x[0-9a-f]{40}$/i.test(parts[1]||'')){selectedWallet=parts[1].toLowerCase();selectedView='wallet';selectedChain='all';}
  else if(parts[0]==='network'&&/^\d+$/.test(parts[1]||'')){selectedNetwork=Number(parts[1]);selectedView='network';tokenSearch='';}
  else if(parts[0]==='token'&&/^\d+$/.test(parts[1]||'')&&/^(native|0x[0-9a-f]{40})$/i.test(parts[2]||'')){selectedToken=Number(parts[1])+':'+parts[2].toLowerCase();selectedView='token';}
  else if(['tokens','activity'].includes(parts[0])){selectedView=parts[0];}
  else if(location.hash){selectedView='home';}
  localStorage.setItem('wallet-view',selectedView);if(selectedWallet)localStorage.setItem('wallet-selection',selectedWallet);
  if(state){renderView();loadRoute();}window.scrollTo({top:0,behavior:'instant'});
}
function selectWallet(key){
  if(!state?.wallets.some(w=>w.key===key))return;
  navigate(typeof FolderUI!=='undefined'?FolderUI.walletPath(key):'#/wallet/'+key);
}
function goHome(){
  navigate('#/home');
}
function renderBreadcrumb(items){
  $('breadcrumbs').innerHTML='<ol>'+items.map(item=>`<li>${item.href?`<a href="${escapeHTML(item.href)}" title="${escapeHTML(item.label)}">${escapeHTML(item.label)}</a>`:`<span aria-current="page" title="${escapeHTML(item.label)}">${escapeHTML(item.label)}</span>`}</li>`).join('')+'</ol>';
}
function renderWallets(){
  const wallets=typeof FolderUI!=='undefined'?FolderUI.wallets():state.wallets;
  $('wallet-count').textContent=wallets.length;
  const visible=typeof matchingWallets==='function'?matchingWallets(wallets,$('wallet-nav-search').value):wallets;
  $('wallet-list').innerHTML=visible.map(w=>{
    const active=selectedView==='wallet'&&w.key===selectedWallet;
    const status=KiraView.walletStatus(typeof jobList==='undefined'?[]:jobList,w);
    const label={partial:'Saved · gaps',complete:'Complete',interrupted:'Interrupted',paused:'Paused',failed:'Lookup failed',waiting:'Queued',pausing:'Pausing',running:'Looking up tokens'}[status.mode]||status.label;
    const routine=['partial','saved','complete'].includes(status.mode);
    return `<button class="wallet-button ${active?'active':''}" data-wallet="${escapeHTML(w.key)}" aria-label="Select ${escapeHTML(w.name)}" title="${escapeHTML(w.address)} · ${escapeHTML(status.label)}" ${active?'aria-current="page"':''}><span class="wallet-glyph">${walletAvatar(w.address)}</span><span class="wallet-nav-name">${escapeHTML(w.name)}${routine?'':`<span class="wallet-nav-address">${escapeHTML(label)}</span>`}</span><span class="wallet-status-dot" data-mode="${status.mode}" title="${escapeHTML(label)}" aria-hidden="true"></span></button>`;
  }).join('')||'<p class="wallet-nav-empty">No saved wallets match.</p>';
}
function renderView(){
  if(selectedView==='wallet'){
    const w=currentWallet(),pending=typeof pendingWalletJob==='function'&&pendingWalletJob(w||{key:selectedWallet});
    if(!w){
      if(!w)toast(pending?'This wallet is waiting for registration. Follow its progress in Activity.':'This wallet is not registered in this workspace.');
      navigate('#/activity');return;
    }
  }
  renderWallets();
  $('home-view').hidden=selectedView!=='home';$('wallet-view').hidden=selectedView!=='wallet';
  $('detail-view').hidden=!['token','network'].includes(selectedView);
  if(selectedView==='home'){renderHome();document.title='Home · Kira Wallet';}
  else if(selectedView==='wallet'){renderWallet();document.title=(currentWallet()?.name||'Wallet')+' · Kira Wallet';}
  else if(['token','network'].includes(selectedView))renderDetail();
  if(typeof renderWorkspace==='function')renderWorkspace();
  if(typeof KiraSelect!=='undefined')KiraSelect.refresh();
  if(typeof FolderUI!=='undefined')FolderUI.render();
  if(typeof CapitalUI!=='undefined')CapitalUI.render();
}
function progress(value,total,label){
  return value!=null&&total>0 ? `<progress class="allocation-progress" value="${value}" max="${total}" aria-label="${escapeHTML(label)}">${(value/total*100).toFixed(1)}%</progress>` : '';
}
function shareBar(value,total,label){return progress(value,total,label)||'<span class="allocation-empty" aria-hidden="true"></span>';}
function share(value,total){return value!=null&&total>0 ? (value/total*100).toFixed(1)+'%' : '—';}
function chainIcon(chain){
  const name=typeof chain==='string'?chain:chain.name;
  const url=safeImage(typeof chain==='string'?state?.details?.networks.find(c=>c.name===name)?.image_url:chain.image_url);
  const cls=name.toLowerCase().split(' ')[0],glyph=name==='Base'?'—':name==='Ethereum'?'◆':name.charAt(0);
  return `<span class="chain-icon ${escapeHTML(cls)}" aria-hidden="true"><span class="chain-fallback">${escapeHTML(glyph)}</span>${url?`<img src="${escapeHTML(url)}" alt="" width="24" height="24" loading="lazy" decoding="async" referrerpolicy="no-referrer" data-chain-image>`:''}</span>`;
}
function renderHome(){
  const home=typeof FolderUI!=='undefined'?FolderUI.view():state;
  const crumbs=typeof FolderUI!=='undefined'?FolderUI.breadcrumb():[{label:'Home'}];
  renderBreadcrumb([...crumbs.slice(0,-1),{label:crumbs.at(-1).label}]);
  if(!home){$('home-summary').hidden=true;$('home-details').hidden=true;$('home-empty').hidden=true;$('home-discovery-notice').hidden=true;$('home-coverage-note').textContent='';$('home-price-time').textContent='';return;}
  const s=home.dashboard,total=s.capital_allocation?s.capital_allocation.known_value_usd:s.known_value_usd;$('home-summary').hidden=false;
  $('sync-label').textContent=s.analysed_wallet_count+' of '+s.wallet_count+' '+(s.wallet_count===1?'wallet':'wallets')+' analysed';
  $('home-total').textContent=money(total);
  $('home-sell-out').innerHTML=sellSummary(s.sell_out_summary,walletTokenValue(s.capital_allocation,s.known_value_usd));
  const waiting=s.wallet_count-s.analysed_wallet_count;
  $('home-meta').innerHTML=`<span class="chip"><strong>${integer(s.wallet_count)}</strong> ${s.wallet_count===1?'wallet':'wallets'}</span><span class="chip"><strong>${integer(s.chain_count)}</strong> ${s.chain_count===1?'network':'networks'}</span><a class="chip" href="${typeof FolderUI!=='undefined'?FolderUI.path('tokens'):'#/tokens'}"><strong>${integer(s.unique_asset_count)}</strong> ${s.unique_asset_count===1?'token':'tokens'}</a>${waiting>0?`<span class="chip warn">${integer(waiting)} awaiting analysis</span>`:''}${policyNotice(s.asset_policy_summary)}`;
  $('home-valuation-note').textContent=s.capital_allocation?.position_count?'Wallet tokens plus recorded platform NAV. Unpriced claims are excluded.':s.priced_count ? 'Market and curve spot estimates. '+integer(s.unpriced_count)+' unpriced holdings are excluded.' : 'Value appears as priced holdings become available.';
  $('home-empty').hidden=s.wallet_count>0;$('home-details').hidden=s.wallet_count===0;
  renderHomeCoverage();
  const incomplete=home.wallets.some(w=>w.chains.some(c=>c.environment==='mainnet'&&KiraView.coverageGap(c)));
  $('home-coverage-note').textContent='Mainnet holdings only. '+(incomplete?'Research coverage is incomplete.':'Testnets are excluded from totals.');
  $('home-price-time').textContent=s.prices_from ? 'Prices '+stamp(s.prices_from)+(s.prices_from!==s.prices_to?' – '+stamp(s.prices_to):'') : '';
  const ranked=home.wallets.map(w=>({w,value:w.capital_allocation?w.capital_allocation.known_value_usd:(w.analysed_at?w.known_value_usd:null)})).sort((a,b)=>(b.value??-1)-(a.value??-1)||a.w.name.localeCompare(b.w.name));
  $('home-wallet-total').textContent=integer(ranked.length);
  $('wallet-cards').innerHTML=ranked.map(({w,value})=>{
    const tokens=w.mainnet_asset_count??w.assets.filter(a=>a.environment==='mainnet').length,unpriced=w.mainnet_unpriced_count??w.unpriced_count,sale=w.sell_out_summary?.value_usd;
    const detail=w.analysed_at?integer(tokens)+(tokens===1?' token':' tokens'):'Not checked';
    return `<button class="rank-row" data-wallet="${escapeHTML(w.key)}" aria-label="Open ${escapeHTML(w.name)} holdings" title="${escapeHTML(shortAddress(w.address)+(w.analysed_at?' · '+unpriced+' unpriced · Sell-out est. '+(sale==null?'unknown':'≈ '+money(sale)):''))}"><span class="rank-name">${walletAvatar(w.address)}<span class="rank-label"><strong>${escapeHTML(w.name)}</strong><small>${detail}</small></span></span>${shareBar(value,total,w.name+' share of priced value')}<span class="rank-value"><strong>${money(value)}</strong><small>${share(value,total)}</small></span></button>`;
  }).join('');
  if(typeof filterHomeWallets==='function')filterHomeWallets();
  const networks=s.networks.map(c=>({...c,value_usd:c.capital_allocation?c.capital_allocation.known_value_usd:c.value_usd})).sort((a,b)=>(b.value_usd??-1)-(a.value_usd??-1));
  $('home-network-total').textContent=integer(networks.length);
  $('network-allocation').innerHTML=networks.map(c=>`<a class="rank-row" href="${networkHref(c.id)}" aria-label="Open ${escapeHTML(c.name)} network overview" title="${escapeHTML(integer(c.position_count)+(c.position_count===1?' holding':' holdings'))}"><span class="rank-name">${chainIcon(c.name)}<span class="rank-label"><strong>${escapeHTML(c.name)}</strong></span></span>${shareBar(c.value_usd,total,c.name+' share of priced value')}<span class="rank-value"><strong>${money(c.value_usd)}</strong><small>${c.value_usd==null?'Unpriced':share(c.value_usd,total)}</small></span></a>`).join('')||'<p class="panel-empty">Networks appear after analysis.</p>';
  const more=$('home-network-more'),expanded=$('network-allocation').hasAttribute('data-expanded');
  more.hidden=networks.length<=8;more.textContent=expanded?'Show top 8':'Show all '+networks.length;more.setAttribute('aria-expanded',String(expanded));
  if(typeof renderHomeTokens==='function')renderHomeTokens();
  bindImages();
}
function renderWallet(){
  const w=currentWallet();if(!w)return;
  if($('wallet-tools').dataset.wallet!==w.key){$('wallet-tools').open=false;$('wallet-tools').dataset.wallet=w.key;}
  $('wallet-name').textContent=w.name;renderBreadcrumb([...(typeof FolderUI!=='undefined'?FolderUI.breadcrumb():[{label:'Home',href:'#/home'}]),{label:w.name}]);$('address').textContent=w.address;$('address').title=w.address;
  $('wallet-tags').innerHTML=w.tags.slice(1).map(t=>`<span class="tag">${escapeHTML(t)}</span>`).join(' ');
  $('report-link').hidden=!w.report_url;if(w.report_url)$('report-link').href=safeURL(w.report_url);
  $('total-value').textContent=money((w.capital_allocation?w.capital_allocation.known_value_usd:(w.analysed_at?w.known_value_usd:null)));
  $('wallet-sell-out').innerHTML=sellSummary(w.sell_out_summary,walletTokenValue(w.capital_allocation,w.known_value_usd));
  $('wallet-avatar').innerHTML=walletAvatar(w.address);
  const partial=w.chains.some(c=>c.environment==='mainnet'&&KiraView.coverageGap(c));
  $('wallet-policy-note').innerHTML=policyNotice(w.asset_policy_summary);
  $('valuation-note').textContent=w.analysed_at?(partial?'Partial portfolio · ':'')+(w.known_value_usd==null?((w.asset_count??w.assets.length)?'Value is unknown because prices are unavailable.':'No positive holdings recorded · unchecked networks remain unknown.'):'Market and curve spot estimates. Unpriced assets are excluded.'):'No holdings lookup saved yet.';
  const held=w.asset_count??w.assets.length;
  $('asset-count').textContent=integer(held);$('unpriced-count').textContent=integer(w.unpriced_count)+' unpriced';
  $('priced-meter').innerHTML=held?`<progress class="allocation-progress" value="${Math.max(0,held-w.unpriced_count)}" max="${held}" aria-label="${escapeHTML(integer(Math.max(0,held-w.unpriced_count))+' of '+integer(held)+' tokens priced')}"></progress>`:'';
  const mainnets=w.chains.filter(c=>c.environment==='mainnet'&&c.lifecycle?.status!=='retired');
  $('chain-count').textContent=mainnets.filter(c=>c.assets>0).length;
  const coverage=mainnets.filter(c=>c.complete).length;
  $('coverage-note').textContent=coverage+' of '+mainnets.length+' checked';if(typeof coverageVisual==='function')$('wallet-coverage-meter').innerHTML=coverageVisual(w.chains,true);
  $('coverage-note').title='Token discovery and on-chain balance checks are separate. See network coverage details for failures.';
  $('sync-label').textContent=w.analysed_at?'Analysis '+stamp(w.analysed_at):'Not checked';
  $('price-time').textContent=w.prices_at?'Prices '+stamp(w.prices_at):'';
  const chainOptions=w.chains.filter(c=>c.assets>0||KiraView.coverageGap(c));
  if(selectedChain!=='all'&&!chainOptions.some(c=>String(c.id)===selectedChain))selectedChain='all';
  $('chain-filter').innerHTML='<option value="all">All chains</option>'+chainOptions.map(c=>`<option value="${c.id}" data-chain-id="${c.id}">${escapeHTML(c.name)}${c.environment==='testnet'?' · Testnet':''}${KiraView.coverageGap(c)?' · Incomplete':''}</option>`).join('');
  $('chain-filter').value=selectedChain;renderHoldings();renderDiscoveryCoverage(w);
  if(typeof renderWalletScan==='function')renderWalletScan();
}
function renderHomeCoverage(){
  const readiness=typeof setupReadiness!=='undefined'?setupReadiness:null;
  const wallets=typeof FolderUI!=='undefined'?(FolderUI.view()?.wallets||[]):state?.wallets||[];
  const affected=wallets.find(w=>KiraView.discoveryNotice(w,readiness)?.rpcIssues)||wallets.find(w=>{const n=KiraView.discoveryNotice(w,readiness);return n?.gapCount>0||n?.action==='settings';});
  const notice=affected?KiraView.discoveryNotice(affected,readiness):null;
  $('home-discovery-notice').hidden=!notice;
  if(!notice)return;
  $('home-discovery-title').textContent=notice.title;
  $('home-discovery-text').textContent=notice.action==='settings'?notice.message:affected.name+': saved holdings are available. Review coverage for missing or incomplete checks.';
  $('home-discovery-settings').textContent=notice.settingsLabel||'Review data connection';
  $('home-discovery-settings').dataset.wallet=affected.key;
  $('home-discovery-settings').hidden=(notice.action!=='settings'&&!notice.settings)||typeof localSession==='undefined'||localSession?.controls!==true||state.demo===true;
  $('home-discovery-review').href=typeof FolderUI!=='undefined'?FolderUI.walletPath(affected.key):'#/wallet/'+encodeURIComponent(affected.key);
}
function renderDiscoveryCoverage(w) {
  const readiness=typeof setupReadiness!=='undefined'?setupReadiness:null;
  const notice=KiraView.discoveryNotice(w,readiness);
  $('discovery-notice').hidden=!notice;
  if(!notice)return;
  $('discovery-notice-title').textContent=notice.title;
  $('discovery-notice-text').textContent=notice.message;if(typeof coverageVisual==='function')$('discovery-coverage-grid').innerHTML=coverageVisual(w.chains);
  const controls=typeof localSession!=='undefined'&&localSession?.controls===true&&state?.demo!==true;
  $('discovery-settings').hidden=!controls||!(notice.action==='settings'||notice.settings);
  $('discovery-settings').textContent=notice.settingsLabel||'Set up Alchemy';
  $('discovery-refresh').hidden=!controls||notice.action!=='refresh';
  $('discovery-refresh').textContent=notice.refreshLabel||'Refresh holdings';
  $('discovery-refresh').disabled=$('refresh-wallet').disabled;
  // Keep the operator's expanded/collapsed state across data updates.
  $('discovery-network-details').textContent=w.chains.filter(c=>c.environment==='mainnet'&&KiraView.coverageGap(c)).map(c=>{
    const reasons=[];
    if(c.lifecycle?.status==='retirement_reported')reasons.push('retirement reported; no verified official closure notice. RPC failure is not proof of closure');
    else if(c.rpc_pending)reasons.push('not yet checked; follow or resume detailed research in Activity');
    else if(!c.rpc_available)reasons.push('balance reads failed; refresh all holdings to retry, or review RPC settings if this continues');
    if(c.head_status==='stale')reasons.push('provider returned an old head ('+c.head_age_seconds+' seconds old); this does not establish retirement');
    if(!c.complete)reasons.push(({disabled:'token discovery off',missing_credential:'indexer credential unavailable',unsupported:'token discovery is unsupported by the connected indexer; refreshing may update known balances but cannot add indexer coverage',provider_error:'indexer request failed',history_pending:'free transfer history has unfinished ranges',throttled:'discovery is waiting for the provider retry interval',checkpoint_error:'discovery checkpoint needs recovery; saved evidence is preserved',source_limited:'a single block exceeds the discovery source limit'})[c.discovery_status]||'token discovery incomplete');
    if(c.history_window)reasons.push('history window '+c.history_window.startblock+'–'+c.history_window.endblock+(c.history_window.pending_ranges!==undefined?'; pending ranges: '+c.history_window.pending_ranges+'; unresolved ranges: '+(c.history_window.blocked_ranges||0):', next page '+c.history_window.page)+'; transfer identities are candidates, not balances');
    if(c.discovery_sources?.length>1)reasons.push(c.discovery_sources.map(s=>({etherscan_keyless:'Etherscan',routescan:'Routescan',explorer:'Explorer'}[s.provider]||'Source')+': '+(s.complete?'source pages checked':s.status.replaceAll('_',' '))).join('; '));
    if(c.recent_window)reasons.push('newer window '+c.recent_window.startblock+'–'+c.recent_window.endblock+' '+(c.recent_window.complete?'checked':'partly checked')+' while earlier history resumes');
    if(c.registry_phase==='deferred')reasons.push('full Mint Club discovery pending; check or resume it in Activity');
    else if(c.registry_complete===false&&c.rpc_available)reasons.push('Mint Club balances partly unchecked; retry holdings'+(c.registry_errors||c.balance_errors?' ('+(c.registry_errors||0)+' asset checks and '+(c.balance_errors||0)+' balance reads failed)':''));
    if(c.candidate_deferred>0)reasons.push(c.candidate_deferred+' token candidates await balance checks in Activity');
    if(c.candidate_balance_errors>0)reasons.push(c.candidate_balance_errors+' token balance reads failed; missing balances remain unknown');
    if(c.token_detail_errors>0)reasons.push(c.token_detail_errors+' token details unavailable; missing quantities and prices remain unknown');
    if(c.market_pending)reasons.push('balances saved; remaining market checks paused at the time budget; resume in Activity');
    if(c.market_errors>0)reasons.push(c.market_errors+' token market checks had failed reads; prices remain unknown where evidence is missing');
    return c.name+': '+reasons.join('; ');
  }).join('\n');
  const archived=w.chains.filter(c=>c.environment==='mainnet'&&c.lifecycle?.status==='retired');
  if(archived.length)$('discovery-network-details').textContent+='\n\nArchived networks\n'+archived.map(c=>c.name+': historical records only; excluded from new research and current value.').join('\n');
  for(const c of w.chains.filter(c=>c.lifecycle?.notice_url)){
    const url=c.lifecycle.notice_url;
    if(!/^https:\/\/www\.alchemy\.com\/docs\//.test(url))continue;
    const link=document.createElement('a');link.href=url;link.target='_blank';link.rel='noreferrer';link.textContent='Official notice: '+c.name;
    $('discovery-network-details').append(document.createElement('br'),link);
  }
}
function icon(asset){
  if(typeof asset.symbol!=='string'||!asset.symbol)return ['', '?'];
  if(asset.symbol==='ETH')return ['ether','◆'];
  if(asset.symbol==='CHICKEN')return ['chicken','🐔'];
  if(asset.symbol==='hcbBTC')return ['bitcoin','₿'];
  if(asset.symbol.toLowerCase()==='member')return ['member','m'];
  // A badge holds two letters or one emoji. A longer symbol was cut on both sides.
  if(/[^\x00-\x7F]/.test(asset.symbol)){const chars=[...asset.symbol];return ['',/\p{Extended_Pictographic}/u.test(chars[0])?chars[0]:chars.slice(0,2).join('').toUpperCase()];}
  return ['',asset.symbol.slice(0,2).toUpperCase()];
}
function coinIcon(asset){
  const [cls,glyph]=icon(asset),fallback=Number.isSafeInteger(asset.chain_id)&&/^0x[0-9a-fA-F]{40}$/.test(asset.address||'')?'https://fc.hunt.town/tokens/logo/'+asset.chain_id+'/'+asset.address.toLowerCase()+'/image':null;
  const url=safeImage(asset.image_url)||fallback;
  return `<span class="coin-icon ${cls}" aria-hidden="true"><span class="coin-fallback">${escapeHTML(glyph)}</span>${url?`<img src="${escapeHTML(url)}" ${fallback&&fallback!==url?`data-image-fallback="${escapeHTML(fallback)}"`:''} alt="" width="34" height="34" loading="lazy" decoding="async" referrerpolicy="no-referrer" data-token-image>`:''}</span>`;
}
function bindImages(){
  document.querySelectorAll('img[data-token-image],img[data-chain-image]').forEach(img=>{
    if(img.dataset.bound)return;img.dataset.bound='true';
    const show=()=>{const ok=img.naturalWidth>0;img.hidden=!ok;img.parentElement.classList.toggle('has-image',ok);};
    const failed=()=>{const fallback=safeImage(img.dataset.imageFallback);delete img.dataset.imageFallback;if(fallback&&img.src!==fallback){img.src=fallback;return;}show();};
    img.addEventListener('load',show);img.addEventListener('error',failed);
    if(img.complete){if(img.naturalWidth)show();else failed();}
  });
}
function saleValue(a){return a.sell_out_summary?a.sell_out_summary.value_usd:(a.sell_out?.value_usd??a.sell_out_reference?.value_usd);}
function sellSummary(summary,base){
  if(!summary)return '';
  const missing=summary.missing_count,refs=summary.reference_count||0;
  return `<div class="summary-label">Sell-out estimate${infoTip('About sell-out estimates','<p>'+(refs?'Includes '+integer(refs)+' native or stable spot references. ':'')+'Sum of independent saved estimates, not a combined exit quote. Gas excluded. Shared liquidity may change combined proceeds. Missing estimates remain unknown. Platform positions have separate NAV observations and are excluded from this sum.</p>')}</div><strong class="sell-summary-value">${summary.value_usd==null?'—':'≈ '+money(summary.value_usd)}</strong>${ratioBar(summary.value_usd,base,'Share of wallet token value this estimate reaches')}<span class="chip-row estimate-badges">${missing?'<span class="chip warn" title="No saved sell estimate. Unknown, not zero.">'+integer(missing)+' missing</span>':''}${summary.limited_count?'<span class="chip warn" title="A larger known pool was not quoted.">'+integer(summary.limited_count)+' limited routes</span>':''}</span>`;
}
function sellOutNote(a){
  if(a.cashout_eligibility?.balance_changed)return a.cashout_eligibility.reason;
  if(a.environment==='testnet')return 'Testnet assets have no USD sale estimate.';
  if(a.archived)return 'Archived holdings have no current sale estimate.';
  if(a.wallet_count>1&&a.sell_out_summary){const s=a.sell_out_summary;return (s.limited_count?s.limited_count+' positions have limited route coverage. ':'')+s.quoted_count+' position quotes; '+(s.reference_count||0)+' market references; '+s.missing_count+' missing. Sum of independent estimates, not a combined exit quote. Shared liquidity may change proceeds. Gas excluded.';}
  if(a.wallet_count>1)return 'Compare estimates by wallet. Separate quotes may use the same liquidity and cannot be added together.';
  const q=a.sell_out;
  if(q?.value_usd==null&&a.sell_out_reference){const r=a.sell_out_reference;return 'Spot reference for a recognized '+(r.kind==='native_market_reference'?'native asset':'stablecoin')+'. Uses its saved market value, not a simulated sale or a $1 peg. Gas, fees and slippage excluded. Price '+stamp(r.observed_at)+'.';}
  if(!q)return 'No full-balance sale quote saved. This is unknown, not zero.';
  const output=quantity(q.output_amount)+' '+(q.output_symbol||shortAddress(q.output_address));
  const basis=q.valuation==='reserve_reference'?'Value of the '+output+' received from Mint Club. Selling that token to USD is not quoted.':'Saved full-balance route output: '+output+'.';
  return (q.route_coverage?.reason?q.route_coverage.reason+' ':'')+basis+' Gas excluded. Execution is not verified. Quote '+stamp(q.observed_at)+(q.output_price?.observed_at?'; output price '+stamp(q.output_price.observed_at):'; output USD price unavailable')+'.';
}
function sellOutValue(a,linked=true){
  const q=a.sell_out, limited=q?.route_coverage?.status==='limited', note=sellOutNote(a), value=a.environment==='testnet'||a.archived?null:(a.sell_out_summary?a.sell_out_summary.value_usd:(q?.value_usd??a.sell_out_reference?.value_usd)),byWallet=a.wallet_count>1&&!a.sell_out_summary;
  const label=byWallet?'By wallet':value==null?'Unknown':money(value);
  return `<${linked?'a':'span'} class="sell-out-value ${value==null?'unpriced':''}" ${linked?`href="${tokenHref(a.id)}"`:''} title="${escapeHTML(note)}" aria-label="Sell-out estimate: ${escapeHTML(label)}. ${escapeHTML(note)}">${byWallet?'By wallet':value==null?'—':'≈ '+money(value)}</${linked?'a':'span'}>${(a.sell_out_summary?.reference_count>0||a.sell_out_reference&&q?.value_usd==null||a.sell_out_summary?.missing_count>0)?`<span class="price-basis">${a.sell_out_summary?.reference_count>0||a.sell_out_reference&&q?.value_usd==null?'Spot ref.':''}${a.sell_out_summary?.missing_count>0?(a.sell_out_summary?.reference_count>0?' · ':'')+a.sell_out_summary.missing_count+' missing':''}</span>`:''}${limited||a.sell_out_summary?.limited_count?'<span class="price-basis route-limited">Limited routes</span>':''}${a.cashout_eligibility?.balance_changed?'<span class="price-basis route-limited">Refresh holdings</span>':''}`;
}
function assetRow(a){
  const p=a.price;
  const source=p?.usd!=null ? (p.retained_from_previous?'Previous '+(p.basis||'estimate')+' · '+stamp(p.observed_at):p.basis) : p?.quality==='unreliable'?'Thin quote side':p?.quality==='unfunded'?'No funded reserve':'No price';
  const reserve=a.curve_reserve?`Curve reserve: ${a.curve_reserve.amount} ${a.curve_reserve.symbol}`:'';
  return `<tr class="holding-summary" data-asset-id="${escapeHTML(a.id)}" data-value="${a.value_usd ?? ''}"><td><a class="token-name token-link" href="${tokenHref(a.id)}" aria-label="Open ${escapeHTML(a.symbol)} token overview">${coinIcon(a)}<div class="coin-title"><div class="symbol" title="${escapeHTML(a.symbol)}">${escapeHTML(a.symbol)}${policyBadge(a)}</div><div class="token-description" title="${escapeHTML((a.address||'Native asset')+' '+reserve)}">${escapeHTML(a.archived?'Archived observation':a.is_native?'Native asset':a.name)}</div></div></a></td><td><span class="mobile-label">Balance</span><span class="amount" title="${escapeHTML(a.balance)}">${quantity(a.balance)}</span>${a.quantity_retained?'<span class="retained-note">Saved quantity · '+escapeHTML(stamp(a.balance_observed_at))+'</span>':''}</td><td><span class="mobile-label">Price</span><span class="token-price ${p?.usd==null?'unpriced':''}" title="${escapeHTML(p?.observed_at||'')}">${unitPrice(p?.usd)}</span><div class="price-basis">${escapeHTML(source)}</div>${p?.retained_from_previous?'<span class="retained-note">Current price unavailable. Showing the earlier estimate.</span>':''}</td><td><span class="mobile-label">Value</span><span class="token-value ${a.value_usd==null?'unpriced':''}">${money(a.value_usd)}</span>${a.included_in_totals===false?'<div class="price-basis">Reported · not in totals</div>':''}${a.archived?'<div class="price-basis">Archived · historical '+money(a.historical_value_usd)+'</div>':''}</td><td><span class="mobile-label">Sell-out est.</span>${sellOutValue(a)}</td><td class="visibility-cell">${policyActions(a)}</td></tr>`;
}
function renderHoldings(){
  const w=currentWallet();if(!w)return;
  const paged=typeof state!=='undefined'&&state?.paged===true;
  document.querySelectorAll('[data-min]').forEach(b=>b.setAttribute('aria-pressed',String(Number(b.dataset.min)===minimum)));
  const scoped=w.assets.filter(a=>walletStatus==='all'||(a.portfolio_status||'portfolio')===walletStatus).filter(a=>selectedChain==='all'?a.environment!=='testnet':String(a.chain_id)===selectedChain);
  const visible=scoped.filter(a=>minimum===0||(a.value_usd!=null&&a.value_usd>=minimum));
  const hiddenUnpriced=minimum>0?scoped.filter(a=>a.value_usd==null).length:0;
  $('holdings-filter-note').hidden=hiddenUnpriced===0;
  $('holdings-filter-note').innerHTML=hiddenUnpriced?`<span>${hiddenUnpriced} unpriced ${hiddenUnpriced===1?'holding is':'holdings are'} hidden by the ≥ $${minimum} filter.</span><button type="button" class="quiet-button" data-clear-value-filter>Show all holdings</button>`:'';
  $('visible-count').textContent=paged?(w.matched_count??0):visible.length;
  if(paged)renderPagination('wallet',w,100);
  const chains=w.chains.filter(c=>visible.some(a=>a.chain_id===c.id)).sort((a,b)=>(b.value_usd??0)-(a.value_usd??0));
  $('asset-groups').innerHTML=chains.map(c=>{
    const assets=visible.filter(a=>a.chain_id===c.id).sort((a,b)=>((typeof walletSort!=='undefined'&&walletSort==='sell_out')?(saleValue(b)??-1)-(saleValue(a)??-1):(b.value_usd??-1)-(a.value_usd??-1))||a.id.localeCompare(b.id));
    const values=assets.filter(a=>a.included_in_totals!==false&&a.value_usd!=null),sum=paged?c.value_usd:values.length?values.reduce((acc,a)=>acc+a.value_usd,0):null;
    return `<section class="chain-section" aria-label="${escapeHTML(c.name)} holdings"><div class="chain-heading"><h3 class="chain-name"><a class="network-label network-link" href="${networkHref(c.id)}" aria-label="Open ${escapeHTML(c.name)} network overview">${chainIcon(c)}${escapeHTML(c.name)}<span class="detail-arrow" aria-hidden="true">${arrowGlyph}</span></a><span class="chain-assets">${assets.length}${paged?' shown':' assets'}${c.environment==='testnet'?' · Testnet':''}</span></h3><span class="chain-total" title="Saved chain value">${c.environment==='testnet'?'Testnet':money(sum)}</span></div><div class="table-wrap"><table class="token-table holdings-table sale-table"><colgroup><col><col><col><col><col><col class="visibility-column"></colgroup><thead><tr><th scope="col">Token</th><th scope="col">Balance</th><th scope="col">Price</th><th scope="col">Value</th><th scope="col" title="Saved quotes or marked market references, valued in USD. Gas excluded.">Sell-out est.</th><th scope="col" class="visibility-cell"><span class="sr-only">Visibility</span></th></tr></thead><tbody>${assets.map(assetRow).join('')}</tbody></table></div></section>`;
  }).join('');
  $('empty').hidden=visible.length>0||(paged&&!routeData.wallet);
  if(paged&&!routeData.wallet)return;
  if(!visible.length&&hiddenUnpriced){
    $('empty').querySelector('h3').textContent='Holdings hidden by the value filter';
    $('empty').querySelector('p').textContent='These holdings have no price yet. Show all holdings to see their balances.';
  }else if(!visible.length&&selectedChain!=='all'){
    const c=w.chains.find(c=>String(c.id)===selectedChain);
    $('empty').querySelector('h3').textContent=c&&!c.complete?'Research is incomplete on '+c.name:'No assets in this view';
    $('empty').querySelector('p').textContent=c&&!c.complete?'This chain has not been fully checked. Missing data does not mean a zero balance.':'Choose another chain or lower the minimum value.';
  }else{$('empty').querySelector('h3').textContent=w.analysed_at&&!(w.asset_count??w.assets.length)?'No holdings recorded':'No assets in this view';$('empty').querySelector('p').textContent=w.analysed_at?(!(w.asset_count??w.assets.length)?'No positive balances were found in the checked networks. Refresh holdings to check again.':'Choose another chain or lower the minimum value.'):'Your wallet is saved. Use Refresh holdings to check its assets.';}
  bindImages();
}
function timeRange(range){return range?.from?stamp(range.from)+(range.to!==range.from?' – '+stamp(range.to):''):'Not recorded';}
function venueMark(venue){
  const file=({'Mint Club':'mintclub.png',Uniswap:'uniswap.svg',Aerodrome:'aerodrome.svg',Aero:'aerodrome.svg',PancakeSwap:'pancakeswap.png'})[venue];
  return file?`<img class="venue-logo" src="/venues/${file}" width="18" height="18" alt="${escapeHTML(venue)}">`:'<span class="venue-mark" aria-hidden="true">↗</span>';
}
let tokenPoolPage=0,tokenPoolKey=null;
const expandedLists=new Set(),listLimit=10;
const tokenPoolPageSize=5;
function tokenMarkets(token){
  if(tokenPoolKey!==token.id){tokenPoolKey=token.id;tokenPoolPage=0;}
  const pools=token.market_pools||[],curve=(token.links||[]).find(l=>l.label==='Mint Club'&&token.curve_reserve),rows=[...(curve?[{curve:true,url:curve.url,observed_at:token.curve_reserve.observed_at}]:[]),...pools];
  const size=tokenPoolPageSize,pages=Math.max(1,Math.ceil(rows.length/size));tokenPoolPage=Math.min(tokenPoolPage,pages-1);
  const used=new Set((token.wallets||[]).flatMap(w=>{const q=w.asset?.sell_out;return [q?.pool,q?.legs?.[0]?.pool].filter(Boolean).map(p=>p.toLowerCase());}));
  const largest=token.environment==='testnet'?0:Math.max(0,...pools.map(pool=>pool.liquidity_usd||0));
  const list=rows.slice(tokenPoolPage*size,tokenPoolPage*size+size).map(pool=>{
    const pair=pool.curve?[{symbol:token.symbol,image_url:token.image_url,address:token.address},token.curve_reserve]:(pool.pair||[]);
    const label=pair.length?pair.map(c=>c.symbol||'?').join(' / '):'Recorded pool';
    const venue=pool.curve?'Mint Club':pool.venue,versions=pool.curve?'Bonding curve':(pool.version_labels||[]).filter(v=>/^v[234]$/i.test(v)).join(' · ');
    const fee=Number.isFinite(pool.fee_bps)?' · '+Number((pool.fee_bps/100).toFixed(4))+'%':'';
    const amount=pool.curve?quantity(token.curve_reserve.amount)+' '+escapeHTML(token.curve_reserve.symbol):money(token.environment==='testnet'?null:pool.liquidity_usd);
    // A phone row has no room for fourteen digits. It shows the short figure; the row title keeps the exact one.
    const short=!pool.curve&&token.environment!=='testnet'&&pool.liquidity_usd>=100000?'$'+new Intl.NumberFormat('en-US',{notation:'compact',maximumFractionDigits:2}).format(pool.liquidity_usd):'';
    const url=pool.url?safeURL(pool.url):'#',linked=url!=='#',tag=linked?'a':'div';
    const evidence=(pool.curve?'Shared reserve':shortAddress(String(pool.pool||'')))+(short?' · Liquidity '+amount:'')+' · '+(pool.observed_at?'Observed '+stamp(pool.observed_at):'Observation time unavailable');
    return `<${tag} class="market-row" ${linked?`href="${escapeHTML(url)}" target="_blank" rel="noopener noreferrer" aria-label="Open ${escapeHTML(label)} on ${escapeHTML(venue)}"`:''} title="${escapeHTML(evidence)}"><span class="pool-art" aria-hidden="true">${pair.map(c=>coinIcon({...c,chain_id:token.chain_id})).join('')}</span><span class="market-name"><strong>${escapeHTML(label)}</strong><small>${venueMark(venue)}${escapeHTML(venue)}${versions?' · '+escapeHTML(versions):''}${fee}</small></span><span class="market-size">${pool.curve||token.environment==='testnet'?'':shareBar(pool.liquidity_usd,largest,label+' liquidity against the largest recorded pool')}</span><span class="market-flag">${used.has(String(pool.pool).toLowerCase())?'<span class="chip" title="A saved sell estimate uses this pool.">Quoted</span>':''}</span><span class="market-value"><strong>${short?`<span class="num-full">${amount}</span><span class="num-short" aria-hidden="true">${short}</span>`:amount}</strong><small>${pool.curve?'Curve backing':'Liquidity'}</small></span><span class="market-arrow" aria-hidden="true">${linked?'↗':''}</span></${tag}>`;
  }).join('');
  const pager=pages>1?`<div class="mini-pager"><span>${tokenPoolPage*size+1}–${Math.min((tokenPoolPage+1)*size,rows.length)} of ${rows.length}</span><button type="button" class="icon-button" data-token-pool-page="prev" aria-label="Previous markets" ${tokenPoolPage===0?'disabled':''}>‹</button><button type="button" class="icon-button" data-token-pool-page="next" aria-label="More markets" ${tokenPoolPage===pages-1?'disabled':''}>›</button></div>`:'';
  const via=token.market_via?.symbol;
  const about=(via?escapeHTML(token.symbol)+' has no contract of its own. These are saved pools of '+escapeHTML(via)+' and direct pairs. ':'')+(token.market_scope==='workspace'?'Saved markets across this workspace. ':'')+(curve?'Pool liquidity and curve backing are shared market funds, excluded from wallet totals.':'Saved observations. Liquidity can change. A recorded pool does not establish sellability.');
  return `<section class="token-markets" aria-labelledby="token-markets-title"><div class="section-heading"><div class="section-title"><h2 id="token-markets-title">Markets <span class="count-badge">${rows.length}</span></h2>${via?`<span class="chip">via ${escapeHTML(via)}</span>`:''}${infoTip('About these markets','<p>'+about+'</p>')}</div>${pager}</div>${list?'<div class="market-list">'+list+'</div>':'<p class="panel-empty">No markets recorded.</p>'}</section>`;
}
function accountCard(row,token,total){
  const a=row.asset,value=token?a?.value_usd:row.value_usd;
  const chevron='<svg class="ui-icon" viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="m7 10 5 5 5-5"/></svg>';
  if(token&&a){
    const position={...a,id:token.id,environment:token.environment},q=position.sell_out;
    const output=q?quantity(q.output_amount)+' '+escapeHTML(q.output_symbol||shortAddress(q.output_address)):null;
    return `<article class="holder-row position-card"><a class="holder-name account-card-heading" href="#/wallet/${escapeHTML(row.key)}" aria-label="Open ${escapeHTML(row.name)} holdings">${walletAvatar(row.address)}<strong>${escapeHTML(row.name)}</strong></a><span class="holder-balance" title="${escapeHTML(a.balance)}"><span class="mobile-label">Balance</span>${quantity(a.balance)}</span><span class="holder-share">${shareBar(value,total,row.name+' share of this token')}</span><span class="holder-value"><span class="mobile-label">Value</span>${money(value)}</span><span class="holder-sell"><span class="mobile-label">Sell-out est.</span>${sellOutValue(position,false)}</span><details class="position-details" data-disclosure-key="position:${escapeHTML(token.id)}:${escapeHTML(row.key)}"><summary aria-label="Position details for ${escapeHTML(row.name)}" title="Position details">${chevron}</summary><div class="holder-detail">${q?`<div class="position-output"><span>${q.valuation==='reserve_reference'?'Mint Club redemption':'Full-balance route'}</span><strong title="${escapeHTML(q.output_amount)}">Receive ${output}</strong></div>`:''}<p>${escapeHTML(sellOutNote(position))}</p><dl class="position-evidence"><div><dt>Wallet</dt><dd>${escapeHTML(shortAddress(row.address))}</dd></div><div><dt>Unit price</dt><dd>${token.environment==='testnet'?'Testnet':unitPrice(a.price?.usd)+' · '+escapeHTML(a.price?.basis||'No price')}</dd></div>${q?`<div><dt>Quote block</dt><dd>${escapeHTML(q.block_number)}${q.royalty_included?' · After royalty':''}</dd></div>`:''}<div><dt>Holdings checked</dt><dd>${stamp(row.balance_observed_at||row.analysed_at)}</dd></div><div><dt>Price checked</dt><dd>${a.price?.observed_at?stamp(a.price.observed_at):'Not recorded'}</dd></div><div><dt>Coverage</dt><dd>${escapeHTML(row.coverage)}</dd></div></dl></div></details></article>`;
  }
  const meta=token?escapeHTML(row.status):integer(row.position_count)+(row.position_count===1?' token':' tokens')+(row.unpriced_count?' · '+integer(row.unpriced_count)+' unpriced':'');
  return `<article class="holder-row"><a class="holder-name account-card-heading" href="#/wallet/${escapeHTML(row.key)}" aria-label="Open ${escapeHTML(row.name)} holdings" title="${escapeHTML(shortAddress(row.address)+' · '+row.coverage+' · Analysis '+stamp(row.analysed_at))}">${walletAvatar(row.address)}<span class="rank-label"><strong>${escapeHTML(row.name)}</strong><small class="account-meta">${meta}</small></span></a><span class="holder-share">${shareBar(value,total,row.name+' share of this network')}</span><span class="holder-value account-position">${money(value)}</span></article>`;
}
function aggregateRow(a){
  return `<tr class="holding-summary" data-asset-id="${escapeHTML(a.id)}"><td><a class="token-name token-link" href="${tokenHref(a.id)}" aria-label="Open ${escapeHTML(a.symbol)} token overview">${coinIcon(a)}<div class="coin-title"><div class="symbol">${escapeHTML(a.symbol)}${policyBadge(a)}</div><div class="token-description">${escapeHTML(a.archived?'Archived observation':a.is_native?'Native asset':a.name)}</div></div></a></td><td><span class="mobile-label">Total balance</span><span class="amount" title="${escapeHTML(a.balance)}">${quantity(a.balance)}</span></td><td><span class="mobile-label">Wallets</span><span class="amount">${a.wallet_count}</span></td><td><span class="mobile-label">Value</span><span class="token-value">${money(a.value_usd)}</span>${a.included_in_totals===false?'<div class="price-basis">Reported · not in totals</div>':''}${a.unpriced_count?`<div class="price-basis">${a.unpriced_count} unpriced</div>`:''}</td><td><span class="mobile-label">Sell-out est.</span>${sellOutValue(a)}</td><td class="visibility-cell">${policyActions(a)}</td></tr>`;
}
function renderNetworkTokens(network){
  const search=tokenSearch.trim().toLowerCase();
  const recorded=state.paged?(routeData.page?.assets||[]):state.details.tokens.filter(a=>a.chain_id===network.id);
  const assets=recorded.filter(a=>networkStatus==='all'||(a.portfolio_status||'portfolio')===networkStatus).filter(a=>(minimum===0||(a.value_usd!=null&&a.value_usd>=minimum))&&(!search||[a.symbol,a.name,a.address||'native'].some(s=>s.toLowerCase().includes(search))));
  if(typeof networkSort!=='undefined'&&networkSort==='sell_out')assets.sort((a,b)=>(saleValue(b)??-1)-(saleValue(a)??-1)||a.id.localeCompare(b.id));
  $('network-visible-count').textContent=state.paged?(routeData.page?.matched_count??0):assets.length;
  if(state.paged)renderPagination('network',routeData.page,100);
  $('network-token-body').innerHTML=assets.map(aggregateRow).join('');
  $('network-token-table').hidden=assets.length===0;$('network-token-empty').hidden=assets.length>0;
  if(!assets.length){
    const empty=KiraView.networkEmpty(network,state.paged?(network.unique_asset_count||0):recorded.length);
    $('network-token-empty').innerHTML=`<h3>${escapeHTML(empty.title)}</h3><p>${escapeHTML(empty.message)}</p>${empty.activity?'<a class="quiet-button" href="#/activity">View Activity</a>':''}`;
  }
  bindImages();
}
function explorerLink(token){
  const link=token.is_native?null:token.links?.find(l=>l.label==='Explorer');
  if(!link||safeURL(link.url)==='#')return '';
  const known=token.chain_id===8453||token.chain_id===84532?'BaseScan':token.chain_id===1||token.chain_id===11155111?'Etherscan':'Explorer';
  return `<a class="explorer-link" href="${escapeHTML(safeURL(link.url))}" target="_blank" rel="noopener noreferrer" aria-label="View ${escapeHTML(token.symbol)} on ${known}"><img src="/explorers/etherscan.png" width="18" height="18" alt="">${known}<span aria-hidden="true">↗</span></a>`;
}
function renderDetail(){
  const context=typeof FolderUI!=='undefined'?(FolderUI.view()||state):state;
  const disclosures=typeof savedDisclosures==='function'?savedDisclosures($('detail-view')):null;
  const token=selectedView==='token'?(state.paged?routeData.token:state.details.tokens.find(a=>a.id===selectedToken)):null;
  const network=token?.network||(state.paged?routeData.network:state.details.networks.find(c=>c.id===selectedNetwork));
  const record=selectedView==='token'?token:network;
  if(!record){
    renderBreadcrumb([...(typeof FolderUI!=='undefined'?FolderUI.breadcrumb():[{label:'Home',href:'#/home'}]),{label:'Research detail'}]);$('sync-label').textContent='Latest recorded research';
    $('detail-view').innerHTML=routeLoading?'<div class="empty"><h3>Loading saved detail…</h3></div>':'<div class="empty"><h3>No recorded detail for this selection</h3><p>Return Home or retry the saved research above.</p></div>';
    document.title='Research detail · Wallets';return;
  }
  const label=token?token.symbol:network.name,isTestnet=record.environment==='testnet';
  renderBreadcrumb([...(typeof FolderUI!=='undefined'?FolderUI.breadcrumb():[{label:'Home',href:'#/home'}]),...(token?[{label:network.name,href:networkHref(network.id)}]:[]),{label}]);
  $('sync-label').textContent='Across '+context.wallets.length+' registered wallets';document.title=label+' · Kira Wallet';
  const excluded=token&&token.included_in_totals===false;
  const note=excluded?'Reported spot estimate, excluded from portfolio totals. Sellability unverified.':isTestnet?'Testnet holdings are excluded from USD totals.':'Recorded spot estimates. '+integer(record.unpriced_count)+' unpriced holdings are excluded.';
  const value=excluded?record.value_usd:record.capital_allocation?record.capital_allocation.known_value_usd:record.value_usd;
  const address=token?.address?`<span class="address-chip"><code title="${escapeHTML(token.address)}">${escapeHTML(shortAddress(token.address))}</code><button type="button" class="icon-button" data-copy-record="${escapeHTML(token.address)}" aria-label="Copy token address" title="Copy token address"><svg class="ui-icon" viewBox="0 0 24 24" fill="none" aria-hidden="true"><rect x="8" y="8" width="11" height="12" rx="2"/><path d="M15 8V5H4v12h4"/></svg></button></span>`:'';
  const header=`<section class="detail-heading page-bar"><div class="detail-identity">${token?coinIcon(token):chainIcon(network)}<div><div class="token-title-line"><h1>${escapeHTML(label)}</h1>${isTestnet?'<span class="chip">Testnet</span>':''}${token?policyBadge(token):''}</div>${token?`<p class="detail-sub"><span>${escapeHTML(token.name)}</span><a href="${networkHref(network.id)}">${escapeHTML(network.name)}</a>${address}${explorerLink(token)}</p>`:''}</div></div>${!token?`<label class="chain-select"><span class="sr-only">Open another network</span><select id="network-switch">${context.details.networks.map(c=>({...c,value_usd:c.capital_allocation?c.capital_allocation.known_value_usd:c.value_usd})).sort((a,b)=>(b.value_usd??-1)-(a.value_usd??-1)).map(c=>`<option value="${c.id}" data-chain-id="${c.id}" ${c.id===network.id?'selected':''}>${escapeHTML(c.name)}${c.environment==='testnet'?' · Testnet':''}</option>`).join('')}</select></label>`:''}</section>`;
  const heldPrices=token&&!isTestnet?token.wallets.filter(r=>r.asset).map(r=>r.asset.price?.usd).filter(p=>p!=null):[];
  const low=heldPrices.length?Math.min(...heldPrices):null,high=heldPrices.length?Math.max(...heldPrices):null;
  const basis=token?token.wallets.find(r=>r.asset?.price?.usd!=null)?.asset.price.basis:null;
  const facets=token?`<span class="chip" title="${escapeHTML(token.balance||'')}"><strong>${compactQuantity(token.balance)}</strong> ${escapeHTML(token.symbol)}</span><span class="chip"><strong>${integer(record.wallet_count)}</strong> of ${integer(context.wallets.length)} wallets</span>`:`<span class="chip"><strong>${integer(network.unique_asset_count)}</strong> ${network.unique_asset_count===1?'token':'tokens'}</span><span class="chip"><strong>${integer(record.wallet_count)}</strong> of ${integer(context.wallets.length)} wallets</span>${policyNotice(record.asset_policy_summary)}`;
  const priceFigure=token?`<div class="figure"><span class="summary-label">Price</span><strong class="figure-value">${isTestnet?'—':unitPrice(low)}</strong><span class="stat-note">${isTestnet?'Testnet':low!==high?'to '+unitPrice(high):escapeHTML(basis||'No price')}</span></div>`:'';
  const stats=`<section class="hero detail-hero" aria-label="${token?'Token':'Network'} summary"><div class="hero-figures"><div class="figure figure-primary"><div class="summary-label">${excluded?'Reported value':'Value'}${infoTip('About this value','<p>'+escapeHTML(note)+'</p><p>Analysis '+escapeHTML(timeRange(record.analysis_times))+'</p><p>Prices '+escapeHTML(timeRange(record.price_times))+'</p>')}</div><div class="total-value">${money(value)}</div><div class="chip-row">${facets}</div></div><div class="figure sell-figure">${sellSummary(record.sell_out_summary,walletTokenValue(record.capital_allocation,record.value_usd))}</div>${priceFigure}</div></section>`;
  let facts='';
  if(token){
    facts=`<div class="detail-facts detail-identity-facts"><section class="fact-panel"><h2>Token identity</h2><div class="contract-address">${escapeHTML(token.address||'Native asset · chain '+token.chain_id)}</div><dl><div><dt>Recorded price${low!==high?' range':''}</dt><dd>${unitPrice(low)}${low!==high?' – '+unitPrice(high):''}</dd></div><div><dt>Price observations</dt><dd>${timeRange(token.price_times)}</dd></div></dl></section></div>`;
  }
  const heldWallets=token?record.wallets.filter(r=>r.asset).sort((a,b)=>(b.asset.value_usd??-1)-(a.asset.value_usd??-1)||Number(b.asset.balance)-Number(a.asset.balance)||a.name.localeCompare(b.name)):record.wallets.filter(r=>r.has_holdings||r.position_count>0).sort((a,b)=>(b.value_usd??-1)-(a.value_usd??-1)||a.name.localeCompare(b.name));
  const otherWallets=token?[]:record.wallets.filter(r=>!r.has_holdings&&!(r.position_count>0));
  const walletTotal=token?heldWallets.reduce((sum,r)=>sum+(r.asset.value_usd||0),0):record.value_usd;
  const listKey=(token?'holders:':'wallets:')+record.id,listOpen=expandedLists.has(listKey);
  const walletHead=`<div class="holder-head" aria-hidden="true"><span>Wallet</span>${token?'<span>Balance</span>':''}<span></span><span>Value</span>${token?'<span>Sell-out est.</span>':''}</div>`;
  const accounts=`<section class="detail-accounts"><div class="section-heading"><div class="section-title"><h2>${token?'Holders':'Wallets'} <span class="count-badge">${heldWallets.length}</span></h2>${infoTip('About this list','<p>'+(token?'Recorded holders only. Independent sell estimates exclude gas. Shared liquidity can change combined proceeds.':'Mainnet totals exclude unpriced assets. Review wallet coverage for missing checks.')+'</p>')}</div></div>${heldWallets.length?`<div class="holder-table ${token?'holder-table-token':''}" data-limited ${listOpen?'data-expanded':''}>${walletHead}${heldWallets.map(r=>accountCard(r,token,walletTotal)).join('')}</div>${heldWallets.length>listLimit?`<button type="button" class="text-button rank-more" data-rank-more="${escapeHTML(listKey)}" aria-expanded="${listOpen}">${listOpen?'Show top '+listLimit:'Show all '+heldWallets.length}</button>`:''}`:'<p class="panel-empty">No positive holdings recorded. Missing records remain unknown.</p>'}${otherWallets.length?`<details class="other-wallets" data-disclosure-key="network-coverage:${record.id}" ${heldWallets.length?'':'open'}><summary>Other registered wallets <span>${otherWallets.length}</span></summary><p class="detail-note">No holdings recorded on this network. Incomplete checks remain unknown.</p><div class="holder-table">${otherWallets.map(r=>accountCard(r,token,walletTotal)).join('')}</div></details>`:''}</section>`;
  const holdings=token?'':`<section class="holdings"><div class="holdings-toolbar"><h2 class="sr-only">Tokens <span id="network-visible-count"></span></h2><div class="filters"><label><span class="sr-only">Network asset status</span><select id="network-token-status" aria-label="Network asset status"><option value="portfolio">Portfolio</option><option value="review">Needs review</option><option value="excluded">Hidden</option><option value="all">All recorded</option></select></label><label><span class="sr-only">Network token order</span><select id="network-token-sort"><option value="value">Value: high to low</option><option value="sell_out">Sell-out estimate: high to low</option></select></label><label class="token-search"><span class="sr-only">Search network tokens</span><input id="network-token-search" type="search" placeholder="Search tokens" value="${escapeHTML(tokenSearch)}"></label><div class="segment" role="group" aria-label="Minimum combined token value" title="Filters by combined token value across wallets. Summary totals include all recorded holdings.">${[0,5,10].map(n=>`<button data-min="${n}" aria-pressed="${n===minimum}">${n?'≥ $'+n:'All'}</button>`).join('')}</div></div></div><div id="network-token-table" class="table-wrap"><table class="token-table holdings-table sale-table"><colgroup><col><col><col><col><col><col class="visibility-column"></colgroup><thead><tr><th scope="col">Token</th><th scope="col">Total balance</th><th scope="col">Wallets</th><th scope="col">Value</th><th scope="col" title="Saved quotes or marked market references, valued in USD. Gas excluded.">Sell-out est.</th><th scope="col" class="visibility-cell"><span class="sr-only">Visibility</span></th></tr></thead><tbody id="network-token-body"></tbody></table></div><div id="network-pagination" class="pagination" hidden><button class="quiet-button" data-page="network-prev" type="button">Previous</button><span id="network-page"></span><button class="quiet-button" data-page="network-next" type="button">Next</button></div><div id="network-token-empty" class="empty" hidden><h3>No tokens in this view</h3><p>Lower the minimum value or clear your search. Missing coverage does not mean zero holdings.</p></div></section>`;
  const riskOpen=token&&(token.included_in_totals===false||(token.valuation_policy?.reasons||[]).length>0||(token.risk_check?.flags||[]).length>0);
  const risk=token?`<details class="record-risk" data-disclosure-key="risk:${escapeHTML(token.id)}:${escapeHTML(token.portfolio_status||'portfolio')}:${riskOpen?'warning':'routine'}:${escapeHTML(token.risk_check?.observed_at||'')}" ${riskOpen?'open':''}><summary><strong>Valuation &amp; risk</strong>${riskOpen?'<span class="chip warn">Review warnings</span>':''}</summary>${policyPanel(token)}</details>`:'';
  const reference=token?`<details class="record-reference" data-disclosure-key="reference:${escapeHTML(token.id)}"><summary>Token details</summary>${facts}</details>`:'';
  const content=token?accounts+tokenMarkets(token)+risk+reference:typeof networkPanels==='function'?networkPanels(network,holdings,accounts):holdings+accounts;
  $('detail-view').innerHTML=header+stats+content;
  if(disclosures)restoreDisclosures($('detail-view'),disclosures);
  if(token)for(const button of $('detail-view').querySelectorAll('[data-token-pool-page]'))button.addEventListener('click',()=>{const direction=button.dataset.tokenPoolPage;tokenPoolPage+=direction==='next'?1:-1;renderDetail();$('detail-view').querySelector('[data-token-pool-page="'+direction+'"]')?.focus({preventScroll:true});});
  if(!token){$('network-token-status').value=networkStatus;$('network-token-status').addEventListener('change',e=>{networkStatus=e.target.value;networkOffset=0;loadRoute();});$('network-token-sort').value=networkSort;$('network-token-sort').addEventListener('change',e=>{networkSort=e.target.value;networkOffset=0;loadRoute();});$('network-switch').addEventListener('change',e=>navigate(networkHref(e.target.value)));$('network-token-search').addEventListener('input',e=>{tokenSearch=e.target.value;networkOffset=0;clearTimeout(networkSearchTimer);networkSearchTimer=setTimeout(()=>loadRoute(),160);});renderNetworkTokens(network);}
  // This view was rebuilt, so its allocation panel is gone. Paging markets or opening a list must not drop it.
  if(typeof CapitalUI!=='undefined')CapitalUI.render();
  bindImages();
}
async function poll(){
  if(busy)return;busy=true;
  try{
    const response=await fetch('/api/state',{headers:etag?{'If-None-Match':etag}:{},cache:'no-cache',signal:AbortSignal.timeout(9000)});
    if(response.status===304){$('connection').textContent='Connected';return true;}
    if(!response.ok)throw new Error('Research unavailable');
    const data=await response.json();const signature=response.headers.get('ETag');
    const wasLoaded=state!==null;
    state=data;etag=signature;$('load-error').hidden=true;$('content').hidden=false;$('connection').textContent='Connected';$('demo-badge').hidden=data.demo!==true;
    if(signature!==currentSignature){routeData={};routeLoadedKey=null;renderView();currentSignature=signature;await loadRoute();if(wasLoaded)toast('Saved research updated');}
    return true;
  }catch{ $('connection').textContent='Reconnecting';if(!state){$('load-error').hidden=false;$('content').hidden=true;}return false; }
  finally{busy=false;}
}
document.querySelector('.skip-link').addEventListener('click',e=>{e.preventDefault();$('main').focus();$('main').scrollIntoView({block:'start'});});
$('brand-home').addEventListener('click',e=>{e.preventDefault();goHome();});
for(const id of ['wallet-list','wallet-cards'])$(id).addEventListener('click',e=>{const b=e.target.closest('[data-wallet]');if(b)selectWallet(b.dataset.wallet);});
$('chain-filter').addEventListener('change',e=>{selectedChain=e.target.value;walletOffset=0;state.paged?loadRoute():renderHoldings();});
document.addEventListener('click',e=>{const b=e.target.closest('[data-min],[data-clear-value-filter]');if(b){minimum=b.hasAttribute('data-clear-value-filter')?0:Number(b.dataset.min);if(typeof state!=='undefined'&&state?.paged){walletOffset=0;networkOffset=0;loadRoute();}else if(selectedView==='network')renderDetail();else renderHoldings();}});
$('copy-address').addEventListener('click',async()=>{try{await navigator.clipboard.writeText(currentWallet().address);toast('Address copied');}catch{toast('Select the address to copy it');}});

document.addEventListener('click',event=>{for(const tip of document.querySelectorAll('details.info-tip[open]'))if(!tip.contains(event.target))tip.open=false;});
$('home-network-more').addEventListener('click',()=>{$('network-allocation').toggleAttribute('data-expanded');renderHome();});
document.addEventListener('click',event=>{const more=event.target.closest('[data-rank-more]');if(!more)return;const key=more.dataset.rankMore;if(!expandedLists.delete(key))expandedLists.add(key);renderDetail();document.querySelector('[data-rank-more="'+CSS.escape(key)+'"]')?.focus({preventScroll:true});});
document.addEventListener('keydown',event=>{if(event.key!=='Escape')return;for(const tip of document.querySelectorAll('details.info-tip[open]')){tip.open=false;tip.querySelector('summary').focus();}});
window.addEventListener('hashchange',readRoute);
readRoute();

$('wallet-prev').addEventListener('click',()=>{walletOffset=Math.max(0,walletOffset-100);loadRoute();});
$('wallet-next').addEventListener('click',()=>{if(routeData.wallet?.next_offset!=null){walletOffset=routeData.wallet.next_offset;loadRoute();}});
document.addEventListener('click',event=>{const action=event.target.closest('[data-page]')?.dataset.page;if(action==='network-prev'){networkOffset=Math.max(0,networkOffset-100);loadRoute();}else if(action==='network-next'&&routeData.page?.next_offset!=null){networkOffset=routeData.page.next_offset;loadRoute();}});

function policyBadge(asset){
  const status=asset.portfolio_status||'portfolio',reasons=asset.valuation_policy?.reasons||[];
  if(status==='portfolio'&&!reasons.length)return '';
  const label=status==='review'?'Needs review':status==='excluded'?'Hidden':'Included · warning';
  return `<span class="policy-badge ${escapeHTML(status)}" title="${escapeHTML(reasons.join(' ')||'Excluded by your local preference.')}">${label}</span>`;
}
function policyNotice(summary){
  if(!summary)return '';
  const review=summary.review_count||0,excluded=summary.excluded_count||0;
  return (review?`<button class="chip warn" type="button" data-policy-list="review" title="Not in totals. Open these assets.">${integer(review)} ${review===1?'needs review':'need review'}</button>`:'')+(excluded?`<button class="chip" type="button" data-policy-list="excluded" title="Hidden assets are not in totals. Open them.">${integer(excluded)} hidden</button>`:'');
}
function policyButton(asset,mode,label){return `<button class="quiet-button" type="button" data-token-policy="${mode}" data-token-id="${escapeHTML(asset.id)}" data-previous-mode="${escapeHTML(asset.valuation_policy?.mode||'auto')}" ${typeof TokenVisibility!=='undefined'&&TokenVisibility.busy?'disabled':''}>${label}</button>`;}
function visibilityIcon(restore=false){
  return `<svg viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12Z"/><circle cx="12" cy="12" r="3"/>${restore?'':'<path d="m3 3 18 18"/>'}</svg>`;
}
function tokenSelection(asset){
  return typeof TokenManager!=='undefined'&&TokenManager.active&&selectedView==='tokens'?TokenManager.checkbox(asset):'';
}
function policyActions(asset){
  if(typeof localSession==='undefined'||!localSession?.controls)return '';
  if(typeof TokenManager!=='undefined'&&TokenManager.active&&selectedView==='tokens')return '';
  const restore=asset.portfolio_status==='excluded',label=(restore?'Restore ':'Hide ')+asset.symbol+' on '+(asset.network?.name||'chain '+asset.chain_id);
  const busy=typeof TokenVisibility!=='undefined'&&TokenVisibility.busy;
  return `<button class="visibility-button" type="button" data-token-policy="${restore?'auto':'exclude'}" data-token-id="${escapeHTML(asset.id)}" data-previous-mode="${escapeHTML(asset.valuation_policy?.mode||'auto')}" aria-label="${escapeHTML(label)}" title="${escapeHTML(label)}" ${busy?'disabled':''}>${visibilityIcon(restore)}</button>`;
}
function policyPanel(asset){
  const reasons=asset.valuation_policy?.reasons||[],risk=asset.risk_check,enabled=typeof localSession!=='undefined'&&localSession?.controls;
  const observations=[...reasons,...(risk?.flags||[])];
  let status=!risk?'Not checked':risk.status==='flagged'?'Risk reported':risk.status==='no_high_risk_flags_reported'?'No high-risk flags reported · not a safety guarantee':'Unknown';
  if(risk?.last_attempt)status+=' · latest attempt unavailable; earlier observations retained';
  return `<section class="token-policy-panel fact-panel" aria-label="Asset valuation and risk"><div class="section-heading"><h2>Valuation & risk</h2>${policyBadge(asset)}</div><p>${asset.included_in_totals===false?'This asset is excluded from portfolio and sell-out totals. Its reported estimates and holdings are preserved.':'Included in portfolio totals. A reported price does not establish sale proceeds.'}</p>${typeof FolderUI!=='undefined'&&FolderUI.id?'<p class="detail-note">Visibility changes apply across all registered wallets.</p>':''}${observations.length?'<ul>'+observations.map(text=>'<li>'+escapeHTML(text)+'</li>').join('')+'</ul>':''}<dl><div><dt>Risk check</dt><dd>${escapeHTML(status)}</dd></div><div><dt>Sellability</dt><dd>Unverified · estimates do not test token transfer restrictions</dd></div>${risk?`<div><dt>Source & time</dt><dd><a href="${escapeHTML(safeURL(risk.source))}" target="_blank" rel="noopener noreferrer">GoPlus</a> · ${stamp(risk.observed_at)}</dd></div>`:''}</dl>${enabled?`<div class="policy-actions">${asset.portfolio_status!=='excluded'?policyButton(asset,'exclude','Hide token'):policyButton(asset,'auto','Restore token')}${asset.included_in_totals===false?policyButton(asset,'include','Include in totals'):asset.valuation_policy?.mode==='include'?policyButton(asset,'auto','Use automatic classification'):''}${asset.address&&!state.demo?`<button class="quiet-button" type="button" data-token-risk="${escapeHTML(asset.id)}">${risk?'Recheck risk':'Check risk'}</button>`:''}</div>${asset.address&&!state.demo?'<p class="detail-note">Check risk sends only this chain and contract address to GoPlus. It does not connect your wallet or execute a transaction.</p>':''}`:''}<details class="detail-note"><summary>Automatic review rules</summary><p>Automatic review uses saved evidence. Exceeding twice the largest reported pool liquidity with at least $10,000 in spot value and no saved sale quote is a valuation warning, not a scam verdict.</p></details></section>`;
}
function openPolicyList(status){
  navigate(typeof FolderUI!=='undefined'?FolderUI.path('tokens'):'#/tokens');readRoute();
  $('all-token-status').value=status;$('all-token-search').value='';catalogPage=1;catalogMinimum=0;
  if(typeof KiraSelect!=='undefined')KiraSelect.refresh();
  state?.paged?loadRoute(true):renderCatalog();
}
document.addEventListener('click',async event=>{
  const list=event.target.closest('[data-policy-list]');if(list){openPolicyList(list.dataset.policyList);return;}
  const button=event.target.closest('[data-token-policy],[data-token-risk]');
  if(!button||button.disabled)return;
  const identity=button.dataset.tokenId||button.dataset.tokenRisk,[chain,address]=identity.split(':');
  if(button.dataset.tokenPolicy){
    const keyboard=event.detail===0,controls=[...document.querySelectorAll('.visibility-button')].filter(node=>node.offsetParent!==null),index=controls.indexOf(button);
    await TokenVisibility.change([{id:identity,mode:button.dataset.tokenPolicy,previous:button.dataset.previousMode||'auto'}]);
    if(keyboard&&index>=0){const remaining=[...document.querySelectorAll('.visibility-button')].filter(node=>node.offsetParent!==null);(remaining[Math.min(index,remaining.length-1)]||$('manage-tokens')).focus({preventScroll:true});}return;
  }
  button.disabled=true;const label=button.textContent;button.textContent='Checking…';
  try{
    await submitOperation('token.riskCheck',{chain_id:Number(chain),address});
    await poll();await loadRoute(true);toast('Risk observation saved. Review its source and limits.');
  }catch(error){toast(error.message,6000);}
  finally{if(button.isConnected){button.disabled=false;button.textContent=label;}}
});
