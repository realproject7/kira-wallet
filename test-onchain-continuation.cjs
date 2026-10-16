'use strict';
// Bounded work, durable holes and chain scheduling. No live provider calls.
const {test}=require('node:test'),assert=require('node:assert/strict');
const fs=require('node:fs'),os=require('node:os'),path=require('node:path');
const h=require('./onchain.cjs'),{registry,balanceReads,mintclubMembership,scanChain,scanNetworks}=require('./pipeline-onchain.cjs');
const HASH='0x'+'a'.repeat(64),WALLET='0x'+'1'.repeat(40);
const address=i=>'0x'+(i+100).toString(16).padStart(40,'0');

test('registry slices advance past failed indices and resume at the same count and block',async()=>{
 const root=fs.mkdtempSync(path.join(os.tmpdir(),'kira-registry-slices-')),oldRoot=h.root;
 try{
  h.root=root;let countReads=0,fail=true;const indices=[];
  const network={chain_id:999,mintclub_bond_address:address(999)},file=path.join(root,'registry.json');
  const client={readContract:async args=>{assert.equal(args.blockNumber,7n);countReads++;return 257n;},
   multicall:async({contracts,blockNumber})=>{
    assert.equal(blockNumber,7n);assert(contracts.length<=128);
    return contracts.map(c=>{
     if(c.functionName==='decimals')return {status:'success',result:18};
     const i=Number(c.args[0]);indices.push(i);
     return fail&&i===5?{status:'failure',error:new Error('synthetic failure')}:{status:'success',result:address(i)};
    });
   }};
  const options={file,blockHash:HASH,maxBatches:1};
  let row=await registry(client,network,7n,options);
  assert.equal(row.next_index,128);assert.equal(row.entries.filter(e=>e.address).length,127);
  assert.equal(JSON.parse(fs.readFileSync(file)).failures[0].index,5);
  row=await registry(client,network,7n,options);
  assert.equal(row.next_index,256);assert.equal(indices.at(-1),255);
  row=await registry(client,network,7n,options);
  assert.equal(row.next_index,257);assert.equal(row.pending,true);assert.equal(row.errors,1);
  fail=false;row=await registry(client,network,7n,options);
  assert.equal(row.pending,false);assert.equal(row.errors,0);assert.equal(row.entries.length,257);
  assert.equal(countReads,1);assert.equal(indices.length,258);assert.equal(indices.at(-1),5);
  assert.equal(new Set(row.entries.map(e=>e.index)).size,257);
  await assert.rejects(registry(client,network,8n,{...options,blockHash:'0x'+'b'.repeat(64)}),/does not match/);
 }finally{h.root=oldRoot;fs.rmSync(root,{recursive:true,force:true});}
});

test('balance slices leave unread identities pending and never duplicate successful reads',async()=>{
 const root=fs.mkdtempSync(path.join(os.tmpdir(),'kira-balance-slices-'));
 try{
  const file=path.join(root,'balances.json'),tokens=Array.from({length:257},(_,i)=>({address:address(i),token_type:'ERC20'}));
  const observed=[];let checkpoint={balances:{},block_hash:HASH};
  const client={multicall:async({contracts,blockNumber})=>{assert.equal(blockNumber,7n);assert(contracts.length<=128);
   return contracts.map(c=>{observed.push(c.address);return {status:'success',result:3n};});}};
  for(let turn=0;turn<3;turn++){
   const row=await balanceReads(client,tokens,WALLET,7n,checkpoint,file,{chain_id:999},{maxBatches:1});
   assert.equal(row.filter(r=>r.status==='success').length,Math.min((turn+1)*128,257));
   assert.equal(row.filter(r=>r.status==='pending').length,Math.max(0,257-(turn+1)*128));
   checkpoint=JSON.parse(fs.readFileSync(file));
  }
  assert.equal(observed.length,257);assert.equal(new Set(observed).size,257);
 }finally{fs.rmSync(root,{recursive:true,force:true});}
});

