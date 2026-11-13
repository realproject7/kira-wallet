'use strict';
const {test}=require('node:test'),assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs');
const code=fs.readFileSync('viewer/static/capital.js','utf8')+'\nglobalThis.capital=CapitalUI;';
const tick=()=>new Promise(resolve=>setImmediate(resolve));
function harness(api){
 const host={innerHTML:'',querySelector:()=>({addEventListener(){}}),querySelectorAll:()=>[]},target={hidden:false,querySelector:selector=>selector==='.capital-panel'?host:null};
 const allocation={groups:[{id:'wallet',name:'Wallet tokens',color:'#8a7aaf',value_usd:10,percent:25,position_count:0},{id:'uniswap',name:'Uniswap',color:'#ef5da8',logo:'/venues/uniswap.svg',value_usd:30,percent:75,position_count:1}],known_value_usd:40,wallets_checked:1,wallet_count:1,position_count:1};
 const state={data_revision:'r1',wallets:[{key:'0x'+'1'.repeat(40),capital_allocation:allocation}],dashboard:{capital_allocation:allocation},details:{networks:[]}};
 const calls=[],context={state,selectedView:'home',selectedWallet:null,selectedToken:null,selectedNetwork:null,routeData:{},activeJobs:[],localSession:{controls:false},document:{hidden:false},URLSearchParams,
  $:()=>target,escapeHTML:x=>String(x??'').replaceAll('<','&lt;'),money:x=>x==null?'—':'$'+x,stamp:x=>x,quantity:x=>x,safeURL:x=>x,tokenHref:x=>'#/token/'+x,localAPI:async url=>{calls.push(url);return api?api(url,context):{data_revision:context.state.data_revision,positions:[],allocation,matched_count:0,next_offset:null};},currentWallet:()=>state.wallets[0],poll:async()=>{},};
 vm.createContext(context);vm.runInContext(code,context);return {context,host,calls,allocation,render:()=>context.capital.render()};
}
test('segmented bar uses CSP-compatible SVG and bounded local reads coalesce',async()=>{
 const h=harness();for(let i=0;i<20;i++)h.render();await tick();
 assert.equal(h.calls.length,1);assert.match(h.calls[0],/^\/api\/positions\?/);assert.match(h.calls[0],/limit=25/);
 assert.match(h.host.innerHTML,/<svg class="capital-bar"/);assert.match(h.host.innerHTML,/width="750"/);assert.doesNotMatch(h.host.innerHTML,/style=/);
 for(let i=0;i<20;i++)h.render();await tick();assert.equal(h.calls.length,1);
});
test('hidden tabs make no new saved-data requests until visible',async()=>{
 const h=harness();h.context.document.hidden=true;h.render();await tick();assert.equal(h.calls.length,0);
 h.context.document.hidden=false;h.render();await tick();assert.equal(h.calls.length,1);
 h.context.document.hidden=true;h.context.state.data_revision='r2';h.render();await tick();assert.equal(h.calls.length,1);
});
test('a response from the previous wallet cannot populate the newly selected scope',async()=>{
 let resolve;const h=harness((url,ctx)=>h.calls.length===1?new Promise(r=>resolve=r):{data_revision:'r1',positions:[],allocation:h.allocation,matched_count:0,next_offset:null});
 h.render();h.context.selectedView='wallet';h.context.selectedWallet=h.context.state.wallets[0].key;h.render();
 resolve({data_revision:'r1',positions:[{id:'wrong-wallet'}],allocation:h.allocation,matched_count:999,next_offset:null});await tick();await tick();
 assert.equal(h.calls.length,2);assert.match(h.calls[1],/wallet=0x/);assert.doesNotMatch(h.host.innerHTML,/wrong-wallet/);
});
test('unavailable local records retain explicit errors and a saved-view retry',async()=>{
 const h=harness(()=>{throw Error('Saved records unavailable');});h.render();await tick();
 assert.match(h.host.innerHTML,/Saved records unavailable/);assert.match(h.host.innerHTML,/Retry saved view/);
 h.render();await tick();assert.equal(h.calls.length,1);
});

test('mixed saved and unchecked wallets preserve per-wallet default discovery at global refresh',async()=>{
 const testCode=code.replace('return {render};','return {render,refresh};'),submitted=[];
 const h=harness(),button={disabled:false,closest:()=>({querySelector:()=>({textContent:''})})};
 h.context.document.querySelector=()=>button;h.context.setupReadiness={discovery_key_available:true};h.context.submitOperation=async(op,input)=>{submitted.push({op,input});return {jobs:[{},{}]};};
 vm.runInContext(testCode.replace('const CapitalUI=','var CapitalUITest=').replaceAll('globalThis.capital=CapitalUI','globalThis.capitalTest=CapitalUITest'),h.context);
 await h.context.capitalTest.refresh(false);assert.equal(submitted[0].op,'portfolio.positionsRefresh');assert.equal('discover' in submitted[0].input,false);
 await h.context.capitalTest.refresh(true);assert.equal(submitted[1].input.discover,true);
});

test('queued platform scans in the merged job list disable duplicate global discovery',async()=>{
 const h=harness();h.context.localSession.controls=true;h.context.jobList=[{operation:'positions.refresh',state:'queued',input:{wallet:h.context.state.wallets[0].key}}];
 h.render();await tick();assert.match(h.host.innerHTML,/Platform scans in progress/);assert.match(h.host.innerHTML,/class="quiet-button capital-refresh" disabled/);
});
