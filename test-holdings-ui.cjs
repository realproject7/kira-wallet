'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const source=fs.readFileSync('viewer/static/app.js','utf8');
const nodes=new Map(),buttons=[0,5,10].map(min=>({dataset:{min:String(min)},setAttribute(){}}));
const node=id=>{if(!nodes.has(id))nodes.set(id,{textContent:'',innerHTML:'',hidden:false,querySelector:kind=>node(id+'-'+kind)});return nodes.get(id);};
let click;const saved=new Map();
const wallet={name:'Fixture',address:'0x'+'1'.repeat(40),tags:['Fixture'],analysed_at:'2026-10-04',known_value_usd:null,unpriced_count:3,
  assets:[1,33139,56].map((chain_id,i)=>({chain_id,environment:'mainnet',value_usd:null,symbol:['ETH','APE','BNB'][i]})),
  chains:[1,33139,56].map(id=>({id,name:'Chain '+id,environment:'mainnet',assets:1,complete:false,rpc_available:true,value_usd:null}))};
const context={$:node,currentWallet:()=>wallet,minimum:10,selectedChain:'all',selectedView:'wallet',
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
assert.match(node('coverage-note').textContent,/checked for ERC20 tokens/);
click({target:{closest:()=>({hasAttribute:()=>true})}});
assert.equal(saved.get('wallet-minimum'),'0');assert.equal(node('visible-count').textContent,3);
assert.equal(node('holdings-filter-note').hidden,true);assert.equal(node('empty').hidden,true);
assert.match(node('asset-groups').innerHTML,/ETH/);assert.match(node('asset-groups').innerHTML,/APE/);assert.match(node('asset-groups').innerHTML,/BNB/);
console.log('Unknown wallet value and explicit filter recovery preserve all recorded holdings.');
