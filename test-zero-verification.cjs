'use strict';
const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),os=require('node:os'),path=require('node:path');
const h=require('./onchain.cjs'),{balanceReads}=require('./pipeline-onchain.cjs');
const HASH='0x'+'a'.repeat(64),WALLET='0x'+'1'.repeat(40),TOKEN='0x'+'2'.repeat(40);
test('a fresh stale head and a resumed saved observation stay distinct',async()=>{
 const {scanChain}=require('./pipeline-onchain.cjs'),root=fs.mkdtempSync(path.join(os.tmpdir(),'kira-head-'));
 const originalClient=h.client,originalBlock=h.snapshotBlock;
 try{
  h.client=()=>({getChainId:async()=>1,getBalance:async()=>0n});
  h.snapshotBlock=async()=>({number:7n,hash:HASH,timestamp:BigInt(Math.floor(Date.now()/1000)-172800)});
  const input={wallet:WALLET,candidates:[]},network={chain_id:1,network:'ethereum'};
  const fresh=await scanChain(input,network,root,true);assert.equal(fresh.head_status,'stale');assert(fresh.head_age_seconds>=172800);
  fs.rmSync(path.join(root,'baseline-chain-1.json'));
  const resumed=await scanChain(input,network,root,true);assert.equal(resumed.head_status,'saved_observation');assert.equal(resumed.head_age_seconds,null);
 }finally{h.client=originalClient;h.snapshotBlock=originalBlock;fs.rmSync(root,{recursive:true,force:true});}
});
test('the real client factory excludes the successful endpoint when creating a peer',async()=>{
 const seen=[],transport=url=>()=>({request:async request=>{seen.push(url);return request.method==='eth_chainId'?'0x1':'0x7';}});
 const client=h.client(1,undefined,null,transport);
 await client.getBlockNumber({cacheTime:0});const primary=seen.at(-1),peer=h.peerClient(client);
 assert(peer,'A configured qualified peer is available.');await peer.getBlockNumber({cacheTime:0});
 assert.notEqual(seen.at(-1),primary);assert(h.rpcRoutes(peer).some(r=>r.outcome==='succeeded'));
});
test('suspicious zeros preserve qualified agreeing, conflicting and unavailable observations',async()=>{
 const root=fs.mkdtempSync(path.join(os.tmpdir(),'kira-zero-')),originalPeer=h.peerClient,originalBlock=h.snapshotBlock;
 try{
  for(const [direct,other,expected] of [[0n,0n,0n],[9n,9n,9n],[0n,9n,null],[9n,0n,null],[0n,null,null]]){
   const checkpoint={balances:{[TOKEN+':ERC20']:'0'},block_hash:HASH};let reads=0;
   const client={multicall:async()=>[{status:'success',result:0n}],readContract:async query=>{assert.equal(query.blockNumber,7n);reads++;return direct;}};
   h.peerClient=()=>other==null?null:{readContract:async query=>{assert.equal(query.blockNumber,7n);reads++;return other;}};
   h.snapshotBlock=async(client,saved)=>{assert.equal(saved.block_hash,HASH);assert.equal(saved.block_number,'7');return {number:7n,hash:HASH};};
   const [row]=await balanceReads(client,[{address:TOKEN,token_type:'ERC20',suspicious_zero_check:true}],WALLET,7n,checkpoint,path.join(root,'check.json'),{chain_id:1});
   assert.equal(row.status,expected==null?'failure':'success');if(expected!=null)assert.equal(row.result,expected);
   assert(reads<=2);if(expected==null)assert.equal(checkpoint.balances[TOKEN+':ERC20'],undefined);
  }
 }finally{h.peerClient=originalPeer;h.snapshotBlock=originalBlock;fs.rmSync(root,{recursive:true,force:true});}
});
test('zero-heavy registries do not fan out and targeted checks share a fixed cap',async()=>{
 const root=fs.mkdtempSync(path.join(os.tmpdir(),'kira-zero-cap-')),originalPeer=h.peerClient,originalBlock=h.snapshotBlock;
 try{
  let extra=0;const client={multicall:async({contracts})=>contracts.map(()=>({status:'success',result:0n})),readContract:async()=>{extra++;return 0n;}};
  h.peerClient=()=>({readContract:async()=>{extra++;return 0n;}});h.snapshotBlock=async()=>({number:7n,hash:HASH});
  const tokens=Array.from({length:300},(_,i)=>({address:'0x'+(i+100).toString(16).padStart(40,'0'),token_type:'ERC20'}));
  let rows=await balanceReads(client,tokens,WALLET,7n,{balances:{},block_hash:HASH},path.join(root,'unhinted.json'),{chain_id:1});
  assert.equal(extra,0);assert(rows.every(r=>r.result===0n));
  rows=await balanceReads(client,tokens.map(t=>({...t,suspicious_zero_check:true})),WALLET,7n,{balances:{},block_hash:HASH},path.join(root,'hinted.json'),{chain_id:1});
  assert.equal(extra,16);assert.equal(rows.filter(r=>r.status==='success').length,8);assert.equal(rows.filter(r=>r.status==='failure').length,292);
 }finally{h.peerClient=originalPeer;h.snapshotBlock=originalBlock;fs.rmSync(root,{recursive:true,force:true});}
});
test('verification bypasses a cached balance after another request changes endpoint provenance',async()=>{
 const vm=require('node:vm'),{RpcPool,RouteRecorder}=require('./rpc-pool.cjs');
 const urls=['https://primary.example','https://secondary.example'],pool=new RpcPool({interval:0,deadline:1000,attemptTimeout:200,publicUrls:urls});
 const source=fs.readFileSync(path.join(__dirname,'onchain.cjs'),'utf8'),context={viem:h.viem,pool,RouteRecorder,runtime:{endpoints:{1:urls}},module:{exports:{}}};
 vm.runInNewContext(source.slice(source.indexOf('function endpoints('),source.indexOf('const serialize='))+';module.exports={client,verificationClient,peerClient,snapshotBlock};',context);
 const factory=context.module.exports,balances=[];
 const transport=url=>()=>({request:async r=>{
  if(r.method==='eth_chainId')return '0x1';
  if(r.method==='eth_getBlockByNumber')return {number:'0x7',hash:HASH,timestamp:'0x1'};
  if(r.method==='eth_getBlockNumber'&&url===urls[0])throw Object.assign(new Error('Unsupported method'),{code:-32601});
  if(r.method==='eth_call'){balances.push(url);return '0x'+'0'.repeat(64);}return '0x7';
 }});
 const client=factory.client(1,undefined,null,transport);await factory.snapshotBlock(client);
 const query={address:TOKEN,abi:h.viem.parseAbi(['function balanceOf(address) view returns(uint256)']),functionName:'balanceOf',args:[WALLET],blockNumber:7n};
 await client.readContract(query);await client.getBlockNumber({cacheTime:0});
 const verifier=factory.verificationClient(client);await verifier.readContract(query);
 const peer=factory.peerClient(verifier);await factory.snapshotBlock(peer,{block_number:'7',block_hash:HASH});await peer.readContract(query);
 assert.deepEqual(balances,[urls[0],urls[0],urls[1]]);
});
