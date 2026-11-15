'use strict';
// Batch refresh: one network read for several wallets gives each wallet the same chain
// file a single refresh writes, while every balance and registry entry is read once.
const {test}=require('node:test'),assert=require('node:assert/strict');
const fs=require('node:fs'),os=require('node:os'),path=require('node:path');
const h=require('./onchain.cjs'),p=require('./pipeline-onchain.cjs');
const HASH='0x'+'a'.repeat(64);
const address=i=>'0x'+(i+100).toString(16).padStart(40,'0');
const wallet=i=>'0x'+(i+1).toString(16).padStart(40,'0');
const BOND=address(9000);
const NETWORK={chain_id:999,network:'synthetic',environment:'mainnet',mintclub_bond_address:BOND};
const DOWN={chain_id:998,network:'offline',environment:'mainnet',mintclub_bond_address:BOND};
// Wallet w holds catalogue token t when (w+t) is even; candidate 50 is held by everyone.
const holds=(w,token)=>token===address(50)||(parseInt(w.slice(2),16)+parseInt(token.slice(2),16))%2===0;

function fakeClient(seen){
  return {
    getChainId:async()=>999,
    getBalance:async()=>{seen.getBalance++;return 5n*10n**18n;},
    readContract:async({functionName})=>{if(functionName==='tokenCount')return 3n;throw new Error('unexpected single read');},
    request:async()=>{throw new Error('no history in this test');},
    multicall:async({contracts})=>contracts.map(c=>{
      const key=[c.address.toLowerCase(),c.functionName,...(c.args||[]).map(String)].join('|');
      seen.reads.set(key,(seen.reads.get(key)||0)+1);
      if(c.functionName==='getEthBalance')return {status:'success',result:5n*10n**18n};
      if(c.functionName==='tokens')return {status:'success',result:address(Number(c.args[0]))};
      if(c.functionName==='decimals')return {status:'success',result:18};
      // A token whose name() reverts: at one block it reverts again, so the batch asks once.
      if(c.functionName==='name'&&c.address.toLowerCase()===address(50))return {status:'failure',error:new Error('execution reverted')};
      if(['symbol','name'].includes(c.functionName))return {status:'success',result:'T'+c.address.slice(-2)};
      if(c.functionName==='balanceOf')return {status:'success',result:holds(String(c.args[0]).toLowerCase(),c.address.toLowerCase())?7n:0n};
      if(c.functionName==='getDetail')return {status:'success',result:{burnRoyalty:100,info:{reserveToken:address(8000),reserveSymbol:'RES',reserveDecimals:18,
        reserveBalance:1000n,priceForNextMint:5n,currentSupply:100n}}};
      if(c.functionName==='getRefundForTokens')return {status:'success',result:[3n,1n]};
      return {status:'failure',error:new Error('synthetic detail unavailable')};
    }),
  };
}

test('a batch reads each network once for all wallets and writes the same chain files',async()=>{
  const root=fs.mkdtempSync(path.join(os.tmpdir(),'kira-batch-scan-'));
  const originals={root:h.root,endpoints:h.endpoints,client:h.client,snapshotBlock:h.snapshotBlock};
  const lines=[],log=console.log;
  try{
    h.root=root;h.endpoints=()=>['synthetic'];h.snapshotBlock=async()=>({number:100n,hash:HASH,timestamp:BigInt(Math.floor(Date.now()/1000))});
    const seen={reads:new Map(),getBalance:0};
    const client=fakeClient(seen);
    h.client=chain=>chain===998?{getChainId:async()=>{throw new Error('offline network');}}:client;
    const wallets=[0,1,2].map(i=>{
      const folder=path.join(root,'batch',String(i));fs.mkdirSync(folder,{recursive:true});
      const input={wallet:wallet(i),networks:[NETWORK,DOWN],inventory_policy:'full_registry',candidates:[{chain_id:999,address:address(50)}],mintclub_id0_candidates:[]};
      fs.writeFileSync(path.join(folder,'scan-input.json'),JSON.stringify(input));
      return {job_id:'job-'+i,folder,input_path:path.join(folder,'scan-input.json'),input};
    });
    console.log=line=>lines.push(line);
    await p.batchScan({wallets});
    console.log=log;
    // Every balance, registry entry and token detail was read once for the whole batch.
    for(const [key,count] of seen.reads)assert.equal(count,1,`${key} was read ${count} times`);
    assert(seen.reads.has(address(50)+'|name'),'The reverting call was asked.');
    assert.equal([...seen.reads.keys()].filter(k=>k.includes('|getEthBalance|')).length,3,'Native balances of all wallets in one read.');
    assert.equal(seen.getBalance,0);
    assert.equal([...seen.reads.keys()].filter(k=>k.includes('|tokens|')).length,3,'The registry is enumerated once.');
    const events=lines.map(line=>JSON.parse(line)).filter(e=>e.stage==='chain');
    assert.equal(events.length,6);assert(events.every(e=>/^job-[0-2]$/.test(e.job_id)));
    assert(!lines.some(line=>line.includes('onchain_progress')),'A batch reports chains, not read-by-read progress.');
    // Each wallet gets the chain file a single refresh writes, without checkpoints.
    seen.reads.clear();
    for(const w of wallets){
      const summary=JSON.parse(fs.readFileSync(path.join(w.folder,'onchain-summary.json')));
      assert.deepEqual(summary.chains.map(c=>c.chain_id),[999,998]);
      assert.equal(summary.chains[1].status,'unavailable');assert.match(summary.chains[1].error.message,/offline network/);
      const single=path.join(root,'single',w.job_id);fs.mkdirSync(single,{recursive:true});
      console.log=()=>{};
      const alone=await p.scanChain(w.input,NETWORK,single);
      console.log=log;
      const batch=summary.chains[0],pick=row=>row.tokens.map(t=>[t.token_address.toLowerCase(),t.token_type,String(t.wallet_balance_raw),t.symbol,t.decimals]).sort();
      assert.deepEqual(pick(batch),pick(alone));
      assert.equal(batch.native_balance,alone.native_balance);
      for(const field of ['status','block_number','block_hash'])assert.equal(String(batch[field]),String(alone[field]));
      assert.deepEqual(batch.registry_scan.checked,alone.registry_scan.checked);
      const curves=row=>row.tokens.filter(t=>t.mintclub).map(t=>[t.token_address.toLowerCase(),t.mintclub.wallet_full_burn.net_refund_raw.toString(),t.mintclub.reserve_balance]).sort();
      assert.deepEqual(curves(batch),curves(alone));assert(curves(batch).length>0,'Held Mint Club tokens carry curve details.');
      assert.equal(fs.readdirSync(w.folder).filter(name=>name.includes('checkpoint')).length,0);
    }
    assert(seen.getBalance>0,'The single refresh still reads its own native balance.');
  }finally{console.log=log;Object.assign(h,originals);p.setQuiet(false);fs.rmSync(root,{recursive:true,force:true});}
});

