'use strict';
const {test}=require('node:test'),assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs');
const code=fs.readFileSync('viewer/static/capital.js','utf8')+'\nglobalThis.capital=CapitalUI;';
const tick=()=>new Promise(resolve=>setImmediate(resolve));
function harness(api){
 const host={innerHTML:'',querySelector:()=>({addEventListener(){}}),querySelectorAll:()=>[]},target={hidden:false,querySelector:selector=>selector==='.capital-panel'?host:null};
 const allocation={groups:[{id:'wallet',name:'Wallet tokens',color:'#8a7aaf',value_usd:10,percent:25,position_count:0},{id:'uniswap',name:'Uniswap',color:'#ef5da8',logo:'/venues/uniswap.svg',value_usd:30,percent:75,position_count:1}],known_value_usd:40,wallets_checked:1,wallet_count:1,position_count:1};
 const state={data_revision:'r1',wallets:[{key:'0x'+'1'.repeat(40),capital_allocation:allocation}],dashboard:{capital_allocation:allocation},details:{networks:[]}};
 const calls=[],context={state,selectedView:'home',selectedWallet:null,selectedToken:null,selectedNetwork:null,routeData:{},activeJobs:[],localSession:{controls:false},document:{hidden:false},URLSearchParams,
  $:()=>target,coinIcon:a=>'<i class="coin" data-symbol="'+a.symbol+'" data-address="'+a.address+'"></i>',escapeHTML:x=>String(x??'').replaceAll('<','&lt;'),money:x=>x==null?'—':'$'+x,stamp:x=>x,quantity:x=>x,safeURL:x=>x,tokenHref:x=>'#/token/'+x,localAPI:async url=>{calls.push(url);return api?api(url,context):{data_revision:context.state.data_revision,positions:[],allocation,matched_count:0,next_offset:null};},currentWallet:()=>state.wallets[0],poll:async()=>{},};
 vm.createContext(context);vm.runInContext(code,context);return {context,host,calls,allocation,render:()=>context.capital.render()};
}
test('segmented bar uses CSP-compatible SVG and bounded local reads coalesce',async()=>{
 const h=harness();for(let i=0;i<20;i++)h.render();await tick();
 assert.equal(h.calls.length,1);assert.match(h.calls[0],/^\/api\/positions\?/);assert.match(h.calls[0],/limit=25/);
 assert.match(h.host.innerHTML,/<svg class="capital-donut"/);assert.match(h.host.innerHTML,/stroke="#ef5da8"[^>]*stroke-dasharray="75\.000 25\.000" stroke-dashoffset="0\.000"/);assert.match(h.host.innerHTML,/stroke="#8a7aaf"[^>]*stroke-dasharray="25\.000 75\.000" stroke-dashoffset="25\.000"/);
 assert.match(h.host.innerHTML,/class="donut-value"[^>]*>75%<\/text><text class="donut-label"[^>]*>Uniswap</);assert.doesNotMatch(h.host.innerHTML,/style=/);
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

test('the summary card shows where assets sit without repeating its total or explaining itself',async()=>{
 const h=harness();h.render();await tick();
 assert.doesNotMatch(h.host.innerHTML,/Where your assets are|capital-total|capital-basis/);
 assert.match(h.host.innerHTML,/<svg class="alloc-swatch"[^>]*><rect[^>]*fill="#ef5da8"/);assert.match(h.host.innerHTML,/class="alloc-pct">75\.0%/);
 assert.match(h.host.innerHTML,/<details class="info-tip"><summary aria-label="About this allocation">/);assert.match(h.host.innerHTML,/Each claim counts once/);
 assert.match(h.host.innerHTML,/data-platform="uniswap" aria-pressed="false"/);assert.doesNotMatch(h.host.innerHTML,/data-platform="wallet"/);
});
test('a token held only in wallets has no allocation panel and makes no position request',async()=>{
 const h=harness(),single={groups:[{id:'wallet',name:'Wallet tokens',color:'#8a7aaf',value_usd:10,percent:100,position_count:0}],known_value_usd:10,wallets_checked:1,wallet_count:1,position_count:0};
 h.context.selectedView='token';h.context.selectedToken='1:0x'+'2'.repeat(40);h.context.routeData={token:{capital_allocation:single}};
 h.render();await tick();assert.equal(h.host.hidden,true);assert.equal(h.calls.length,0);
 h.context.routeData={token:{capital_allocation:h.allocation}};h.render();await tick();
 assert.equal(h.host.hidden,false);assert.equal(h.calls.length,1);assert.match(h.calls[0],/token_id=1%3A0x2/);
 assert.doesNotMatch(h.host.innerHTML,/capital-refresh|capital-gaps/,'Scans cover a wallet or the portfolio, not one token.');
});
test('the token list has no allocation panel',async()=>{
 const h=harness();h.context.selectedView='tokens';h.render();await tick();
 assert.equal(h.calls.length,0);assert.equal(h.host.innerHTML,'');
});
test('a wallet with nothing to compare keeps one status line and its scan action',async()=>{
 const single={groups:[{id:'wallet',name:'Wallet tokens',color:'#8a7aaf',value_usd:10,percent:100,position_count:0}],known_value_usd:10,wallets_checked:0,wallet_count:1,position_count:0};
 const h=harness(()=>({data_revision:'r1',positions:[],allocation:single,matched_count:0,next_offset:null}));
 h.context.localSession.controls=true;h.context.selectedView='wallet';h.context.selectedWallet=h.context.state.wallets[0].key;h.context.state.wallets[0].capital_allocation=single;
 h.render();await tick();
 assert.doesNotMatch(h.host.innerHTML,/capital-donut|capital-chart|capital-legend|capital-positions/);
 assert.match(h.host.innerHTML,/Platform positions not scanned/);assert.match(h.host.innerHTML,/0\/1 wallets checked/);assert.match(h.host.innerHTML,/class="quiet-button capital-refresh" >Find platform positions/);
});
test('coverage gaps stay one chip until opened; position rows carry flags and evidence',async()=>{
 const testCode=code.replace('return {render};','return {render,toggleCoverage};');
 const position={id:'p1',platform:'uniswap',version:'v3',label:'Pool',chain_id:1,wallet:'0x'+'1'.repeat(40),wallet_name:'Fixture',value_usd:30,observed_at:'2026-11-13T00:00:00Z',source_url:'https://example.com/position',custody_platform:'gauge',retained:true,included_in_totals:false,exit_note:'NAV note.',assets:[{symbol:'AAA',address:'0x'+'a'.repeat(40),amount:'1',price:{observed_at:'2026-11-12T00:00:00Z'}},{symbol:'BBB',address:'0x'+'b'.repeat(40),amount:'2'}]};
 const h=harness((url,ctx)=>({data_revision:'r1',positions:[position],allocation:{...h.allocation,coverage_gap_count:3},matched_count:1,next_offset:null,coverage_gap_count:3,coverage_gaps:[{wallet_name:'Fixture',chain_id:1,message:'Source <unchecked>.'}]}));
 h.context.FolderUI={id:null,view:()=>null,path:route=>'#/'+route};
 vm.runInContext(testCode.replace('const CapitalUI=','var CapitalGaps=').replaceAll('globalThis.capital=CapitalUI','globalThis.capitalGaps=CapitalGaps'),h.context);
 h.context.capitalGaps.render();await tick();
 assert.match(h.host.innerHTML,/class="chip warn capital-gaps" aria-expanded="false"[^>]*>3 coverage gaps/);assert.doesNotMatch(h.host.innerHTML,/class="capital-coverage"/);
 assert.match(h.host.innerHTML,/<li class="capital-position" title="NAV note\. Saved prices 2026-11-12T00:00:00Z\. Observed 2026-11-13T00:00:00Z\.">/);
 assert.match(h.host.innerHTML,/AAA \/ BBB/);assert.match(h.host.innerHTML,/<small>Uniswap · v3<\/small>/);assert.match(h.host.innerHTML,/class="pos-art"[^>]*><i class="coin" data-symbol="AAA"[^>]*><\/i><i class="coin" data-symbol="BBB"/);assert.match(h.host.innerHTML,/Staked/);assert.match(h.host.innerHTML,/Retained/);assert.match(h.host.innerHTML,/Not in totals/);assert.match(h.host.innerHTML,/aria-label="View source for AAA \/ BBB"/);
 h.context.capitalGaps.toggleCoverage();
 assert.match(h.host.innerHTML,/aria-expanded="true"/);assert.match(h.host.innerHTML,/class="capital-coverage"[\s\S]*Source &lt;unchecked>\./);
});

test('two staking pools with the same stake are told apart by number and reward',async()=>{
 const stake=(id,extra)=>({id:'8453:0xstake:'+id,platform:'mintclub-staking',version:'V1_0',label:'Staking pool #'+id,pool_id:String(id),chain_id:8453,wallet:'0x'+'1'.repeat(40),wallet_name:'Fixture',value_usd:21.5,observed_at:'2026-11-13T00:00:00Z',source_url:'https://mint.club/staking/base/'+id,assets:[{symbol:'STAKE',address:'0x'+'f'.repeat(40),amount:'1500'}],...extra});
 const groups=[{id:'mintclub-staking',name:'Mint Club Staking',color:'#30876c',logo:'/venues/mintclub.png',value_usd:43,percent:100,position_count:2}];
 const h=harness(()=>({data_revision:'r1',positions:[stake(41,{reward:{address:'0x'+'2'.repeat(40),symbol:null}}),stake(42,{reward:{address:'0x'+'3'.repeat(40),symbol:'DROP'}}),stake(43,{})],allocation:{groups,known_value_usd:43,wallets_checked:1,wallet_count:1,position_count:3},matched_count:3,next_offset:null}));
 h.context.FolderUI={id:null,view:()=>null,path:route=>'#/'+route};h.context.selectedView='wallet';h.context.selectedWallet=h.context.state.wallets[0].key;
 h.render();await tick();const rows=h.host.innerHTML.split('<li class="capital-position"').slice(1);
 assert.equal(rows.length,3);
 assert.match(rows[0],/Mint Club Staking · V1_0 · Pool #41/);assert.match(rows[0],/title="This pool pays 0x2{40}">earns <i class="coin"[^>]*data-address="0x2{40}"><\/i><\/span>/);
 assert.match(rows[1],/Pool #42/);assert.match(rows[1],/title="This pool pays DROP">earns <i class="coin" data-symbol="DROP"[^>]*><\/i><strong>DROP<\/strong>/);assert.match(rows[1],/aria-label="View source for STAKE Pool #42"/);
 assert.match(rows[2],/Pool #43/);assert.doesNotMatch(rows[2],/earns/,'An older saved claim without a reward token still shows its pool number.');
 assert.match(rows[0],/<img class="pos-platform" src="\/venues\/mintclub\.png"/);
 assert.match(rows[1],/<span class="pos-text"><span class="pos-label"><strong>STAKE<\/strong><small>Mint Club Staking · V1_0 · Pool #42<\/small><\/span><span class="chip pos-reward"/,'Chips wrap under the label, not under the icons.');
 const css=require('node:fs').readFileSync('viewer/static/capital.css','utf8');
 assert.match(css,/\.capital-position-list\{[^}]*container:positions \/ inline-size/,'Rows answer to the width of their own list, not the window.');
 assert.match(css,/@container positions \(max-width:859px\)/);assert.match(css,/@container positions \(max-width:519px\)/);assert.doesNotMatch(css,/@media\(max-width:860px\)\{\s*\.capital-position/);
 assert.match(css,/\.pos-label strong,\.pos-label small\{display:block;white-space:nowrap;overflow:hidden;text-overflow:ellipsis\}/,'A label is cut with an ellipsis instead of wrapping into a narrow column.');
});
