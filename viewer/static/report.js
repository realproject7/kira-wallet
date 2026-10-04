'use strict';
let setupReadiness=null,setupLoading=false,setupUnavailable=false,setupRetryAfter=0;
function renderHomeTokens(){
  if(!state)return;
  const result=KiraView.catalog(state.details.tokens,{sort:'value'}),rows=result.rows.slice(0,5);
  $('home-token-body').innerHTML=rows.map(catalogRow).join('');
  $('home-token-count').textContent=rows.length+' of '+result.count;
  $('home-tokens-empty').hidden=result.count>0;
  bindImages();
  renderSetupPath();
}
function renderSetupPath() {
  if(!state)return;
  const wallet=state.wallets.length>0,analysed=state.dashboard.analysed_wallet_count>0;
  const discovery=setupReadiness?.discovery_key_available===true,configured=setupReadiness?.discovery_configured===true,ai=typeof agentState!=='undefined'&&!!agentState?.config;
  $('setup-path').hidden=state.demo||!localSession?.controls||(wallet&&analysed&&discovery&&ai);
  $('home-empty').hidden=wallet||!$('setup-path').hidden;
  $('setup-path').innerHTML='<details '+(!wallet?'open':'')+'><summary>'+ (wallet?'Finish your setup':'Set up your first wallet')+'</summary><div class="section-heading"><h2>'+ (wallet?'Finish your setup':'Start with one wallet')+'</h2><span class="section-note">Your keys stay yours</span></div><ol class="setup-checklist">'+
    '<li><span class="setup-check">'+(wallet?'✓':'1')+'</span><div><strong>Add a public wallet</strong><p>'+(wallet?'Saved locally.':'Paste an EVM address or choose a browser wallet. No signature or seed phrase.')+'</p></div><button class="quiet-button" id="setup-wallet" type="button">'+(wallet?'Add another':'Add wallet')+'</button></li>'+
    '<li><span class="setup-check">'+(discovery?'✓':'2')+'</span><div><strong>Connect token discovery</strong><p>'+(!setupReadiness?(setupUnavailable?'Could not check the connection. Retrying…':'Checking the discovery connection…'):discovery?'Indexer key detected. Actual chain coverage is confirmed by research results.':configured?'Indexer selected, but its key is unavailable. Use a private environment reference.':'Public RPC checks known assets. Connect an indexer for broader ERC20 discovery, or continue with limited coverage.')+'</p></div><button class="quiet-button" id="setup-discovery" type="button">Review connection</button></li>'+
    '<li><span class="setup-check">'+(analysed?'✓':'3')+'</span><div><strong>Read your first report</strong><p>'+(analysed?'Saved balances, prices and coverage are ready.':'Adding a wallet starts one explicit research job. Follow its progress in Activity; gaps are shown in the report.')+'</p></div><a class="quiet-button" href="#/activity">View Activity</a></li>'+
    '<li><span class="setup-check">'+(ai?'✓':'4')+'</span><div><strong>Connect your AI <small>optional</small></strong><p>'+(ai?'Connected. Wallet context still follows your explicit permissions.':'Use your installed Codex or Claude account when you are ready. Tracking works without it.')+'</p></div><button class="quiet-button" id="setup-ai" type="button">'+(ai?'Permissions':'Connect AI')+'</button></li></ol></details>';
  $('setup-wallet').addEventListener('click',openAdd);
  $('setup-discovery').addEventListener('click',()=>$('open-settings').click());
  $('setup-ai').addEventListener('click',openAgent);
}
async function loadSetupReadiness(){
  if(setupLoading||!localSession?.controls)return false;setupLoading=true;
  try{setupReadiness=await localAPI('/api/onboarding');setupUnavailable=false;setupRetryAfter=0;renderSetupPath();return true;}catch{setupReadiness=null;setupUnavailable=true;setupRetryAfter=Date.now()+5000;renderSetupPath();return false;}finally{setupLoading=false;}
}
window.addEventListener('hashchange',()=>{if(selectedView==='home')renderHomeTokens();});
const setupStartup=setInterval(async()=>{if(state&&localSession?.controls&&!setupReadiness&&Date.now()>=setupRetryAfter){await loadSetupReadiness();renderHomeTokens();}},1000);
renderHomeTokens();

document.addEventListener('visibilitychange',()=>document.body.classList.toggle('page-hidden',document.hidden));
