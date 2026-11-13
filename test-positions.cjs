'use strict';
const {test}=require('node:test'),assert=require('node:assert/strict'),{Reader,math,abi}=require('./position-reader.cjs'),v=require('viem');
const config=require('./sources/position-protocols.json');
const A='0x'+'1'.repeat(40),T0='0x'+'2'.repeat(40),T1='0x'+'3'.repeat(40),POOL='0x'+'4'.repeat(40),MANAGER='0x'+'5'.repeat(40),FACTORY='0x'+'6'.repeat(40),GAUGE='0x'+'7'.repeat(40),VAULT='0x'+'8'.repeat(40);
function harness(task,resolve,{cid=8453,shared={},maxReads=48,ioExtra={}}={}){
 const state={schema_version:1,wallet:A,tasks:[{scope:cid+':test',chain_id:cid,...task}],cursor:0,positions:{},coverage:{},blocks:{},done:0};
 let active=0,maxActive=0,maxBatch=0,requests=0;const input={wallet:A,networks:[{chain_id:cid,environment:'mainnet',native_symbol:'ETH'}],tokens:[],max_reads:maxReads};
 const io={async context(){return {block:{number:'100',hash:'0x'+'a'.repeat(64),observed_at:'2026-11-13T00:00:00Z'}};},
  async multi(c,calls){assert.ok(calls.length<=32);maxBatch=Math.max(maxBatch,calls.length);requests++;active++;maxActive=Math.max(maxActive,active);try{return calls.map(call=>{try{return {status:'success',result:resolve(call)};}catch{return {status:'failure',reason:'transport'};}});}finally{active--;}} ,...ioExtra};
 return {state,input,io,shared,metrics:()=>({requests,maxActive,maxBatch}),reader:()=>new Reader(input,state,io,shared)};
}
async function finish(h){for(let i=0;i<100;i++){const result=await h.reader().run(()=>{});assert.ok(result.last_slice_reads<=48);if(result.complete)return result;}throw Error('Reader did not converge');}
function tokenCalls(c){if(c.functionName==='decimals')return 18;if(c.functionName==='symbol')return c.address===T0?'AAA':'BBB';throw Error(c.functionName);}
function nftResolve(c,{owner=A,factory=FACTORY,manager=MANAGER,pool=POOL}={}){
 if(c.functionName==='stakedContains')return true;
 if(c.functionName==='ownerOf')return owner;
 if(c.functionName==='positions')return [0n,v.zeroAddress,T0,T1,60,-60,60,10n**18n,0n,0n,0n,0n];
 if(c.functionName==='getPool')return pool;
 if(c.functionName==='slot0')return [1n<<96n,0,0,0,0,false];
 return tokenCalls(c);
}
test('exact liquidity math handles boundaries, range changes and large claims',()=>{
 assert.equal(v.encodeFunctionData({abi,functionName:'getPool',args:[T0,T1,3000]}).slice(0,10),'0x1698ee82');
 assert.equal(math.sqrtRatioAtTick(0),1n<<96n);assert.equal(math.sqrtRatioAtTick(-887272),4295128739n);
 assert.equal(math.sqrtRatioAtTick(887272),1461446703485210103287273052203988822378723970342n);
 const l=10n**24n,inside=math.liquidityAmounts(l,1n<<96n,-60,60);
 assert.ok(inside.every(x=>x>0n));assert.ok(inside[0]-inside[1]<=1n);
 assert.equal(math.liquidityAmounts(l,math.sqrtRatioAtTick(-120),-60,60)[1],0n);
 assert.equal(math.liquidityAmounts(l,math.sqrtRatioAtTick(120),-60,60)[0],0n);
 assert.deepEqual(math.shareAmounts(5n,100n,[2000n,6000n]),[100n,300n]);
 assert.throws(()=>math.shareAmounts(101n,100n,[1n,2n]));assert.throws(()=>math.liquidityAmounts(1n,0n,1,2));
 const packed=(BigInt(0xffffff-59)<<8n)|(60n<<32n);assert.deepEqual(math.v4Ticks(packed),[-60,60]);
});
test('native currencies retain chain-specific units, including six-decimal Arc USDC',async()=>{
 const h=harness({kind:'seed'},()=>0n,{cid:5042});h.input.networks[0].native_symbol='USDC';h.input.networks[0].native_decimals=6;
 const rows=await h.reader().assets({chain_id:5042},[v.zeroAddress],[1000000n]);assert.equal(rows[0].amount,'1');assert.equal(rows[0].symbol,'USDC');
});
test('Factory NFT ownership is NAV once, before the separate burn fee',async()=>{
 const f=config.factory_nft,h=harness({kind:'factory'},c=>c.functionName==='balanceOf'?3n:c.functionName==='navPerNFT'?200n*10n**18n:tokenCalls(c),{cid:1});
 const result=await finish(h),rows=Object.values(result.positions);assert.equal(rows.length,1);assert.equal(rows[0].platform,'factory');assert.equal(rows[0].assets[0].amount,'600');assert.match(rows[0].exit_note,/5%/);
});
test('lpTOKEN factory membership and full share claim are verified independently',async()=>{
 const f=config.lptoken.find(p=>p.chain_id===8453),h=harness({kind:'vault',vault:VAULT},c=>{
  if(c.functionName==='factory')return f.factory;if(c.functionName==='target')return T0;if(c.functionName==='counter')return T1;
  if(c.functionName==='balanceOf')return 5n*10n**18n;if(c.functionName==='isVault')return true;if(c.functionName==='claimForShares')return [2n*10n**18n,3n*10n**18n];return tokenCalls(c);
 });
 const rows=Object.values((await finish(h)).positions);assert.equal(rows[0].assets[1].amount,'3');assert.equal(rows[0].receipt.custody,'wallet');
 const bad=harness({kind:'vault',vault:VAULT},c=>c.functionName==='factory'?FACTORY:c.functionName==='balanceOf'?100n:T0);assert.equal(Object.keys((await finish(bad)).positions).length,0);assert.equal(bad.state.coverage['8453:test'].status,'partial');
});
test('Mint Club staking finds principal without requiring loose-token ownership',async()=>{
 const address=config.mintclub_staking.find(p=>p.chain_id===8453&&p.version==='V1_2').address;
 const h=harness({kind:'stake',address,pool_id:'37',shares:String(100n*10n**18n),version:'V1_2'},c=>{
  if(c.functionName==='pools')return {stakingToken:T0,isStakingTokenERC20:true};if(c.functionName==='isVault')return false;return tokenCalls(c);
 });const rows=Object.values((await finish(h)).positions);assert.equal(rows[0].platform,'mintclub-staking');assert.equal(rows[0].assets[0].amount,'100');
 const nft=harness({kind:'stake',address,pool_id:'38',shares:'2',version:'V1_2'},()=>({stakingToken:T0,isStakingTokenERC20:false}));assert.equal(Object.values((await finish(nft)).positions)[0].assets[0].amount,'2');
});
test('Uniswap, Pancake and Aero NFTs use owner, factory and pinned liquidity',async()=>{
 for(const [platform,type,version] of [['uniswap','v3','v3'],['pancakeswap','v3','v3'],['aerodrome','cl','legacy-slipstream'],['aerodrome','cl','aero-cl']]){
  const h=harness({kind:'nft',ids:['1'],manager:MANAGER,factory:FACTORY,platform,type,version},c=>nftResolve(c));
  const row=Object.values((await finish(h)).positions)[0];assert.equal(row.platform,platform);assert.equal(row.assets.length,2);assert.equal(row.block_number,'100');
 }
 const other=harness({kind:'nft',ids:['1'],manager:MANAGER,factory:FACTORY,platform:'uniswap',type:'v3'},c=>nftResolve(c,{owner:GAUGE}));assert.equal(Object.keys((await finish(other)).positions).length,0);
});
test('gauge stakes are attributed to the beneficiary and Aeromax counts the same NFT once',async()=>{
 const a=config.aero.find(p=>p.chain_id===8453&&p.version==='aero-cl');
 const h=harness({...a,kind:'gauge-cl',platform:'aerodrome',pools:[{pool:POOL,gauge:GAUGE}]},c=>c.functionName==='stakedValues'?[12n]:nftResolve(c,{owner:GAUGE}),{ioExtra:{async aeromax(ids){assert.deepEqual(ids,['12']);return {status:'ready',indexedThroughBlock:'99',positions:[{tokenId:'12',entryMode:'token0'}]};}}});
 const rows=Object.values((await finish(h)).positions);assert.equal(rows.length,1);assert.equal(rows[0].platform,'aeromax');assert.equal(rows[0].protocol,'aerodrome');assert.equal(rows[0].custody_platform,'aerodrome');
});
test('Pancake farm ownership is verified before an underlying position counts',async()=>{
 const h=harness({kind:'nft',ids:['1'],manager:MANAGER,inventory_address:GAUGE,platform:'pancakeswap',factory:FACTORY,type:'v3'},c=>c.functionName==='userPositionInfos'?[0n,0n,0,0,0n,0n,A,1n,0n]:nftResolve(c,{owner:GAUGE}));
 assert.equal(Object.values((await finish(h)).positions)[0].custody_platform,'pancakeswap');
 const wrong=harness({kind:'nft',ids:['1'],manager:MANAGER,inventory_address:GAUGE,platform:'pancakeswap',factory:FACTORY,type:'v3'},c=>c.functionName==='userPositionInfos'?[0n,0n,0,0,0n,0n,T0,1n,0n]:nftResolve(c,{owner:GAUGE}));assert.equal(Object.keys((await finish(wrong)).positions).length,0);assert.equal(wrong.state.coverage['8453:test'].status,'partial');
});
test('v4 packed pool identity, owner and chain-specific state view precede valuation',async()=>{
 const k={currency0:T0,currency1:T1,fee:3000,tickSpacing:60,hooks:v.zeroAddress},pool=v.keccak256(v.encodeAbiParameters([{type:'address'},{type:'address'},{type:'uint24'},{type:'int24'},{type:'address'}],Object.values(k)));
 const info=(BigInt(pool)>>56n<<56n)|(BigInt(0xffffff-59)<<8n)|(60n<<32n);
 const resolve=c=>c.functionName==='ownerOf'?A:c.functionName==='getPoolAndPositionInfo'?[k,info]:c.functionName==='getPositionLiquidity'?10n**18n:c.functionName==='getSlot0'?[1n<<96n,0,0,3000]:tokenCalls(c);
 const h=harness({kind:'nft',ids:['2'],manager:MANAGER,view:FACTORY,type:'v4'},resolve);const row=Object.values((await finish(h)).positions)[0];assert.equal(row.pool,pool);assert.equal(row.platform,'uniswap');
 const bad=harness({kind:'nft',ids:['2'],manager:MANAGER,view:FACTORY,type:'v4'},c=>c.functionName==='getPoolAndPositionInfo'?[k,0n]:resolve(c));assert.equal(Object.keys((await finish(bad)).positions).length,0);
});
test('a V4 owner transport failure remains unknown even when wallet NFT count is zero',async()=>{
 const h=harness({kind:'nft',ids:['2'],manager:MANAGER,view:FACTORY,type:'v4'},()=>{throw Error('offline');});
 h.state.nft_expected={'8453:test':'0'};
 const state=await finish(h);assert.equal(state.coverage['8453:test'].status,'partial');assert.equal(state.coverage['8453:test'].errors,1);assert.equal(Object.keys(state.positions).length,0);
});
test('principal records retain the raw calculation inputs without more provider calls',async()=>{
 const h=harness({kind:'nft',ids:['1'],manager:MANAGER,factory:FACTORY,platform:'uniswap',type:'v3'},c=>nftResolve(c));
 const row=Object.values((await finish(h)).positions)[0];assert.equal(row.audit.kind,'concentrated-liquidity');
 assert.deepEqual(math.liquidityAmounts(row.audit.liquidity_raw,row.audit.sqrt_price_x96,row.audit.tick_lower,row.audit.tick_upper).map(String),row.assets.map(a=>a.amount_raw));
});
test('a spoofed LP cannot claim reserves merely by naming a real factory',async()=>{
 const h=harness({kind:'pair',pool:POOL,factory:FACTORY,platform:'uniswap',type:'v2'},c=>({factory:FACTORY,token0:T0,token1:T1,totalSupply:100n,getReserves:[1000n,1000n,1n],balanceOf:10n,getPair:GAUGE}[c.functionName]));
 assert.equal(Object.keys((await finish(h)).positions).length,0);assert.equal(h.state.coverage['8453:test'].status,'partial');
});
test('paginated v4 discovery detects repeated pages and owner-count disagreement',async()=>{
 const h=harness({kind:'nft-history',manager:MANAGER,view:FACTORY,type:'v4',expected:'1',page:null,ids:[]},()=>0n,{ioExtra:{async transfers(){return {transfers:[],pageKey:'same'};}}});
 await finish(h);assert.equal(h.state.coverage['8453:test'].status,'partial');assert.ok(h.metrics().requests<10);
});
test('large directories resume with one request at a time and 32-contract multicalls',async()=>{
 const h=harness({kind:'stake-count',address:FACTORY,start:0,version:'V1_2'},c=>c.functionName==='poolCount'?3000n:[0n,0n,0n,0n],{maxReads:12});
 const result=await finish(h);assert.equal(result.cursor,95);assert.equal(result.complete,true);assert.equal(h.metrics().maxActive,1);assert.equal(h.metrics().maxBatch,32);assert.equal(Object.keys(result.positions).length,0);
});
test('legacy Sugar pages cover 30,002 pools without treating empty pages as completion',async()=>{
 const a=config.aero.find(a=>a.version==='legacy-basic');let pages=0;
 const h=harness({...a,kind:'aero-count'},c=>{
  if(c.functionName==='allPoolsLength')return 30002n;
  if(c.functionName==='positionsByFactory'){assert.ok(c.args[0]<=128n);pages++;return [];}
  if(c.functionName==='allPools')return '0x'+(10000n+c.args[0]).toString(16).padStart(40,'0');
  if(c.functionName==='gauges')return v.zeroAddress;if(c.functionName==='balanceOf')return 0n;throw Error(c.functionName);
 });
 const result=await finish(h);assert.equal(pages,235);assert.ok(result.complete);assert.equal(h.metrics().maxActive,1);assert.ok(h.metrics().requests<250);assert.equal(result.coverage['8453:test'].status,'checked');
});
test('known-claim refresh does not enqueue whole-pool or farm discovery',async()=>{
 const h=harness({kind:'seed'},c=>c.functionName==='poolCount'?0n:c.functionName==='balanceOf'?0n:tokenCalls(c));
 h.input.discover=false;const result=await finish(h);
 assert.ok(!result.tasks.some(t=>['aero-count','aero-sugar','aero-directory','farm-count','farm-scan'].includes(t.kind)));
 assert.equal(result.coverage['8453:new-position-discovery'].status,'not_requested');
});
