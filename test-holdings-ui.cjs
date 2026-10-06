'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const source=fs.readFileSync('viewer/static/app.js','utf8');
const nodes=new Map(),buttons=[0,5,10].map(min=>({dataset:{min:String(min)},setAttribute(){}}));
const node=id=>{if(!nodes.has(id))nodes.set(id,{textContent:'',innerHTML:'',hidden:false,querySelector:kind=>node(id+'-'+kind)});return nodes.get(id);};
let click;const saved=new Map();
const wallet={name:'Fixture',address:'0x'+'1'.repeat(40),tags:['Fixture'],analysed_at:'2026-10-04',known_value_usd:null,unpriced_count:3,
  assets:[1,33139,56].map((chain_id,i)=>({chain_id,environment:'mainnet',value_usd:null,symbol:['ETH','APE','BNB'][i]})),
  chains:[1,33139,56].map(id=>({id,name:'Chain '+id,environment:'mainnet',assets:1,complete:false,rpc_available:true,value_usd:null}))};
const context={$:node,KiraView:require('./viewer/static/workspace-model.js'),currentWallet:()=>wallet,minimum:10,selectedChain:'all',selectedView:'wallet',
  escapeHTML:String,money:n=>n==null?'—':'$'+n,stamp:String,safeURL:String,
  document:{querySelectorAll:()=>buttons,addEventListener:(event,handler)=>{click=handler;}},
  localStorage:{setItem:(key,value)=>saved.set(key,value)},renderBreadcrumb(){},bindImages(){},
  assetRow:a=>'<tr>'+a.symbol+'</tr>',chainIcon:()=>'',networkHref:String,arrowGlyph:'',renderDetail(){}};
vm.createContext(context);
vm.runInContext(source.slice(source.indexOf('function renderWallet(){'),source.indexOf('function icon(asset){')),context);
vm.runInContext(source.slice(source.indexOf('function renderHoldings(){'),source.indexOf('function timeRange(')),context);
vm.runInContext(source.split('\n').find(line=>line.startsWith("document.addEventListener('click',e=>{const b=e.target.closest('[data-min]")),context);
context.renderWallet();
assert.equal(node('total-value').textContent,'—');
assert.equal(node('visible-count').textContent,0);
assert.match(node('holdings-filter-note').innerHTML,/3 unpriced holdings are hidden/);
assert.match(node('empty-h3').textContent,/hidden by the value filter/);
assert.match(node('coverage-note').textContent,/Token discovery: 0 of 3 mainnets checked/);
assert.equal(node('discovery-notice').hidden,false);
assert.match(node('discovery-notice-title').textContent,/partial/);
context.setupReadiness={discovery_provider:'none',discovery_configured:false,discovery_key_available:false};
context.renderWallet();assert.equal(node('discovery-notice-title').textContent,'Token discovery is off');
assert.equal(node('discovery-settings').hidden,true,'Read-only views cannot change discovery settings.');
wallet.chains[0].complete=true;wallet.chains[0].discovery_status='checked';
context.renderWallet();assert.match(node('discovery-notice-title').textContent,/partial/,'Explorer coverage must not be described as entirely disabled.');
wallet.chains[0].complete=false;
wallet.chains.forEach(c=>c.discovery_status='disabled');
context.setupReadiness={discovery_provider:'alchemy',discovery_configured:true,discovery_key_available:true};
context.localSession={controls:true};context.state={demo:false};context.renderWallet();
assert.match(node('discovery-notice-title').textContent,/Refresh holdings/);
assert.equal(node('discovery-refresh').hidden,false);
context.setupReadiness={discovery_provider:'alchemy',discovery_configured:true,discovery_key_available:false};context.renderWallet();
assert.match(node('discovery-notice-title').textContent,/needs a connection/);
assert.equal(node('discovery-settings').hidden,false);
wallet.chains.forEach(c=>{c.complete=true;c.registry_complete=true;});
wallet.chains[0].rpc_available=false;wallet.chains[1].candidate_balance_errors=2;
context.renderWallet();
assert.equal(node('discovery-notice-title').textContent,'Some balances could not be checked');
assert.match(node('discovery-notice-text').textContent,/2 networks/);
assert.match(node('discovery-notice-text').textContent,/Wait a moment.*retry holdings.*review RPC settings/);
assert.match(node('valuation-note').textContent,/Partial portfolio/);
assert.match(node('discovery-network-details').textContent,/Chain 1: balance reads failed/);
assert.match(node('discovery-network-details').textContent,/Chain 33139: 2 token balance reads failed/);
assert.equal(node('discovery-notice-details').open,true);
assert.equal(node('discovery-settings').textContent,'Review RPC settings');
assert.equal(node('discovery-refresh').textContent,'Retry holdings');
assert.equal(node('discovery-settings').hidden,false);assert.equal(node('discovery-refresh').hidden,false);
context.localSession.controls=false;context.renderWallet();
assert.equal(node('discovery-settings').hidden,true);assert.equal(node('discovery-refresh').hidden,true);
context.localSession.controls=true;wallet.chains[0].rpc_available=true;wallet.chains[1].candidate_balance_errors=0;
context.renderWallet();assert.equal(node('discovery-notice').hidden,true,'A new successful analysis removes the failure notice.');
wallet.chains.forEach(c=>c.complete=false);
wallet.chains[0].registry_complete=false;context.renderWallet();
assert.match(node('discovery-notice-title').textContent,/balances/,'Registry failures need the same recovery guidance.');
assert.equal(node('discovery-settings').textContent,'Review connections','Missing discovery and RPC errors must both have a recovery path.');
wallet.chains[0].registry_complete=true;
click({target:{closest:()=>({hasAttribute:()=>true})}});
assert.equal(saved.size,0,'View filters stay temporary.');assert.equal(node('visible-count').textContent,3);
assert.equal(node('holdings-filter-note').hidden,true);assert.equal(node('empty').hidden,true);
assert.match(node('asset-groups').innerHTML,/ETH/);assert.match(node('asset-groups').innerHTML,/APE/);assert.match(node('asset-groups').innerHTML,/BNB/);
console.log('Unknown wallet value and explicit filter recovery preserve all recorded holdings.');
context.unitPrice=n=>'$'+n;context.quantity=String;context.tokenHref=String;context.coinIcon=()=>'';
context.shortAddress=s=>s.slice(0,6)+'…'+s.slice(-4);
vm.runInContext(source.slice(source.indexOf('function marketLinks('),source.indexOf('function accountCard(')),context);
vm.runInContext(source.slice(source.indexOf('function assetRow(a){'),source.indexOf('function renderHoldings(){')),context);
const historic=context.assetRow({id:'fixture',symbol:'Fixture',name:'Fixture',balance:'1',value_usd:100,links:[],
  price:{usd:100,basis:'Curve spot',retained_from_previous:true,observed_at:'2026-10-01T00:00:00Z'}});
