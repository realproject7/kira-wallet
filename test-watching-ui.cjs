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
  Object.assign(context,{provider,A,ID});
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
