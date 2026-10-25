'use strict';
const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs=require('node:fs'), vm=require('node:vm');
const ID='12345678-1111-4111-8111-111111111111';
function harness(storage, api) {
  const nodes=new Map(),routes=[];
  const el=id=>{if(!nodes.has(id))nodes.set(id,{value:'',hidden:false,textContent:'',disabled:false,open:false,listeners:{},querySelectorAll:()=>[],replaceChildren(){},focus(){},close(){},showModal(){},addEventListener(k,v){this.listeners[k]=v;}});return nodes.get(id);};
  const context=vm.createContext({$:el,sessionStorage:{getItem:k=>storage.get(k)||null,setItem:(k,v)=>storage.set(k,v),removeItem:k=>storage.delete(k)},localSession:{controls:true},state:{demo:false},
    watchingConnection:{snapshot:()=>({accounts:[]})},watchingCanAct:()=>true,localAPI:api,agentPost:api,walletChoice:()=>({}),shortAddress:s=>s,crypto:{randomUUID:()=>ID},AbortSignal,navigator:{clipboard:{}},location:{origin:'http://synthetic.test'},toast(){},navigate(route){routes.push(route);},renderWatching(){},async poll(){context.state.wallets=[{key:'0x'+'1'.repeat(40)}];}});
  vm.runInContext(fs.readFileSync('viewer/static/ows.js','utf8'),context);
  return {el,routes,run:s=>vm.runInContext(s,context)};
}
test('a new OWS wallet opens its saved account without submitting research',async()=>{
  const address='0x'+'1'.repeat(40),requests=[];
  const h=harness(new Map(),async(path,options)=>{
    if(path==='/api/ows')return {available:true,wallets:[],connection:null};
    requests.push(path);return {job_id:null,connection:{address},created:true};
  });
  await h.run('loadOws()');h.el('ows-create-name').value='New wallet';
  h.el('ows-passphrase').value=h.el('ows-passphrase-confirm').value='synthetic-fixture-only';
  await h.el('ows-create-form').listeners.submit({preventDefault(){}});
  assert.deepEqual(requests,['/api/ows/create']);assert.deepEqual(h.routes,['#/wallet/'+address]);
});
test('a pending state read cannot send a newly created wallet to missing-wallet Activity',async()=>{
  const h=harness(new Map(),async(path)=>path==='/api/ows'?{available:true,wallets:[]}:{job_id:null,connection:{address:'0x'+'1'.repeat(40)},created:true});
  await h.run('loadOws()');h.run('poll=async()=>undefined');h.el('ows-create-name').value='New wallet';
  h.el('ows-passphrase').value=h.el('ows-passphrase-confirm').value='synthetic-fixture-only';
  await h.el('ows-create-form').listeners.submit({preventDefault(){}});
  assert.deepEqual(h.routes,['#/home']);assert.equal(h.el('ows-error').textContent,'');
});
test('a failed descriptor reload after creation retains the same request for recovery',async()=>{
  const storage=new Map(),requests=[];let reads=0;
  const h=harness(storage,async(path,options)=>{
    if(path==='/api/ows'){if(++reads===2)throw Error('Temporary read failure');return {available:true,wallets:[]};}
    requests.push(JSON.parse(options.body));return {job_id:null,connection:{address:'0x'+'1'.repeat(40)},created:true};
  });
  await h.run('loadOws()');h.el('ows-create-name').value='New wallet';
  h.el('ows-passphrase').value=h.el('ows-passphrase-confirm').value='synthetic-fixture-only';
  await h.el('ows-create-form').listeners.submit({preventDefault(){}});
  assert.equal(storage.size,1);assert.equal(h.routes.length,0);
  h.el('ows-passphrase').value=h.el('ows-passphrase-confirm').value='synthetic-fixture-only';
  await h.el('ows-create-form').listeners.submit({preventDefault(){}});
  assert.equal(requests[0].idempotency_key,requests[1].idempotency_key);assert.equal(storage.size,0);
  assert.deepEqual(h.routes,['#/wallet/'+'0x'+'1'.repeat(40)]);
});
test('an ambiguous OWS creation retains only public identity and recovers after reload',async()=>{
  const storage=new Map(), requests=[];
  let pendingReject;
  const api=async(path,options)=>{
    if(path==='/api/ows')return {available:true,wallets:[],connection:null};
    requests.push(JSON.parse(options.body));return new Promise((resolve,reject)=>{pendingReject=reject;});
  };
  const first=harness(storage,api);await first.run('loadOws()');
  first.el('ows-create-name').value='Synthetic owner';first.el('ows-passphrase').value=first.el('ows-passphrase-confirm').value='synthetic-fixture-only';
  const request=first.el('ows-create-form').listeners.submit({preventDefault(){}});
  assert.equal(first.el('ows-passphrase').value,'');assert.equal(first.el('ows-passphrase-confirm').value,'');
  assert(!JSON.stringify([...storage]).includes('synthetic-fixture-only'));
  pendingReject(Error('Unknown outcome'));await request;
  const second=harness(storage,async(path,options)=>{
    if(path==='/api/ows')return {available:true,wallets:[],connection:null};
    requests.push(JSON.parse(options.body));return {job_id:null,connection:{address:'0x'+'1'.repeat(40)},recovered:true,note:'Original passphrase unchanged'};
  });
  await second.run('loadOws()');assert.equal(second.el('ows-create-name').value,'Synthetic owner');assert.equal(second.el('ows-pending').hidden,false);
  second.el('ows-passphrase').value=second.el('ows-passphrase-confirm').value='synthetic-second-passphrase';
  await second.el('ows-create-form').listeners.submit({preventDefault(){}});
  assert.equal(requests.length,2);assert.equal(requests[0].idempotency_key,requests[1].idempotency_key);assert.equal(storage.size,0);
});
test('a changed public identity cannot silently start a second creation after ambiguity',async()=>{
  const storage=new Map([['kira-ows-request',JSON.stringify({key:ID,identity:JSON.stringify([true,'Original','Original',null])})]]);
  let submitted=0;const h=harness(storage,async(path)=>{if(path==='/api/ows')return {available:true,wallets:[]};submitted++;});await h.run('loadOws()');
  h.el('ows-create-name').value='Changed';h.el('ows-passphrase').value=h.el('ows-passphrase-confirm').value='synthetic-passphrase';
  await h.el('ows-create-form').listeners.submit({preventDefault(){}});
  assert.equal(submitted,0);assert.match(h.el('ows-error').textContent,/already have finished/);
});
test('registered names hide internal creation identities without changing wallet selection',async()=>{
  const address='0x'+'1'.repeat(40),internal='Savings-'+ID;
  const h=harness(new Map(),async()=>({available:true,wallets:[],connection:{name:internal,address,tag:'Savings'}}));
  await h.run('loadOws()');assert.equal(h.el('ows-connected-name').textContent,'Savings');
  h.run(`owsSelected={id:'${ID}',name:'${internal}',accounts:[{address:'${address}'}]};renderOws()`);
  assert.equal(h.el('ows-selected-name').textContent,'Savings');
  h.run(`state.wallets=[{key:'${address}',name:'Renamed Savings'}];owsSelected={id:'${ID}',name:'${internal}',accounts:[{address:'${address}'}]};renderOws()`);
  assert.equal(h.el('ows-connected-name').textContent,'Renamed Savings');assert.equal(h.el('ows-selected-name').textContent,'Renamed Savings');
  assert.equal(h.run('owsSelected.id'),ID);assert.equal(h.el('ows-selected-address').textContent,address);
});
