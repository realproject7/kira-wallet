'use strict';
let setupReadiness=null,setupLoading=false,setupUnavailable=false,setupRetryAfter=0;
function renderHomeTokens(){
  if(!state)return;
  const result=state.paged?{rows:routeData.page?.assets||[],count:routeData.page?.matched_count??state.dashboard.unique_asset_count}:KiraView.catalog(state.details.tokens,{sort:'value'}),rows=result.rows.slice(0,5);
  $('home-token-body').innerHTML=rows.map(catalogRow).join('');
  $('home-token-count').textContent=rows.length+' of '+result.count;
  $('home-tokens-empty').hidden=result.count>0;
  bindImages();
  renderSetupPath();
}
function renderSetupPath() {
  if(!state)return;
  const wallet=state.wallets.length>0,connected=setupReadiness?.discovery_key_available===true;
  $('home-heading').hidden=!wallet;$('home-summary').hidden=!wallet;
  $('setup-path').hidden=state.demo||!localSession?.controls||(wallet&&connected);
  $('home-empty').hidden=wallet||!$('setup-path').hidden;
  if($('setup-path').hidden)return;
  $('setup-path').innerHTML='<div class="section-heading"><h1>Your wallets, in one place.</h1></div><p>Connect Alchemy once, then add your public wallet. AI is optional.</p><ol class="setup-checklist">'+
    '<li><span class="setup-check">'+(connected?'✓':'1')+'</span><div><strong>Connect Alchemy</strong><p>'+(connected?'Connected on this computer.':!setupReadiness?(setupUnavailable?'Could not check the connection. Retrying…':'Checking the connection…'):'Alchemy supplies the token list across networks. Your API key stays on this computer.')+'</p></div><button class="'+(connected?'quiet':'primary')+'-button" id="setup-discovery" type="button">'+(connected?'Connected':'Connect Alchemy')+'</button></li>'+
    '<li><span class="setup-check">'+(wallet?'✓':'2')+'</span><div><strong>Add your wallet</strong><p>Use a public EVM address. No signature or seed phrase.</p></div><button class="quiet-button" id="setup-wallet" type="button" '+(!connected?'disabled':'')+'>'+ (wallet?'Add another':'Add wallet')+'</button></li></ol><p class="form-note">Your agent can use the same saved research through the Kira CLI.</p>';
  $('setup-wallet').addEventListener('click',openAdd);
  $('setup-discovery').addEventListener('click',()=>openDataConnections());
}
async function loadSetupReadiness(){
  if(setupLoading||!localSession?.controls)return false;setupLoading=true;
  try{setupReadiness=await localAPI('/api/onboarding');setupUnavailable=false;setupRetryAfter=0;renderSetupPath();if(typeof renderWatching==='function')renderWatching();if(typeof renderHomeCoverage==='function')renderHomeCoverage();if(typeof currentWallet==='function'&&currentWallet())renderDiscoveryCoverage(currentWallet());return true;}catch{setupReadiness=null;setupUnavailable=true;setupRetryAfter=Date.now()+5000;renderSetupPath();return false;}finally{setupLoading=false;}
}
window.addEventListener('hashchange',()=>{if(selectedView==='home')renderHomeTokens();});

renderHomeTokens();

document.addEventListener('visibilitychange',()=>document.body.classList.toggle('page-hidden',document.hidden));
