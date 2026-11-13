'use strict';
const {test}=require('node:test'),assert=require('node:assert/strict');
const fs=require('fs'),os=require('os'),path=require('path');
const h=require('./onchain.cjs'),dex=require('./dex-adapters.cjs');
const {dexChain}=require('./pipeline-onchain.cjs'),{quotePool,v2AmountOut}=require('./cashout-quotes.cjs');
const address=n=>'0x'+n.toString(16).padStart(40,'0'),HASH='0x'+'a'.repeat(64),TOKEN=address(10),POOL=address(20),WALLET=address(1);
const WETH='0x4200000000000000000000000000000000000006',WBNB='0xbb4CdB9CBd36B01bD1cBaEBF2De08d9173bc095c';

test('Pancake V2 applies 25 basis points, independently of the Uniswap 30 basis points',()=>{
 assert.equal(v2AmountOut(10000n,10000n,10000n,25),4993n);
 assert.equal(v2AmountOut(10000n,10000n,10000n),4992n);
 assert.throws(()=>v2AmountOut(1n,1n,1n,-1));
 assert(!dex.supported(1,{pool:POOL,venue:'pancakeswap',version_labels:['v3']}));
 assert(!dex.supported(56,{pool:HASH,venue:'pancakeswap',version_labels:['infinity']}));
});

for(const type of ['v2','v3','basic','cl'])test(`official ${type} pools retain amount, chain, factory and quote identity across restart`,async()=>{
 const root=fs.mkdtempSync(path.join(os.tmpdir(),'kira-dex-adapter-')),original={endpoints:h.endpoints,client:h.client,snapshotBlock:h.snapshotBlock};
 try{
  const chain=['v2','v3'].includes(type)?56:8453,a=dex.records.find(r=>r.chain_id===chain&&r.type===type),output=chain===56?WBNB:WETH;
  const requests=[];
  const query=q=>{
   assert.equal(q.blockNumber,7n);requests.push(q);
   const values={factory:a.factory,token0:TOKEN,token1:output,getReserves:[10000n,10000n,0n],liquidity:10000n,fee:2500,tickSpacing:50,balanceOf:10000n,decimals:0,symbol:'OUTPUT',getPool:POOL,getPair:POOL};
   if(q.functionName==='getPool'&&type==='cl')assert.equal(q.abi.find(x=>x.name==='getPool').inputs[2].type,'int24');
   if(q.functionName==='getPool'&&type==='basic')assert.equal(q.args.length,2);
   if(q.functionName.startsWith('quoteExactInput')){
    assert.equal(q.address,a.quoter);
    if(type==='v3'){assert.equal(q.args[0].fee,2500);assert.equal(q.args[0].amountIn,100n);return [90n,2n**96n,0,1n];}
    assert.equal(q.args[0],POOL);assert([TOKEN,output].includes(q.args[1]));assert.equal(q.args[2],100n);
    assert.equal(q.functionName,type==='cl'?'quoteExactInputSingleV3':'quoteExactInputSingleV2');
    return type==='cl'?[90n,2n**96n,0]:90n;
   }
   assert(q.functionName in values,'Unexpected call '+q.functionName);return values[q.functionName];
  };
  h.endpoints=()=>['synthetic'];h.snapshotBlock=async()=>({number:7n,hash:HASH});
  h.client=()=>({getChainId:async()=>chain,readContract:async q=>query(q),multicall:async({contracts,blockNumber})=>contracts.map(q=>({status:'success',result:query({...q,blockNumber})}))});
  const input={chain_id:chain,token_address:TOKEN,token_type:'ERC20',wallet_balance_raw:'100',balance_block_number:'7',balance_block_hash:HASH,
   dex_pools:[{pool:POOL,venue:a.venue,version_labels:[type==='cl'?'v2':type==='basic'?'v3':type],paired_tokens:[{address:TOKEN},{address:output}],source_url:'https://example.com/pool'}]};
  const second={...structuredClone(input),token_address:output};
  const file=path.join(root,'market.json'),[result]=await dexChain({chain_id:chain},[structuredClone(input),structuredClone(second)],{file,wallet:WALLET,representative:true,fullOnly:true});
  const pool=result.dex_pools[0];assert.equal(pool.rpc_verification.verification,'official_factory_verified');assert.equal(pool.cashout_quote.kind,a.kind);
  assert.equal(pool.cashout_quote.partial_input,false);assert.equal(pool.cashout_quote.block_hash,HASH);
  assert.equal(pool.cashout_quote.input_amount_raw,'100');assert.equal(pool.cashout_quote.output_address,output.toLowerCase());
  if(['cl','basic'].includes(type))assert.match(pool.cashout_quote.fee_context,/MEV tax/);
  const count=requests.length;await dexChain({chain_id:chain},[structuredClone(input),structuredClone(second)],{file,wallet:WALLET,representative:true,fullOnly:true});assert.equal(requests.length,count);
  const impostor=structuredClone(pool);impostor.factory_measurement.state.factory=address(999);
  assert.equal((await quotePool({readContract:async()=>assert.fail('Unknown factory must not quote')},{chain_id:chain},result,impostor,7n,HASH,[])).status,'unknown');
  if(type==='cl'||type==='v3'){
   const boundary=await quotePool({readContract:async()=>[90n,4295128740n,0,1n]},{chain_id:chain},result,pool,7n,HASH,[],{fullOnly:true});
   assert.equal(boundary.status,'unknown');
  }
 }finally{Object.assign(h,original);fs.rmSync(root,{recursive:true,force:true});}
});
