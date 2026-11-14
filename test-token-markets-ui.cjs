'use strict';
const {test}=require('node:test'),assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs');
const source=fs.readFileSync('viewer/static/app.js','utf8');
function harness(){
 const escapeHTML=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
 const ctx=vm.createContext({escapeHTML,quantity:String,money:v=>v==null?'—':'$'+v,stamp:String,coinIcon:()=>'<i></i>',venueMark:()=>'',shortAddress:a=>String(a).slice(0,10),safeURL:url=>/^https:\/\//.test(url)?url:'#'});
 vm.runInContext(source.split('\n').find(line=>line.startsWith('const infoTip =')),ctx);
 vm.runInContext(source.slice(source.indexOf('let tokenPoolPage='),source.indexOf('function accountCard(')),ctx);return ctx;
}
const token={id:'1:token',chain_id:1,symbol:'TOKEN',environment:'mainnet',market_scope:'workspace',wallets:[],links:[],market_pools:Array.from({length:1000},(_,i)=>({pool:'pool-'+i,venue:i%2?'Aero':'PancakeSwap',pair:[{symbol:'TOKEN'},{symbol:'USD'}],url:'https://example.com/pool/'+i,version_labels:['v3'],liquidity_usd:i===0?null:100,observed_at:'2026-11-13T00:00:00Z'}))};
test('market rows stay bounded, paged and explicit about missing observations',()=>{
 const ctx=harness();ctx.token=structuredClone(token);let html=ctx.tokenMarkets(ctx.token);
 assert.equal((html.match(/class="market-row"/g)||[]).length,5);assert.match(html,/1–5 of 1000/);assert.match(html,/<strong>—<\/strong><small>Liquidity/);
 assert.match(html,/Saved markets across this workspace/);assert.match(html,/Observed 2026/);assert.match(html,/PancakeSwap/);assert.match(html,/Aero/);
 assert.match(html,/Markets <span class="count-badge">1000<\/span>/);assert.doesNotMatch(html,/pool-0x|token-market-card/);
 vm.runInContext('tokenPoolPage=199',ctx);html=ctx.tokenMarkets(ctx.token);assert.match(html,/996–1000 of 1000/);assert.match(html,/data-token-pool-page="next"[^>]*disabled/);
 ctx.token.id='1:other';assert.match(ctx.tokenMarkets(ctx.token),/1–5 of 1000/);
});
test('curve backing remains separate from USD liquidity; testnets and unsafe links stay unpriced',()=>{
 const ctx=harness();ctx.token={...token,id:'1:curve',market_pools:[],curve_reserve:{amount:'5',symbol:'RESERVE',observed_at:'2026-11-13T00:00:00Z'},links:[{label:'Mint Club',url:'https://mint.club/token/ethereum/TOKEN'}]};
 let html=ctx.tokenMarkets(ctx.token);assert.match(html,/Curve backing/);assert.match(html,/5 RESERVE/);assert.doesNotMatch(html,/\$5/);assert.match(html,/Mint Club · Bonding curve/);assert.match(html,/excluded from wallet totals/);
 ctx.token={...token,environment:'testnet',market_pools:[{...token.market_pools[1],url:'javascript:alert(1)',venue:'<img src=x onerror=alert(1)>'}]};
 html=ctx.tokenMarkets(ctx.token);assert.match(html,/<strong>—<\/strong><small>Liquidity/);assert.doesNotMatch(html,/href="javascript:|<img src=x/);assert.match(html,/<div class="market-row"/);
 ctx.token={...token,market_pools:[]};assert.match(ctx.tokenMarkets(ctx.token),/No markets recorded/);
});
