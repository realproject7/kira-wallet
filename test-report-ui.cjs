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
  await interval();
  assert.equal(cleared,false);assert.match(nodes.get('setup-path').innerHTML,/Could not check the connection. Retrying/);
  assert.doesNotMatch(nodes.get('setup-path').innerHTML,/Public RPC checks known assets/);
  now=1000;await interval();assert.equal(calls,1); // Bound retries during an outage.
  now=6000;await interval();assert.equal(calls,2);assert.equal(cleared,false);
  assert.match(nodes.get('setup-path').innerHTML,/Local Alchemy key found/);
  assert.equal(nodes.get('home-empty').hidden,true);
  now=12000;await interval();assert.equal(calls,2); // Successful readiness does not keep polling.
  failNext=true;await context.loadSetupReadiness();assert.match(nodes.get('setup-path').innerHTML,/Retrying/);
  now=18000;await interval();assert.equal(calls,4);assert.match(nodes.get('setup-path').innerHTML,/Local Alchemy key found/);
  console.log('Wallet setup recovers from transient readiness failure without inventing an unconfigured state.');
  // State may arrive before this final deferred script in a read-only session.
  nodes.clear();context.localSession={controls:false};context.state.details.tokens=[{id:'1:sample',environment:'mainnet',value_usd:10}];
  const readOnly={...context};vm.createContext(readOnly);vm.runInContext(fs.readFileSync('viewer/static/report.js','utf8'),readOnly);
  assert.equal(nodes.get('home-token-body').innerHTML,'<tr>1:sample</tr>');
  assert.equal(nodes.get('home-token-count').textContent,'1 of 1');
  assert.equal(nodes.get('setup-path').hidden,true);
  const previousCalls=calls;await interval();assert.equal(calls,previousCalls);
  console.log('Preloaded read-only state renders immediately without a privileged readiness request.');
})().catch(error=>{console.error(error);process.exitCode=1;});
