'use strict';
const {test} = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const {EventEmitter} = require('node:events');
const KiraWatching = require('./viewer/static/watching-model.js');
const A = '0x'+'2'.repeat(40), B = '0x'+'3'.repeat(40);
const ID = '11111111-1111-4111-8111-111111111111';

// Exercise the real jobs and Watching controllers while the local POST is suspended.
// DOM, transport and extension are synthetic. No server, storage or provider is used.
function harness() {
  const nodes = new Map(), storage = new Map(), posts = [], notices = [];
  let generated = 0, resolvePost;
  const document = {activeElement:null, hidden:false, querySelectorAll:()=>[], addEventListener() {}};
  function element(id) {
    if (nodes.has(id)) return nodes.get(id);
    const node = {id, value:'', textContent:'', hidden:false, disabled:false, readOnly:false,
      open:false, dataset:{}, attributes:{}, children:[], listeners:{},
      classList:{toggle() {}, add() {}},
      setAttribute(key,value) {this.attributes[key]=value;},
      getAttribute(key) {return this.attributes[key];},
      addEventListener(type,listener) {this.listeners[type]=listener;},
      append(...children) {this.children.push(...children);},
      replaceChildren(...children) {this.children=children;},
      contains() {return false;}, querySelector() {return this.children[0]||null;},
      focus() {document.activeElement=this;}, showModal() {this.open=true;},
      close() {this.open=false;this.listeners.close?.();},
      reset() {element('new-wallet-address').value='';element('new-wallet-tag').value='';}
    };
    nodes.set(id,node);return node;
  }
  document.createElement=()=>element('generated-'+(++generated));
  const context=vm.createContext({KiraWatching, window:new EventTarget(), document, $:element,
    state:{demo:false,wallets:[]}, selectedWallet:null, selectedView:'home',
    currentWallet:()=>null, setInterval:()=>0, AbortSignal,
    crypto:{randomUUID:()=>ID}, shortAddress:address=>address.slice(0,6)+"…"+address.slice(-4),
    sessionStorage:{getItem:key=>storage.get(key),setItem:(key,value)=>storage.set(key,value),removeItem:key=>storage.delete(key)},
    toast:message=>notices.push(message), navigate:route=>notices.push(route),
    fetch:(path,options)=>{
      if (path==='/api/session') return new Promise(()=>{}); // Startup polling remains suspended.
      assert.equal(path,'/api/operations');
      posts.push(JSON.parse(options.body));
      return new Promise(resolve=>{resolvePost=resolve;});
    }
  });
  const run=code=>vm.runInContext(code,context);
  run(fs.readFileSync('viewer/static/jobs.js','utf8'));
  run("localSession={controls:true,token:'synthetic'};pollJobs=async()=>{};");
  run(fs.readFileSync('viewer/static/watching.js','utf8'));
  const provider=new EventEmitter();provider.request=async()=>[A,B];
  Object.assign(context,{provider,A,B,ID});
  async function choose() {
    run("watchingConnection.announce({info:{uuid:ID,name:'Synthetic wallet',rdns:'test.synthetic'},provider});setWatchingMode('browser');");
    await run('watchingConnection.connect(ID)');
    run("watchingConnection.select(A);$('new-wallet-tag').value='  Exact synthetic name  ';$('wallet-dialog').showModal();renderWatching();");
  }
  const submit=()=>element('wallet-form').listeners.submit({preventDefault() {}});
  const respond=(status=200)=>resolvePost({status,ok:status===200,json:async()=>status===200?{job_id:ID}:{error:{message:'Synthetic transport failure'}}});
  return {element,run,provider,choose,submit,respond,posts,storage,notices};
}
function assertCaptured(h) {
  assert.equal(h.element('wallet-submission').hidden,false);
  assert.equal(h.element('wallet-submission-address').textContent,A);
  assert.equal(h.element('wallet-submission-name').textContent,'  Exact synthetic name  ');
  assert.equal(h.element('wallet-registration-fields').hidden,true);
  assert.equal(h.run('Object.isFrozen(watchingSubmission)'),true);
}
test('coverage recovery opens Alchemy guidance and rechecks local readiness without a write',async()=>{
  const h=harness();
  h.run("currentWallet=()=>({key:A});localAPI=async path=>path==='/api/settings'?{rpc:{mode:'public',allow_public_fallback:true,chains:{}},discovery:{provider:'none',key_env:'ALCHEMY_API_KEY'}}:{local_key_available:false,discovery_key_available:false};");
  await h.run('openDataConnections(false,true,A)');
  assert.equal(h.element('data-provider').value,'alchemy');assert.equal(h.element('provider-key-guide').open,true);
  assert.equal(h.element('provider-save').disabled,true);assert.equal(h.posts.length,0);
  h.run("localAPI=async path=>path==='/api/settings'?{rpc:{mode:'custom',allow_public_fallback:true,priority:'public_first',chains:{}},discovery:{provider:'alchemy',key_env:'ALCHEMY_API_KEY'}}:{local_key_available:true,discovery_key_available:true};");
  await h.element('provider-recheck').listeners.click();
  assert.equal(h.element('provider-save').disabled,false);assert.equal(h.element('provider-key-guide').open,false);
  assert.equal(h.element('settings-refresh').hidden,false);assert.equal(h.element('settings-refresh').disabled,false);assert.equal(h.posts.length,0);
});
test('settings refresh retains its chosen wallet and is explicit',async()=>{
  const h=harness();
  h.run("currentWallet=()=>({key:A});localAPI=async path=>path==='/api/settings'?{rpc:{mode:'custom',allow_public_fallback:true,chains:{}},discovery:{provider:'alchemy',key_env:'KEY'}}:{local_key_available:true,discovery_key_available:true};globalThis.refreshes=[];submitOperation=async(operation,input)=>{refreshes.push({operation,input});return {job_id:ID};};");
  await h.run('openDataConnections(false,false,A)');assert.equal(h.run('refreshes.length'),0);
  h.run('currentWallet=()=>({key:B});selectedWallet=B');
  await h.element('settings-refresh').listeners.click();
  assert.equal(h.run('refreshes[0].operation'),'wallet.refresh');assert.equal(h.run('refreshes[0].input.wallet'),A);
  assert.equal(h.element('settings-dialog').open,false);assert(h.notices.includes('#/activity'));
});
test('closing and reopening a pending request retains its exact review and prevents duplicate submission',async()=>{
  const h=harness();await h.choose();const done=h.submit();assertCaptured(h);
  h.element('wallet-dialog').close();h.element('wallet-session').listeners.click();
  assert.equal(h.element('wallet-dialog').open,true);assertCaptured(h);
  h.run("setWatchingMode('manual')");assert.equal(h.run('watchingMode'),'browser');
  h.element('wallet-choose-again').listeners.click();assertCaptured(h);
  await h.submit();assert.equal(h.posts.length,1);
  h.respond();await done;
  assert.equal(h.run('watchingSubmission'),null);assert.equal(h.element('wallet-dialog').open,false);
  assert.equal(h.element('wallet-submission').hidden,true);assert.ok(h.notices.includes('#/activity'));
  assert.equal(h.storage.size,0);
});
test('account change and disconnect during POST do not change the submitted request or its review',async()=>{
  const h=harness();await h.choose();const done=h.submit();
  h.provider.emit('accountsChanged',[B]);assertCaptured(h);
  h.provider.emit('disconnect');assertCaptured(h);
  assert.equal(h.element('wallet-session-panel').hidden,false);
  assert.deepEqual(h.posts[0].input,{address:A,tag:'  Exact synthetic name  '});
  h.respond();await done;
});
test('failed transport retains its review and error across both open paths until explicitly acknowledged',async()=>{
  const h=harness();await h.choose();const done=h.submit();
  h.provider.emit('accountsChanged',[B]);h.respond(500);await done;assertCaptured(h);
  assert.equal(h.element('wallet-form-error').textContent,'Synthetic transport failure');
  assert.equal(h.element('wallet-choose-again').disabled,false);
  h.element('wallet-dialog').close();h.element('open-wallet').listeners.click();assertCaptured(h);
  assert.equal(h.element('wallet-form-error').textContent,'Synthetic transport failure');
  h.element('wallet-dialog').close();h.element('wallet-session').listeners.click();assertCaptured(h);
  assert.equal(h.storage.size,1); // A retry of the same exact input retains the idempotency key.
  h.element('wallet-choose-again').listeners.click();
  assert.equal(h.run('watchingSubmission'),null);assert.equal(h.element('wallet-form-error').textContent,'');
  assert.equal(h.run('watchingConnection.snapshot().selected'),null);
  assert.equal(h.element('wallet-accounts-section').hidden,false);
  assert.equal(h.element('wallet-register').disabled,true);
});
test('manual submission also keeps captured address and name available in Activity and on reopen',async()=>{
  const h=harness();
  h.element('new-wallet-address').value=A;h.element('new-wallet-tag').value='  Exact synthetic name  ';
  h.run("renderWatching();$('wallet-dialog').showModal();");
  const done=h.submit();assertCaptured(h);
  h.element('wallet-submission-activity').listeners.click();assert.ok(h.notices.includes('#/activity'));
  h.element('open-wallet').listeners.click();assertCaptured(h);
  h.respond(500);await done;assertCaptured(h);
});