test('all chains receive a slice before a large chain resumes and unchanged work is bounded',async()=>{
 const root=fs.mkdtempSync(path.join(os.tmpdir(),'kira-fair-slices-'));
 try{
  const input={networks:[{chain_id:1},{chain_id:2},{chain_id:3}]},calls=[],turns={};
  const scan=async(input,n,output,baseline,options)=>{
   assert.equal(options.maxBatches,4);calls.push(n.chain_id);turns[n.chain_id]=(turns[n.chain_id]||0)+1;
   return {chain_id:n.chain_id,research_pending:n.chain_id!==2&&turns[n.chain_id]<n.chain_id+2,
    work_progress:{balances:turns[n.chain_id]},status:'partial'};
  };
  const rows=await scanNetworks(input,root,false,{scan});
  assert.deepEqual(calls.slice(0,5),[1,2,3,1,3]);assert.equal(rows.length,3);
  let stalledCalls=0;
  const stalled=await scanNetworks({networks:[{chain_id:4}]},root,false,{scan:async()=>{
   stalledCalls++;return {chain_id:4,research_pending:true,work_progress:{balances:0}};
  }});
  assert.equal(stalledCalls,4);assert.equal(stalled[0].continuation_stalled,true);assert.equal(stalled[0].status,'partial');
 }finally{fs.rmSync(root,{recursive:true,force:true});}
});

test('one-round candidate scan leaves unfinished chain work pending for publication and continuation',async()=>{
 const root=fs.mkdtempSync(path.join(os.tmpdir(),'kira-one-round-'));
 try{
  const calls=[];
  const rows=await scanNetworks({networks:[{chain_id:1},{chain_id:2}]},root,false,{maxRounds:1,scan:async(input,n)=>{
   calls.push(n.chain_id);return {chain_id:n.chain_id,research_pending:true,work_progress:{balances:128},status:'partial'};
  }});
  assert.deepEqual(calls,[1,2]);assert(rows.every(r=>r.research_pending));
  assert(rows.every(r=>!r.continuation_stalled));
 }finally{fs.rmSync(root,{recursive:true,force:true});}
});

test('persistent failed batches cannot starve unread balances before no-progress detection',async()=>{
 const root=fs.mkdtempSync(path.join(os.tmpdir(),'kira-balance-frontier-'));
 const originals={root:h.root,endpoints:h.endpoints,client:h.client,snapshotBlock:h.snapshotBlock};
 try{
  const candidates=Array.from({length:2049},(_,i)=>({chain_id:999,address:address(i)})),seen=new Set();
  h.root=root;h.endpoints=()=>['synthetic'];h.snapshotBlock=async()=>({number:7n,hash:HASH});
  h.client=()=>({getChainId:async()=>999,getBalance:async()=>0n,readContract:async()=>0n,
   multicall:async({contracts})=>contracts.map(c=>{
    if(c.functionName==='balanceOf'){
     seen.add(c.address);return c.address===address(2048)?{status:'success',result:9n}:{status:'failure',error:new Error('synthetic persistent revert')};
    }
    return {status:'success',result:c.functionName==='decimals'?18:'TEST'};
   })});
  const [row]=await scanNetworks({wallet:WALLET,candidates,networks:[{chain_id:999,mintclub_bond_address:address(9999)}]},root);
  assert.equal(seen.size,2049);assert.equal(row.tokens.find(t=>t.token_address===address(2048)).wallet_balance_raw,9n);
  assert.equal(row.continuation_stalled,true);assert.equal(row.work_progress.balance_attempted,2049);
  assert.equal(row.candidate_scan.complete,false);assert.equal(row.status,'partial');
 }finally{Object.assign(h,originals);fs.rmSync(root,{recursive:true,force:true});}
});

