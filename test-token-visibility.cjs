'use strict';
const {test}=require('node:test'),assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs');
const A='8453:0x'+'1'.repeat(40),B='8453:0x'+'2'.repeat(40);
const plain=x=>JSON.parse(JSON.stringify(x));
function harness(submit=async()=>({completed:true})){
  const nodes=new Map(),listeners={},writes=[];let reads=0;
  function element(id){
    if(nodes.has(id))return nodes.get(id);
    const n={id,value:'',checked:false,disabled:false,hidden:false,dataset:{},children:[],listeners:{},textContent:'',innerHTML:'',
      setAttribute(k,v){this[k]=v;},append(...items){this.children.push(...items);},addEventListener(k,v){this.listeners[k]=v;},querySelector(s){return element(id+s);},focus(){},click(){return this.listeners.click?.();}};
    nodes.set(id,n);return n;
  }
  element('all-token-status').value='portfolio';element('all-token-network').value='all';
  const context={Map,Set,Event,document:{createElement:()=>element('new-'+nodes.size),addEventListener:(k,v)=>listeners[k]=v,querySelectorAll:()=>[]},$:element,
    state:{paged:true,dashboard:{asset_policy_summary:{portfolio_count:2,review_count:0,excluded_count:0}}},routeData:{page:{next_offset:null}},routeLoading:false,catalogPage:1,catalogMinimum:0,
    localSession:{controls:true},selectedView:'tokens',escapeHTML:x=>String(x??''),setTimeout:()=>1,clearTimeout(){},toast(){},
    poll:async()=>{reads++;},loadRoute:async()=>{},renderView(){},renderCatalog(){context.TokenManager.render();},
    submitOperation:async(op,input,options)=>{writes.push({op,input,options});return submit(op,input,options);}};
  vm.createContext(context);vm.runInContext(fs.readFileSync('viewer/static/token-visibility.js','utf8'),context);
  const assets=[{id:A,symbol:'ALPHA',chain_id:8453,valuation_policy:{mode:'include'}},{id:B,symbol:'BETA',chain_id:8453,valuation_policy:{mode:'auto'}}];
  context.TokenManager.sync(assets,{page:1,status:'portfolio'});
  function select(id){listeners.change({target:{dataset:{tokenSelect:id},checked:true,matches:s=>s==='[data-token-select]'}});}
  return {context,nodes,writes,element,select,assets,get reads(){return reads;}};
}
test('one click writes the exact contract, refreshes once and Undo restores the prior preference',async()=>{
  const h=harness();await h.context.TokenVisibility.change([{id:A,mode:'exclude',previous:'include'}]);
  assert.deepEqual(plain(h.writes),[{op:'token.policy',input:{chain_id:8453,address:'0x'+'1'.repeat(40),mode:'exclude'},options:{refresh:false}}]);
  assert.equal(h.reads,1);const undo=h.element('policy-undo').children.find(n=>n.textContent==='Undo');await undo.listeners.click();
  assert.equal(h.writes[1].input.mode,'include');assert.equal(h.element('policy-undo').hidden,true);
});
test('partial success offers Undo for confirmed writes only',async()=>{
  const h=harness(async(_op,input)=>{if(input.address==='0x'+'2'.repeat(40))throw Error('Receipt unavailable');return {completed:true};});
  const result=await h.context.TokenVisibility.change([{id:A,mode:'exclude',previous:'auto'},{id:B,mode:'exclude',previous:'auto'}]);
  assert.deepEqual(plain(result.succeeded).map(x=>x.id),[A]);assert.deepEqual(plain(result.failed).map(x=>x.id),[B]);
  await h.element('policy-undo').children.find(n=>n.textContent==='Undo').listeners.click();
  assert.equal(h.writes.length,3);assert.equal(h.writes[2].input.address,'0x'+'1'.repeat(40));
});
test('bulk selection retries only unconfirmed changes and does not refresh once per token',async()=>{
  let fail=true;const h=harness(async(_op,input)=>{if(input.address==='0x'+'2'.repeat(40)&&fail){fail=false;throw Error('Lost response');}return {completed:true};});
  h.context.TokenManager.toggle();h.select(A);h.select(B);await h.context.TokenManager.apply();
  assert.equal(h.writes.length,2);assert.equal(h.reads,1);assert.match(h.element('token-selection-bar').innerHTML,/Retry changes/);
  await h.context.TokenManager.apply(true);assert.equal(h.writes.length,3);assert.equal(h.writes[2].input.address,'0x'+'2'.repeat(40));assert.equal(h.reads,2);
});
test('a page or filter change clears selected identities so off-screen tokens cannot be hidden',async()=>{
  const h=harness();h.context.TokenManager.toggle();h.select(A);h.context.TokenManager.sync(h.assets,{page:2,status:'portfolio'});
  await h.context.TokenManager.apply();assert.equal(h.writes.length,0);
  h.select(B);h.context.TokenManager.sync(h.assets,{page:2,status:'excluded'});await h.context.TokenManager.apply();assert.equal(h.writes.length,0);
});
test('Hidden management restores automatic classification and preserves earlier exclusion for Undo',async()=>{
  const h=harness();h.assets[0].valuation_policy.mode='exclude';h.context.TokenManager.toggle();h.element('all-token-status').value='excluded';h.select(A);
  await h.context.TokenManager.apply();assert.equal(h.writes[0].input.mode,'auto');
  await h.element('policy-undo').children.find(n=>n.textContent==='Undo').listeners.click();assert.equal(h.writes[1].input.mode,'exclude');
});
test('overlapping visibility operations cannot submit a second writer',async()=>{
  let finish;const gate=new Promise(resolve=>finish=resolve);const h=harness(async()=>gate);
  const first=h.context.TokenVisibility.change([{id:A,mode:'exclude',previous:'auto'}]);
  const second=await h.context.TokenVisibility.change([{id:B,mode:'exclude',previous:'auto'}]);assert.equal(second.failed.length,1);assert.equal(h.writes.length,1);
  finish({completed:true});await first;assert.equal(h.context.TokenVisibility.busy,false);
});
