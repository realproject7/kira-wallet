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
