'use strict';
const {test}=require('node:test'),assert=require('node:assert/strict');
const fs=require('node:fs'),os=require('node:os'),path=require('node:path');
const h=require('./onchain.cjs'),{expandRoutes}=require('./cashout-routes.cjs'),{liquidationChain}=require('./pipeline-onchain.cjs');
const TOKEN='0x'+'1'.repeat(40),RESERVE='0x'+'2'.repeat(40),USD='0x833589fcd6edb6e08f4c7c32d4f71b54bda02913',HASH='0x'+'a'.repeat(64);
const leg=(input,output,amount='100',out='200',extra={})=>({status:'quoted',kind:'mintclub_burn',input_address:input,input_amount_raw:amount,
 holding_amount_raw:amount,output_address:output,output_amount_raw:out,output_amount:out,output_decimals:0,
 funded:true,reserve_balance_raw:'999999999',block_number:'7',block_hash:HASH,observed_at:'2026-10-13T07:00:00Z',route_fees_included:true,
 price_impact_included:true,gas_included:false,execution_verified:false,transfer_tax_included:false,...extra});
const token=()=>({chain_id:8453,token_address:TOKEN,token_type:'ERC20',wallet_balance_raw:'100',balance_block_number:'7',balance_block_hash:HASH,
 dex_pools:[{cashout_quote:leg(TOKEN,RESERVE)}]});

test('nested liquidation passes the actual net output into the next quote without using a spot price',async()=>{
 const seen=[];
 const state=await expandRoutes(token(),async(address,amount)=>{seen.push([address,amount]);return [leg(RESERVE,USD,'150','1000000',{holding_amount_raw:'200',output_decimals:6,output_amount:'1'})];});
 assert.deepEqual(seen,[[RESERVE,200n]]);assert.equal(state.routes.length,1);assert.equal(state.routes[0].output_amount,'1');
 assert.equal(state.routes[0].input_amount_raw,'100');assert.equal(state.routes[0].legs.length,2);assert.equal(state.pending.length,0);
});
test('budget interruption preserves the remaining amount frontier and completed root leg across restart',async()=>{
 let saved;
 await assert.rejects(expandRoutes(token(),async()=>{const error=new Error('budget');error.code='market_budget';throw error;},{save:s=>saved=structuredClone(s)}),/budget/);
 assert.equal(saved.pending[0].amount,'200');assert.equal(saved.pending[0].legs.length,1);
 const state=await expandRoutes(token(),async()=>[leg(RESERVE,USD,'200','1')],{state:saved});
 assert.equal(state.routes[0].legs.length,2);assert.equal(state.expanded,2);
 const other={...token(),wallet_balance_raw:'101'};
 await assert.rejects(expandRoutes(other,async()=>[],{state}),/does not match/);
});
test('failed, unbacked, excessive or reorged output legs never establish cash proceeds',async()=>{
 for(const quote of [{status:'unknown'},leg(RESERVE,USD,'201','1'),leg(RESERVE,USD,'200','1',{funded:false}),
   leg(RESERVE,USD,'200','1',{block_hash:'0x'+'b'.repeat(64)}),leg(RESERVE,USD,'200','1',{output_amount:'2'})]){
  const state=await expandRoutes(token(),async()=>[quote]);assert.equal(state.routes.length,0);assert(state.unknown.length>0);
 }
});
test('cycles and finite depth leave explicit unknown scopes',async()=>{
 let state=await expandRoutes(token(),async()=>[leg(RESERVE,TOKEN,'200','1')]);
 assert.equal(state.routes.length,0);assert(state.unknown.some(reason=>reason.includes('Cyclic')));
 state=await expandRoutes(token(),async()=>[],{maxLegs:1});
 assert.equal(state.routes.length,0);assert(state.unknown.some(reason=>reason.includes('leg limit')));
});
test('new verified root quotes reopen an earlier empty frontier without refreshing source clocks',async()=>{
 const held={...token(),dex_pools:[]};
 let state=await expandRoutes(held,async()=>[]);
 assert.equal(state.routes.length,0);
 held.dex_pools=[{cashout_quote:leg(TOKEN,USD)}];
 state=await expandRoutes(held,async()=>assert.fail('Terminal quote expanded'),{state});
 assert.equal(state.routes.length,1);
 const expanded=state.expanded;
 held.dex_pools[0].cashout_quote.observed_at='2026-10-14T01:00:00Z';
 state=await expandRoutes(held,async()=>assert.fail('Unchanged amount reread'),{state});
 assert.equal(state.expanded,expanded);assert.equal(state.routes.length,1);
});
test('installed pipeline composes funded nested burns at the holding block and retains paths on restart',async()=>{
 const root=fs.mkdtempSync(path.join(os.tmpdir(),'kira-nested-liquidation-'));
 const originals={endpoints:h.endpoints,client:h.client,snapshotBlock:h.snapshotBlock};
 try{
  const network={chain_id:8453,network:'base',environment:'mainnet',mintclub_bond_address:'0x'+'9'.repeat(40)};
  const held={...token(),dex_pools:[],mintclub:{reserve_token:RESERVE,reserve_decimals:0,reserve_balance_raw:'999',funded:true,block_number:'7',block_hash:HASH,
   observed_at:'2026-10-13T07:00:00Z',wallet_full_burn:{net_refund_raw:'200',net_refund:'200',royalty_raw:'1',gas_included:false}}};
  const cache={schema_version:1,wallet:TOKEN,chain_id:8453,bond:network.mintclub_bond_address,block_number:'7',block_hash:HASH,requests:{},nodes:{},asset_pools:{[RESERVE]:{pools:[],unknown:null}}};
  fs.writeFileSync(path.join(root,'cashout-checkpoint-8453.json'),JSON.stringify(cache));
  let refundReads=0;
  h.endpoints=()=>['synthetic'];h.snapshotBlock=async(c,known)=>{assert.equal(known.block_hash,HASH);return {number:7n,hash:HASH};};
  h.client=()=>({getChainId:async()=>8453,readContract:async query=>{
   assert.equal(query.blockNumber,7n);
   if(query.functionName==='exists')return true;
   if(query.functionName==='getDetail')return {info:{reserveToken:USD,reserveDecimals:6,reserveBalance:5000000n}};
   if(query.functionName==='getRefundForTokens'){assert.deepEqual(query.args,[RESERVE,200n]);refundReads++;return [1000000n,10000n];}
   throw new Error('Unexpected synthetic query');
  },multicall:async()=>assert.fail('Funded redemption blocked by alternate DEX lookup')});
  const input={wallet:TOKEN,tokens:[held],market_chain_names:{}};
  let result=await liquidationChain(network,input,path.join(root,'result.json'));
  assert.equal(result.market_pending,false);assert.equal(result.tokens[0].liquidation_routes[0].output_amount,'1');
  assert.equal(result.tokens[0].liquidation_routes[0].legs[1].royalty_raw,'10000');assert.equal(refundReads,1);
  result=await liquidationChain(network,input,path.join(root,'result.json'));
  assert.equal(refundReads,1);assert.equal(result.tokens[0].liquidation_routes.length,1);
 }finally{Object.assign(h,originals);fs.rmSync(root,{recursive:true,force:true});}
});

