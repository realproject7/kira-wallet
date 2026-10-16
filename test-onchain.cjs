// Cache identity and RPC outage regressions. No network calls.
const assert=require('node:assert/strict');
const fs=require('fs'),os=require('os'),path=require('path');
const h=require('./onchain.cjs');
const {calls,registry,connect,scanChain}=require('./pipeline-onchain.cjs');
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
  console.log('Registry cache identity, incremental reads and RPC outage checks passed.');
})().catch(e=>{console.error(e);process.exitCode=1;}).finally(()=>{h.root=original;fs.rmSync(root,{recursive:true,force:true});});