assert.match(historic,/Previous Curve spot/);assert.match(historic,/title="2026-10-01T00:00:00Z"/);
console.log('Retained price labels preserve the original observation time.');
const pools=Array.from({length:4},(_,i)=>({url:'https://example.com/pool/'+i,pool:'0x'+'1'.repeat(40),
  venue:'Uniswap V3',pair:[{symbol:'USDC'},{symbol:'WETH'}],liquidity_usd:i===0?null:100,
  observed_at:'2026-10-05T00:00:00Z'}));
const markets=context.marketLinks([{url:pools[0].url,label:'Uniswap V3'}],{market_pools:pools},true);
assert.equal(markets.split('<details')[0].match(/class="pool-link"/g).length,2);
assert.match(markets,/<summary>Show 2 more pools<\/summary>/);
assert.equal(markets.match(/class="pool-link"/g).length,4);
assert.match(markets,/<strong>—<\/strong><small>Pool liquidity/);
assert.match(markets,/Observed 2026-10-05T00:00:00Z/);
console.log('Markets show two pools initially, retain every route and preserve unknown liquidity.');
context.safeImage=()=>null;
vm.runInContext(source.slice(source.indexOf('function icon(asset){'),source.indexOf('function bindImages(){')),context);
const malformed=context.marketLinks([],{symbol:'Fixture',market_pools:[{...pools[0],pair:[{symbol:123},{}]}]});
assert.match(malformed,/coin-fallback">\?<\/span>/);
console.log('Malformed pool symbols cannot crash the real artwork renderer.');

context.walletGlyph='';context.share=(value,total)=>value==null?'—':(value/total*100).toFixed(1)+'%';
vm.runInContext(source.slice(source.indexOf('function accountCard('),source.indexOf('function aggregateRow(')),context);
const account={name:'Synthetic wallet',key:'fixture',address:'0x'+'1'.repeat(40),status:'No holding recorded',coverage:'Researched',analysed_at:'2026-10-04T00:00:00Z'};
const absent=context.accountCard(account,{symbol:'SAMPLE',value_usd:100,environment:'mainnet'});
assert.match(absent,/account-position/);assert.match(absent,/No holding recorded/);assert.match(absent,/>—</);
assert.doesNotMatch(absent,/account-facts|account-quote/);
const recorded=context.accountCard({...account,asset:{balance:'1',value_usd:100,price:{usd:100,basis:'Curve spot',observed_at:'2026-10-01T00:00:00Z'},
  exit_quote:{output_amount:'0.123',output_symbol:'ETH',observed_at:'2026-10-02T00:00:00Z',block_number:123}}},{symbol:'SAMPLE',value_usd:100,environment:'mainnet'});
assert.match(recorded,/100.0%/);assert.match(recorded,/Curve spot/);assert.match(recorded,/0.123 ETH/);
assert.match(recorded,/block 123 · net of royalty · excludes gas/);assert.match(recorded,/Price 2026-10-01/);
const testnet=context.accountCard({...account,asset:{balance:'1',value_usd:null,price:{usd:999}}},{symbol:'SAMPLE',value_usd:null,environment:'testnet'});
assert.match(testnet,/Testnet/);assert.doesNotMatch(testnet,/999/);
console.log('Compact wallet rows retain unknown holdings, dated burn outputs and testnet price exclusion.');

const workspaceSource=fs.readFileSync('viewer/static/workspace.js','utf8');
for(const id of ['all-token-network','all-token-pricing','all-token-sort','all-token-search','job-filter'])node(id).value='previous';
node('all-token-testnets').checked=true;context.catalogPage=8;context.jobsPage=9;
vm.runInContext(workspaceSource.slice(workspaceSource.indexOf('function resetRouteFilters()'),workspaceSource.indexOf('\n}',workspaceSource.indexOf('function resetRouteFilters()'))+2),context);
context.resetRouteFilters();
assert.equal(node('all-token-network').value,'all');assert.equal(node('all-token-pricing').value,'all');
assert.equal(node('all-token-sort').value,'value');assert.equal(node('all-token-search').value,'');
assert.equal(node('all-token-testnets').checked,false);assert.equal(node('job-filter').value,'all');
assert.equal(context.catalogPage,1);assert.equal(context.jobsPage,1);
console.log('Returning to a route starts with default view filters.');
const paneWorkspace={dataset:{pane:'portfolio'}},paneScroll={scrollTop:0,scrollHeight:3000,clientHeight:600};
const paneHarness={chatPanePosition:null,$:()=>paneScroll,matchMedia:()=>({matches:true}),
  document:{querySelector:()=>paneWorkspace,querySelectorAll:()=>[],body:{classList:{toggle(){}}}}};
vm.createContext(paneHarness);
const paneStart=workspaceSource.indexOf('function setWorkspacePane(');
vm.runInContext(workspaceSource.slice(paneStart,workspaceSource.indexOf('\n}',paneStart)+2),paneHarness);
paneHarness.setWorkspacePane('kira');assert.equal(paneScroll.scrollTop,3000);
paneScroll.scrollTop=400;paneHarness.setWorkspacePane('kira');assert.equal(paneScroll.scrollTop,400);
paneHarness.setWorkspacePane('portfolio');paneScroll.scrollTop=0;paneScroll.scrollHeight=3500;
paneHarness.setWorkspacePane('kira');assert.equal(paneScroll.scrollTop,400);
paneScroll.scrollTop=2900;paneHarness.setWorkspacePane('portfolio');paneScroll.scrollTop=0;paneScroll.scrollHeight=4000;
paneHarness.setWorkspacePane('kira');assert.equal(paneScroll.scrollTop,4000);
console.log('Mobile chat opens at the latest answer and preserves an existing reader position.');
const chatLayoutSource=fs.readFileSync('viewer/static/chat-workspace.js','utf8'),resizeScroll={scrollTop:300,scrollHeight:900,clientHeight:600};
const resizeHarness={$:id=>id==='conversation-scroll'?resizeScroll:{getBoundingClientRect:()=>({height:120})},
  document:{querySelector:()=>({style:{setProperty(){resizeScroll.scrollHeight+=150;}}})}};
vm.createContext(resizeHarness);const resizeStart=chatLayoutSource.indexOf('function updateComposerReserve(');
vm.runInContext(chatLayoutSource.slice(resizeStart,chatLayoutSource.indexOf('\n}',resizeStart)+2),resizeHarness);
resizeHarness.updateComposerReserve();assert.equal(resizeScroll.scrollTop,1050);
resizeScroll.scrollTop=100;resizeHarness.updateComposerReserve();assert.equal(resizeScroll.scrollTop,100);
console.log('Composer resize follows pinned answers without moving a reader in history.');
// A queued or unknown address must never display the previous wallet's balances.
const routeHarness={selectedView:'wallet',selectedWallet:'0x'+'2'.repeat(40),currentWallet:()=>null,
  pendingWalletJob:()=>({state:'queued'}),toast:text=>routeHarness.note=text,
  navigate:hash=>routeHarness.route=hash,renderWallets:()=>{throw Error('Rendered a missing wallet');}};
vm.createContext(routeHarness);
vm.runInContext(source.slice(source.indexOf('function renderView(){'),source.indexOf('function renderKiraNote(){')),routeHarness);
routeHarness.renderView();assert.equal(routeHarness.route,'#/activity');assert.match(routeHarness.note,/waiting for registration/);
routeHarness.pendingWalletJob=()=>null;routeHarness.renderView();assert.equal(routeHarness.route,'#/activity');assert.match(routeHarness.note,/not registered/);
Object.assign(routeHarness,{busy:false,state:null,etag:null,currentSignature:null,$:node,AbortSignal,
  fetch:async()=>({status:200,ok:true,headers:{get:()=> 'fresh-state'},json:async()=>({wallets:[],demo:false})})});
vm.runInContext(source.slice(source.indexOf('async function poll(){'),source.indexOf("document.querySelector('.skip-link')")),routeHarness);
routeHarness.pendingWalletJob=()=>({state:'queued'});
routeHarness.poll().then(()=>{
  assert.equal(routeHarness.route,'#/activity');assert.equal(routeHarness.selectedView,'wallet');
  assert.match(routeHarness.note,/waiting for registration/);assert.equal(routeHarness.busy,false);
  console.log('Fresh state polling preserves missing wallet routing for pending research.');
}).catch(error=>{console.error(error);process.exitCode=1;});