test('verified root membership recovers missing bulk quotes and keeps failed reads pending across restart',async()=>{
 const held={...token(),dex_pools:[],mintclub_membership_status:'verified',mintclub_error:{message:'RPC Request failed.'}};
 let attempts=0;
 let state=await expandRoutes(held,async(address,amount,options)=>{
  assert.equal(address,TOKEN);assert.equal(amount,100n);assert.equal(options.mintOnly,true);attempts++;
  return [{status:'unknown',reason:'Redemption unavailable.',retryable:true,failure_kind:'transport'}];
 });
 assert.equal(state.routes.length,0);assert.equal(state.pending.length,1);assert.equal(state.expanded,0);
 assert.equal(state.root_error_kind,'transport');
 state=await expandRoutes(held,async()=>{attempts++;return [leg(TOKEN,USD,'100','1000000',{output_decimals:6,output_amount:'1'})];},{state:JSON.parse(JSON.stringify(state))});
 assert.equal(state.routes.length,1);assert.equal(state.pending.length,0);assert.equal(state.root_retry_pending,false);
 const clock=state.routes[0].observed_at;
 state=await expandRoutes(held,async()=>assert.fail('Successful root recovery reread'),{state});
 assert.equal(attempts,2);assert.equal(state.routes[0].observed_at,clock);
});

test('root recovery does not lose an existing DEX witness or duplicate it when a burn becomes available',async()=>{
 const held={...token(),mintclub_membership_status:'verified',dex_pools:[{cashout_quote:leg(TOKEN,USD,'100','200',{kind:'aerodrome_pool'})}]};
 let state=await expandRoutes(held,async()=>[{status:'unknown',reason:'Retry root.',retryable:true}]);
 assert.equal(state.routes.length,1);assert.equal(state.root_retry_pending,true);
 state=await expandRoutes(held,async()=>[leg(TOKEN,USD,'100','300')],{state});
 assert.equal(state.routes.length,2);assert.equal(state.root_retry_pending,false);
});