test('the top-bar chooser exposes the missing-wallet help without an extension request',()=>{
  const h=harness();h.element('open-connection').listeners.click();
  assert.equal(h.element('wallet-dialog').open,true);assert.equal(h.element('wallet-no-providers').hidden,false);
  assert.equal(h.element('open-connection').textContent,'Connect wallet');assert.equal(h.posts.length,0);
});
test('a connected browser wallet is visible from the top bar and explicit disconnect retains saved data',async()=>{
  const h=harness();await h.choose();assert.match(h.element('open-connection').textContent,/0x2222/);
  h.element('wallet-disconnect').listeners.click();assert.equal(h.element('open-connection').textContent,'Connect wallet');assert.equal(h.posts.length,0);
});
test('data connection detour keeps the chosen browser account and wallet name',async()=>{
  const h=harness();await h.choose();
  const config={rpc:{mode:'public',allow_public_fallback:true,chains:{}},discovery:{provider:'none',key_env:'TEST_KEY'}};
  Object.assign(h.run('globalThis'),{connectionFixture:config});
  h.run("localAPI=async path=>path==='/api/settings'?connectionFixture:{local_key_available:false}");
  await h.element('wallet-discovery-settings').listeners.click();
  assert.equal(h.element('wallet-dialog').open,true);assert.equal(h.element('settings-dialog').open,true);
  assert.equal(h.element('settings-done').textContent,'Back to wallet');
  h.element('settings-dialog').close();
  assert.equal(h.run('watchingRegistrationInput().address'),A);
  assert.equal(h.element('new-wallet-tag').value,'  Exact synthetic name  ');
  assert.equal(h.posts.length,0);
});
test('a lost settings result retries the same accepted job without another submission',async()=>{
  const h=harness();
  h.run("globalThis.settingPosts=0;globalThis.failSettingRead=true;submitOperation=async()=>{settingPosts++;return {job_id:'accepted-setting'}};localAPI=async path=>{if(path.startsWith('/api/jobs/')){if(failSettingRead)throw Error('Synthetic lost read');return {state:'succeeded'};}return path==='/api/settings'?{rpc:{mode:'public',chains:{}},discovery:{provider:'none',key_env:'KEY'}}:{local_key_available:false};};$('data-provider').value='public';$('discovery-key').value='KEY';");
  await assert.rejects(h.run("saveConnectionSetting('settings.provider',{provider:'public',key_env:'KEY'})"),/lost read/);
  h.run('failSettingRead=false');
  await h.run("saveConnectionSetting('settings.provider',{provider:'public',key_env:'KEY'})");
  assert.equal(h.run('settingPosts'),1);assert.match(h.element('provider-status').textContent,/saved/);
});
test('failed provider save shows guidance and never describes the connection as saved',async()=>{
  const h=harness();h.run("submitOperation=async()=>({job_id:'failed-setting'});localAPI=async()=>({state:'failed',errors:[{message:'Local key missing. Follow the guide.'}]})");
  await assert.rejects(h.run("saveConnectionSetting('settings.provider',{provider:'alchemy',key_env:'KEY'})"),/Local key missing/);
  assert.equal(h.run('pendingSetting'),null);assert.equal(h.element('provider-status').textContent,'Connection settings were not saved.');
});
test('status failure after commit reports saved settings and retry still checks the same job',async()=>{
  const h=harness();h.run("globalThis.settingPosts=0;globalThis.failStatus=true;submitOperation=async()=>{settingPosts++;return {job_id:'committed-setting'}};localAPI=async path=>{if(path.startsWith('/api/jobs/'))return {state:'succeeded'};if(failStatus)throw Error('Lost status');return path==='/api/settings'?{rpc:{mode:'public',chains:{}},discovery:{provider:'none',key_env:'KEY'}}:{local_key_available:false};};$('data-provider').value='public';$('discovery-key').value='KEY'");
  await assert.rejects(h.run("saveConnectionSetting('settings.provider',{provider:'public',key_env:'KEY'})"),/Settings were saved/);
  assert.match(h.element('provider-status').textContent,/Connection saved/);
  h.run('failStatus=false');await h.run("saveConnectionSetting('settings.provider',{provider:'public',key_env:'KEY'})");
  assert.equal(h.run('settingPosts'),1);
});
test('a lost submission receipt stays uncertain instead of claiming the write did not happen',async()=>{
  const h=harness();h.run("submitOperation=async()=>{throw Error('Lost submission receipt')}");
  await assert.rejects(h.run("saveConnectionSetting('settings.provider',{provider:'public',key_env:'KEY'})"),/Lost submission receipt/);
  assert.match(h.element('provider-status').textContent,/Could not confirm/);
  assert.doesNotMatch(h.element('provider-status').textContent,/not saved/);
});
test('Workspace settings reads saved model choices even before initial chat status arrives',async()=>{
  const h=harness();h.run("globalThis.agentState=null;localAPI=async path=>path==='/api/agent'?{config:{provider:'claude',model:'sonnet',scope:'none',retain_history:false,wallet_tools:true}}:{rpc:{mode:'public'},discovery:{provider:'none'}}");
  await h.run('openWorkspaceSettings()');
  assert.match(h.element('workspace-model-summary').textContent,/Claude · sonnet/);
  assert.match(h.element('workspace-model-summary').textContent,/History off · Research off/);
});
test('an older dismissed Workspace lookup cannot replace the latest saved summary',async()=>{
  const h=harness();h.run("globalThis.lookupNumber=0;globalThis.pendingLookup=[];localAPI=path=>new Promise(resolve=>pendingLookup.push({path,resolve}));");
  const old=h.run('openWorkspaceSettings()');h.element('workspace-settings-dialog').close();
  const current=h.run('openWorkspaceSettings()');
  h.run("pendingLookup[2].resolve({config:{provider:'claude',model:'new-model',scope:'none',retain_history:false,wallet_tools:false}});pendingLookup[3].resolve({rpc:{mode:'custom'},discovery:{provider:'alchemy'}})");
  await current;
  h.run("pendingLookup[0].resolve({config:{provider:'codex',model:'old-model',scope:'portfolio',retain_history:true,wallet_tools:true}});pendingLookup[1].resolve({rpc:{mode:'public'},discovery:{provider:'none'}})");
  await old;
  assert.match(h.element('workspace-model-summary').textContent,/Claude · new-model/);
  assert.match(h.element('workspace-data-summary').textContent,/Alchemy selected/);
});
