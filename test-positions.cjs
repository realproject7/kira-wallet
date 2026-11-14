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
 });const rows=Object.values((await finish(h)).positions);assert.equal(rows[0].platform,'mintclub-staking');assert.equal(rows[0].assets[0].amount,'100');assert.equal(rows[0].source_url,'https://mint.club/staking/base/37');assert.equal(rows[0].pool_id,'37');
 const nft=harness({kind:'stake',address,pool_id:'38',shares:'2',version:'V1_2'},()=>({stakingToken:T0,isStakingTokenERC20:false}));assert.equal(Object.values((await finish(nft)).positions)[0].assets[0].amount,'2');
 assert.equal('reward_token' in rows[0],false,'An unreported reward token stays absent.');
 // Two pools can hold the same token and amount. The reward token from the same pool read tells them apart.
 const REWARD='0x'+'Ab'.repeat(20);let poolReads=0;
 const paid=harness({kind:'stake',address,pool_id:'41',shares:String(5n*10n**18n),version:'V1_2'},c=>{
  if(c.functionName==='pools'){poolReads++;return {stakingToken:T0,isStakingTokenERC20:true,rewardToken:REWARD};}if(c.functionName==='isVault')return false;return tokenCalls(c);
 });const claim=Object.values((await finish(paid)).positions)[0];
 assert.equal(claim.reward_token,REWARD.toLowerCase());assert.equal(claim.label,'Staking pool #41');assert.equal(poolReads,1,'The reward token costs no extra read.');
 const none=harness({kind:'stake',address,pool_id:'42',shares:'1',version:'V1_2'},c=>c.functionName==='pools'?{stakingToken:T0,isStakingTokenERC20:true,rewardToken:'0x'+'0'.repeat(40)}:c.functionName==='isVault'?false:tokenCalls(c));
 assert.equal('reward_token' in Object.values((await finish(none)).positions)[0],false);
});
test('pruned chain state is rebuilt once at a fresh pin without mixing epochs',async()=>{
 const cid=4663,h=harness({kind:'nft-count',manager:MANAGER},c=>c.functionName==='balanceOf'||c.functionName==='poolCount'?0n:tokenCalls(c),{cid});
 h.input.discover=false;h.state.cursor=1;h.state.done=1;h.state.complete=true;
 h.state.blocks[cid]={number:'1',hash:'0x'+'b'.repeat(64),observed_at:'1970-01-01T00:00:00Z'};
 h.state.coverage[cid+':test']={id:cid+':test',chain_id:cid,status:'partial',errors:1};
 h.state.failed_tasks=[{index:0,scope:cid+':test',kind:'nft-count',reason:'method'}];
 h.state.positions.old={id:'old',chain_id:cid};h.state.positions.other={id:'other',chain_id:1};
 h.state.absent_positions=[cid+':old','1:other'];h.state.nft_expected={[cid+':old']:'1','1:other':'0'};
 h.state.nft_owned={[cid+':old:9']:true};
 let contexts=0;h.io.context=async(_cid,saved)=>{contexts++;assert.equal(saved,undefined);assert.equal(h.state.complete,false);return {block:{number:'100',hash:'0x'+'a'.repeat(64),observed_at:new Date().toISOString()}};};
 const result=await finish(h);
 assert.equal(contexts,1);assert.equal(result.pin_rechecks[cid],1);assert.equal(result.blocks[cid].number,'100');
 assert.equal(result.positions.old,undefined);assert.deepEqual(result.positions.other,{id:'other',chain_id:1});
 assert.deepEqual(result.absent_positions,['1:other']);assert.equal(result.nft_expected[cid+':old'],undefined);
 assert.equal(result.coverage[cid+':test'],undefined);assert.equal(result.failed_tasks[0].replaced_by_recheck,true);
 assert.equal(result.pin_recheck_history[0].previous_block,'1');assert.equal(result.rechecking_chain,undefined);
 assert.ok(h.metrics().maxActive<=1);assert.ok(result.last_slice_reads<=48);
});
test('a fresh-chain retry stays bounded when the provider still cannot read state',async()=>{
 const cid=4663,h=harness({kind:'nft-count',manager:MANAGER},()=>0n,{cid});h.input.discover=false;
 h.io.multi=async(_c,calls)=>calls.map(call=>({status:'failure',function:call.functionName,reason:'historical_state'}));
 const result=await finish(h);
 assert.equal(result.pin_rechecks[cid],1);assert.equal(result.pin_recheck_history.length,1);
 assert.equal(result.complete,true);assert.ok(Object.values(result.coverage).some(c=>c.status==='partial'));
 assert.ok(result.failed_tasks.some(f=>!f.replaced_by_recheck));
});
test('ordinary transport errors and recent method failures keep their original pin',async()=>{
 for(const [reason,date] of [['transport','1970-01-01T00:00:00Z'],['method',new Date().toISOString()]]){
  const cid=4663,h=harness({kind:'nft-count',manager:MANAGER},()=>0n,{cid});
  h.state.blocks[cid]={number:'1',hash:'0x'+'b'.repeat(64),observed_at:date};h.state.cursor=1;
  h.state.failed_tasks=[{index:0,scope:cid+':test',kind:'nft-count',reason}];
  const result=await finish(h);assert.equal(result.blocks[cid].number,'1');assert.equal(result.pin_rechecks[cid],undefined);
 }
});
test('pre-burst historical failures get one fresh recovery without waiting for stale pending tasks',async()=>{
 const cid=4663,h=harness({kind:'nft-count',manager:MANAGER},()=>0n,{cid});h.input.discover=false;
 h.state.cursor=1;h.state.pin_rechecks={[cid]:1};h.state.rechecking_chain=cid;
 h.state.blocks[cid]={number:'1',hash:'0x'+'b'.repeat(64),observed_at:'1970-01-01T00:00:00Z'};
 h.state.tasks.push({kind:'nft-count',scope:cid+':pending',chain_id:cid,manager:MANAGER});
 h.state.failed_tasks=[{index:0,scope:cid+':test',kind:'nft-count',reason:'historical_state'}];
 let contexts=0;h.io.context=async(_cid,saved)=>{contexts++;assert.equal(saved,undefined);return {block:{number:'100',hash:'0x'+'a'.repeat(64),observed_at:new Date().toISOString()}};};
 const s=await finish(h);assert.equal(s.pin_rechecks[cid],2);assert.equal(s.chain_recheck_version[cid],2);assert.equal(contexts,1);
 s.failed_tasks.push({index:0,scope:cid+':test',kind:'nft-count',reason:'historical_state'});
 await finish(h);assert.equal(s.pin_rechecks[cid],2);assert.equal(s.pin_recheck_history.length,1);assert.equal(contexts,1);
});
test('the recovery priority budget does not reset when another chain is rebuilt',async()=>{
 const cid=4663,h=harness({kind:'nft-count',manager:MANAGER},()=>0n,{cid});h.input.discover=false;
 h.input.networks.push({chain_id:1,environment:'mainnet'});h.state.recheck_slices=4;h.state.cursor=2;
 h.state.tasks.push({kind:'nft-count',scope:'1:test',chain_id:1,manager:MANAGER});
 for(const chain of [cid,1])h.state.blocks[chain]={number:'1',hash:'0x'+'b'.repeat(64),observed_at:'1970-01-01T00:00:00Z'};
 h.state.failed_tasks=[{index:0,scope:cid+':test',kind:'nft-count',reason:'historical_state'},{index:1,scope:'1:test',kind:'nft-count',reason:'historical_state'}];
 const s=await finish(h);assert.ok(s.recheck_slices>=6);assert.equal(s.pin_rechecks[cid],1);assert.equal(s.pin_rechecks[1],1);
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
test('new Aero Basic and CL gauges come from the canonical FactoryRegistry',async()=>{
 for(const type of ['basic','cl']){
  const a=config.aero.find(a=>a.chain_id===8453&&a.version.startsWith('aero-')&&a.type===type);let registryReads=0;
  const h=harness({...a,kind:'aero-directory',start:0,end:1},c=>{
   assert.notEqual(c.functionName,'gauge');
   if(c.functionName==='poolsIndexPaginated')return [{pool:POOL,creationTimestamp:1n}];
   if(c.functionName==='targetToGauge'){assert.equal(c.address,a.registry.toLowerCase());assert.deepEqual(c.args,[POOL]);registryReads++;return GAUGE;}
   if(c.functionName==='balanceOf')return c.address===GAUGE?5n*10n**18n:0n;
   if(c.functionName==='stakedValues')return [1n];
   if(c.functionName==='factory')return a.factory;
   if(c.functionName==='token0')return T0;if(c.functionName==='token1')return T1;
   if(c.functionName==='totalSupply')return 100n*10n**18n;
   if(c.functionName==='getReserves')return [100n*10n**18n,200n*10n**18n,1n];
   return nftResolve(c,{owner:GAUGE,factory:a.factory,manager:a.manager});
  });
  const s=await finish(h),rows=Object.values(s.positions);assert.equal(registryReads,1);assert.equal(rows.length,1);
  assert.equal(rows[0].custody_platform,'aerodrome');assert.equal(rows[0].gauge,GAUGE);
  if(type==='basic'){assert.equal(rows[0].receipt.custody,'gauge');assert.equal(rows[0].assets[0].amount,'5');assert.equal(rows[0].assets[1].amount,'10');}
 }
});
test('a missing new Aero gauge still records loose LP ownership',async()=>{
 const a=config.aero.find(a=>a.chain_id===8453&&a.version==='aero-basic');
 const h=harness({...a,kind:'aero-directory',start:0,end:1},c=>{
  if(c.functionName==='poolsIndexPaginated')return [{pool:POOL,creationTimestamp:1n}];
  if(c.functionName==='targetToGauge')return v.zeroAddress;
  if(c.functionName==='balanceOf'){assert.equal(c.address,POOL);return 5n;}
  if(c.functionName==='factory')return a.factory;if(c.functionName==='getPool')return POOL;
  if(c.functionName==='token0')return T0;if(c.functionName==='token1')return T1;
  if(c.functionName==='totalSupply')return 100n;if(c.functionName==='getReserves')return [1000n,2000n,1n];
  return tokenCalls(c);
 });const rows=Object.values((await finish(h)).positions);assert.equal(rows.length,1);assert.equal(rows[0].receipt.custody,'wallet');
});
test('legacy new-Aero gauge accessor failures receive one compatible chain rebuild',async()=>{
 const a=config.aero.find(a=>a.chain_id===4663&&a.version==='aero-basic');let registryReads=0;
 const h=harness({...a,kind:'aero-directory',start:0,end:1},c=>{
  assert.notEqual(c.functionName,'gauge');
  if(c.functionName==='balanceOf'||c.functionName==='poolCount')return 0n;
  if(c.functionName==='poolsIndexLength')return 1n;
  if(c.functionName==='poolsIndexPaginated')return [{pool:POOL,creationTimestamp:1n}];
  if(c.functionName==='targetToGauge'){registryReads++;return v.zeroAddress;}
  throw Error(c.functionName);
 },{cid:4663});h.state.cursor=1;h.state.blocks['4663']={number:'1',hash:'0x'+'b'.repeat(64),observed_at:'1970-01-01T00:00:00Z'};
 h.state.failed_tasks=[{index:0,scope:'4663:test',kind:'aero-directory',function:'gauge',reason:'contract'}];
 const s=await finish(h);assert.equal(s.gauge_registry_rechecks['4663'],1);assert.ok(registryReads>0);
 assert.equal(s.pin_recheck_history[0].reason,'gauge_registry');assert.equal(s.failed_tasks[0].replaced_by_recheck,true);
 assert.equal(s.pin_rechecks['4663'],undefined);assert.equal(s.complete,true);
});
test('superseded method failures cannot revive an already replaced chain epoch',async()=>{
 const a=config.aero.find(a=>a.chain_id===4663&&a.version==='aero-basic');
 const h=harness({...a,kind:'aero-directory',start:0,end:1},()=>0n,{cid:4663});
 h.state.cursor=1;h.state.blocks['4663']={number:'1',hash:'0x'+'b'.repeat(64),observed_at:'1970-01-01T00:00:00Z'};
 h.state.gauge_registry_rechecks={'4663':1};
 h.state.failed_tasks=[{index:0,scope:'4663:test',kind:'aero-directory',function:'gauge',reason:'method',replaced_by_recheck:true}];
 const s=await finish(h);assert.equal(s.blocks['4663'].number,'1');assert.equal(s.pin_rechecks['4663'],undefined);
 assert.equal(s.pin_recheck_history,undefined);assert.equal(s.complete,true);
});
test('known-claim refresh does not enqueue whole-pool or farm discovery',async()=>{
 const h=harness({kind:'seed'},c=>c.functionName==='poolCount'?0n:c.functionName==='balanceOf'?0n:tokenCalls(c));
 h.input.discover=false;const result=await finish(h);
 assert.ok(!result.tasks.some(t=>['aero-count','aero-sugar','aero-directory','farm-count','farm-scan'].includes(t.kind)));
 assert.equal(result.coverage['8453:new-position-discovery'].status,'not_requested');
});
test('chains without a supported pair factory do not probe every wallet token as an LP',async()=>{
 let factoryReads=0;const h=harness({kind:'seed'},c=>{if(c.functionName==='factory')factoryReads++;return 0n;},{cid:109});
 h.input.tokens=[{chain_id:109,address:T0,symbol:'SAMPLE'}];await finish(h);assert.equal(factoryReads,0);assert.ok(!h.state.tasks.some(t=>t.kind==='pair-discover'));
});

test('checked-zero staking claims retire independently of another pool RPC failure',async()=>{
 const direct='8453:'+FACTORY+':0',nested='8453:'+VAULT+':'+FACTORY+':0',unknown='8453:'+FACTORY+':1';
 const h=harness({kind:'stake-scan',address:FACTORY,start:0,end:2},c=>{if(c.args[1]===0n)return [0n,0n,0n,0n];throw Error('source down');});
 h.input.known_positions=[direct,nested,unknown].map(id=>({id,chain_id:8453}));
 const s=await finish(h);assert.equal(s.coverage['8453:test'].status,'partial');assert.deepEqual(new Set(s.absent_positions),new Set([direct,nested]));
});
test('an NFT transferred away is retired while unrelated ownership remains unknown',async()=>{
 const gone='8453:'+MANAGER+':1',unknown='8453:'+MANAGER+':2';
 const h=harness({kind:'nft',type:'v4',manager:MANAGER,view:FACTORY,ids:['1','2']},c=>{if(c.functionName==='ownerOf'&&c.args[0]===1n)return T0;throw Error('source down');});
 h.input.known_positions=[{id:gone},{id:unknown}];const s=await finish(h);assert.equal(s.coverage['8453:test'].status,'partial');assert.deepEqual(s.absent_positions,[gone]);
});
test('incomplete holdings discovery cannot become complete LP inventory coverage',async()=>{
 const h=harness({kind:'seed'},()=>0n,{cid:109});h.input.inventory_coverage=[{chain_id:109,status:'partial'}];
 const s=await finish(h);assert.equal(s.coverage['109:wallet-token-inventory'].status,'partial');assert.match(s.coverage['109:wallet-token-inventory'].message,/receipts may be missing/);
});
test('long NFT histories keep only the pending frontier rather than copying it into completed pages',async()=>{
 let peak=0;const h=harness({kind:'nft-history',type:'v4',manager:MANAGER,view:FACTORY,ids:[],page:null},c=>c.functionName==='ownerOf'?T0:0n,{ioExtra:{async transfers(c,args){
  const page=Number(args.pageKey||0);return {transfers:Array.from({length:100},(_,i)=>({rawContract:{address:MANAGER},tokenId:v.toHex(BigInt((page*100+i)%1024)),hash:'event-'+page+'-'+i})),...(page<63?{pageKey:String(page+1)}:{})};
 }}});
 for(let i=0;i<100;i++){const s=await h.reader().run(s=>{peak=Math.max(peak,Buffer.byteLength(JSON.stringify(s)));});if(s.complete)break;}
 assert.ok(h.state.complete);assert.ok(peak<200000,'checkpoint retained completed page payloads');
 assert.ok(h.state.tasks.filter(t=>t.kind==='nft-history').every(t=>!t.ids&&!t.seen_hashes));assert.equal(h.metrics().maxActive,1);
});