test('pipeline retries failed root detail through pinned individual reads without a fallback request burst',async()=>{
 const root=fs.mkdtempSync(path.join(os.tmpdir(),'kira-root-recovery-'));
 const originals={endpoints:h.endpoints,client:h.client,snapshotBlock:h.snapshotBlock};
 try{
  const network={chain_id:8453,network:'base',environment:'mainnet',mintclub_bond_address:'0x'+'9'.repeat(40)};
  const held={...token(),dex_pools:[],mintclub_membership_status:'verified',mintclub:null,mintclub_error:{message:'RPC Request failed.'}};
  let detailReads=0,existsReads=0;
  h.endpoints=()=>['synthetic'];h.snapshotBlock=async()=>({number:7n,hash:HASH});
  h.client=()=>({getChainId:async()=>8453,readContract:async query=>{
   assert.equal(query.blockNumber,7n);
   if(query.functionName==='exists'){existsReads++;return true;}
   if(query.functionName==='getDetail'){
    if(++detailReads===1){const e=new Error('Synthetic transport unavailable');e.name='HttpRequestError';throw e;}
    return {info:{reserveToken:USD,reserveDecimals:6,reserveBalance:5000000n}};
   }
   if(query.functionName==='getRefundForTokens'){assert.deepEqual(query.args,[TOKEN,100n]);return [1000000n,10000n];}
   assert.fail('Unexpected recovery query');
  },multicall:async()=>assert.fail('Failed transport caused a request burst')});
  const input={wallet:TOKEN,tokens:[held],market_chain_names:{}},output=path.join(root,'result.json');
  let result=await liquidationChain(network,input,output);
  assert.equal(result.market_pending,true);assert.equal(result.tokens[0].cashout_pending,true);assert.equal(detailReads,1);
  result=await liquidationChain(network,input,output);
  assert.equal(result.market_pending,false);assert.equal(result.tokens[0].liquidation_routes[0].output_amount,'1');
  assert.equal(detailReads,2);assert.equal(existsReads,1);
  await liquidationChain(network,input,output);assert.equal(detailReads,2);
 }finally{Object.assign(h,originals);fs.rmSync(root,{recursive:true,force:true});}
});

test('root-only pass records the burn prefix before any intermediate venue work',async()=>{
 let state=await expandRoutes(token(),async()=>assert.fail('Intermediate lookup blocked other root quotes'),{rootOnly:true,maxSteps:2});
 assert.equal(state.expanded,1);assert.equal(state.pending[0].address,RESERVE);assert.equal(state.pending[0].amount,'200');
 state=await expandRoutes(token(),async()=>[leg(RESERVE,USD,'200','1')],{state,maxSteps:2});
 assert.equal(state.routes.length,1);assert.equal(state.pending.length,0);
});

test('one slow root preserves its pending work and lets another held asset receive a quote',async()=>{
 const root=fs.mkdtempSync(path.join(os.tmpdir(),'kira-fair-root-'));
 const originals={endpoints:h.endpoints,client:h.client,snapshotBlock:h.snapshotBlock};
 try{
  const second='0x'+'3'.repeat(40),network={chain_id:8453,network:'base',environment:'mainnet',mintclub_bond_address:'0x'+'9'.repeat(40)};
  const first={...token(),dex_pools:[],mintclub_membership_status:'verified'},other={...first,token_address:second};
  let fail=true;
  h.endpoints=()=>['synthetic'];h.snapshotBlock=async()=>({number:7n,hash:HASH});
  h.client=()=>({getChainId:async()=>8453,readContract:async query=>{
   if(query.functionName==='exists')return true;
   if(query.functionName==='getDetail'){
    if(fail&&query.args[0]===TOKEN){const error=new Error('Synthetic asset budget');error.code='market_budget';throw error;}
    return {info:{reserveToken:USD,reserveDecimals:6,reserveBalance:5000000n}};
   }
   if(query.functionName==='getRefundForTokens')return [1000000n,10000n];
   assert.fail('Unexpected fair root query');
  }});
  const input={wallet:TOKEN,tokens:[first,other],cashout_root_only:true,market_chain_names:{}},output=path.join(root,'result.json');
  let result=await liquidationChain(network,input,output);
  assert.equal(result.market_pending,true);assert.equal(result.tokens[0].cashout_pending,true);
  assert.equal(result.tokens[1].liquidation_routes[0].output_amount,'1');
  const checkpoint=JSON.parse(fs.readFileSync(path.join(root,'cashout-checkpoint-8453.json')));
  assert.equal(checkpoint.nodes[TOKEN+':ERC20'].pending.length,1);assert.equal(checkpoint.root_attempts[TOKEN+':ERC20'],1);
  fail=false;result=await liquidationChain(network,input,output);
  assert.equal(result.market_pending,false);assert(result.tokens.every(t=>t.liquidation_routes.length===1));
 }finally{Object.assign(h,originals);fs.rmSync(root,{recursive:true,force:true});}
});
