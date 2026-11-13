'use strict';
const {test}=require('node:test'),assert=require('node:assert/strict');
const {v2AmountOut,inputAmounts,quotePool}=require('./cashout-quotes.cjs');
const TOKEN='0x'+'1'.repeat(40),OUTPUT='0x'+'2'.repeat(40),FACTORY='0x'+'3'.repeat(40),QUOTER='0x'+'4'.repeat(40),HASH='0x'+'a'.repeat(64);
function fixture(protocol='v2') {
 const token={token_address:TOKEN,wallet_balance_raw:'100',balance_block_number:'7',balance_block_hash:HASH};
 const pool={pool:'0x'+'5'.repeat(40),venue:'uniswap',source_url:'https://example.com/pool',rpc_verification:{verification:'official_factory_verified'},
  factory_measurement:{active_liquidity_verified:true,quote_token:OUTPUT,quote_decimals:0,quote_symbol:'USD',quote_balance:'1000',state:{factory:FACTORY,token0:TOKEN,token1:OUTPUT,getReserves:[1000n,1000n,0],fee:3000}}};
 const deployments=[{chainId:1,protocol,contract:protocol==='v2'?'UniswapV2Factory':'UniswapV3Factory',address:FACTORY},
  {chainId:1,protocol:'v3',contract:'QuoterV2',address:QUOTER,status:'active'}];
 return {token,pool,deployments};
}
test('canonical V2 output includes fee, price impact and integer rounding',async()=>{
 assert.equal(v2AmountOut(100n,1000n,1000n),90n);
 assert.equal(v2AmountOut(1000n,1000n,1000n),499n);
 assert.equal(v2AmountOut(10n**40n,1000n,1000n),999n);
 const {token,pool,deployments}=fixture();
 const quote=await quotePool({}, {chain_id:1},token,pool,7n,HASH,deployments);
 assert.equal(quote.output_amount,'90');assert.equal(quote.block_hash,HASH);
 assert.equal(quote.route_fees_included,true);assert.equal(quote.gas_included,false);assert.equal(quote.execution_verified,false);
 pool.factory_measurement.state.token0=OUTPUT;pool.factory_measurement.state.token1=TOKEN;
 pool.factory_measurement.state.getReserves=[2000n,1000n,0];
 assert.equal((await quotePool({}, {chain_id:1},token,pool,7n,HASH,deployments)).output_amount,'181');
});
test('verified V3 quote uses the held input and pinned block, with bounded partial-input fallback',async()=>{
 const {token,pool,deployments}=fixture('v3'),inputs=[];
 const client={readContract:async request=>{
  assert.equal(request.address,QUOTER);assert.equal(request.blockNumber,7n);
  assert.equal(request.args[0].tokenIn,TOKEN);assert.equal(request.args[0].tokenOut,OUTPUT);
  assert.equal(request.args[0].fee,3000);assert.equal(request.args[0].sqrtPriceLimitX96,0n);
  inputs.push(request.args[0].amountIn);if(inputs.length===1)throw Object.assign(new Error('Full input exceeds pool limits'),{name:'ExecutionRevertedError'});return [12n,1n,2,3n];
 }};
 const quote=await quotePool(client,{chain_id:1},token,pool,7n,HASH,deployments);
 assert.deepEqual(inputs,[100n,50n]);assert.equal(quote.partial_input,true);
 assert.equal(quote.input_amount_raw,'50');assert.equal(quote.holding_amount_raw,'100');assert.equal(quote.output_amount_raw,'12');
 assert.equal(quote.input_amount_is_maximum,true);
});
test('Aerodrome delegates stable or volatile curve and fee math to the verified pool',async()=>{
 const {token,pool}=fixture();pool.venue='aerodrome';pool.factory_measurement.state.factory='0x420DD381b31aEf6683db6B902084cB0FFECe40Da';
 const quote=await quotePool({readContract:async request=>{
  assert.equal(request.functionName,'getAmountOut');assert.deepEqual(request.args,[100n,TOKEN]);assert.equal(request.blockNumber,7n);return 20n;
 }},{chain_id:8453},token,pool,7n,HASH,[]);
 assert.equal(quote.kind,'aerodrome_pool');assert.equal(quote.output_amount,'20');
});
test('quick estimates never search partial balances after a full-input revert',async()=>{
 const {token,pool,deployments}=fixture('v3');let calls=0;
 const result=await quotePool({readContract:async()=>{calls++;throw Object.assign(Error('Synthetic revert'),{name:'ExecutionRevertedError'});}},
  {chain_id:1},token,pool,7n,HASH,deployments,{fullOnly:true});
 assert.equal(calls,1);assert.equal(result.status,'unknown');
});
test('quick V3 estimates reject a price boundary that can leave input unspent',async()=>{
 const {token,pool,deployments}=fixture('v3');
 for(const after of [undefined,4295128740n,1461446703485210103287273052203988822378723970341n]){
  const result=await quotePool({readContract:async()=>[10n,after,0,0n]},{chain_id:1},token,pool,7n,HASH,deployments,{fullOnly:true});
  assert.equal(result.status,'unknown');
  const deep=await quotePool({readContract:async()=>[10n,after,0,0n]},{chain_id:1},token,pool,7n,HASH,deployments);
  assert.equal(deep.status,'quoted');assert.equal(deep.input_amount_is_maximum,true);assert.equal(deep.partial_input,true);
 }
 for(const fullOnly of [false,true]){
  const full=await quotePool({readContract:async()=>[10n,2n**96n,0,0n]},{chain_id:1},token,pool,7n,HASH,deployments,{fullOnly});
  assert.equal(full.status,'quoted');assert.equal(full.partial_input,false);assert.equal(full.input_amount_is_maximum,false);
 }
});
test('failed and zero quotes stay unknown; deadline cancellation is not consumed by fallback',async()=>{
 const {token,pool,deployments}=fixture('v3');let calls=0;
 const failed=await quotePool({readContract:async()=>{calls++;throw new Error('RPC failed');}},{chain_id:1},token,pool,7n,HASH,deployments);
 assert.equal(failed.status,'unknown');assert.equal(calls,1);assert.match(failed.reason,/failed/);
 const zero=await quotePool({readContract:async()=>[0n]},{chain_id:1},token,pool,7n,HASH,deployments);
 assert.equal(zero.status,'unknown');assert.match(zero.reason,/other routes remain unknown/);
 await assert.rejects(quotePool({readContract:async()=>{throw Object.assign(new Error('Budget'),{code:'market_budget'});}},{chain_id:1},token,pool,7n,HASH,deployments),error=>error.code==='market_budget');
 assert.deepEqual(inputAmounts(1n),[1n]);
});
test('unrecognized factories, token mismatches and stale block hashes cannot produce a quote',async()=>{
 const {token,pool,deployments}=fixture();
 assert.equal((await quotePool({}, {chain_id:1},token,pool,8n,HASH,deployments)).status,'unknown');
 token.balance_block_hash='0x'+'b'.repeat(64);
 assert.equal((await quotePool({}, {chain_id:1},token,pool,7n,HASH,deployments)).status,'unknown');
 token.balance_block_hash=HASH;pool.factory_measurement.state.factory=QUOTER;
 assert.equal((await quotePool({}, {chain_id:1},token,pool,7n,HASH,deployments)).status,'unknown');
 pool.factory_measurement.state.factory=FACTORY;pool.factory_measurement.state.token0=QUOTER;
 assert.equal((await quotePool({}, {chain_id:1},token,pool,7n,HASH,deployments)).status,'unknown');
});

