'use strict';
const {test}=require('node:test'),assert=require('node:assert/strict');
const fs=require('node:fs'),os=require('node:os'),path=require('node:path');
const h=require('./onchain.cjs'),v=h.viem;
const {dexChain,liquidationChain,scanChain}=require('./pipeline-onchain.cjs');
const {expandRoutes,representativeQuote}=require('./cashout-routes.cjs');
const address=n=>'0x'+n.toString(16).padStart(40,'0'),HASH='0x'+'a'.repeat(64),WALLET=address(1);
const WETH='0x4200000000000000000000000000000000000006';
const token=(n,chain=8453)=>({chain_id:chain,token_address:address(n),token_type:'ERC20',wallet_balance_raw:'1000000000000000000',balance_block_number:'7',balance_block_hash:HASH,dex_pools:[]});
const leg=(input,output)=>({status:'quoted',kind:'mintclub_burn',input_address:input,input_amount_raw:'1000000000000000000',holding_amount_raw:'1000000000000000000',output_address:output,output_amount_raw:'1000000000000000000',output_amount:'1',output_decimals:18,block_number:'7',block_hash:HASH,observed_at:'2026-10-15T00:00:00Z',route_fees_included:true,price_impact_included:true,gas_included:false,funded:true,reserve_balance_raw:'2000000000000000000'});

test('one representative terminal route ends saved alternative work without extra reads',async()=>{
 const t=token(10);t.dex_pools=[{cashout_quote:leg(t.token_address,WETH)},{cashout_quote:leg(t.token_address,address(11))}];
 const s=await expandRoutes(t,async()=>{throw Error('Alternative route must not be read');},{representative:true});
 assert.equal(s.routes.length,1);assert.equal(s.pending.length,0);assert(representativeQuote(t,s.routes));
 const replay=await expandRoutes(t,async()=>{throw Error('Completed work must not be read');},{state:JSON.parse(JSON.stringify(s)),representative:true});
 assert.equal(replay.routes.length,1);assert.match(replay.unknown.join(' '),/Alternative/);
 const bad=structuredClone(s.routes);bad[0].legs[0].block_hash='0x'+'b'.repeat(64);
 assert.equal(representativeQuote({...t,dex_pools:[]},bad),null);
});

test('representative pool selection skips the full factory grid and batches shared reads',async()=>{
 const root=fs.mkdtempSync(path.join(os.tmpdir(),'kira-assets-')),original={endpoints:h.endpoints,client:h.client,snapshotBlock:h.snapshotBlock};
 try{
  const network={chain_id:1,environment:'mainnet'},factory=require('./sources/uniswap-deployments.json').records.find(d=>d.chainId===1&&d.protocol==='v2'&&d.contract==='UniswapV2Factory').address;
  const held=[token(10,1),token(11,1)],pools=new Map(held.map((t,i)=>[address(100+i),t.token_address]));let batches=0;const seen=[];
  const query=q=>{
   seen.push(q.address);if(q.functionName==='factory')return factory;
   if(q.functionName==='token0')return pools.get(q.address);
   if(q.functionName==='token1')return WETH;
   if(q.functionName==='getReserves')return [10n**24n,10n**24n,0];
   if(q.functionName==='getPair')return [...pools].find(([,a])=>a===q.args[0])[0];
   if(q.functionName==='balanceOf')return 10n**24n;
   if(q.functionName==='decimals')return 18;
   if(q.functionName==='symbol')return 'WETH';
   throw Error('Unexpected read '+q.functionName);
  };
  held.forEach((t,i)=>t.dex_pools=[{pool:address(100+i),venue:'uniswap',version_labels:['v2'],reported_liquidity:{usd:100},paired_tokens:[{address:t.token_address},{address:WETH}]},{pool:address(200+i),venue:'uniswap',version_labels:['v2'],reported_liquidity:{usd:1},paired_tokens:[{address:t.token_address},{address:WETH}]}]);
  h.endpoints=()=>['synthetic'];h.snapshotBlock=async()=>({number:7n,hash:HASH});h.client=()=>({getChainId:async()=>1,readContract:async q=>query(q),multicall:async({contracts})=>{batches++;return contracts.map(q=>({status:'success',result:query(q)}));}});
  const file=path.join(root,'market.json'),options={wallet:WALLET,file,representative:true};
  const rows=await dexChain(network,structuredClone(held),options);
  assert(rows.every(t=>t.dex_pools.filter(p=>p.cashout_quote?.status==='quoted').length===1));assert(!seen.includes(address(200)));assert(!seen.includes(address(201)));assert(batches<=3);
  const before=batches;const resumed=await dexChain(network,structuredClone(held),options);assert.equal(batches,before);assert(resumed.every(t=>!t.market_pending));
  await assert.rejects(dexChain(network,[{...held[0],wallet_balance_raw:'9'},held[1]],options),/does not match/);
 }finally{Object.assign(h,original);fs.rmSync(root,{recursive:true,force:true});}
});

