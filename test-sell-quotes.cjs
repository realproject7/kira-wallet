const {test}=require('node:test'),assert=require('node:assert/strict');
const h=require('./onchain.cjs'),p=require('./pipeline-onchain.cjs'),{collect}=require('./sell-quotes.cjs');
const TOKEN='0x'+'1'.repeat(40),OUTPUT='0x4200000000000000000000000000000000000006',POOL='0x'+'3'.repeat(40),WALLET='0x'+'9'.repeat(40),HASH='0x'+'a'.repeat(64);
const input=()=>({wallet:WALLET,networks:[{chain_id:8453,environment:'mainnet'}],tokens:[{chain_id:8453,token_address:TOKEN,token_type:'ERC20',wallet_balance_raw:'100',dex_pools:[{pool:POOL,venue:'aerodrome',version_labels:[]}]}]});
test('bounded collector rechecks quantity, verifies the official pool and quotes at one block',async()=>{
  const original={client:h.client,endpoints:h.endpoints,snapshotBlock:h.snapshotBlock};let reads=0,quotes=0;
  try{
    h.endpoints=()=>['synthetic'];h.snapshotBlock=async(c,pin)=>{if(pin){assert.equal(pin.block_number,'9');assert.equal(pin.block_hash,HASH);}return {number:9n,hash:HASH};};
    h.client=()=>({getChainId:async()=>8453,multicall:async({contracts,blockNumber})=>{
      reads++;assert.equal(blockNumber,9n);
      return contracts.map(q=>({status:'success',result:q.functionName==='balanceOf'?q.args[0]===WALLET?100n:1000n:
        {factory:'0x420dd381b31aef6683db6b902084cb0ffece40da',token0:TOKEN,token1:OUTPUT,getReserves:[1000n,1000n,0],decimals:18,symbol:'WETH'}[q.functionName]}));
    },readContract:async q=>{
      reads++;assert.equal(q.blockNumber,9n);
      if(q.functionName==='stable')return false;
      if(q.functionName==='getPool')return POOL;
      assert.equal(q.functionName,'getAmountOut');assert.deepEqual(q.args,[100n,TOKEN]);quotes++;return 2n*10n**18n;
    }});
    const source=input(),before=JSON.stringify(source),result=await collect(source);
    assert.equal(result.status,'checked');assert.equal(result.records[0].quote.output_amount,'2');
    assert.equal(result.records[0].quote.partial_input,false);assert.equal(result.records[0].balance_block_number,'9');
    assert.equal(quotes,1);assert(reads<=7);assert.equal(JSON.stringify(source),before);
  }finally{Object.assign(h,original);}
});
test('changed holdings, failed balances and exhausted budgets never quote or turn unknown into zero',async()=>{
  const original={connect:p.connect,calls:p.calls,dexChain:p.dexChain,snapshotBlock:h.snapshotBlock};
  try{
    p.connect=async()=>({});h.snapshotBlock=async()=>({number:9n,hash:HASH});p.dexChain=async()=>assert.fail('Do not quote an unverified quantity');
    for(const balance of [{status:'success',result:99n},{status:'failure',error:Error('unavailable')}]){
      p.calls=async()=>[balance];const result=await collect(input());
      assert.equal(result.records[0].status,'unknown');assert.equal(result.records[0].quote,undefined);
    }
    const result=await collect({...input(),budget_ms:0});assert.equal(result.status,'partial');assert.deepEqual(result.records,[]);
  }finally{Object.assign(p,{connect:original.connect,calls:original.calls,dexChain:original.dexChain});h.snapshotBlock=original.snapshotBlock;}
});