test('fallback batches preserve every sampled input, ordering and the full-input fast path',async()=>{
 const {token,pool,deployments}=fixture('v3');token.wallet_balance_raw='65536';
 const reverted=()=>Object.assign(Error('Synthetic contract revert'),{name:'ExecutionRevertedError'});
 let singles=0,batches=0;const sampled=[];
 const client={readContract:async q=>{singles++;sampled.push(q.args[0].amountIn);throw reverted();}};
 const batchRead=async contracts=>{batches++;assert(contracts.length<=3);return contracts.map(q=>{sampled.push(q.args[0].amountIn);return {status:'failure',error:reverted()};});};
 const unknown=await quotePool(client,{chain_id:1},token,pool,7n,HASH,deployments,{batchRead});
 assert.equal(unknown.status,'unknown');assert.deepEqual(sampled,inputAmounts(65536n));assert.equal(singles+batches,3);
 const fast=await quotePool({readContract:async()=>[12n]},{chain_id:1},token,pool,7n,HASH,deployments,{batchRead:async()=>assert.fail('Full input must not start a batch')});
 assert.equal(fast.input_amount_raw,'65536');
 const partial=await quotePool(client,{chain_id:1},token,pool,7n,HASH,deployments,{batchRead:async contracts=>contracts.map((q,i)=>({status:'success',result:[BigInt(i+12)]}))});
 assert.equal(partial.input_amount_raw,'32768');assert.equal(partial.output_amount_raw,'12');assert.equal(partial.holding_amount_raw,'65536');
});