test('failed representative pools finish unknown after bounded attempts',async()=>{
 const root=fs.mkdtempSync(path.join(os.tmpdir(),'kira-asset-errors-')),original={endpoints:h.endpoints,client:h.client,snapshotBlock:h.snapshotBlock};
 try{
  const t=token(10,1);t.dex_pools=[{pool:address(100),venue:'uniswap',paired_tokens:[]}];
  h.endpoints=()=>['synthetic'];h.snapshotBlock=async()=>({number:7n,hash:HASH});h.client=()=>({getChainId:async()=>1,multicall:async()=>{throw Error('Synthetic outage');}});
  const options={wallet:WALLET,file:path.join(root,'market.json'),representative:true};
  const [first]=await dexChain({chain_id:1},[structuredClone(t)],options);assert.equal(first.market_pending,true);
  const [last]=await dexChain({chain_id:1},[structuredClone(t)],options);assert.equal(last.market_pending,undefined);assert(!last.dex_pools[0].cashout_quote);
  const saved=JSON.parse(fs.readFileSync(options.file));assert.equal(saved.asset_reviews[t.token_address+':ERC20'].failures,2);
 }finally{Object.assign(h,original);fs.rmSync(root,{recursive:true,force:true});}
});

test('unfinished indexer discovery cannot be finalized as an unknown pool absence',async()=>{
 const root=fs.mkdtempSync(path.join(os.tmpdir(),'kira-asset-pending-')),original={endpoints:h.endpoints,client:h.client,snapshotBlock:h.snapshotBlock};
 try{
  h.endpoints=()=>['synthetic'];h.snapshotBlock=async()=>({number:7n,hash:HASH});h.client=()=>({getChainId:async()=>1});
  const t={...token(10,1),dex_discovery_status:'pending'},options={wallet:WALLET,file:path.join(root,'market.json'),representative:true};
  const [pending]=await dexChain({chain_id:1},[t],options);assert.equal(pending.market_pending,true);
  const [settled]=await dexChain({chain_id:1},[{...t,dex_discovery_status:'unavailable'}],options);assert.equal(settled.market_pending,undefined);
  assert.equal(JSON.parse(fs.readFileSync(options.file)).asset_reviews[t.token_address+':ERC20'].done,true);
 }finally{Object.assign(h,original);fs.rmSync(root,{recursive:true,force:true});}
});

test('failed warm batches settle unknown even when every slice ends before the pool loop',async()=>{
 const root=fs.mkdtempSync(path.join(os.tmpdir(),'kira-warm-failures-')),original={endpoints:h.endpoints,client:h.client,snapshotBlock:h.snapshotBlock},realNow=Date.now;
 try{
  const base=realNow();let clock=base;Date.now=()=>clock;
  const tokens=Array.from({length:140},(_,i)=>({...token(1000+i,1),dex_pools:[{pool:address(2000+i),venue:'uniswap',version_labels:['v2'],paired_tokens:[]}]}));
  const observed=new Map();h.endpoints=()=>['synthetic'];h.snapshotBlock=async()=>({number:7n,hash:HASH});
  h.client=()=>({getChainId:async()=>1,multicall:async({contracts})=>{
   await Promise.resolve();clock+=20000;
   return contracts.map(q=>{const key=q.address+':'+q.functionName;observed.set(key,(observed.get(key)||0)+1);
    return q.functionName==='token0'?{status:'success',result:address(10)}:{status:'failure',error:Error('Synthetic provider failure')};});
  }});
  const file=path.join(root,'market.json');let rows;
  for(let turn=0;turn<10;turn++){
   clock=base;rows=await dexChain({chain_id:1},structuredClone(tokens),{file,wallet:WALLET,representative:true,deadline:base+30000});
   if(rows.every(t=>!t.market_pending))break;
  }
  assert(rows.every(t=>!t.market_pending&&!t.dex_pools[0].cashout_quote));
  const saved=JSON.parse(fs.readFileSync(file));assert.equal(Object.values(saved.asset_reviews).filter(r=>r.done&&r.failures===2).length,140);
  assert([...observed].filter(([k])=>k.endsWith(':token0')).every(([,n])=>n===1));
  assert([...observed].filter(([k])=>k.endsWith(':factory')).every(([,n])=>n===2));
  h.client=()=>({getChainId:async()=>1,multicall:async({contracts})=>{
   await Promise.resolve();clock+=20000;const error=Error('Synthetic queue wait');error.name='RpcSchedulingTimeout';
   return contracts.map(()=>({status:'failure',error}));
  }});
  for(let turn=0;turn<3;turn++){
   clock=base;const waiting=await dexChain({chain_id:1},structuredClone(tokens.slice(0,2)),{file:path.join(root,'waiting.json'),wallet:WALLET,representative:true,deadline:base+30000});
   assert(waiting.every(t=>t.market_pending));
  }
  assert(Object.values(JSON.parse(fs.readFileSync(path.join(root,'waiting.json'))).asset_reviews).every(r=>!r.done&&r.failures===0));
 }finally{Date.now=realNow;Object.assign(h,original);fs.rmSync(root,{recursive:true,force:true});}
});