test('suspicious-zero retry holes rotate after restart without blocking later evidence',async()=>{
 const root=fs.mkdtempSync(path.join(os.tmpdir(),'kira-zero-frontier-'));
 const originals={peerClient:h.peerClient,snapshotBlock:h.snapshotBlock};
 try{
  const tokens=Array.from({length:9},(_,i)=>({address:address(i),token_type:'ERC20',suspicious_zero_check:true}));
  const file=path.join(root,'balances.json'),seen=[];
  const client={multicall:async({contracts})=>contracts.map(()=>({status:'success',result:0n})),
   readContract:async query=>{seen.push(query.address);if(query.address!==address(8))throw new Error('synthetic verification failure');return 9n;}};
  h.peerClient=()=>({readContract:async()=>9n});h.snapshotBlock=async()=>({number:7n,hash:HASH});
  await balanceReads(client,tokens,WALLET,7n,{balances:{},block_hash:HASH},file,{chain_id:999});
  assert.equal(seen.length,8);assert(!seen.includes(address(8)));
  const checkpoint=JSON.parse(fs.readFileSync(file));
  const rows=await balanceReads(client,tokens,WALLET,7n,checkpoint,file,{chain_id:999});
  assert.equal(rows[8].status,'success');assert.equal(rows[8].result,9n);assert.equal(seen[8],address(8));
  assert.equal(Object.keys(checkpoint.zero_attempts).length,9);assert.equal(rows.filter(r=>r.status==='failure').length,8);
 }finally{Object.assign(h,originals);fs.rmSync(root,{recursive:true,force:true});}
});

test('retained native balances preserve their original observation time after RPC failure',async()=>{
 const root=fs.mkdtempSync(path.join(os.tmpdir(),'kira-native-retention-'));
 const originals={endpoints:h.endpoints,client:h.client};
 try{
  const observed='2020-01-01T00:00:00.000Z';
  fs.writeFileSync(path.join(root,'chain-999.json'),JSON.stringify({wallet:WALLET,chain_id:999,status:'partial',tokens:[],native_balance:'1',block_number:'7',block_hash:HASH,observed_at:observed}));
  h.endpoints=()=>['synthetic'];h.client=()=>({getChainId:async()=>{throw new Error('synthetic RPC outage');}});
  const row=await scanChain({wallet:WALLET,candidates:[{chain_id:999,address:address(1)}]},{chain_id:999,mintclub_bond_address:address(999)},root);
  assert.equal(row.native_balance,'1');assert.equal(row.observed_at,observed);assert.equal(row.block_number,'7');
  assert.equal(row.native_balance_evidence_retained,true);assert.equal(row.status,'partial');
 }finally{Object.assign(h,originals);fs.rmSync(root,{recursive:true,force:true});}
});