test('a batched transport failure cannot be skipped for a later quote and budgets remain pauses',async()=>{
 const {token,pool,deployments}=fixture('v3');
 const client={readContract:async()=>{throw Object.assign(Error('Synthetic revert'),{name:'ExecutionRevertedError'});}};
 const unknown=await quotePool(client,{chain_id:1},token,pool,7n,HASH,deployments,{batchRead:async contracts=>contracts.map((q,i)=>i?{status:'success',result:[12n]}:{status:'failure',error:Object.assign(Error('Synthetic outage'),{name:'HttpRequestError'})})});
 assert.equal(unknown.status,'unknown');
 await assert.rejects(quotePool(client,{chain_id:1},token,pool,7n,HASH,deployments,{batchRead:async()=>{throw Object.assign(Error('Budget'),{code:'market_budget'});}}),e=>e.code==='market_budget');
 assert.equal((await quotePool(client,{chain_id:1},token,pool,7n,HASH,deployments,{batchRead:async()=>[]})).status,'unknown');
});

test('market pipeline pins quotes to holdings and reuses the durable quote after restart',async()=>{
 const fs=require('node:fs'),os=require('node:os'),path=require('node:path');
 const h=require('./onchain.cjs'),{dexChain}=require('./pipeline-onchain.cjs');
 const root=fs.mkdtempSync(path.join(os.tmpdir(),'kira-cashout-resume-'));
 const original={endpoints:h.endpoints,client:h.client,snapshotBlock:h.snapshotBlock};
 try {
  const deployed=JSON.parse(fs.readFileSync(path.join(__dirname,'sources/uniswap-deployments.json'))).records;
  const factory=deployed.find(d=>d.chainId===1&&d.contract==='UniswapV2Factory').address;
  const poolAddress='0x'+'5'.repeat(40),wallet='0x'+'6'.repeat(40),file=path.join(root,'market.json');
  let reads=0;
  const client={getChainId:async()=>1,multicall:async({contracts,blockNumber})=>{
   assert.equal(blockNumber,7n);reads++;
   return contracts.map(c=>({status:'success',result:{factory,token0:TOKEN,token1:OUTPUT,getReserves:[1000n,1000n,0],balanceOf:1000n,decimals:0,symbol:'USD'}[c.functionName]}));
  },readContract:async request=>{assert.equal(request.blockNumber,7n);assert.equal(request.functionName,'getPair');reads++;return poolAddress;}};
  h.endpoints=()=>['synthetic'];h.client=()=>client;
  h.snapshotBlock=async(c,saved)=>{assert.equal(saved.block_number,'7');assert.equal(saved.block_hash,HASH);return {number:7n,hash:HASH};};
  const token={chain_id:1,token_address:TOKEN,token_type:'ERC20',wallet_balance_raw:'100',balance_block_number:'7',balance_block_hash:HASH,
   dex_pools:[{pool:poolAddress,venue:'uniswap',version_labels:['v2'],source_url:'https://example.com/pool'}]};
  const first=await dexChain({chain_id:1},[token],{file,wallet});
  assert.equal(first[0].dex_pools[0].cashout_quote.output_amount,'90');
  const saved=JSON.parse(fs.readFileSync(file));assert.equal(saved.block_hash,HASH);assert.equal(saved.completed_pools.length,1);
  const before=reads;
  const fresh={...token,dex_pools:[{pool:poolAddress,venue:'uniswap',version_labels:['v2'],source_url:'https://example.com/pool'}]};
  const resumed=await dexChain({chain_id:1},[fresh],{file,wallet});
  assert.equal(reads,before);assert.deepEqual(resumed[0].dex_pools[0].cashout_quote,first[0].dex_pools[0].cashout_quote);
 }finally{Object.assign(h,original);fs.rmSync(root,{recursive:true,force:true});}
});

