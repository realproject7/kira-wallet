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
assert.equal(saved.size,0,'View filters stay temporary.');assert.equal(node('visible-count').textContent,3);
assert.equal(node('holdings-filter-note').hidden,true);assert.equal(node('empty').hidden,true);
assert.match(node('asset-groups').innerHTML,/ETH/);assert.match(node('asset-groups').innerHTML,/APE/);assert.match(node('asset-groups').innerHTML,/BNB/);
console.log('Unknown wallet value and explicit filter recovery preserve all recorded holdings.');
context.unitPrice=n=>'$'+n;context.quantity=String;context.tokenHref=String;context.coinIcon=()=>'';
vm.runInContext(source.slice(source.indexOf('function assetRow(a){'),source.indexOf('function renderHoldings(){')),context);
const historic=context.assetRow({id:'fixture',symbol:'Fixture',name:'Fixture',balance:'1',value_usd:100,links:[],
  price:{usd:100,basis:'Curve spot',retained_from_previous:true,observed_at:'2026-10-01T00:00:00Z'}});
assert.match(historic,/Previous Curve spot/);assert.match(historic,/title="2026-10-01T00:00:00Z"/);
console.log('Retained price labels preserve the original observation time.');

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
