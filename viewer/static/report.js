'use strict';
let setupReadiness=null,setupLoading=false,reportLimit=6;
function exitRow(position){
  const a=position.asset,w=position.wallet,q=a.exit_quote;
  const network=state.details.networks.find(n=>n.id===a.chain_id)?.name||'Chain '+a.chain_id;
  const receive=q?'<strong title="'+escapeHTML(q.output_amount)+'">'+escapeHTML(q.output_amount)+' '+escapeHTML(q.output_symbol)+'</strong><small>Net of royalty · gas not included</small>':'<strong>Not quoted</strong><small>'+escapeHTML(a.is_native?'Native asset; conversion not quoted.':a.exit_route==='dex_unquoted'?'Pool found; full-balance sell quote needed.':a.exit_route==='mintclub_burn'?'Full-balance burn quote unavailable.':'No verified exit route in saved research.')+'</small>';
  return '<article class="exit-row"><div><a href="'+tokenHref(a.id)+'" class="exit-token">'+escapeHTML(a.symbol)+'</a><small>'+escapeHTML(w.name)+' · '+escapeHTML(network)+'</small><span>Full balance: '+quantity(a.balance)+' '+escapeHTML(a.symbol)+'</span></div><div class="exit-receive">'+receive+(q?'<small title="'+escapeHTML(q.observed_at)+'">Quoted '+stamp(q.observed_at)+' · block '+q.block_number+'</small><small class="exit-address" title="'+escapeHTML(q.output_address)+'">Receive contract: '+escapeHTML(shortAddress(q.output_address))+'</small>':'')+'</div><a class="exit-details" href="'+tokenHref(a.id)+'">Inspect <span aria-hidden="true">↗</span></a></article>';
}
function renderReport(){
  if(!state)return;
  const r=KiraView.report(state);
  const rows=[...r.positive,...r.zero,...r.unquoted].slice(0,reportLimit);
  const line=r.positive.length?'I found '+r.positive.length+' full-balance quote'+(r.positive.length===1?'':'s')+' with a positive token return. They are saved observations; I still need fresh routes and gas costs to establish what you can recover now.':'I can show your balances, but I cannot yet establish how much you could recover. Spot prices and pool liquidity do not answer that question.';
  $('home-report').innerHTML='<div class="section-heading"><div><h2>What could you recover?</h2><p class="section-note">Full-balance exit proceeds, separate from displayed portfolio value.</p></div><button id="report-explain" class="quiet-button" type="button">Talk through the exits</button></div><div class="exit-kira"><img src="/kira-explain.png" width="52" height="72" alt=""><p><strong>Kira</strong>'+escapeHTML(line)+'</p></div><div class="exit-summary">'+r.positive.length+' positive return quote'+(r.positive.length===1?'':'s')+(r.zero.length?' · '+r.zero.length+' zero return quotes':'')+' · '+r.unquoted.length+' positions still need exit quotes</div><div class="exit-columns" aria-hidden="true"><span>Held asset</span><span>Receive after royalty, before gas</span><span></span></div><div class="exit-rows">'+(rows.map(exitRow).join('')||'<p class="panel-empty">Add a wallet and run holdings research to inspect recorded exit routes.</p>')+'</div>'+(r.positions.length>reportLimit?'<button id="report-more" class="quiet-button" type="button">Show more exit routes ('+(r.positions.length-reportLimit)+' remaining)</button>':'')+'<p class="report-note">These Mint Club burn quotes return the specified reserve token at the recorded block. A further swap may be needed. Outputs are independent, can share curve backing, and are not summed into a cash total. Current execution, token restrictions, approvals and gas are not verified. Refresh holdings from a wallet to update recorded quotes.</p>';
  $('report-explain').addEventListener('click',async()=>{if(!agentState?.config){await openAgent();return;}selectKiraPane();$('kira-draft').value='Which recorded holdings have full-balance exit quotes? Explain the exact output token amounts, missing routes and costs. Do not treat spot value as recoverable cash or sum independent curve quotes.';$('kira-draft').dispatchEvent(new Event('input'));$('kira-draft').focus();});
  $('report-more')?.addEventListener('click',()=>{reportLimit+=20;renderReport();});
  renderSetupPath();
}
function selectKiraPane(){document.querySelector('[data-pane="kira"]')?.click();$('kira-panel').scrollIntoView({behavior:matchMedia('(prefers-reduced-motion: reduce)').matches?'auto':'smooth',block:'nearest'});}
function renderSetupPath() {
  if(!state)return;
  const wallet=state.wallets.length>0,analysed=state.dashboard.analysed_wallet_count>0;
  const discovery=setupReadiness?.discovery_key_available===true,configured=setupReadiness?.discovery_configured===true,ai=typeof agentState!=='undefined'&&!!agentState?.config;
  $('setup-path').hidden=state.demo||!localSession?.controls||(wallet&&analysed&&discovery&&ai);
  $('home-empty').hidden=wallet||!$('setup-path').hidden;
  $('setup-path').innerHTML='<details '+(!wallet?'open':'')+'><summary>'+ (wallet?'Finish your setup':'Set up your first wallet')+'</summary><div class="section-heading"><h2>'+ (wallet?'Finish your setup':'Start with one wallet')+'</h2><span class="section-note">Your keys stay yours</span></div><ol class="setup-checklist">'+
    '<li><span class="setup-check">'+(wallet?'✓':'1')+'</span><div><strong>Add a public wallet</strong><p>'+(wallet?'Saved locally.':'Paste an EVM address or choose a browser wallet. No signature or seed phrase.')+'</p></div><button class="quiet-button" id="setup-wallet" type="button">'+(wallet?'Add another':'Add wallet')+'</button></li>'+
    '<li><span class="setup-check">'+(discovery?'✓':'2')+'</span><div><strong>Connect token discovery</strong><p>'+(discovery?'Indexer key detected. Actual chain coverage is confirmed by research results.':configured?'Indexer selected, but its key is unavailable. Use a private environment reference.':'Public RPC checks known assets. Connect an indexer for broader ERC20 discovery, or continue with limited coverage.')+'</p></div><button class="quiet-button" id="setup-discovery" type="button">Review connection</button></li>'+
    '<li><span class="setup-check">'+(analysed?'✓':'3')+'</span><div><strong>Read your first report</strong><p>'+(analysed?'Saved balances, prices and coverage are ready.':'Adding a wallet starts one explicit research job. Follow its progress in Activity; gaps are shown in the report.')+'</p></div><a class="quiet-button" href="#/activity">View Activity</a></li>'+
    '<li><span class="setup-check">'+(ai?'✓':'4')+'</span><div><strong>Connect your AI <small>optional</small></strong><p>'+(ai?'Connected. Wallet context still follows your explicit permissions.':'Use your installed Codex or Claude account when you are ready. Tracking works without it.')+'</p></div><button class="quiet-button" id="setup-ai" type="button">'+(ai?'Permissions':'Connect AI')+'</button></li></ol></details>';
  $('setup-wallet').addEventListener('click',openAdd);
  $('setup-discovery').addEventListener('click',()=>$('open-settings').click());
  $('setup-ai').addEventListener('click',openAgent);
}
async function loadSetupReadiness(){
  if(setupLoading||!localSession?.controls)return;setupLoading=true;
  try{setupReadiness=await localAPI('/api/onboarding');renderSetupPath();}catch{/* Existing reconnect handling owns session recovery. */}finally{setupLoading=false;}
}
window.addEventListener('hashchange',()=>{if(selectedView==='home')renderReport();});
const setupStartup=setInterval(()=>{if(state&&localSession?.controls){loadSetupReadiness();renderReport();clearInterval(setupStartup);}},1000);

document.addEventListener('visibilitychange',()=>document.body.classList.toggle('page-hidden',document.hidden));