test('a failed market pool cannot repeatedly starve an unread qualifying pool after a budget pause',async()=>{
 const fs=require('node:fs'),os=require('node:os'),path=require('node:path');
 const h=require('./onchain.cjs'),{dexChain}=require('./pipeline-onchain.cjs');
 const root=fs.mkdtempSync(path.join(os.tmpdir(),'kira-market-retry-frontier-'));
 const original={endpoints:h.endpoints,client:h.client,snapshotBlock:h.snapshotBlock},now=Date.now;
 try{
  const factory=require('./sources/uniswap-deployments.json').records.find(d=>d.chainId===1&&d.contract==='UniswapV2Factory').address;
  const bad='0x'+'5'.repeat(40),good='0x'+'6'.repeat(40),wallet='0x'+'7'.repeat(40),file=path.join(root,'market.json');
  let clock=0;const reads=[];Date.now=()=>clock;
  h.endpoints=()=>['synthetic'];h.snapshotBlock=async()=>({number:7n,hash:HASH});
  h.client=()=>({getChainId:async()=>1,multicall:async({contracts})=>{
   const address=contracts[0].address;reads.push(address);
   if(address===bad){clock=20;return contracts.map(()=>({status:'failure',error:new Error('persistent synthetic pool outage')}));}
   return contracts.map(c=>({status:'success',result:{factory,token0:TOKEN,token1:OUTPUT,getReserves:[1000n,1000n,0],balanceOf:1000n,decimals:0,symbol:'USD'}[c.functionName]}));
  },readContract:async query=>{assert.equal(query.functionName,'getPair');return good;}});
  const create=()=>({chain_id:1,token_address:TOKEN,token_type:'ERC20',wallet_balance_raw:'100',balance_block_number:'7',balance_block_hash:HASH,
   dex_pools:[bad,good].map(pool=>({pool,venue:'uniswap',version_labels:['v2'],source_url:'https://example.com/pool'}))});
  const first=await dexChain({chain_id:1},[create()],{file,wallet,deadline:10});
  assert.equal(first[0].market_pending,true);assert.deepEqual(reads,[bad]);
  const saved=JSON.parse(fs.readFileSync(file));assert.equal(saved.pool_attempts[TOKEN.toLowerCase()+':'+bad],1);
  clock=0;const start=reads.length;
  const second=await dexChain({chain_id:1},[create()],{file,wallet,deadline:10});
  assert.equal(reads[start],good);assert.equal(second[0].dex_pools.find(p=>p.pool===good).cashout_quote.output_amount,'90');
  assert.equal(second[0].dex_pools.find(p=>p.pool===bad).cashout_quote,undefined);
  assert(JSON.parse(fs.readFileSync(file)).completed_pools.includes(TOKEN.toLowerCase()+':'+good));
 }finally{Date.now=now;Object.assign(h,original);fs.rmSync(root,{recursive:true,force:true});}
});

test('V4 keys require an exact pool ID; quotes use the reviewed full-input quoter',async()=>{
 const {v4Key,v4KeyId}=require('./cashout-quotes.cjs'),{zeroAddress}=require('viem');
 const {token,pool,deployments}=fixture();const key={currency0:TOKEN,currency1:OUTPUT,fee:10000,tickSpacing:100,hooks:zeroAddress};
 pool.pool=v4KeyId(key);pool.paired_tokens=[{address:OUTPUT},{address:TOKEN}];pool.rpc_verification={verification:'initialized_at_official_v4_state_view',state_view:FACTORY};
 pool.factory_measurement.state={token0:TOKEN,token1:OUTPUT,pool_key:key,pool_manager:FACTORY};
 deployments.push(...['PoolManager','StateView','V4Quoter'].map(contract=>({chainId:1,protocol:'v4',contract,address:contract==='V4Quoter'?QUOTER:FACTORY,status:'active',fullInputChecked:true})));
 assert.deepEqual(v4Key(pool,10000),key);assert.equal(v4Key(pool,3000),null);
 assert.equal(v4Key({...pool,pool:v4KeyId({...key,hooks:QUOTER})},10000),null);
 let reads=0;const client={readContract:async q=>{reads++;assert.equal(q.address,QUOTER);assert.equal(q.blockNumber,7n);assert.deepEqual(q.args[0],{poolKey:key,zeroForOne:true,exactAmount:100n,hookData:'0x'});return [123n,40000n];}};
 const quote=await quotePool(client,{chain_id:1},token,pool,7n,HASH,deployments,{fullOnly:true});
 assert.equal(reads,1);assert.equal(quote.kind,'uniswap_v4_quoter');assert.equal(quote.output_amount,'123');assert.equal(quote.partial_input,false);assert.equal(quote.full_input_verified,true);
 for(const mutate of [p=>{p.factory_measurement.state.pool_key.tickSpacing=60;},p=>{p.rpc_verification.state_view=OUTPUT;},p=>{p.factory_measurement.state.pool_manager=OUTPUT;}]){
  const bad=structuredClone(pool);mutate(bad);assert.equal((await quotePool(client,{chain_id:1},token,bad,7n,HASH,deployments,{fullOnly:true})).status,'unknown');
 }
 const outdated=structuredClone(deployments);outdated.find(d=>d.protocol==='v4'&&d.contract==='V4Quoter').fullInputChecked=false;
 assert.equal((await quotePool(client,{chain_id:1},token,pool,7n,HASH,outdated)).status,'unknown');
 token.wallet_balance_raw=String(1n<<127n);assert.equal((await quotePool(client,{chain_id:1},token,pool,7n,HASH,deployments)).status,'unknown');assert.equal(reads,1);
});

