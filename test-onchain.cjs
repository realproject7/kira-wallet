// Cache identity and RPC outage regressions. No network calls.
const assert=require('node:assert/strict');
const fs=require('fs'),os=require('os'),path=require('path');
const h=require('./onchain.cjs');
const {calls,registry,connect}=require('./pipeline-onchain.cjs');
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
  const originalEndpoints=h.endpoints,originalClient=h.client;
  try {
    const tried=[];
    h.endpoints=()=>['custom','public'];
    h.client=(chain,url)=>({getChainId:async()=>{tried.push(url);return url==='custom'?1:8453;}});
    await connect({chain_id:8453,public_rpc:['must-not-use-unconfigured']});
    assert.deepEqual(tried,['custom','public']);
    h.endpoints=()=>['custom'];tried.length=0;
    await assert.rejects(connect({chain_id:8453,public_rpc:['must-not-use-unconfigured']}),/identity mismatch/);
    assert.deepEqual(tried,['custom']);
    h.endpoints=()=>[];await assert.rejects(connect({chain_id:8453}),/No RPC endpoint/);
  } finally {h.endpoints=originalEndpoints;h.client=originalClient;}
  console.log('Registry cache identity, incremental reads and RPC outage checks passed.');
})().catch(e=>{console.error(e);process.exitCode=1;}).finally(()=>{h.root=original;fs.rmSync(root,{recursive:true,force:true});});
