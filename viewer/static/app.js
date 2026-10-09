'use strict';
const $ = id => document.getElementById(id);
const escapeHTML = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
let state = null, selectedWallet = localStorage.getItem('wallet-selection'), selectedView = localStorage.getItem('wallet-view') === 'wallet' ? 'wallet' : 'home', selectedChain = 'all', minimum = 0, etag = null, currentSignature = null, busy = false;
let selectedToken = null, selectedNetwork = null, tokenSearch = '';
if (![0,5,10].includes(minimum)) minimum=0;
const money = value => value == null ? '—' : value > 0 && value < .01 ? '< $0.01' : new Intl.NumberFormat('en-US',{style:'currency',currency:'USD',maximumFractionDigits:2}).format(value);
const unitPrice = value => value == null ? '—' : value === 0 ? '$0.00' : value < .000001 ? '$'+value.toExponential(3) : '$'+new Intl.NumberFormat('en-US',{maximumFractionDigits:value < .01 ? 8 : value < 1 ? 6 : 2}).format(value);
const quantity = raw => raw==null ? '—' : Number(raw)>0&&Number(raw)<.000001 ? Number(raw).toExponential(3) : new Intl.NumberFormat('en-US',{maximumFractionDigits:Number(raw)<1 ? 6 : 3}).format(Number(raw));
const compactQuantity = raw => raw!=null&&Number(raw)>=100000 ? new Intl.NumberFormat('en-US',{notation:'compact',maximumFractionDigits:3}).format(Number(raw)) : quantity(raw);
const shortAddress = address => address.slice(0,6)+'…'+address.slice(-4);
const stamp = raw => raw ? new Date(raw).toLocaleString('en-US',{month:'short',day:'numeric',hour:'2-digit',minute:'2-digit',hour12:false}) : 'Not analysed yet';
const safeURL = raw => {try{const url=new URL(raw,location.origin);return (url.origin===location.origin||url.protocol==='https:') ? url.href : '#';}catch{return '#';}};
const imageHosts = new Set(['mint.club','tokens.1inch.io','coin-images.coingecko.com','fc.hunt.town','mint-club-v2.s3.us-west-2.amazonaws.com','cdn.dexscreener.com']);
const safeImage = raw => {try{const url=new URL(raw);return url.protocol==='https:'&&imageHosts.has(url.hostname)&&!url.username&&!url.password&&(!url.port||url.port==='443') ? url.href : null;}catch{return null;}};
const walletGlyph = '<svg viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="M4 6.5h13a2 2 0 0 1 2 2V18a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V6a2 2 0 0 1 1.4-1.9L15 1.8v4.7"/><path d="M19 10h-4a2 2 0 0 0 0 4h4"/><path d="M15.5 12h.01"/></svg>';

