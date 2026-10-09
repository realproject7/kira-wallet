// Cache identity and RPC outage regressions. No network calls.
const assert=require('node:assert/strict');
const fs=require('fs'),os=require('os'),path=require('path');
const h=require('./onchain.cjs');
const {calls,registry,connect,scanChain,balanceReads,dexChain,reserveChain,MarketBudget}=require('./pipeline-onchain.cjs');
const root=fs.mkdtempSync(path.join(os.tmpdir(),'wallet-registry-test-'));
const original=h.root;h.root=root;
const addresses=['0x0000000000000000000000000000000000000001','0x0000000000000000000000000000000000000002','0x0000000000000000000000000000000000000003'];
const network={chain_id:999,mintclub_bond_address:'0x0000000000000000000000000000000000000004'};
const cacheFile=path.join(root,'cache/mintclub-registry','999-'+network.mintclub_bond_address+'.json');
const seed=()=>{fs.mkdirSync(path.dirname(cacheFile),{recursive:true});fs.writeFileSync(cacheFile,JSON.stringify({
  chain_id:999,bond_address:network.mintclub_bond_address,entries:[
    {index:0,address:addresses[0],token_type:'ERC20',decimals:18},
    {index:1,address:addresses[1],token_type:'ERC1155',decimals:0}]}));};