test('a recovered ID0 burn finishes once and keeps original evidence on resume',async()=>{
 const root=fs.mkdtempSync(path.join(os.tmpdir(),'kira-asset-burn-')),original={endpoints:h.endpoints,client:h.client,snapshotBlock:h.snapshotBlock};
 try{
  const t={...token(10),token_type:'ERC1155',token_id:'0',mintclub_membership_status:'verified'},network={chain_id:8453,environment:'mainnet',network:'base',mintclub_bond_address:address(99)};let reads=0;
  const query=q=>{reads++;if(q.functionName==='tokenBond')return [0n,0n,0n,0n,WETH,10n**22n];if(q.functionName==='decimals')return 18;if(q.functionName==='getRefundForTokens')return [10n**18n,0n];throw Error('Unexpected read');};
  h.endpoints=()=>['synthetic'];h.snapshotBlock=async()=>({number:7n,hash:HASH});h.client=()=>({getChainId:async()=>8453,readContract:async q=>query(q),multicall:async({contracts})=>contracts.map(q=>({status:'success',result:query(q)}))});
  const input={wallet:WALLET,tokens:[t],market_scope:'representative_v1'},out=path.join(root,'result.json');
  const first=await liquidationChain(network,structuredClone(input),out);assert.equal(first.market_pending,false);assert.equal(first.tokens[0].asset_review.status,'quoted');assert.equal(first.tokens[0].liquidation_routes.length,1);
  const count=reads;const second=await liquidationChain(network,structuredClone(input),out);assert.equal(reads,count);assert.deepEqual(second.tokens[0].liquidation_routes,first.tokens[0].liquidation_routes);
  const boundary=await liquidationChain(network,{...structuredClone(input),tokens:[structuredClone(t),token(11)]},out,Date.now()-1);
  assert.equal(boundary.market_pending,true);assert.equal(boundary.tokens[0].asset_review.status,'quoted');assert.equal(boundary.tokens[0].cashout_pending,undefined);
  assert.deepEqual(boundary.tokens[0].liquidation_routes,first.tokens[0].liquidation_routes);assert.equal(boundary.tokens[1].cashout_pending,true);assert.equal(boundary.tokens[1].asset_review,undefined);
 }finally{Object.assign(h,original);fs.rmSync(root,{recursive:true,force:true});}
});

test('successful pinned token details are reused without new metadata calls',async()=>{
 const root=fs.mkdtempSync(path.join(os.tmpdir(),'kira-asset-metadata-')),original={endpoints:h.endpoints,client:h.client,snapshotBlock:h.snapshotBlock};
 try{
  let metadata=0;h.endpoints=()=>['synthetic'];h.snapshotBlock=async()=>({number:7n,hash:HASH});h.client=()=>({getChainId:async()=>999,getBalance:async()=>0n,multicall:async({contracts})=>contracts.map(q=>{
   if(q.functionName==='exists')return {status:'success',result:false};if(q.functionName==='balanceOf')return {status:'success',result:1234567n};metadata++;return {status:'success',result:q.functionName==='decimals'?6:'TEST'};
  })});
  const input={wallet:WALLET,inventory_policy:'wallet_candidates_v1',candidates:[{chain_id:999,address:address(10)}]},network={chain_id:999,mintclub_bond_address:address(99)};
  const first=await scanChain(input,network,root);assert.equal(first.tokens[0].wallet_balance,'1.234567');const count=metadata;
  const next=await scanChain(input,network,root);assert.equal(metadata,count);assert.equal(next.tokens[0].wallet_balance,'1.234567');
 }finally{Object.assign(h,original);fs.rmSync(root,{recursive:true,force:true});}
});
