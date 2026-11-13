'use strict';
const {test}=require('node:test'),assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs');
const source=fs.readFileSync('viewer/static/app.js','utf8');
function harness(){
 const escapeHTML=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
 const ctx=vm.createContext({escapeHTML,quantity:String,money:v=>v==null?'—':'$'+v,stamp:String,coinIcon:()=>'<i></i>',venueMark:()=>'',shortAddress:a=>String(a).slice(0,10),safeURL:url=>/^https:\/\//.test(url)?url:'#'});
 vm.runInContext(source.slice(source.indexOf('let tokenPoolPage='),source.indexOf('function accountCard(')),ctx);return ctx;
}
const token={id:'1:token',chain_id:1,symbol:'TOKEN',environment:'mainnet',market_scope:'workspace',wallets:[],links:[],market_pools:Array.from({length:1000},(_,i)=>({pool:'pool-'+i,venue:i%2?'Aero':'PancakeSwap',pair:[{symbol:'TOKEN'},{symbol:'USD'}],url:'https://example.com/pool/'+i,version_labels:['v3'],liquidity_usd:i===0?null:100,observed_at:'2026-11-13T00:00:00Z'}))};
test('top-level market cards stay bounded, paged and explicit about missing observations',()=>{
 const ctx=harness();ctx.token=structuredClone(token);let html=ctx.tokenMarkets(ctx.token);
 assert.equal((html.match(/class="token-market-card"/g)||[]).length,4);assert.match(html,/1–4 of 1000/);assert.match(html,/Pool liquidity<\/span><strong>—/);
 assert.match(html,/Saved markets across this workspace/);assert.match(html,/Observed 2026/);assert.match(html,/PancakeSwap/);assert.match(html,/Aero/);
 vm.runInContext('tokenPoolPage=249',ctx);html=ctx.tokenMarkets(ctx.token);assert.match(html,/997–1000 of 1000/);assert.match(html,/data-token-pool-page="next" disabled/);
 ctx.token.id='1:other';assert.match(ctx.tokenMarkets(ctx.token),/1–4 of 1000/);
});
test('curve backing remains separate from USD liquidity; testnets and unsafe links stay unpriced',()=>{
 const ctx=harness();ctx.token={...token,id:'1:curve',market_pools:[],curve_reserve:{amount:'5',symbol:'RESERVE',observed_at:'2026-11-13T00:00:00Z'},links:[{label:'Mint Club',url:'https://mint.club/token/ethereum/TOKEN'}]};
 let html=ctx.tokenMarkets(ctx.token);assert.match(html,/Curve backing/);assert.match(html,/5 RESERVE/);assert.doesNotMatch(html,/\$5/);assert.match(html,/0 pools · Bonding curve/);
 ctx.token={...token,environment:'testnet',market_pools:[{...token.market_pools[1],url:'javascript:alert(1)',venue:'<img src=x onerror=alert(1)>'}]};
 html=ctx.tokenMarkets(ctx.token);assert.match(html,/Pool liquidity<\/span><strong>—/);assert.doesNotMatch(html,/href="javascript:|<img src=x/);assert.match(html,/<article class="token-market-card"/);
 ctx.token={...token,market_pools:[]};assert.match(ctx.tokenMarkets(ctx.token),/No liquidity pools recorded/);
});