test('suspicious zeros are read again on both nodes in one call each',async()=>{
  const root=fs.mkdtempSync(path.join(os.tmpdir(),'kira-batch-zeros-'));
  const originals={root:h.root,endpoints:h.endpoints,client:h.client,snapshotBlock:h.snapshotBlock,verificationClient:h.verificationClient,peerClient:h.peerClient};
  const log=console.log;
  try{
    h.root=root;h.endpoints=()=>['synthetic'];h.snapshotBlock=async()=>({number:100n,hash:HASH,timestamp:BigInt(Math.floor(Date.now()/1000))});
    p.setTransportPause(0);
    const zeros=Array.from({length:20},(_,i)=>address(300+i)),seen={reads:new Map(),getBalance:0},base=fakeClient(seen);
    // The index listed these tokens, yet each reads zero on chain: every one is double-checked
    // directly and on a second node, at most eight per balance pass.
    const client={...base,readContract:async q=>q.functionName==='balanceOf'?0n:base.readContract(q),
      multicall:async({contracts})=>{const rows=await base.multicall({contracts});
      return rows.map((row,i)=>contracts[i].functionName==='balanceOf'&&zeros.includes(contracts[i].address.toLowerCase())?{status:'success',result:0n}:row);}};
    let single=0;
    // Like onchain.cjs: a verification client is new, and it has a peer only once it has
    // answered from one endpoint (the peer is another endpoint).
    const peer={readContract:async()=>{single++;return 0n;},multicall:async({contracts})=>contracts.map(()=>({status:'success',result:0n}))};
    h.client=()=>client;
    h.verificationClient=()=>{const v={answered:false,readContract:async q=>{v.answered=true;return client.readContract(q);},
      multicall:async args=>{v.answered=true;return client.multicall(args);}};return v;};
    h.peerClient=v=>v.answered?peer:null;
    const folder=path.join(root,'w');fs.mkdirSync(folder,{recursive:true});
    const input={wallet:wallet(0),networks:[NETWORK],inventory_policy:'full_registry',mintclub_id0_candidates:[],
      candidates:[{chain_id:999,address:address(50)},...zeros.map(address=>({chain_id:999,address,suspicious_zero_check:true}))]};
    fs.writeFileSync(path.join(folder,'scan-input.json'),JSON.stringify(input));
    console.log=()=>{};
    await p.batchScan({wallets:[{job_id:'job-z',folder,input_path:path.join(folder,'scan-input.json')}]});
    console.log=log;
    const row=JSON.parse(fs.readFileSync(path.join(folder,'onchain-summary.json'))).chains[0];
    assert.equal(Object.keys(row.zero_verification).length,20,'Every suspicious zero was checked across rounds.');
    assert(Object.values(row.zero_verification).every(z=>z.outcome==='agreed'));assert.equal(row.research_pending,false);
    assert.equal(single,0,'The batch read every suspicious zero again in one call per node.');
    assert(row.tokens.length>0&&row.tokens.every(t=>!t.metadata_pending&&t.wallet_balance!==null),'Held tokens get their details once verification is done.');
  }finally{console.log=log;Object.assign(h,originals);p.setQuiet(false);p.setTransportPause(5500);fs.rmSync(root,{recursive:true,force:true});}
});