const arrowGlyph = '<svg class="ui-icon" viewBox="0 0 24 24" fill="none" aria-hidden="true" focusable="false"><path d="M7 17 17 7M7 7h10v10"/></svg>';
function toast(message){$('toast').textContent=message;$('toast').classList.add('show');setTimeout(()=>$('toast').classList.remove('show'),2200);}
function currentWallet(){return state?.wallets.find(w=>w.key===selectedWallet);}
const tokenHref = id => '#/token/'+id.split(':').map(encodeURIComponent).join('/');
const networkHref = id => '#/network/'+id;
function navigate(hash){if(typeof setWorkspacePane==='function')setWorkspacePane('portfolio');if(location.hash===hash)readRoute();else location.hash=hash;}
let routeIdentity=null;
function readRoute(){
  const identity=location.hash||'#/home';
  if(identity!==routeIdentity){selectedChain='all';minimum=0;tokenSearch='';if(typeof resetRouteFilters==='function')resetRouteFilters();routeIdentity=identity;}
  let parts=[];try{parts=location.hash.replace(/^#\/?/,'').split('/').map(decodeURIComponent);}catch{}
  if(parts[0]==='wallet'&&/^0x[0-9a-f]{40}$/i.test(parts[1]||'')){selectedWallet=parts[1].toLowerCase();selectedView='wallet';selectedChain='all';}
  else if(parts[0]==='network'&&/^\d+$/.test(parts[1]||'')){selectedNetwork=Number(parts[1]);selectedView='network';tokenSearch='';}
  else if(parts[0]==='token'&&/^\d+$/.test(parts[1]||'')&&/^(native|0x[0-9a-f]{40})$/i.test(parts[2]||'')){selectedToken=Number(parts[1])+':'+parts[2].toLowerCase();selectedView='token';}
  else if(['tokens','activity'].includes(parts[0])){selectedView=parts[0];}
  else if(location.hash){selectedView='home';}
  localStorage.setItem('wallet-view',selectedView);if(selectedWallet)localStorage.setItem('wallet-selection',selectedWallet);
  if(state)renderView();window.scrollTo({top:0,behavior:'instant'});
}
function selectWallet(key){
  if(!state?.wallets.some(w=>w.key===key))return;
  const wallet=state.wallets.find(w=>w.key===key);
  navigate(!wallet.analysed_at&&typeof pendingWalletJob==='function'&&pendingWalletJob(wallet)?'#/activity':'#/wallet/'+key);
}
function goHome(){
  navigate('#/home');
}
function renderBreadcrumb(items){
  $('breadcrumbs').innerHTML='<ol>'+items.map(item=>`<li>${item.href?`<a href="${escapeHTML(item.href)}" title="${escapeHTML(item.label)}">${escapeHTML(item.label)}</a>`:`<span aria-current="page" title="${escapeHTML(item.label)}">${escapeHTML(item.label)}</span>`}</li>`).join('')+'</ol>';
}
function renderWallets(){
  $('wallet-count').textContent=state.wallets.length;
  $('wallet-list').innerHTML=state.wallets.map(w=>{
    const active=selectedView==='wallet'&&w.key===selectedWallet;
    const pending=typeof pendingWalletJob==='function'&&pendingWalletJob(w);
    return `<button class="wallet-button ${active?'active':''}" data-wallet="${escapeHTML(w.key)}" aria-label="Select ${escapeHTML(w.name)}" ${active?'aria-current="page"':''}><span class="wallet-glyph">${walletGlyph}</span><span class="wallet-nav-name">${escapeHTML(w.name)}<span class="wallet-nav-address">${pending?'<span class="spinner" aria-hidden="true"></span> Analysing…':escapeHTML(shortAddress(w.address))}</span></span><span class="wallet-arrow" aria-hidden="true">›</span></button>`;
  }).join('');
}
function renderView(){
  if(selectedView==='wallet'){
    const w=currentWallet(),pending=typeof pendingWalletJob==='function'&&pendingWalletJob(w||{key:selectedWallet});
    if(!w||(!w.analysed_at&&pending)){
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
  renderKiraNote();
  if(typeof renderWorkspace==='function')renderWorkspace();
  if(typeof KiraSelect!=='undefined')KiraSelect.refresh();
}
function renderKiraNote(){
  let text='I keep unknown prices and incomplete coverage visible. These are recorded estimates.';
  if(selectedView==='home'){
    const s=state.dashboard;
    text=s.wallet_count?`I have gathered ${s.wallet_count} registered ${s.wallet_count===1?'wallet':'wallets'}. ${s.priced_count} mainnet ${s.priced_count===1?'position has':'positions have'} a price reference; ${s.unpriced_count} remain unpriced. Open a wallet or a network to inspect the recorded evidence.`:'Your notebook is ready. Add a public wallet address to begin recorded research.';
  }else if(selectedView==='wallet'){
    const w=currentWallet();
    if(w){const gaps=w.chains.filter(c=>c.environment==='mainnet'&&(!c.complete||!c.rpc_available)).length;
      text=w.analysed_at?`This wallet has ${w.assets.filter(a=>a.environment==='mainnet').length} recorded mainnet ${w.assets.filter(a=>a.environment==='mainnet').length===1?'position':'positions'}. ${gaps?gaps+(gaps===1?' network still has a coverage gap.':' networks still have coverage gaps.'):'Recorded mainnet coverage is available.'} Unpriced positions stay outside the estimated total.`:'This wallet is registered. Its analysis has not been published yet.';}
  }else if(selectedView==='token'){
    const t=state.details.tokens.find(t=>t.id===selectedToken);
    if(t)text=`This is ${t.symbol} on ${state.details.networks.find(c=>c.id===t.chain_id)?.name||'chain '+t.chain_id}, identified by its chain and contract. I found recorded holdings in ${t.wallet_count} ${t.wallet_count===1?'wallet':'wallets'}. Any curve backing is shared by all holders and excluded from their wallet totals.`;
  }else if(selectedView==='network'){
    const n=state.details.networks.find(n=>n.id===selectedNetwork);
    if(n)text=`${n.name} has ${n.position_count} recorded positions across ${n.wallet_count} holding wallets. The account cards show each wallet's coverage, including missing records. An absent holding is not proof of a zero balance.`;
  }
  $('kira-note-text').textContent=text;
}
function progress(value,total,label){
  return value!=null&&total>0 ? `<progress class="allocation-progress" value="${value}" max="${total}" aria-label="${escapeHTML(label)}">${(value/total*100).toFixed(1)}%</progress>` : '';
}
function share(value,total){return value!=null&&total>0 ? (value/total*100).toFixed(1)+'%' : '—';}
function chainIcon(chain){
  const name=typeof chain==='string'?chain:chain.name;
  const url=safeImage(typeof chain==='string'?state?.details?.networks.find(c=>c.name===name)?.image_url:chain.image_url);
  const cls=name.toLowerCase().split(' ')[0],glyph=name==='Base'?'—':name==='Ethereum'?'◆':name.charAt(0);
  return `<span class="chain-icon ${escapeHTML(cls)}" aria-hidden="true"><span class="chain-fallback">${escapeHTML(glyph)}</span>${url?`<img src="${escapeHTML(url)}" alt="" width="24" height="24" loading="lazy" decoding="async" referrerpolicy="no-referrer" data-chain-image>`:''}</span>`;
}
function renderHome(){
  const s=state.dashboard;
  renderBreadcrumb([{label:'Home'}]);
  $('sync-label').textContent=s.analysed_wallet_count+' of '+s.wallet_count+' '+(s.wallet_count===1?'wallet':'wallets')+' analysed';
  $('home-total').textContent=money(s.known_value_usd);
  $('home-wallet-count').textContent=s.wallet_count;
  $('home-network-count').textContent=s.chain_count;
  $('home-position-count').textContent=s.position_count;
  $('home-wallet-note').textContent=s.wallet_count>s.analysed_wallet_count?(s.wallet_count-s.analysed_wallet_count)+' awaiting analysis':'All registered';
  $('home-position-note').textContent=s.unique_asset_count+' unique '+(s.unique_asset_count===1?'asset':'assets');
  $('home-valuation-note').textContent=s.priced_count ? 'Market and curve spot estimates · '+s.unpriced_count+' unpriced positions excluded' : 'Value appears as priced holdings become available.';
  $('home-empty').hidden=s.wallet_count>0;$('home-details').hidden=s.wallet_count===0;
  renderHomeCoverage();
  const incomplete=state.wallets.some(w=>w.chains.some(c=>c.environment==='mainnet'&&KiraView.coverageGap(c)));
  $('home-coverage-note').textContent='Mainnet holdings only · '+(incomplete?'Research coverage is incomplete.':'Testnets excluded from totals.');
  $('home-price-time').textContent=s.prices_from ? 'Prices '+stamp(s.prices_from)+(s.prices_from!==s.prices_to?' – '+stamp(s.prices_to):'') : '';
  $('wallet-cards').innerHTML=state.wallets.map(w=>{
    const assets=w.assets.filter(a=>a.environment==='mainnet'),unpriced=assets.filter(a=>a.value_usd==null).length;
    const value=w.analysed_at&&assets.some(a=>a.value_usd!=null)?w.known_value_usd:null;
    return `<button class="wallet-card" data-wallet="${escapeHTML(w.key)}" aria-label="Open ${escapeHTML(w.name)} holdings"><span class="wallet-card-heading"><span class="card-wallet-icon">${walletGlyph}</span><span class="wallet-card-identity"><strong>${escapeHTML(w.name)}</strong><span>${escapeHTML(shortAddress(w.address))}</span></span><span class="card-arrow" aria-hidden="true">${arrowGlyph}</span></span><span class="wallet-card-value">${money(value)}</span><span class="wallet-card-meta"><span>${w.analysed_at?assets.length+(assets.length===1?' position · ':' positions · ')+unpriced+' unpriced':'Awaiting analysis'}</span><span>${value!=null?share(value,s.known_value_usd)+' of priced value':''}</span></span>${progress(value,s.known_value_usd,w.name+' share of priced value')}</button>`;
  }).join('');
  $('network-allocation').innerHTML=s.networks.map(c=>`<a class="network-row" href="${networkHref(c.id)}" aria-label="Open ${escapeHTML(c.name)} network overview"><div class="network-row-heading"><span class="network-label">${chainIcon(c.name)}${escapeHTML(c.name)}<span class="detail-arrow" aria-hidden="true">${arrowGlyph}</span></span><span class="network-value">${money(c.value_usd)}</span></div><div class="network-row-meta"><span>${c.position_count} ${c.position_count===1?'position':'positions'}${c.value_usd==null?' · Unpriced':''}</span><span>${share(c.value_usd,s.known_value_usd)}</span></div>${progress(c.value_usd,s.known_value_usd,c.name+' share of priced value')}</a>`).join('')||'<p class="panel-empty">Networks appear after analysis.</p>';
  if(typeof renderHomeTokens==='function')renderHomeTokens();
  bindImages();
}
function renderWallet(){
  const w=currentWallet();if(!w)return;
  $('wallet-name').textContent=w.name;renderBreadcrumb([{label:'Home',href:'#/home'},{label:w.name}]);$('address').textContent=w.address;$('address').title=w.address;
  $('wallet-tags').innerHTML=w.tags.slice(1).map(t=>`<span class="tag">${escapeHTML(t)}</span>`).join(' ');
  $('report-link').hidden=!w.report_url;if(w.report_url)$('report-link').href=safeURL(w.report_url);
  $('total-value').textContent=w.analysed_at?money(w.known_value_usd):'—';
  const partial=w.chains.some(c=>c.environment==='mainnet'&&KiraView.coverageGap(c));
  $('valuation-note').textContent=w.analysed_at?(partial?'Partial portfolio · ':'')+(w.known_value_usd==null?(w.assets.length?'Value is unknown because prices are unavailable.':'No positive holdings recorded · unchecked networks remain unknown.'):'Market and curve spot estimates · excludes unpriced assets'):'Analysis will appear here when it is ready.';
  $('asset-count').textContent=w.assets.length;$('unpriced-count').textContent=w.unpriced_count+' unpriced';
  const mainnets=w.chains.filter(c=>c.environment==='mainnet');
  $('chain-count').textContent=mainnets.filter(c=>c.assets>0).length;
  const coverage=mainnets.filter(c=>c.complete).length;
  $('coverage-note').textContent='Token discovery: '+coverage+' of '+mainnets.length+' mainnets checked';
  $('coverage-note').title='Token discovery and on-chain balance checks are separate. See network coverage details for failures.';
  $('sync-label').textContent=w.analysed_at?'Analysis '+stamp(w.analysed_at):'Awaiting analysis';
  $('price-time').textContent=w.prices_at?'Prices '+stamp(w.prices_at):'';
  const chainOptions=w.chains.filter(c=>c.assets>0||KiraView.coverageGap(c));
  if(selectedChain!=='all'&&!chainOptions.some(c=>String(c.id)===selectedChain))selectedChain='all';
  $('chain-filter').innerHTML='<option value="all">All chains</option>'+chainOptions.map(c=>`<option value="${c.id}">${escapeHTML(c.name)}${c.environment==='testnet'?' · Testnet':''}${KiraView.coverageGap(c)?' · Incomplete':''}</option>`).join('');
  $('chain-filter').value=selectedChain;renderHoldings();renderDiscoveryCoverage(w);
}
function renderHomeCoverage(){
  const readiness=typeof setupReadiness!=='undefined'?setupReadiness:null;
  const affected=state?.wallets.find(w=>KiraView.discoveryNotice(w,readiness)?.rpcIssues)||state?.wallets.find(w=>KiraView.discoveryNotice(w,readiness));
  const notice=affected?KiraView.discoveryNotice(affected,readiness):null;
  $('home-discovery-notice').hidden=!notice;
  if(!notice)return;
  $('home-discovery-title').textContent=notice.title;
  $('home-discovery-text').textContent=notice.message;
  $('home-discovery-settings').textContent=notice.settingsLabel||'Review data connection';
  $('home-discovery-settings').dataset.wallet=affected.key;
  $('home-discovery-settings').hidden=typeof localSession==='undefined'||localSession?.controls!==true||state.demo===true;
  $('home-discovery-review').href='#/wallet/'+encodeURIComponent(affected.key);
}
function renderDiscoveryCoverage(w) {
  const readiness=typeof setupReadiness!=='undefined'?setupReadiness:null;
  const notice=KiraView.discoveryNotice(w,readiness);
  $('discovery-notice').hidden=!notice;
  if(!notice)return;
  $('discovery-notice-title').textContent=notice.title;
  $('discovery-notice-text').textContent=notice.message;
  const controls=typeof localSession!=='undefined'&&localSession?.controls===true&&state?.demo!==true;
  $('discovery-settings').hidden=!controls||!(notice.action==='settings'||notice.settings);
  $('discovery-settings').textContent=notice.settingsLabel||'Set up Alchemy';
  $('discovery-refresh').hidden=!controls||notice.action!=='refresh';
  $('discovery-refresh').textContent=notice.refreshLabel||'Refresh holdings';
  $('discovery-refresh').disabled=$('refresh-wallet').disabled;
  $('discovery-notice').querySelector('details').open=notice.rpcIssues===true;
  $('discovery-network-details').textContent=w.chains.filter(c=>c.environment==='mainnet'&&KiraView.coverageGap(c)).map(c=>{
    const reasons=[];
    if(c.rpc_pending)reasons.push('not yet checked; detailed research continues in Activity');
    else if(!c.rpc_available)reasons.push('balance reads failed; retry holdings, then review RPC settings if this continues');
    if(!c.complete)reasons.push(({disabled:'token discovery off',missing_credential:'indexer credential unavailable',unsupported:'indexer unsupported',provider_error:'indexer request failed'})[c.discovery_status]||'token discovery incomplete');
    if(c.registry_phase==='deferred')reasons.push('full Mint Club discovery continues in Activity');
    else if(c.registry_complete===false&&c.rpc_available)reasons.push('Mint Club balances partly unchecked; retry holdings'+(c.registry_errors||c.balance_errors?' ('+(c.registry_errors||0)+' asset checks and '+(c.balance_errors||0)+' balance reads failed)':''));
    if(c.candidate_deferred>0)reasons.push(c.candidate_deferred+' token candidates await balance checks in Activity');
    if(c.candidate_balance_errors>0)reasons.push(c.candidate_balance_errors+' token balance reads failed; missing balances remain unknown');
    return c.name+': '+reasons.join('; ');
  }).join('\n');
}
function icon(asset){
  if(typeof asset.symbol!=='string'||!asset.symbol)return ['', '?'];
  if(asset.symbol==='ETH')return ['ether','◆'];
  if(asset.symbol==='CHICKEN')return ['chicken','🐔'];
  if(asset.symbol==='hcbBTC')return ['bitcoin','₿'];
  if(asset.symbol.toLowerCase()==='member')return ['member','m'];
  if(/[^\x00-\x7F]/.test(asset.symbol)&&asset.symbol.length<10)return ['',asset.symbol];
  return ['',asset.symbol.slice(0,2).toUpperCase()];
}
function coinIcon(asset){
  const [cls,glyph]=icon(asset),url=safeImage(asset.image_url);
  return `<span class="coin-icon ${cls}" aria-hidden="true"><span class="coin-fallback">${escapeHTML(glyph)}</span>${url?`<img src="${escapeHTML(url)}" alt="" width="34" height="34" loading="lazy" decoding="async" referrerpolicy="no-referrer" data-token-image>`:''}</span>`;
}
function bindImages(){
  document.querySelectorAll('img[data-token-image],img[data-chain-image]').forEach(img=>{
    if(img.dataset.bound)return;img.dataset.bound='true';
    const show=()=>{const ok=img.naturalWidth>0;img.hidden=!ok;img.parentElement.classList.toggle('has-image',ok);};
    img.addEventListener('load',show,{once:true});img.addEventListener('error',show,{once:true});
    if(img.complete)show();
  });
}
function assetRow(a){
  const p=a.price;
  const source=p?.usd!=null ? (p.retained_from_previous?'Previous '+(p.basis||'estimate'):p.basis) : p?.quality==='unreliable'?'Thin quote side':p?.quality==='unfunded'?'No funded reserve':'No price';
  const links=a.links.filter(l=>l.label!=='Explorer');
  if(!links.length){const e=a.links.find(l=>l.label==='Explorer');if(e)links.push(e);}
  const reserve=a.curve_reserve?`Curve reserve: ${a.curve_reserve.amount} ${a.curve_reserve.symbol}`:'';
  return `<tr data-asset-id="${escapeHTML(a.id)}" data-value="${a.value_usd ?? ''}"><td><a class="token-name token-link" href="${tokenHref(a.id)}" aria-label="Open ${escapeHTML(a.symbol)} token overview">${coinIcon(a)}<div class="coin-title"><div class="symbol" title="${escapeHTML(a.symbol)}">${escapeHTML(a.symbol)}</div><div class="token-description" title="${escapeHTML((a.address||'Native asset')+' '+reserve)}">${escapeHTML(a.is_native?'Native asset':a.name)}</div></div></a></td><td><span class="mobile-label">Balance</span><span class="amount" title="${escapeHTML(a.balance)}">${quantity(a.balance)}</span></td><td><span class="mobile-label">Price</span><span class="token-price ${p?.usd==null?'unpriced':''}" title="${escapeHTML(p?.observed_at||'')}">${unitPrice(p?.usd)}</span><div class="price-basis">${escapeHTML(source)}</div></td><td><span class="token-value ${a.value_usd==null?'unpriced':''}">${money(a.value_usd)}</span></td><td><div class="market-links">${marketLinks(links,a)}</div></td></tr>`;
}
function renderHoldings(){
  const w=currentWallet();if(!w)return;
  document.querySelectorAll('[data-min]').forEach(b=>b.setAttribute('aria-pressed',String(Number(b.dataset.min)===minimum)));
  const scoped=w.assets.filter(a=>selectedChain==='all'?a.environment!=='testnet':String(a.chain_id)===selectedChain);
  const visible=scoped.filter(a=>minimum===0||(a.value_usd!=null&&a.value_usd>=minimum));
  const hiddenUnpriced=minimum>0?scoped.filter(a=>a.value_usd==null).length:0;
  $('holdings-filter-note').hidden=hiddenUnpriced===0;
  $('holdings-filter-note').innerHTML=hiddenUnpriced?`<span>${hiddenUnpriced} unpriced ${hiddenUnpriced===1?'holding is':'holdings are'} hidden by the ≥ $${minimum} filter.</span><button type="button" class="quiet-button" data-clear-value-filter>Show all holdings</button>`:'';
  $('visible-count').textContent=visible.length;
  const chains=w.chains.filter(c=>visible.some(a=>a.chain_id===c.id)).sort((a,b)=>(b.value_usd??0)-(a.value_usd??0));
  $('asset-groups').innerHTML=chains.map(c=>{
    const assets=visible.filter(a=>a.chain_id===c.id).sort((a,b)=>(b.value_usd??-1)-(a.value_usd??-1));
    const values=assets.filter(a=>a.value_usd!=null),sum=values.length?values.reduce((acc,a)=>acc+a.value_usd,0):null;
    return `<section class="chain-section" aria-label="${escapeHTML(c.name)} holdings"><div class="chain-heading"><h3 class="chain-name"><a class="network-label network-link" href="${networkHref(c.id)}" aria-label="Open ${escapeHTML(c.name)} network overview">${chainIcon(c)}${escapeHTML(c.name)}<span class="detail-arrow" aria-hidden="true">${arrowGlyph}</span></a><span class="chain-assets">${assets.length} assets${c.environment==='testnet'?' · Testnet':''}</span></h3><span class="chain-total">${c.environment==='testnet'?'Testnet':money(sum)}</span></div><div class="table-wrap"><table class="token-table"><colgroup><col><col><col><col><col></colgroup><thead><tr><th scope="col">Token</th><th scope="col">Balance</th><th scope="col">Price</th><th scope="col">Value</th><th scope="col">Markets</th></tr></thead><tbody>${assets.map(assetRow).join('')}</tbody></table></div></section>`;
  }).join('');
  $('empty').hidden=visible.length>0;
  if(!visible.length&&hiddenUnpriced){
    $('empty').querySelector('h3').textContent='Holdings hidden by the value filter';
    $('empty').querySelector('p').textContent='These holdings have no price yet. Show all holdings to see their balances.';
  }else if(!visible.length&&selectedChain!=='all'){
    const c=w.chains.find(c=>String(c.id)===selectedChain);
    $('empty').querySelector('h3').textContent=c&&!c.complete?'Research is incomplete on '+c.name:'No assets in this view';
    $('empty').querySelector('p').textContent=c&&!c.complete?'This chain has not been fully checked. Missing data does not mean a zero balance.':'Choose another chain or lower the minimum value.';
  }else{$('empty').querySelector('h3').textContent=w.analysed_at&&!w.assets.length?'No holdings recorded':'No assets in this view';$('empty').querySelector('p').textContent=w.analysed_at?(!w.assets.length?'No positive balances were found in the checked networks. Refresh holdings to check again.':'Choose another chain or lower the minimum value.'):'Analysis will appear here when it is ready.';}
  bindImages();
}
function timeRange(range){return range?.from?stamp(range.from)+(range.to!==range.from?' – '+stamp(range.to):''):'Not recorded';}
function marketLinks(links,asset={},detailed=false){
  const pools=asset.market_pools||[];
  const row=pool=>{
    const pair=pool.pair||[],label=pair.length?pair.map(c=>c.symbol).join(' / '):'Recorded pool';
    const artwork=pair.length?pair.map(c=>coinIcon({...c,chain_id:asset.chain_id})).join(''):coinIcon(asset);
    return `<a class="pool-link" href="${escapeHTML(safeURL(pool.url))}" target="_blank" rel="noreferrer" title="${escapeHTML(pool.pool||pool.url)}"><span class="pool-art" aria-hidden="true">${artwork}</span><span class="pool-description"><strong>${escapeHTML(label)}</strong><small>${escapeHTML(pool.venue)}${detailed?' · '+escapeHTML(pool.pool?shortAddress(pool.pool):'Address unavailable'):''}</small>${detailed?`<small>Observed ${escapeHTML(pool.observed_at?stamp(pool.observed_at):'time unknown')}</small>`:''}</span>${detailed?`<span class="pool-metrics"><strong>${money(pool.liquidity_usd)}</strong><small>Pool liquidity</small></span>`:''}<span class="pool-arrow" aria-hidden="true">↗</span></a>`;
  };
  const poolURLs=new Set(pools.map(p=>p.url));
  const other=links.filter(l=>!poolURLs.has(l.url)).map(l=>`<a class="market-link ${l.label==='Mint Club'?'mint':''}" href="${escapeHTML(safeURL(l.url))}" target="_blank" rel="noreferrer"><span class="venue-mark" aria-hidden="true">${l.label==='Mint Club'?'M':l.label==='Explorer'?'↗':escapeHTML(l.label.slice(0,1))}</span>${escapeHTML(l.label)} <span aria-hidden="true">↗</span></a>`).join('');
  const limit=2;
  return pools.slice(0,limit).map(row).join('')+(pools.length>limit?`<details class="more-pools"><summary>Show ${pools.length-limit} more pools</summary><div>${pools.slice(limit).map(row).join('')}</div></details>`:'')+other||'<span class="native-label">No market recorded</span>';
}
function accountCard(row,token){
  const a=row.asset,value=token?a?.value_usd:row.value_usd;
  const meta=token?(a?quantity(a.balance)+' '+escapeHTML(token.symbol):escapeHTML(row.status)):row.position_count+' positions · '+row.unpriced_count+' unpriced';
  const shareValue=token?share(value,token.value_usd):null;
  const quote=a?.exit_quote?`<div class="account-quote"><div><span>Recorded full-balance burn output</span><strong>${escapeHTML(a.exit_quote.output_amount)} ${escapeHTML(a.exit_quote.output_symbol)}</strong></div><small>${stamp(a.exit_quote.observed_at)} · block ${escapeHTML(a.exit_quote.block_number)} · net of royalty · excludes gas</small></div>`:'';
  const price=token?.environment==='testnet'?null:a?.price?.usd;
  return `<article class="account-card"><a class="account-card-heading" href="#/wallet/${escapeHTML(row.key)}" aria-label="Open ${escapeHTML(row.name)} holdings"><span class="card-wallet-icon">${walletGlyph}</span><span class="wallet-card-identity"><strong>${escapeHTML(row.name)}</strong><span>${escapeHTML(shortAddress(row.address))}</span></span><span class="account-position"><span class="account-value">${money(value)}</span><span class="account-meta">${meta}</span></span><span class="card-arrow" aria-hidden="true">${arrowGlyph}</span></a>${token&&a?`<dl class="account-facts"><div><dt>Recorded price</dt><dd>${unitPrice(price)} <span>${escapeHTML(token.environment==='testnet'?'Testnet':a.price?.basis||'No price')}</span></dd></div><div><dt>Share of priced holdings</dt><dd>${shareValue}</dd></div></dl>${quote}`:''}<div class="account-footnote"><span>${escapeHTML(row.coverage)}</span><span>Analysis ${stamp(row.analysed_at)}</span>${token&&a?`<span>Price ${a.price?.observed_at?stamp(a.price.observed_at):'not recorded'}</span>`:''}</div></article>`;
}
function aggregateRow(a){
  return `<tr data-asset-id="${escapeHTML(a.id)}"><td><a class="token-name token-link" href="${tokenHref(a.id)}" aria-label="Open ${escapeHTML(a.symbol)} token overview">${coinIcon(a)}<div class="coin-title"><div class="symbol">${escapeHTML(a.symbol)}</div><div class="token-description">${escapeHTML(a.is_native?'Native asset':a.name)}</div></div></a></td><td><span class="mobile-label">Total balance</span><span class="amount" title="${escapeHTML(a.balance)}">${quantity(a.balance)}</span></td><td><span class="mobile-label">Wallets</span><span class="amount">${a.wallet_count}</span></td><td><span class="token-value">${money(a.value_usd)}</span>${a.unpriced_count?`<div class="price-basis">${a.unpriced_count} unpriced</div>`:''}</td><td><div class="market-links">${marketLinks(a.links.filter(l=>l.label!=='Explorer'),a)}</div></td></tr>`;
}
function renderNetworkTokens(network){
  const search=tokenSearch.trim().toLowerCase();
  const assets=state.details.tokens.filter(a=>a.chain_id===network.id&&(minimum===0||(a.value_usd!=null&&a.value_usd>=minimum))&&(!search||[a.symbol,a.name,a.address||'native'].some(s=>s.toLowerCase().includes(search))));
  $('network-visible-count').textContent=assets.length;
  $('network-token-body').innerHTML=assets.map(aggregateRow).join('');
  $('network-token-table').hidden=assets.length===0;$('network-token-empty').hidden=assets.length>0;
  bindImages();
}
function renderDetail(){
  const token=selectedView==='token'?state.details.tokens.find(a=>a.id===selectedToken):null;
  const network=token?.network||state.details.networks.find(c=>c.id===selectedNetwork);
  const record=selectedView==='token'?token:network;
  if(!record){
    renderBreadcrumb([{label:'Home',href:'#/home'},{label:'Research detail'}]);$('sync-label').textContent='Latest recorded research';
    $('detail-view').innerHTML='<div class="empty"><h3>No recorded detail for this selection</h3><p>It may be absent from the latest analysis. Return Home to explore recorded holdings.</p></div>';
    document.title='Research detail · Wallets';return;
  }
  const label=token?token.symbol:network.name,isTestnet=record.environment==='testnet';
  renderBreadcrumb([{label:'Home',href:'#/home'},...(token?[{label:network.name,href:networkHref(network.id)}]:[]),{label}]);
  $('sync-label').textContent='Across '+state.wallets.length+' registered wallets';document.title=label+' · Kira Wallet';
  const note=isTestnet?'Testnet holdings · excluded from USD totals.':'Recorded spot estimates · '+record.unpriced_count+' unpriced positions excluded';
  const header=`<section class="detail-heading"><div class="detail-identity">${token?coinIcon(token):chainIcon(network)}<div><div class="eyebrow">${token?'TOKEN':'NETWORK'} OVERVIEW${isTestnet?' · TESTNET':''}</div><h1>${escapeHTML(label)}</h1><p>${token?escapeHTML(token.name)+' · '+escapeHTML(network.name):'Holdings across all your registered wallets.'}</p></div></div>${!token?`<label class="chain-select"><span class="sr-only">Open another network</span><select id="network-switch">${state.details.networks.map(c=>`<option value="${c.id}" ${c.id===network.id?'selected':''}>${escapeHTML(c.name)}${c.environment==='testnet'?' · Testnet':''}</option>`).join('')}</select></label>`:''}</section>`;
  const stats=`<section class="portfolio-summary detail-summary" aria-label="${token?'Token':'Network'} summary"><div class="valuation"><div class="summary-label">Estimated value across wallets</div><div class="total-value">${money(record.value_usd)}</div><div class="valuation-note">${note}</div></div><div class="summary-stat"><span class="summary-label">${token?'Total balance':'Unique assets'}</span><strong title="${escapeHTML(token?.balance||'')}">${token?compactQuantity(token.balance):network.unique_asset_count}</strong><span class="stat-note">${token?escapeHTML(token.symbol):network.position_count+' positions'}</span></div><div class="summary-stat"><span class="summary-label">Holding wallets</span><strong>${record.wallet_count}</strong><span class="stat-note">Of ${state.wallets.length} registered</span></div></section>`;
  let facts='';
  if(token){
    const held=token.wallets.filter(r=>r.asset),prices=isTestnet?[]:held.map(r=>r.asset.price?.usd).filter(p=>p!=null);
    const low=prices.length?Math.min(...prices):null,high=prices.length?Math.max(...prices):null;
    const latest=[...held].sort((a,b)=>(b.asset.price?.observed_at||b.analysed_at||'').localeCompare(a.asset.price?.observed_at||a.analysed_at||''))[0]?.asset;
    const reserve=latest?.curve_reserve;
    facts=`<div class="detail-facts"><section class="fact-panel"><h2>Token identity</h2><div class="contract-address">${escapeHTML(token.address||'Native asset · chain '+token.chain_id)}</div><dl><div><dt>Recorded price${low!==high?' range':''}</dt><dd>${unitPrice(low)}${low!==high?' – '+unitPrice(high):''}</dd></div><div><dt>Price observations</dt><dd>${timeRange(token.price_times)}</dd></div></dl></section><section class="fact-panel"><h2>Markets & backing</h2><div class="market-links detail-markets">${marketLinks(token.links,token,true)}</div>${reserve?`<dl><div><dt>Recorded curve reserve</dt><dd>${quantity(reserve.amount)} ${escapeHTML(reserve.symbol)}</dd></div></dl><p>Shared curve backing. Excluded from wallet value.</p>`:'<p>Links reflect markets found in the recorded research.</p>'}</section></div>`;
  }
  const accounts=`<section class="detail-accounts"><div class="section-heading"><h2>By wallet</h2><span class="section-note">${token?'Recorded holdings':'Network allocation'}</span></div><div class="account-grid">${record.wallets.map(r=>accountCard(r,token)).join('')}</div><p class="detail-note">${token?'An absent record is not a verified zero balance. Prices and burn quotes can differ between analysis times.':'Totals include known mainnet values. Incomplete discovery can omit additional holdings.'}</p></section>`;
  const holdings=token?'':`<section class="holdings"><div class="holdings-toolbar"><h2>Tokens <span id="network-visible-count" class="count-badge"></span></h2><div class="filters"><label class="token-search"><span class="sr-only">Search network tokens</span><input id="network-token-search" type="search" placeholder="Search tokens" value="${escapeHTML(tokenSearch)}"></label><div class="segment" role="group" aria-label="Minimum combined token value">${[0,5,10].map(n=>`<button data-min="${n}" aria-pressed="${n===minimum}">${n?'≥ $'+n:'All'}</button>`).join('')}</div></div></div><p class="detail-note filter-note">Filter by combined token value across wallets. Summary totals include all recorded holdings.</p><div id="network-token-table" class="table-wrap"><table class="token-table"><colgroup><col><col><col><col><col></colgroup><thead><tr><th scope="col">Token</th><th scope="col">Total balance</th><th scope="col">Wallets</th><th scope="col">Value</th><th scope="col">Markets</th></tr></thead><tbody id="network-token-body"></tbody></table></div><div id="network-token-empty" class="empty" hidden><h3>No tokens in this view</h3><p>Lower the minimum value or clear your search. Missing coverage does not mean zero holdings.</p></div></section>`;
  $('detail-view').innerHTML=header+stats+facts+accounts+holdings+`<footer class="page-footer detail-footer"><span>Analysis ${timeRange(record.analysis_times)}</span><span>Prices ${timeRange(record.price_times)}</span></footer>`;
  if(!token){$('network-switch').addEventListener('change',e=>navigate(networkHref(e.target.value)));$('network-token-search').addEventListener('input',e=>{tokenSearch=e.target.value;renderNetworkTokens(network);});renderNetworkTokens(network);}
  bindImages();
}
async function poll(){
  if(busy)return;busy=true;
  try{
    const response=await fetch('/api/state',{headers:etag?{'If-None-Match':etag}:{},cache:'no-cache',signal:AbortSignal.timeout(9000)});
    if(response.status===304){$('connection').textContent='Connected';return;}
    if(!response.ok)throw new Error('Research unavailable');
    const data=await response.json();const signature=response.headers.get('ETag');
    const wasLoaded=state!==null;
    state=data;etag=signature;$('load-error').hidden=true;$('content').hidden=false;$('connection').textContent='Connected';$('demo-badge').hidden=data.demo!==true;
    if(signature!==currentSignature){renderView();currentSignature=signature;if(wasLoaded)toast('Research updated');}
  }catch{ $('connection').textContent='Reconnecting';if(!state){$('load-error').hidden=false;$('content').hidden=true;} }
  finally{busy=false;}
}
document.querySelector('.skip-link').addEventListener('click',e=>{e.preventDefault();$('main').focus();$('main').scrollIntoView({block:'start'});});
$('brand-home').addEventListener('click',e=>{e.preventDefault();goHome();});
for(const id of ['wallet-list','wallet-cards'])$(id).addEventListener('click',e=>{const b=e.target.closest('[data-wallet]');if(b)selectWallet(b.dataset.wallet);});
$('chain-filter').addEventListener('change',e=>{selectedChain=e.target.value;renderHoldings();});
document.addEventListener('click',e=>{const b=e.target.closest('[data-min],[data-clear-value-filter]');if(b){minimum=b.hasAttribute('data-clear-value-filter')?0:Number(b.dataset.min);if(selectedView==='network')renderDetail();else renderHoldings();}});
$('copy-address').addEventListener('click',async()=>{try{await navigator.clipboard.writeText(currentWallet().address);toast('Address copied');}catch{toast('Select the address to copy it');}});
document.addEventListener('visibilitychange',()=>{if(!document.hidden)poll();});
window.addEventListener('hashchange',readRoute);
readRoute();poll();setInterval(poll,5000);
