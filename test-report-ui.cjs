'use strict';
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const KiraView=require('./viewer/static/workspace-model.js');
(async()=>{
  const nodes=new Map();let interval,cleared=false,calls=0,now=0,failNext=false;
  const context={state:{wallets:[],details:{networks:[],tokens:[]},dashboard:{analysed_wallet_count:0}},localSession:{controls:true},agentState:null,KiraView,
    $:id=>{if(!nodes.has(id))nodes.set(id,{hidden:false,innerHTML:'',addEventListener(){}});return nodes.get(id);},
    escapeHTML:String,openAdd(){},openAgent(){},catalogRow:t=>'<tr>'+t.id+'</tr>',bindImages(){},
    localAPI:async()=>{++calls;if(calls===1||failNext){failNext=false;throw new Error('Transient local session failure');}return {discovery_configured:true,discovery_key_available:true};},
    Date:{now:()=>now},document:{addEventListener(){},querySelector(){return null;}},window:{addEventListener(){}},
    setInterval:callback=>{interval=callback;return 7;},clearInterval:id=>{assert.equal(id,7);cleared=true;}};
  vm.createContext(context);vm.runInContext(fs.readFileSync('viewer/static/report.js','utf8'),context);
  await context.loadSetupReadiness();
  assert.equal(cleared,false);assert.match(nodes.get('setup-path').innerHTML,/Could not check the connection. Retrying/);
  assert.doesNotMatch(nodes.get('setup-path').innerHTML,/Public RPC checks known assets/);
  now=1000;assert.equal(calls,1); // Bound retries during an outage.
  now=6000;await context.loadSetupReadiness();assert.equal(calls,2);assert.equal(cleared,false);
  assert.match(nodes.get('setup-path').innerHTML,/Connected on this computer/);
  assert.equal(nodes.get('home-empty').hidden,true);
  now=12000;assert.equal(calls,2); // Successful readiness does not keep polling.
  failNext=true;await context.loadSetupReadiness();assert.match(nodes.get('setup-path').innerHTML,/Retrying/);
  now=18000;await context.loadSetupReadiness();assert.equal(calls,4);assert.match(nodes.get('setup-path').innerHTML,/Connected on this computer/);
  console.log('Wallet setup recovers from transient readiness failure without inventing an unconfigured state.');
  // State may arrive before this final deferred script in a read-only session.
  nodes.clear();context.localSession={controls:false};context.state.details.tokens=[{id:'1:sample',environment:'mainnet',value_usd:10}];
  const readOnly={...context};vm.createContext(readOnly);vm.runInContext(fs.readFileSync('viewer/static/report.js','utf8'),readOnly);
  assert.equal(nodes.get('home-token-body').innerHTML,'<tr>1:sample</tr>');
  assert.equal(nodes.get('home-token-count').textContent,'1 of 1');
  assert.equal(nodes.get('setup-path').hidden,true);
  const previousCalls=calls;await readOnly.loadSetupReadiness();assert.equal(calls,previousCalls);
  console.log('Preloaded read-only state renders immediately without a privileged readiness request.');
  const mainnet={id:'1:mainnet',environment:'mainnet',value_usd:10},testnet={id:'11155111:testnet',environment:'testnet',value_usd:null};
  const home={state:{paged:true,data_revision:'fixture'},selectedView:'home',routeEpoch:0,routeLoadedKey:null,routeAbort:null,routeCache:new Map(),
    document:{activeElement:null},AbortController,queryPath:(path,args)=>path+'?'+new URLSearchParams(args),showRouteStatus(){},renderView(){},publishUiContext(){},
    readAPI:async path=>{const include=new URL('http://local'+path).searchParams.get('include_testnets')!=='0';return {assets:include?[mainnet,testnet]:[mainnet],matched_count:include?2:1};}};
  vm.createContext(home);const app=fs.readFileSync('viewer/static/app.js','utf8');
  vm.runInContext(app.slice(app.indexOf('async function loadRoute('),app.indexOf('function currentWallet(')),home);
  await home.loadRoute();assert.equal(home.routeData.page.matched_count,1);
  readOnly.state.paged=true;readOnly.routeData=home.routeData;readOnly.renderHomeTokens();
  assert.equal(nodes.get('home-token-count').textContent,'1 of 1');assert.doesNotMatch(nodes.get('home-token-body').innerHTML,/testnet/);
  const historyNodes=new Map(),handlers=new Map();
  const historyNode=id=>{if(!historyNodes.has(id))historyNodes.set(id,{checked:false,hidden:false,innerHTML:'',textContent:'',selectedIndex:0,showModal(){},addEventListener:(event,fn)=>handlers.set(id+':'+event,fn)});return historyNodes.get(id);};
  const rows=[{snapshot_id:'old',compiled_at:'2026-01-01',status:'completed'},
    {snapshot_id:'progress',compiled_at:'2026-01-02',phase:'initial'},
    {snapshot_id:'new',compiled_at:'2026-01-03',phase:'holdings',status:'completed_with_coverage_gaps'}];
  const history=vm.createContext({$:historyNode,stamp:String,escapeHTML:String,selectedWallet:'fixture',localAPI:async()=>rows,toast:message=>{throw Error(message);}});
  const jobs=fs.readFileSync('viewer/static/jobs.js','utf8');
  vm.runInContext(jobs.slice(jobs.indexOf('let historyRows='),jobs.indexOf("formAction($('compare-form')")),history);
  await handlers.get('view-history:click')();
  assert.doesNotMatch(historyNode('compare-after').innerHTML,/progress/);assert.match(historyNode('compare-after').innerHTML,/old/);
  assert.equal(historyNode('compare-before').selectedIndex,0);assert.equal(historyNode('compare-after').selectedIndex,1);
  assert.ok(historyNode('history-list').innerHTML.indexOf('2026-01-03')<historyNode('history-list').innerHTML.indexOf('2026-01-01'));
  historyNode('history-intermediate').checked=true;handlers.get('history-intermediate:change')();
  assert.match(historyNode('compare-after').innerHTML,/progress/);assert.match(historyNode('history-list').innerHTML,/In progress/);
  assert.equal(rows.length,3,'Filtering does not delete saved evidence.');
  rows.splice(0,rows.length,{snapshot_id:'progress-only',compiled_at:'2026-01-04',phase:'initial'});
  await handlers.get('view-history:click')();assert.match(historyNode('history-list').innerHTML,/In progress/);assert.equal(historyNode('compare-form').hidden,true);
  console.log('Home excludes testnets; history keeps final saves prominent and all progress evidence accessible.');
})().catch(error=>{console.error(error);process.exitCode=1;});
