'use strict';
const assert = require('node:assert/strict');
const viem = require('viem'), fs=require('node:fs'), vm=require('node:vm');
(async () => {
  const seen = [];
  const transport = url => options => viem.custom({request: async ({method, params}) => {
    seen.push([url, method, params]);
    if (method === 'eth_chainId') return url === 'wrong' ? '0x1' : '0x2105';
    if (url === 'custom') throw new Error('Endpoint failed after its chain handshake');
    return '0x7';
  }}, {retryCount: 0})(options);
  const loaded={exports:{}};
  const requireFixture=name=> name==='viem' ? {...viem,http:transport} : name==='node:child_process' ? {spawnSync:()=>({status:0,stdout:JSON.stringify({endpoints:{8453:['custom','wrong','public']},secrets:[],data_root:'synthetic'})})} : require(name);
  vm.runInNewContext(fs.readFileSync('onchain.cjs','utf8'),{require:requireFixture,__dirname,module:loaded,process:{env:{}}});
  const client=loaded.exports.client(8453);
  const resilientTransport=loaded.exports.resilientTransport;
  assert.equal(await client.getChainId(), 8453);
  assert.equal(await client.getBlockNumber(), 7n);
  const result=await client.request({method:'eth_call',params:[{to:'0x'+'1'.repeat(40),data:'0x'},'0x7']});
  assert.equal(result,'0x7');
  assert.deepEqual(seen.filter(([,method])=>method==='eth_call').map(([, ,params])=>params[1]), ['0x7','0x7']);assert.deepEqual([...loaded.exports.rpcEndpointsUsed(client)],[0,2]);
  assert(seen.some(([url, method]) => url === 'custom' && method === 'eth_blockNumber'));
  assert(!seen.some(([url, method]) => url === 'wrong' && method === 'eth_blockNumber'));
  assert(seen.some(([url, method]) => url === 'public' && method === 'eth_blockNumber'));
  await assert.rejects(viem.createPublicClient({transport: resilientTransport(8453, ['wrong'], transport)}).getBlockNumber(), /identity mismatch/);
  console.log('RPC falls back after a live read failure and rejects the wrong chain.');
})().catch(error => { console.error(error); process.exitCode = 1; });