(async()=>{
  let requests=[];
  const client={
    readContract:async()=>3n,
    multicall:async({contracts})=>{requests.push(...contracts);return contracts.map(c=>({status:'success',result:c.functionName==='tokens'?addresses[Number(c.args[0])]:18}));}
  };
  seed();
  const current=await registry(client,network,100n);
  assert.equal(current.cache_reused,2);assert.equal(current.entries.length,3);assert.equal(current.errors,0);
  assert.equal(requests.filter(c=>c.functionName==='decimals').length,1);
  assert.equal(current.entries[1].token_type,'ERC1155');
  const saved=JSON.parse(fs.readFileSync(cacheFile));
  assert(!JSON.stringify(saved).includes('balance_raw'));
  seed();requests=[];
  const drift={
    ...client,
    multicall:async({contracts})=>{
      requests.push(...contracts);
      return contracts.map(c=>({status:'success',result:c.functionName==='tokens'?addresses[Number(c.args[0])===1?2:Number(c.args[0])]:18}));
    }
  };
  const rebuilt=await registry(drift,network,101n);
  assert.equal(rebuilt.cache_reused,0);
  assert.equal(requests.filter(c=>c.functionName==='decimals').length,3);
  let outages=0;
  const outage={multicall:async()=>{outages++;const e=new Error('offline');e.name='HttpRequestError';throw e;}};
  const failed=await calls(outage,Array.from({length:100},()=>({})),102n);
  assert.equal(outages,1);assert.equal(failed.length,100);assert(failed.every(r=>r.status==='failure'));
  let wrappedRequests=0;
  const wrapped={multicall:async()=>{wrappedRequests++;const cause=Object.assign(new Error('offline'),{name:'HttpRequestError',status:429});throw Object.assign(new Error('HTTP request failed'),{name:'ContractFunctionExecutionError',cause});}};
  assert((await calls(wrapped,[{},{},{}],102n)).every(r=>r.status==='failure'));assert.equal(wrappedRequests,1);
  let limitedRequests=0;
  const limited={multicall:async({contracts,blockNumber})=>{limitedRequests++;assert.equal(blockNumber,103n);if(contracts.length>2)throw Object.assign(new Error('Payload too large'),{name:'HttpRequestError',status:413});return contracts.map(()=>({status:'success',result:1n}));}};
  assert((await calls(limited,Array.from({length:8},()=>({})),103n)).every(r=>r.status==='success'));assert.equal(limitedRequests,7);
  const aggregateAbi=h.viem.parseAbi(['function aggregate3((address target, bool allowFailure, bytes callData)[] calls) payable returns ((bool success, bytes returnData)[] returnData)']);
  const balanceAbi=h.viem.parseAbi(['function balanceOf(address) view returns (uint256)']);
  let actualRequests=0;
  const {RpcPool}=require('./rpc-pool.cjs'),pool=new RpcPool({interval:0}),hash='0x'+'a'.repeat(64);pool.pin(999,103n,hash);
  const transport=()=>h.viem.custom({request:async({method,params})=>{
    if(method==='eth_chainId')return '0x3e7';if(method==='eth_getBlockByNumber')return {number:'0x67',hash};
    assert.equal(method,'eth_call');assert.deepEqual(params[1],{blockHash:hash,requireCanonical:true});actualRequests++;
    const batch=h.viem.decodeFunctionData({abi:aggregateAbi,data:params[0].data}).args[0];
    if(batch.length>2)throw Object.assign(new Error('Payload too large'),{code:-32005});
    return h.viem.encodeFunctionResult({abi:aggregateAbi,functionName:'aggregate3',result:batch.map(()=>({success:true,returnData:h.viem.encodeAbiParameters([{type:'uint256'}],[1n])}))});
  }},{retryCount:0});
  const actual=h.viem.createPublicClient({transport:pool.transport(999,['synthetic'],transport)});
  const realResults=await calls(actual,Array.from({length:8},(_,i)=>({address:'0x'+(i+1).toString(16).padStart(40,'0'),abi:balanceAbi,functionName:'balanceOf',args:[addresses[1]]})),103n);
  assert(realResults.every(r=>r.status==='success'&&r.result===1n));assert.equal(actualRequests,7);
  const diagnostic=h.safeError(Object.assign(new Error('Failure https://private.example/SECRET-MARKER'),{name:'ContractFunctionExecutionError',cause:{status:413,code:-32005}}));
  assert.equal(diagnostic.http_status,413);assert.equal(diagnostic.rpc_code,-32005);assert(!JSON.stringify(diagnostic).includes('SECRET-MARKER'));
  const originalEndpoints=h.endpoints,originalClient=h.client;
  try {
    const tried=[];
    h.endpoints=()=>['custom','public'];
    h.client=(chain,url)=>({getChainId:async()=>{tried.push(url);return url==='custom'?1:8453;}});
    await connect({chain_id:8453,public_rpc:['must-not-use-unconfigured']});
    assert.deepEqual(tried,[undefined]);
    h.endpoints=()=>['custom'];tried.length=0;h.client=()=>({getChainId:async()=>{tried.push('custom');return 1;}});
    await assert.rejects(connect({chain_id:8453,public_rpc:['must-not-use-unconfigured']}),/identity mismatch/);
    assert.deepEqual(tried,['custom']);
    h.endpoints=()=>[];await assert.rejects(connect({chain_id:8453}),/No RPC endpoint/);
  } finally {h.endpoints=originalEndpoints;h.client=originalClient;}
  const originalSnapshot=h.snapshotBlock;
  try {
    const candidateContracts=Array.from({length:200},(_,i)=>({chain_id:999,address:'0x'+(i+10).toString(16).padStart(40,'0')}));
    h.endpoints=()=>['synthetic'];h.snapshotBlock=async()=>({number:103n,hash});
    h.client=()=>({getChainId:async()=>999,getBalance:async()=>1n,
      multicall:async({contracts})=>contracts.map(c=>({status:'success',result:c.functionName==='balanceOf'?1n:c.functionName==='decimals'?18:c.functionName==='exists'?false:'TEST'}))});
    const row=await scanChain({wallet:addresses[0],candidates:candidateContracts},network,path.join(root,'initial'),true);
    assert.equal(row.tokens.length,128);assert.equal(row.candidate_scan.total,200);
    assert.equal(row.candidate_scan.deferred,72);assert.equal(row.candidate_scan.complete,false);
    assert.equal(row.registry_scan.phase,'deferred');assert.equal(row.registry_scan.complete,false);
    assert.equal(row.status,'partial');
  } finally {h.endpoints=originalEndpoints;h.client=originalClient;h.snapshotBlock=originalSnapshot;}
  try {
    let reads=0;
    h.endpoints=()=>['synthetic'];h.snapshotBlock=async()=>({number:103n,hash});
    h.client=()=>({getChainId:async()=>999,getBalance:async()=>1n,readContract:async()=>0n,
      multicall:async({contracts})=>contracts.map(c=>{if(c.functionName==='balanceOf')reads++;return {status:'success',result:c.functionName==='balanceOf'?1n:c.functionName==='decimals'?18:'TEST'};})});
    const output=path.join(root,'expanded');
    const first=await scanChain({wallet:addresses[0],candidates:[{chain_id:999,address:addresses[1]}]},network,output);
    assert.equal(first.status,'complete');const observed=first.tokens[0].balance_observed_at;
    const more=await scanChain({wallet:addresses[0],candidates:[{chain_id:999,address:addresses[1]},{chain_id:999,address:addresses[2]}]},network,output);
    assert.equal(more.status,'complete');assert.equal(more.candidate_scan.total,2);assert.equal(more.tokens.length,2);assert.equal(reads,2);
    assert.equal(more.tokens[0].balance_observed_at,observed);
  } finally {h.endpoints=originalEndpoints;h.client=originalClient;h.snapshotBlock=originalSnapshot;}
  const balanceFile=path.join(root,'balance-prefix.json'),checkpoint={balances:{}};
  const plans=Array.from({length:257},(_,i)=>({address:'0x'+(i+100).toString(16).padStart(40,'0'),token_type:'ERC20'}));
  let balanceCalls=0;
  const interrupted={multicall:async({contracts,blockNumber})=>{assert.equal(blockNumber,103n);if(++balanceCalls===2)throw new MarketBudget();return contracts.map(()=>({status:'success',result:7n}));}};
  await assert.rejects(balanceReads(interrupted,plans,addresses[0],103n,checkpoint,balanceFile,network),MarketBudget);
  assert.equal(Object.keys(JSON.parse(fs.readFileSync(balanceFile)).balances).length,128);
  balanceCalls=0;
  const resumed={multicall:async({contracts,blockNumber})=>{assert.equal(blockNumber,103n);balanceCalls++;return contracts.map(()=>({status:'success',result:7n}));}};
  assert((await balanceReads(resumed,plans,addresses[0],103n,JSON.parse(fs.readFileSync(balanceFile)),balanceFile,network)).every(r=>r.result===7n));
  assert.equal(balanceCalls,2);
  let freshReads=0;
  await balanceReads({multicall:async({contracts,blockNumber})=>{assert.equal(blockNumber,104n);freshReads+=contracts.length;return contracts.map(c=>{assert.equal(c.args[0],addresses[1]);return {status:'success',result:9n};});}},plans,addresses[1],104n,{balances:{}},path.join(root,'fresh-prefix.json'),network);
  assert.equal(freshReads,257);
  let marketCalls=0,slow=true,savedBlocks=[];
  const marketFile=path.join(root,'market-prefix.json');
  const marketTokens=()=>[{chain_id:999,token_address:addresses[0],token_type:'ERC20',wallet_balance_raw:'7',balance_block_number:'103',dex_pools:[1,2].map(i=>({pool:addresses[i],venue:'uniswap',version_labels:['v2']}))}];
  try {
    h.endpoints=()=>['synthetic'];h.snapshotBlock=async(c,saved)=>{savedBlocks.push(saved?.block_number||null);return {number:103n,hash};};
    h.client=()=>({getChainId:async()=>999,multicall:async({contracts,blockNumber})=>{
      assert.equal(blockNumber,103n);marketCalls++;
      if(slow&&marketCalls===2)await new Promise(resolve=>setTimeout(resolve,100));
      return contracts.map(c=>({status:'success',result:c.functionName==='getReserves'?[1n,1n,0]:c.functionName==='token0'?addresses[0]:c.functionName==='token1'?addresses[1]:'0x'+'f'.repeat(40)}));
    }});
    const partial=await dexChain(network,marketTokens(),{file:marketFile,wallet:addresses[0],deadline:Date.now()+30});
    assert.equal(partial[0].market_pending,true);
    assert.equal(JSON.parse(fs.readFileSync(marketFile)).completed_pools.length,1);
    slow=false;marketCalls=0;
    const finished=await dexChain(network,marketTokens(),{file:marketFile,wallet:addresses[0],deadline:Date.now()+1000});
    assert.equal(finished[0].market_pending,undefined);assert.equal(marketCalls,1);assert.equal(savedBlocks.at(-1),'103');
    assert.equal(finished[0].dex_pools[0].rpc_verification.verification,'unverified');
    await assert.rejects(dexChain(network,marketTokens(),{file:marketFile,wallet:addresses[1]}),/does not match/);
    assert(!fs.readFileSync(marketFile,'utf8').includes('synthetic'));
    // A transient failed pool is retried after a different pool hits the budget.
    const failureFile=path.join(root,'transient-prefix.json');marketCalls=0;slow=true;
    const make=h.client;
    h.client=()=>{const client=make();const multi=client.multicall;client.multicall=async args=>{if(marketCalls===0){marketCalls++;return args.contracts.map(()=>({status:'failure',error:{message:'HTTP 503'}}));}return multi(args);};return client;};
    await dexChain(network,marketTokens(),{file:failureFile,wallet:addresses[0],deadline:Date.now()+30});
    assert.equal(JSON.parse(fs.readFileSync(failureFile)).completed_pools.length,0);
    h.client=make;slow=false;marketCalls=0;
    const retried=await dexChain(network,marketTokens(),{file:failureFile,wallet:addresses[0],deadline:Date.now()+1000});
    assert.equal(marketCalls,2);assert.equal(retried[0].market_pending,undefined);
    // A deadline in a 413 singleton fallback must propagate as a pause.
    await assert.rejects(calls({multicall:async()=>{throw Object.assign(new Error('Payload too large'),{status:413});},readContract:async()=>{throw new MarketBudget();}},[{}],103n),MarketBudget);
    // A budget signal can arrive before the wall-clock deadline. Its pool is incomplete.
    const earlyFile=path.join(root,'early-budget-prefix.json');
    h.client=()=>({getChainId:async()=>999,multicall:async()=>{throw new MarketBudget();}});
    const early=await dexChain(network,marketTokens(),{file:earlyFile,wallet:addresses[0],deadline:Date.now()+1000});
    assert.equal(early[0].market_pending,true);
    assert.equal(JSON.parse(fs.readFileSync(earlyFile)).completed_pools.length,0);
    const reserveFile=path.join(root,'reserve-test','graph.json');let reserveReads=0;
    h.client=()=>({getChainId:async()=>999,readContract:async()=>{reserveReads++;return false;}});
    const reserveInput={wallet:addresses[0],tokens:[{chain_id:999,token_address:addresses[0],mintclub:{}}]};
    const reserveFirst=await reserveChain(network,reserveInput,reserveFile,Date.now()+1000);
    const reserveAgain=await reserveChain(network,reserveInput,reserveFile,Date.now()+1000);
    assert.equal(reserveReads,1);assert.equal(reserveFirst.tokens[0].block_number,103n);assert.equal(reserveAgain.tokens[0].block_number,103n);
    assert.equal(reserveAgain.market_pending,false);
  } finally {h.endpoints=originalEndpoints;h.client=originalClient;h.snapshotBlock=originalSnapshot;}
  console.log('Registry cache identity, incremental reads and RPC outage checks passed.');
})().catch(e=>{console.error(e);process.exitCode=1;}).finally(()=>{h.root=original;fs.rmSync(root,{recursive:true,force:true});});