test('representative verification selects the liquid V4 market before a dust address pool',async()=>{
 const fs=require('node:fs'),os=require('node:os'),path=require('node:path'),{zeroAddress}=require('viem');
 const h=require('./onchain.cjs'),{dexChain}=require('./pipeline-onchain.cjs'),{v4KeyId}=require('./cashout-quotes.cjs');
 const original={endpoints:h.endpoints,client:h.client,snapshotBlock:h.snapshotBlock},root=fs.mkdtempSync(path.join(os.tmpdir(),'kira-v4-market-'));
 try{
  let reads=0;const deployed=require('./sources/uniswap-deployments.json').records,quoter=deployed.find(d=>d.chainId===8453&&d.contract==='V4Quoter').address;
  const key={currency0:zeroAddress,currency1:TOKEN,fee:10000,tickSpacing:200,hooks:zeroAddress},id=v4KeyId(key);
  const client={getChainId:async()=>8453,multicall:async({contracts,blockNumber})=>{reads++;assert.equal(blockNumber,7n);return contracts.map(q=>({status:'success',result:q.functionName==='getSlot0'?[2n**96n,0,0,10000]:10000n}));},
   readContract:async q=>{reads++;assert.equal(q.address,quoter);assert.equal(q.blockNumber,7n);assert.equal(q.args[0].zeroForOne,false);return [10n**18n,50000n];}};
  h.endpoints=()=>['synthetic'];h.client=()=>client;h.snapshotBlock=async()=>({number:7n,hash:HASH});
  const input={chain_id:8453,token_address:TOKEN,token_type:'ERC20',wallet_balance_raw:'100',balance_block_number:'7',balance_block_hash:HASH,dex_pools:[
   {pool:'0x'+'5'.repeat(40),venue:'aerodrome',reported_liquidity:{usd:4},paired_tokens:[{address:TOKEN},{address:OUTPUT}]},
   {pool:id,venue:'uniswap',version_labels:['v4'],reported_liquidity:{usd:500000},paired_tokens:[{address:TOKEN},{address:zeroAddress}],source_url:'https://example.com/pool'}]};
  const file=path.join(root,'market.json'),[token]=await dexChain({chain_id:8453},[structuredClone(input)],{file,wallet:'0x'+'6'.repeat(40),representative:true,fullOnly:true});
  const pool=token.dex_pools.find(p=>p.pool===id);assert.equal(pool.cashout_quote.kind,'uniswap_v4_quoter');assert.equal(pool.cashout_quote.output_symbol,'ETH');assert.equal(pool.cashout_quote.output_amount,'1');
  assert.equal(token.dex_pools[0].cashout_quote,undefined);const before=reads;
  const [resumed]=await dexChain({chain_id:8453},[structuredClone(input)],{file,wallet:'0x'+'6'.repeat(40),representative:true,fullOnly:true});
  assert.equal(reads,before);assert.equal(resumed.dex_pools.find(p=>p.pool===id).cashout_quote.output_amount,'1');
 }finally{Object.assign(h,original);fs.rmSync(root,{recursive:true,force:true});}
});