test('wallet candidate mode verifies ID0 membership before balances and never enumerates the registry',async()=>{
 const root=fs.mkdtempSync(path.join(os.tmpdir(),'kira-wallet-candidates-'));
 const originals={root:h.root,endpoints:h.endpoints,client:h.client,snapshotBlock:h.snapshotBlock};
 try{
  const reads=[],network={chain_id:999,mintclub_bond_address:address(9999)},nft=address(10),foreign=address(11),unknown=address(12);
  h.root=root;h.endpoints=()=>['synthetic'];h.snapshotBlock=async()=>({number:7n,hash:HASH});
  h.client=()=>({getChainId:async()=>999,getBalance:async()=>0n,
   readContract:async()=>{throw new Error('No registry calls permitted in wallet candidate mode.');},
   multicall:async({contracts,blockNumber})=>{assert.equal(blockNumber,7n);return contracts.map(c=>{
    reads.push(c);
    if(c.functionName==='exists')return c.args[0]===unknown?{status:'failure',error:new Error('synthetic outage')}:{status:'success',result:c.args[0]===nft};
    if(c.functionName==='decimals')return {status:'success',result:c.address===nft?0:18};
    if(c.functionName==='balanceOf'){assert(![foreign,unknown].includes(c.address));if(c.address===nft)assert.deepEqual(c.args,[WALLET,0n]);return {status:'success',result:9n};}
    if(['name','symbol'].includes(c.functionName))return {status:'success',result:'TEST'};
    return {status:'failure',error:new Error('synthetic curve unavailable')};
   });}});
  const input={wallet:WALLET,inventory_policy:'wallet_candidates_v1',candidates:[{chain_id:999,address:address(1)}],
   mintclub_id0_candidates:[nft,foreign,unknown].map(address=>({chain_id:999,address,token_type:'ERC1155',token_id:'0'}))};
  const row=await scanChain(input,network,root);
  assert.equal(row.registry_scan.phase,'not_requested');assert.equal(row.registry_scan.registry_count,null);assert.equal(row.registry_scan.complete,false);
  assert.equal(row.mintclub_membership_scan.id0_registered,1);assert.equal(row.mintclub_membership_scan.id0_outside_scope,1);assert.equal(row.mintclub_membership_scan.id0_unknown,1);
  assert.equal(row.tokens.find(t=>t.token_address===nft).wallet_balance_raw,9n);assert.equal(row.tokens.find(t=>t.token_address===nft).token_type,'ERC1155');
  assert.equal(row.tokens.find(t=>t.token_address===nft).mintclub_membership_status,'verified');assert(row.tokens.find(t=>t.token_address===nft).mintclub_error);
  assert.equal(row.research_pending,true);assert.equal(row.status,'partial');
  const before=reads.filter(c=>c.functionName==='balanceOf').length;
  await scanChain(input,network,root);
  assert.equal(reads.filter(c=>c.functionName==='balanceOf').length,before);
  const checkpoint=JSON.parse(fs.readFileSync(path.join(root,'balance-checkpoint-999.json')));
  assert.equal(checkpoint.block_hash,HASH);assert.equal(checkpoint.balances[nft+':ERC1155'],'9');
  const bytes=fs.readFileSync(path.join(root,'chain-999.json'));
  await assert.rejects(scanChain({...input,inventory_policy:'full_registry'},network,root),/inventory scope mismatch/);
  assert.deepEqual(fs.readFileSync(path.join(root,'chain-999.json')),bytes);
 }finally{Object.assign(h,originals);fs.rmSync(root,{recursive:true,force:true});}
});

test('bounded membership retries cannot starve unread candidates and successful facts survive restart',async()=>{
 const root=fs.mkdtempSync(path.join(os.tmpdir(),'kira-membership-frontier-'));
 try{
  const tokens=Array.from({length:129},(_,i)=>({address:address(i),token_type:'ERC1155'})),file=path.join(root,'checkpoint.json');
  let checkpoint={balances:{},block_hash:HASH},seen=[];
  const client={multicall:async({contracts,blockNumber})=>{assert.equal(blockNumber,7n);assert(contracts.length<=128);return contracts.map(c=>{
   if(c.functionName==='decimals')return {status:'success',result:0};
   seen.push(c.args[0]);return c.args[0]===address(0)?{status:'failure',error:new Error('synthetic failure')}:{status:'success',result:true};
  });}};
  let rows=await mintclubMembership(client,{chain_id:999,mintclub_bond_address:address(999)},tokens,7n,checkpoint,file,{maxBatches:1});
  assert.equal(rows.filter(r=>r.status==='success').length,127);
  checkpoint=JSON.parse(fs.readFileSync(file));
  rows=await mintclubMembership(client,{chain_id:999,mintclub_bond_address:address(999)},tokens,7n,checkpoint,file,{maxBatches:1});
  assert.equal(seen[128],address(128));assert.equal(rows[128].registered,true);assert.equal(rows[0].status,'failure');
  assert.equal(rows.filter(r=>r.status==='success').length,128);assert.equal(new Set(seen).size,129);
 }finally{fs.rmSync(root,{recursive:true,force:true});}
});
