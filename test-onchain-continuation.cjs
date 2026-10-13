'use strict';
// Bounded work, durable holes and chain scheduling. No live provider calls.
const {test}=require('node:test'),assert=require('node:assert/strict');
const fs=require('node:fs'),os=require('node:os'),path=require('node:path');
const h=require('./onchain.cjs'),{registry,balanceReads,scanNetworks}=require('./pipeline-onchain.cjs');
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
