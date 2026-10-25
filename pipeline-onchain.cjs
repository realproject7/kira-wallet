// Read-only wallet analysis. Credentials stay in the RPC helper process.
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');
const h = require('./onchain.cjs');
const {mintclubUrl}=require('./market-links.cjs');
const v = h.viem;
const {quotePool}=require('./cashout-quotes.cjs');
const {expandRoutes,terminal,validLeg,seedQuotes,representativeQuote}=require('./cashout-routes.cjs');
const MULTICALL = '0xcA11bde05977b3631167028862bE2a173976CA11';
const erc20 = v.parseAbi([
  'function balanceOf(address) view returns (uint256)',
  'function decimals() view returns (uint8)',
  'function symbol() view returns (string)',
  'function name() view returns (string)',
]);
const erc1155 = v.parseAbi(['function balanceOf(address,uint256) view returns (uint256)']);
const poolAbi = v.parseAbi([
  'function factory() view returns (address)', 'function token0() view returns (address)',
  'function token1() view returns (address)', 'function liquidity() view returns (uint128)',
  'function getReserves() view returns (uint112,uint112,uint32)',
  'function getSlot0(bytes32) view returns (uint160,int24,uint24,uint24)',
  'function getLiquidity(bytes32) view returns (uint128)',
  'function getPool(address,address,uint24) view returns (address)',
  'function getPool(address,address,bool) view returns (address)',
  'function getPair(address,address) view returns (address)',
]);
const deployments = JSON.parse(fs.readFileSync(path.join(h.assets, 'sources/uniswap-deployments.json'))).records;
const stamp = () => new Date().toISOString();
const endpointIdentity = new WeakMap();
const emitProgress = (n,operation,checked,total) => console.log(JSON.stringify({stage:'onchain_progress',chain_id:n.chain_id,operation,checked,total}));
const emitChain = row => console.log(JSON.stringify({stage:'chain',chain_id:row.chain_id,status:row.status,endpoint_index:row.endpoint_index,rpc_endpoint_indices:row.rpc_endpoint_indices,
  block_number:row.block_number==null?null:row.block_number.toString(),registry:row.registry_scan?.registry_count,
  checked:row.registry_scan?.checked,held:row.tokens.length,cache_reused:row.registry_scan?.cache_reused}));
const write = (file, data) => {
  fs.mkdirSync(path.dirname(file), {recursive:true});
  const fd=fs.openSync(file+'.tmp','w');
  try{fs.writeFileSync(fd,h.serialize(data)+'\n');fs.fsyncSync(fd);}finally{fs.closeSync(fd);}
  fs.renameSync(file + '.tmp', file);
  const directory=fs.openSync(path.dirname(file),'r');
  try{fs.fsyncSync(directory);}finally{fs.closeSync(directory);}
};
async function parallel(items, workers, fn) {
  const results = new Array(items.length); let next = 0;
  await Promise.all(Array.from({length:Math.min(workers, items.length)}, async () => {
    for (;;) {const i = next++; if (i >= items.length) return; results[i] = await fn(items[i], i);}
  }));
  return results;
}
async function connect(n, onClient=()=>{}) {
  if(!h.endpoints(n.chain_id).length)throw new Error('No RPC endpoint configured; public fallback is disabled.');
  const c=h.client(n.chain_id);
  onClient(c);
  if(await c.getChainId()!==n.chain_id)throw new Error('RPC chain identity mismatch');
  endpointIdentity.set(c,h.rpcEndpointsUsed(c)[0]??0);return c;
}
function rpcFailure(error) {
  let sizeLimit=false,transportFailure=false,schedulingFailure=false;
  for(let cause=error,depth=0;cause&&depth<10;cause=cause.cause,depth++) {
    if(['HttpRequestError','TimeoutError'].includes(cause.name))transportFailure=true;
    if(cause.name==='RpcSchedulingTimeout')schedulingFailure=true;
    if(cause.status===413||/\b(batch|payload|response|request body)\b.*\b(large|size|limit|exceed)/i.test(cause.shortMessage||cause.message||'')||/gas.*(cap|limit).*exceed|exceed.*gas.*(cap|limit)/i.test(cause.shortMessage||cause.message||''))sizeLimit=true;
    if(cause.status===429)return {sizeLimit:false,transportFailure:true};
  }
  return {sizeLimit,transportFailure,schedulingFailure};
}
async function calls(c, contracts, block) {
  if (!contracts.length) return [];
  try {
    const results=await c.multicall({contracts,blockNumber:block,batchSize:0,multicallAddress:MULTICALL});
    // viem allowFailure also wraps an aggregate RPC failure as per-contract rows.
    if(results.length&&results.every(r=>r.status==='failure')) {
      const limited=results.find(r=>rpcFailure(r.error).sizeLimit);
      if(limited)throw limited.error;
    }
    return results;
  } catch (e) {
    if(e.code==='market_budget')throw e;
    const {sizeLimit,transportFailure}=rpcFailure(e);
    if (!sizeLimit) return contracts.map(()=>({status:'failure',error:e}));
    if (contracts.length > 1) {
      const mid = Math.ceil(contracts.length/2);
      return [...await calls(c,contracts.slice(0,mid),block), ...await calls(c,contracts.slice(mid),block)];
    }
    try {return [{status:'success',result:await c.readContract({...contracts[0],blockNumber:block})}];}
    catch (inner) {if(inner.code==='market_budget')throw inner;return [{status:'failure',error:inner}];}
  }
}
async function batches(c, contracts, block, size=128, progress=null) {
  const plans = [];
  for (let i=0; i<contracts.length; i+=size) plans.push(contracts.slice(i,i+size));
  const results=[];
  for(const plan of plans){results.push(...await calls(c,plan,block));if(progress)progress(results.length,contracts.length);}
  return results;
}
async function factReads(c,contracts,block,checkpoint,file,n,operation) {
  checkpoint.facts=checkpoint.facts||{};
  if(typeof checkpoint.facts!=='object'||Array.isArray(checkpoint.facts))throw new Error('Invalid pinned detail facts.');
  const key=q=>crypto.createHash('sha256').update(h.serialize({address:q.address.toLowerCase(),name:q.functionName,args:q.args||[]})).digest('hex');
  const pending=contracts.filter(q=>checkpoint.facts[key(q)]===undefined);
  let checked=contracts.length-pending.length;emitProgress(n,operation,checked,contracts.length);
  const failures=new Map();
  const capture=(group,rows)=>rows.forEach((row,i)=>{
    if(row.status==='success'){checkpoint.facts[key(group[i])]={value:cacheEncode(row.result),observed_at:stamp()};failures.delete(key(group[i]));}
    else failures.set(key(group[i]),row.error);
  });
  for(let start=0;start<pending.length;start+=128){
    const group=pending.slice(start,start+128),rows=await calls(c,group,block);
    capture(group,rows);
    write(file,checkpoint);checked+=group.length;emitProgress(n,operation,checked,contracts.length);
  }
  // Retry only failed facts once in smaller groups. A transient aggregate
  // failure must not permanently strip curve prices from verified holdings.
  const retry=pending.filter(q=>checkpoint.facts[key(q)]===undefined);
  for(let start=0;start<retry.length;start+=8){
    const group=retry.slice(start,start+8);capture(group,await calls(c,group,block));write(file,checkpoint);
  }
  return contracts.map(q=>{const fact=checkpoint.facts[key(q)];return fact?{status:'success',result:cacheDecode(fact.value),observed_at:fact.observed_at}:{status:'failure',error:failures.get(key(q))||new Error('Pinned token details unavailable.')};});
}
async function balanceReads(c,tokens,wallet,block,checkpoint,file,n,{maxBatches=Infinity}={}) {
  checkpoint.balance_times=checkpoint.balance_times||{};
  const key=t=>t.address.toLowerCase()+':'+t.token_type;
  for(const field of ['balance_attempts','zero_attempts']) {
    checkpoint[field]=checkpoint[field]||{};
    if(typeof checkpoint[field]!=='object'||Array.isArray(checkpoint[field])||Object.values(checkpoint[field]).some(n=>!Number.isSafeInteger(n)||n<0))throw new Error('Invalid saved balance attempt frontier.');
  }
  // Prefer never-read identities, then rotate retry holes. Verification has
  // its own frontier so eight failing suspicious zeros cannot block the rest.
  const pending=tokens.filter(t=>checkpoint.balances[key(t)]===undefined||t.token_type==='ERC20'&&t.suspicious_zero_check&&checkpoint.balances[key(t)]==='0'&&checkpoint.zero_checks?.[key(t)]?.outcome!=='agreed')
    .sort((a,b)=>(checkpoint.balance_attempts[key(a)]||0)-(checkpoint.balance_attempts[key(b)]||0)
      ||(checkpoint.zero_attempts[key(a)]||0)-(checkpoint.zero_attempts[key(b)]||0));
  for(const token of pending){delete checkpoint.balances[key(token)];delete checkpoint.balance_times[key(token)];}
  let checked=tokens.length-pending.length;
  emitProgress(n,'balances',checked,tokens.length);
  const failures=new Map();
  checkpoint.zero_checks=checkpoint.zero_checks||{};
  // The bound applies to this slice. Saved successful checks are not charged
  // again; failed checks and previously deferred identities can resume later.
  let verified=0;
  for(let start=0;start<pending.length&&start/128<maxBatches;start+=128) {
    const plan=pending.slice(start,start+128);
    const rows=await calls(c,plan.map(t=>({address:t.address,abi:t.token_type==='ERC1155'?erc1155:erc20,
      functionName:'balanceOf',args:t.token_type==='ERC1155'?[wallet,0n]:[wallet]})),block);
    for(const token of plan)checkpoint.balance_attempts[key(token)]=(checkpoint.balance_attempts[key(token)]||0)+1;
    for(let i=0;i<plan.length;i++){
      const token=plan[i],r=rows[i];
      if(r.status!=='success'||r.result!==0n||!token.suspicious_zero_check||token.token_type!=='ERC20')continue;
      if(verified>=8){rows[i]={status:'failure',deferred:true,error:new Error('Targeted zero verification budget reached. Balance remains unknown.')};continue;}
      verified++;
      checkpoint.zero_attempts[key(token)]=(checkpoint.zero_attempts[key(token)]||0)+1;
      try{
        const query={address:token.address,abi:erc20,functionName:'balanceOf',args:[wallet],blockNumber:block};
        const verifier=h.verificationClient(c)||c;
        const direct=await verifier.readContract(query),peer=h.peerClient(verifier);
        if(!peer)throw new Error('A qualified peer is unavailable for this suspicious zero. Balance remains unknown.');
        await h.snapshotBlock(peer,{block_number:block.toString(),block_hash:checkpoint.block_hash});
        const other=await peer.readContract(query);
        checkpoint.zero_checks[key(token)]={direct:direct.toString(),peer:other.toString(),block_hash:checkpoint.block_hash,
          outcome:direct===other?'agreed':'conflicting',rpc_routes:h.rpcRoutes(peer)};
        if(direct!==other)throw new Error('Pinned balance observations conflict. Balance remains unknown.');
        rows[i]={status:'success',result:direct};
      }catch(error){if(error.code==='market_budget')throw error;const evidence=checkpoint.zero_checks[key(token)]||{};checkpoint.zero_checks[key(token)]={...evidence,outcome:evidence.outcome==='conflicting'?'conflicting':'unknown',block_hash:checkpoint.block_hash};rows[i]={status:'failure',error};}
    }
    rows.forEach((r,i)=>{if(r.status==='success'){checkpoint.balances[key(plan[i])]=r.result.toString();checkpoint.balance_times[key(plan[i])]=stamp();}else failures.set(key(plan[i]),r);});
    write(file,checkpoint);checked+=plan.length;emitProgress(n,'balances',checked,tokens.length);
  }
  return tokens.map(t=>checkpoint.balances[key(t)]!==undefined?{status:'success',result:BigInt(checkpoint.balances[key(t)]),observed_at:checkpoint.balance_times[key(t)]||checkpoint.observed_at}:failures.get(key(t))||{status:'pending'});
}
async function registry(c, n, block, {file,blockHash,maxBatches=Infinity}={}) {
  const cacheFile=path.join(h.root,'cache/mintclub-registry',`${n.chain_id}-${n.mintclub_bond_address.toLowerCase()}.json`);
  const validEntry=t=>t&&Number.isSafeInteger(t.index)&&t.index>=0&&v.isAddress(t.address)
    &&(t.decimals===18&&t.token_type==='ERC20'||t.decimals===0&&t.token_type==='ERC1155');
  let state=file&&fs.existsSync(file)?JSON.parse(fs.readFileSync(file)):null,cacheReused=0;
  if(state&&(state.chain_id!==n.chain_id||state.bond_address!==n.mintclub_bond_address.toLowerCase()
      ||state.block_number!==block.toString()||state.block_hash!==blockHash
      ||!Number.isSafeInteger(state.count)||state.count<0||!Number.isSafeInteger(state.next_index)||state.next_index<0||state.next_index>state.count
      ||!Array.isArray(state.entries)||!state.entries.every(t=>validEntry(t)&&t.index<state.next_index)
      ||!Array.isArray(state.failures)||!state.failures.every(t=>Number.isSafeInteger(t.index)&&t.index>=0&&t.index<state.next_index)
      ||new Set([...state.entries,...state.failures].map(t=>t.index)).size!==state.next_index
      ||state.entries.length+state.failures.length!==state.next_index))throw new Error('Registry checkpoint does not match this pinned research window.');
  if(state)cacheReused=state.entries.length;
  else {
    const count=Number(await c.readContract({address:n.mintclub_bond_address,abi:h.bondAbi,functionName:'tokenCount',blockNumber:block}));
    if(!Number.isSafeInteger(count)||count<0)throw new Error('Invalid registry count');
    let entries=[];
    if(fs.existsSync(cacheFile)) {
      const cache=JSON.parse(fs.readFileSync(cacheFile));
      if(cache.chain_id===n.chain_id&&typeof cache.bond_address==='string'&&cache.bond_address.toLowerCase()===n.mintclub_bond_address.toLowerCase()
          &&Array.isArray(cache.entries)&&cache.entries.length<=count&&cache.entries.every((t,i)=>validEntry(t)&&t.index===i)) {
        const old=cache.entries;
        const checks=old.length?await calls(c,[0,old.length-1].map(i=>({address:n.mintclub_bond_address,abi:h.bondAbi,functionName:'tokens',args:[BigInt(i)]})),block):[];
        if(!old.length||checks.every((r,i)=>r.status==='success'&&r.result.toLowerCase()===old[i?old.length-1:0].address.toLowerCase()))entries=old;
      }
    }
    cacheReused=entries.length;
    state={chain_id:n.chain_id,bond_address:n.mintclub_bond_address.toLowerCase(),block_number:block.toString(),block_hash:blockHash,
      count,next_index:entries.length,entries,failures:[]};
  }
  const persist=()=>{if(file)write(file,state);};persist();
  const entries=new Map(state.entries.map(t=>[t.index,t])),failures=new Map(state.failures.map(t=>[t.index,t]));
  // Advance the unscheduled frontier, then retry saved holes once per slice.
  // A bad identity cannot prevent unrelated indices from receiving a turn.
  const retries=[...failures.keys()].sort((a,b)=>a-b);
  let used=0;
  while(used<maxBatches&&(retries.length||state.next_index<state.count)) {
    const indices=state.next_index<state.count?Array.from({length:Math.min(128,state.count-state.next_index)},(_,i)=>state.next_index+i):retries.splice(0,128);
    const addresses=await calls(c,indices.map(i=>({address:n.mintclub_bond_address,abi:h.bondAbi,functionName:'tokens',args:[BigInt(i)]})),block);
    const additions=addresses.map((r,i)=>({index:indices[i],address:r.status==='success'&&v.isAddress(r.result)?r.result:null,
      error:r.status==='success'?null:h.safeError(r.error)}));
    const valid=additions.filter(t=>t.address);
    const decimals=await calls(c,valid.map(t=>({address:t.address,abi:erc20,functionName:'decimals'})),block);
    valid.forEach((t,i)=>{const r=decimals[i];t.decimals=r.status==='success'?r.result:null;t.token_type=t.decimals===18?'ERC20':t.decimals===0?'ERC1155':'unknown';if(t.token_type==='unknown')t.error=r.status==='failure'?h.safeError(r.error):{message:'Unexpected Mint Club decimals'};});
    for(const item of additions){if(validEntry(item)){entries.set(item.index,item);failures.delete(item.index);}else failures.set(item.index,{index:item.index,error:item.error||{message:'Registry address unavailable'}});}
    state.next_index=Math.max(state.next_index,indices.at(-1)+1);
    state.entries=[...entries.values()].sort((a,b)=>a.index-b.index);state.failures=[...failures.values()].sort((a,b)=>a.index-b.index);
    persist();
    const prefix=[];for(let i=0;entries.has(i);i++)prefix.push(entries.get(i));
    write(cacheFile,{chain_id:n.chain_id,bond_address:n.mintclub_bond_address,observed_at:stamp(),block_number:block,entries:prefix});
    used++;emitProgress(n,'registry',entries.size,state.count);
  }
  return {count:state.count,entries:[...state.entries,...state.failures],cache_reused:cacheReused,
    errors:state.failures.length+(state.next_index<state.count?1:0),next_index:state.next_index,
    deferred:state.next_index<state.count,pending:state.next_index<state.count||!!state.failures.length};
}
async function mintclubMembership(c,n,tokens,block,checkpoint,file,{maxBatches=Infinity}={}) {
  // Typed membership is pinned to the balance checkpoint. ID0 histories never
  // authorize arbitrary NFT reads. Failed calls remain unknown and retryable.
  const key=t=>t.address.toLowerCase()+':'+t.token_type;
  checkpoint.mintclub_membership=checkpoint.mintclub_membership||{};
  checkpoint.membership_attempts=checkpoint.membership_attempts||{};
  if(typeof checkpoint.mintclub_membership!=='object'||Array.isArray(checkpoint.mintclub_membership)
      ||Object.entries(checkpoint.mintclub_membership).some(([identity,r])=>!/^0x[0-9a-f]{40}:ERC(20|1155)$/.test(identity)||!r||typeof r.registered!=='boolean'||r.registered&&r.decimals!==(identity.endsWith(':ERC1155')?0:18))
      ||typeof checkpoint.membership_attempts!=='object'||Array.isArray(checkpoint.membership_attempts)
      ||Object.values(checkpoint.membership_attempts).some(value=>!Number.isSafeInteger(value)||value<0))throw new Error('Invalid saved Mint Club membership frontier.');
  const pending=tokens.filter(t=>!checkpoint.mintclub_membership[key(t)])
    .sort((a,b)=>(checkpoint.membership_attempts[key(a)]||0)-(checkpoint.membership_attempts[key(b)]||0));
  const failures=new Map();
  for(let start=0;start<pending.length&&start/128<maxBatches;start+=128){
    const plan=pending.slice(start,start+128);
    const exists=await calls(c,plan.map(t=>({address:n.mintclub_bond_address,abi:h.bondAbi,functionName:'exists',args:[t.address]})),block);
    const registered=plan.filter((t,i)=>exists[i].status==='success'&&exists[i].result===true);
    const decimals=await calls(c,registered.map(t=>({address:t.address,abi:erc20,functionName:'decimals'})),block);
    const byAddress=new Map(registered.map((t,i)=>[t.address.toLowerCase(),decimals[i]]));
    plan.forEach((t,i)=>{
      checkpoint.membership_attempts[key(t)]=(checkpoint.membership_attempts[key(t)]||0)+1;
      const row=exists[i],meta=byAddress.get(t.address.toLowerCase()),expected=t.token_type==='ERC1155'?0:18;
      if(row.status==='success'&&row.result===false)checkpoint.mintclub_membership[key(t)]={registered:false};
      else if(row.status==='success'&&row.result===true&&meta?.status==='success'&&meta.result===expected)
        checkpoint.mintclub_membership[key(t)]={registered:true,decimals:expected};
      else failures.set(key(t),{status:'failure',error:row.error||meta?.error||new Error('Mint Club token standard could not be verified.')});
    });
    write(file,checkpoint);emitProgress(n,'mintclub_membership',Object.keys(checkpoint.mintclub_membership).length,tokens.length);
  }
  return tokens.map(t=>checkpoint.mintclub_membership[key(t)]?{status:'success',...checkpoint.mintclub_membership[key(t)]}:failures.get(key(t))||{status:'pending'});
}
async function scanChain(input, n, output, baseline=false, {maxBatches=Infinity}={}) {
  const file = path.join(output,`${baseline?'baseline-':''}chain-${n.chain_id}.json`);
  const policy=input.inventory_policy||'full_registry',market=policy==='wallet_candidates_v1';
  if(!['full_registry','wallet_candidates_v1'].includes(policy))throw new Error('Invalid inventory scope.');
  if(market&&!v.isAddress(n.mintclub_bond_address))throw new Error('Mint Club bond identity required for wallet candidate scope.');
  const candidates=input.candidates.filter(t=>t.chain_id===n.chain_id).map(t=>t.address.toLowerCase()).sort();
  const id0Candidates=market?(input.mintclub_id0_candidates||[]).filter(t=>t.chain_id===n.chain_id):[];
  if(id0Candidates.some(t=>!v.isAddress(t.address)||t.token_type!=='ERC1155'||String(t.token_id)!=='0'))throw new Error('Invalid Mint Club ID0 candidate.');
  const id0Identities=[...new Set(id0Candidates.map(t=>t.address.toLowerCase()))].sort();
  const fingerprint=crypto.createHash('sha256').update(h.serialize(market?[n.mintclub_bond_address,policy,candidates,id0Identities]:[n.mintclub_bond_address,candidates])).digest('hex');
  // A resumed run retains its fixed-block completed evidence, never wallet-independent balances.
  let previous;
  if (fs.existsSync(file)) {
    previous = JSON.parse(fs.readFileSync(file));
    if((previous.inventory_policy||'full_registry')!==policy)throw new Error('Saved chain inventory scope mismatch. Start a new holdings analysis.');
    if (previous.wallet.toLowerCase()===input.wallet.toLowerCase() && previous.candidate_fingerprint===fingerprint && (previous.status==='complete'||baseline&&previous.phase==='baseline')) {emitChain(previous);return previous;}
  }
  const row = {wallet:input.wallet,chain_id:n.chain_id,network:n.network,inventory_policy:policy,phase:baseline?'baseline':'enrichment',observed_at:stamp(),status:'unavailable',tokens:[],native_balance:null};
  emitProgress(n,'balances',0,null);
  let rpcClient;
  try {
    const checkpointFile=path.join(output,`${baseline?'baseline-':''}balance-checkpoint-${n.chain_id}.json`);
    let checkpoint=fs.existsSync(checkpointFile)?JSON.parse(fs.readFileSync(checkpointFile)):null;
    const resumedCheckpoint=!!checkpoint;
    if(checkpoint&&((checkpoint.inventory_policy||'full_registry')!==policy||market&&checkpoint.bond_address!==n.mintclub_bond_address.toLowerCase()||checkpoint.wallet!==input.wallet.toLowerCase()||checkpoint.chain_id!==n.chain_id||checkpoint.fingerprint!==fingerprint&&(!checkpoint.candidates||checkpoint.candidates.some(a=>!candidates.includes(a))||(checkpoint.id0_candidates||[]).some(a=>!id0Identities.includes(a)))))
      throw new Error('Saved balance checkpoint does not match this research request. Start a new holdings analysis.');
    const c = await connect(n,c=>{rpcClient=c;}), snapshot = await h.snapshotBlock(c,checkpoint),block=snapshot.number;
    checkpoint=checkpoint||{wallet:input.wallet.toLowerCase(),chain_id:n.chain_id,block_number:block.toString(),block_hash:snapshot.hash,observed_at:stamp(),balances:{}};
    checkpoint.inventory_policy=policy;checkpoint.bond_address=n.mintclub_bond_address?.toLowerCase();checkpoint.fingerprint=fingerprint;checkpoint.candidates=candidates;checkpoint.id0_candidates=id0Identities;row.candidate_fingerprint=fingerprint;
    row.preferred_endpoint_index=endpointIdentity.get(c);
    row.block_number = block;
    row.block_hash = snapshot.hash;
    row.head_age_seconds=resumedCheckpoint||snapshot.timestamp==null?null:Math.max(0,Math.floor(Date.now()/1000)-Number(snapshot.timestamp));
    row.head_status=row.head_age_seconds==null?'saved_observation':row.head_age_seconds>86400?'stale':'observed';
    if(checkpoint.native_balance===undefined)checkpoint.native_balance=v.formatUnits(await c.getBalance({address:input.wallet,blockNumber:block}),18);
    row.native_balance=checkpoint.native_balance;row.observed_at=checkpoint.observed_at;write(checkpointFile,checkpoint);
    row.rpc_status = 'available';
    // Check discovered and built-in candidates before expensive cold registry work.
    let id0Membership=[];
    const id0Plan=[...new Map(id0Candidates.map(t=>[t.address.toLowerCase(),{...t,token_type:'ERC1155'}])).values()];
    if(id0Plan.length)id0Membership=await mintclubMembership(c,n,id0Plan,block,checkpoint,checkpointFile,{maxBatches});
    // ERC20 candidates have their own admission path. An ID0-only identity
    // never enters this map until its bond membership and standard are verified.
    const initial=new Map(input.candidates.filter(t=>t.chain_id===n.chain_id).map(t=>[t.address.toLowerCase(),{...t,token_type:'ERC20'}]));
    id0Plan.forEach((t,i)=>{if(id0Membership[i].status==='success'&&id0Membership[i].registered)initial.set(t.address.toLowerCase(),{...t,decimals:0,registered_mintclub:true});});
    const allCandidates=[...initial.values()];
    const initialTokens=allCandidates;
    if(baseline){initial.clear();for(const t of initialTokens)initial.set(t.address.toLowerCase(),t);}
    const initialBalances=await balanceReads(c,initialTokens,input.wallet,block,checkpoint,checkpointFile,n,{maxBatches});
    const firstReads=new Map(initialTokens.map((t,i)=>[t.address.toLowerCase(),initialBalances[i]]));
    let reg;
    try {
      reg = baseline||market?{count:null,entries:[],errors:0,cache_reused:0}:await registry(c,n,block,{file:path.join(output,`registry-checkpoint-${n.chain_id}.json`),blockHash:snapshot.hash,maxBatches});
      if(!baseline&&!market){checkpoint.registry=reg;write(checkpointFile,checkpoint);}
    } catch (e) {
      row.registry_error = h.safeError(e);
      reg = checkpoint.registry?{...checkpoint.registry,errors:Math.max(1,checkpoint.registry.errors),retained:true}:{count:null,entries:[],errors:1,cache_reused:0};
    }
    const plans = new Map();
    for (const [key,t] of initial) plans.set(key,t);
    for (const t of reg.entries.filter(t => t.address && t.token_type && t.token_type!=='unknown')) {
      plans.set(t.address.toLowerCase(),{...plans.get(t.address.toLowerCase()),...t,registered_mintclub:true});
    }
    const tokens = [...plans.values()];
    const remaining=tokens.filter(t=>!firstReads.has(t.address.toLowerCase())||!market&&t.token_type==='ERC1155');
    if(remaining.length)emitProgress(n,'balances',0,remaining.length);
    const later=await balanceReads(c,remaining,input.wallet,block,checkpoint,checkpointFile,n,{maxBatches});
    remaining.forEach((t,i)=>firstReads.set(t.address.toLowerCase(),later[i]));
    const balances=tokens.map(t=>firstReads.get(t.address.toLowerCase()));
    const errors = []; let checked = 0, erc20Checked = 0, erc1155Checked = 0;
    const held = [];
    tokens.forEach((t,i) => {
      const r = balances[i];
      if (r.status==='pending')return;
      if (r.status==='failure') {errors.push({address:t.address,registered_mintclub:!!t.registered_mintclub,error:h.safeError(r.error)}); return;}
      if (t.registered_mintclub) {checked++; if(t.token_type==='ERC20')erc20Checked++;else erc1155Checked++;}
      if (r.result>0n) held.push({...t,balance_raw:r.result});
    });
    row.candidate_scan={total:allCandidates.length,deferred:allCandidates.length-initialTokens.length,checked:initialBalances.filter(r=>r.status==='success').length,
      complete:initialTokens.length===allCandidates.length&&initialBalances.every(r=>r.status==='success')&&id0Membership.every(r=>r.status==='success')};
    let heldMembership=[];
    if(market&&held.length){
      heldMembership=await mintclubMembership(c,n,held,block,checkpoint,checkpointFile,{maxBatches});
      held.forEach((t,i)=>{const membership=heldMembership[i];t.registered_mintclub=membership.status==='success'&&membership.registered;
        if(membership.status!=='success')t.mintclub_membership_unknown=true;});
    }else if(baseline&&held.length){
      const exists=await batches(c,held.map(t=>({address:n.mintclub_bond_address,abi:h.bondAbi,functionName:'exists',args:[t.address]})),block);
      held.forEach((t,i)=>{t.registered_mintclub=exists[i].status==='success'&&exists[i].result===true;});
    }
    const balancesPending=initialBalances.some(r=>r.status==='pending'||r.deferred)||balances.some(r=>r.status==='pending'||r.deferred);
    const membershipPending=[...id0Membership,...heldMembership].some(r=>r.status!=='success');
    const workPending=!!reg.pending||balancesPending||membershipPending,deferDetails=!!reg.deferred||balancesPending;
    if(market)row.mintclub_membership_scan={id0_candidates:id0Plan.length,id0_registered:id0Membership.filter(r=>r.status==='success'&&r.registered).length,
      id0_outside_scope:id0Membership.filter(r=>r.status==='success'&&!r.registered).length,
      id0_unknown:id0Membership.filter(r=>r.status!=='success').length,held_unknown:heldMembership.filter(r=>r.status!=='success').length,
      block_number:block,block_hash:snapshot.hash,complete:!membershipPending,source:'Pinned bond exists(address) and registered token decimals; ERC1155 ID0 only.'};
    row.research_pending=workPending;
    row.work_progress={registry_entries:reg.entries.filter(t=>t.address&&!t.error).length,registry_scheduled:reg.next_index||0,
      balances:Object.keys(checkpoint.balances).length,balance_attempted:Object.keys(checkpoint.balance_attempts).length,
      zero_attempted:Object.keys(checkpoint.zero_attempts).length,membership_checked:Object.keys(checkpoint.mintclub_membership||{}).length,
      membership_attempted:Object.keys(checkpoint.membership_attempts||{}).length};
    const metadata=deferDetails?held.flatMap(()=>Array.from({length:3},()=>({status:'pending'}))):await factReads(c,held.flatMap(t=>['decimals','symbol','name'].map(functionName=>({address:t.address,abi:erc20,functionName}))),block,checkpoint,checkpointFile,n,'metadata');
    const curves=held.filter(t=>t.registered_mintclub);
    const details=deferDetails?curves.map(()=>({status:'pending'})):await factReads(c,curves.map(t=>({address:n.mintclub_bond_address,abi:h.bondAbi,functionName:'getDetail',args:[t.address]})),block,checkpoint,checkpointFile,n,'curves');
    const refunds=deferDetails?curves.map(()=>({status:'pending'})):await factReads(c,curves.map(t=>({address:n.mintclub_bond_address,abi:h.bondAbi,functionName:'getRefundForTokens',args:[t.address,t.balance_raw]})),block,checkpoint,checkpointFile,n,'curves');
    const curveRows=new Map(curves.map((t,i)=>[t.address.toLowerCase(),{detail:details[i],refund:refunds[i]}]));
    row.registry_scan = {registry_count:reg.count,registry_errors:reg.errors,checked,erc20_checked:erc20Checked,erc1155_checked:erc1155Checked,
      cache_reused:reg.cache_reused,balance_errors:errors.filter(t=>t.registered_mintclub).length,
      positive_balances:held.filter(t=>t.registered_mintclub).length,block_number:block,complete:!baseline && !market && reg.errors===0 && checked===reg.count,phase:market?'not_requested':baseline||workPending?'deferred':'checked',enumerated:reg.entries.filter(t=>t.address&&!t.error).length,next_index:reg.next_index??null,
      source:market?'Wallet-history candidates; full registry enumeration not requested.':'On-chain Mint Club bond tokenCount()/tokens(index), then direct wallet balance calls',bond_address:n.mintclub_bond_address};
    row.registry_scan.error_examples=reg.entries.filter(t=>t.error||!t.address).slice(0,5).map(t=>({index:t.index,error:t.error||{message:'Registry address unavailable'}}));
    row.balance_errors = errors;
    row.zero_verification=checkpoint.zero_checks||{};
    for (const [heldIndex,t] of held.entries()) {
      const item = {chain_id:n.chain_id,network:n.network,token_address:t.address,token_type:t.token_type,token_id:t.token_type==='ERC1155'?'0':null,
        wallet_balance_raw:t.balance_raw,balance_block_number:block,balance_block_hash:snapshot.hash,balance_observed_at:firstReads.get(t.address.toLowerCase())?.observed_at||checkpoint.observed_at,indexer_price_references:t.prices||[],indexer_image_url:t.image_url||null,mintclub:null,dex_pools:[]};
      const meta=metadata.slice(heldIndex*3,heldIndex*3+3);
      item.decimals = meta[0].status==='success'?meta[0].result:t.decimals;
      item.dex_liquidity_found=false;
      item.symbol = meta[1].status==='success'?meta[1].result:t.symbol||t.address.slice(0,10);
      item.name = meta[2].status==='success'?meta[2].result:t.name||item.symbol;
      item.wallet_balance = Number.isInteger(item.decimals)?v.formatUnits(t.balance_raw,item.decimals):null;
      if(t.registered_mintclub)item.mintclub_membership_status='verified';
      else if(t.mintclub_membership_unknown)item.mintclub_membership_status='unknown';
      if (item.wallet_balance===null) item.metadata_error = 'Token decimals unavailable; quantity remains unknown.';
      if(deferDetails)item.metadata_pending=true;
      if (t.registered_mintclub&&deferDetails)item.mintclub_pending=true;
      else if (t.registered_mintclub) {
        try {
          const captured=curveRows.get(t.address.toLowerCase());
          if(captured.detail.status!=='success')throw captured.detail.error;
          const detail=captured.detail.result;
          const info = detail.info;
          let refund=null,quoteError=null;
          if(captured.refund.status==='success')refund=captured.refund.result;else quoteError=h.safeError(captured.refund.error);
          item.mintclub = {bond_address:n.mintclub_bond_address,reserve_token:info.reserveToken,reserve_symbol:info.reserveSymbol,reserve_decimals:info.reserveDecimals,
            reserve_balance_raw:info.reserveBalance,reserve_balance:v.formatUnits(info.reserveBalance,info.reserveDecimals),funded:info.reserveBalance>0n,
            price_for_next_mint_in_reserve_token:v.formatUnits(info.priceForNextMint,info.reserveDecimals),current_supply:v.formatUnits(info.currentSupply,item.decimals),
            burn_royalty_bps:detail.burnRoyalty,wallet_full_burn:refund?{net_refund_raw:refund[0],net_refund:v.formatUnits(refund[0],info.reserveDecimals),
              royalty_raw:refund[1],royalty:v.formatUnits(refund[1],info.reserveDecimals),asset:info.reserveSymbol,gas_included:false}:null,
            wallet_full_burn_error:quoteError,block_number:block,block_hash:snapshot.hash,observed_at:captured.refund.observed_at||captured.detail.observed_at||stamp(),source_url:mintclubUrl(n.chain_id,item.symbol,item.token_type)};
        } catch(e) {item.mintclub_error=h.safeError(e);}
      }
      row.tokens.push(item);
    }
    row.token_detail_errors=row.tokens.filter(t=>t.mintclub_error||t.wallet_balance===null).length;
    row.status = !workPending && row.registry_scan.complete && errors.length===0 && row.token_detail_errors===0?'complete':'partial';
    if(market)row.candidate_scan.completion_scope='Recorded wallet candidates only. Exhaustive inventory and qualifying cash-out assets remain unproven.';
  } catch(e) {row.error=h.safeError(e);}
  // A failed reread must not erase successful observations from this same
  // research folder. Preserve their original blocks and timestamps, including
  // ERC1155 identities absent from a failed registry response on legacy runs.
  if(previous&&previous.wallet.toLowerCase()===input.wallet.toLowerCase()
      &&(row.block_hash===undefined||row.block_hash===previous.block_hash)) {
    for(const token of row.tokens){
      const old=previous.tokens.find(t=>t.token_address.toLowerCase()===token.token_address.toLowerCase()&&t.token_type===token.token_type
        &&String(t.wallet_balance_raw)===String(token.wallet_balance_raw)&&t.balance_block_hash===token.balance_block_hash);
      if(!old)continue;
      if(token.wallet_balance===null&&typeof old.wallet_balance==='string'&&Number.isInteger(old.decimals)){
        Object.assign(token,{decimals:old.decimals,wallet_balance:v.formatUnits(BigInt(token.wallet_balance_raw),old.decimals),symbol:old.symbol,name:old.name,metadata_evidence_retained:true});
      }
      if(!token.mintclub&&old.mintclub){token.mintclub=old.mintclub;token.mintclub_evidence_retained=true;}
    }
    const observed=new Set(row.tokens.map(t=>t.token_address.toLowerCase()+':'+t.token_type));
    const retained=previous.tokens.filter(t=>!observed.has(t.token_address.toLowerCase()+':'+t.token_type));
    if(retained.length||row.native_balance===null&&previous.native_balance!==null){
      row.tokens.push(...retained.map(t=>({...t,balance_evidence_retained:true})));
      row.retained_balance_observations=retained.length;
      if(row.native_balance===null){row.native_balance=previous.native_balance;row.observed_at=previous.observed_at;row.native_balance_evidence_retained=true;}
      row.status='partial';row.block_number??=previous.block_number;row.block_hash??=previous.block_hash;
    }
  }
  row.rpc_endpoint_indices=h.rpcEndpointsUsed(rpcClient);
  row.rpc_routes=h.rpcRoutes(rpcClient);
  row.endpoint_index=row.rpc_endpoint_indices.length===1?row.rpc_endpoint_indices[0]:null;
  write(file,row);
  emitChain(row);
  return row;
}
function deployment(chain,protocol,name) {
  return deployments.find(r=>r.chainId===chain && r.protocol===protocol && r.contract.toLowerCase()===name.toLowerCase())?.address;
}
class MarketBudget extends Error {
  constructor(){super('Market verification time budget reached. Saved checks can be resumed.');this.code='market_budget';}
}
const cacheEncode=value=>JSON.parse(JSON.stringify(value,(_,v)=>typeof v==='bigint'?{$bigint:v.toString()}:v));
const cacheDecode=value=>JSON.parse(JSON.stringify(value),(_,v)=>v&&typeof v==='object'&&Object.keys(v).length===1&&typeof v.$bigint==='string'?BigInt(v.$bigint):v);
async function boundedMarket(promise,deadline) {
  if(Date.now()>=deadline)throw new MarketBudget();
  let timer;
  try{return await Promise.race([promise,new Promise((_,reject)=>{timer=setTimeout(()=>reject(new MarketBudget()),deadline-Date.now());})]);}
  finally{clearTimeout(timer);}
}
async function dexChain(n, tokens, {file,wallet,deadline=Date.now()+180_000,representative=false,fullOnly=false}={}) {
  const identity=t=>h.serialize([t.chain_id,t.token_address.toLowerCase(),t.token_type,t.token_id??null,String(t.balance_block_number),String(t.wallet_balance_raw)]);
  const identities=new Set(tokens.map(identity));
  const fingerprint=crypto.createHash('sha256').update(h.serialize([...identities].sort())).digest('hex');
  let cache=file&&fs.existsSync(file)?JSON.parse(fs.readFileSync(file)):null;
  if(cache&&(cache.wallet!==wallet.toLowerCase()||cache.chain_id!==n.chain_id||!Array.isArray(cache.tokens)
      ||cacheDecode(cache.tokens).some(t=>!identities.has(identity(t)))))
    throw new Error('Market checkpoint does not match this research request.');
  if(cache)cache.fingerprint=fingerprint;
  const save=()=>{if(file)write(file,cache);};
  try {
  if(Date.now()>=deadline)throw new MarketBudget();
  const pinned=tokens.find(t=>t.balance_block_hash&&t.balance_block_number!=null);
  const holdingBlock=pinned?{block_number:String(pinned.balance_block_number),block_hash:pinned.balance_block_hash}:null;
  const client=await boundedMarket(connect(n),deadline),snapshot=await boundedMarket(h.snapshotBlock(client,cache||holdingBlock),deadline),block=snapshot.number;
  cache=cache||{wallet:wallet.toLowerCase(),chain_id:n.chain_id,fingerprint,block_number:block.toString(),block_hash:snapshot.hash,requests:{},completed_pools:[],tokens:cacheEncode(tokens),quote_schema_version:2};
  // Legacy completed pool checks predate amount-specific quotes. Preserve their
  // cached reads and fixed block, but revisit the pools to record quote status.
  if(cache.quote_schema_version!==2){cache.completed_pools=[];cache.quote_schema_version=2;}
  cache.pool_attempts=cache.pool_attempts||{};
  cache.asset_reviews=cache.asset_reviews||{};
  if(typeof cache.asset_reviews!=='object'||Array.isArray(cache.asset_reviews)||Object.values(cache.asset_reviews).some(r=>!r||typeof r!=='object'||typeof r.done!=='boolean'||!Number.isSafeInteger(r.failures)||r.failures<0))throw new Error('Invalid saved asset review frontier.');
  const assetKey=t=>t.token_address.toLowerCase()+':'+t.token_type;
  const done=t=>cache.asset_reviews[assetKey(t)]?.done===true;
  if(typeof cache.pool_attempts!=='object'||Array.isArray(cache.pool_attempts)||Object.values(cache.pool_attempts).some(value=>!Number.isSafeInteger(value)||value<0))throw new Error('Invalid saved market attempt frontier.');
  const saved=cacheDecode(cache.tokens);
  for(const token of tokens){
    const previous=saved.find(t=>identity(t)===identity(token));
    for(const pool of previous?.dex_pools||[]){
      const index=token.dex_pools.findIndex(p=>p.pool.toLowerCase()===pool.pool.toLowerCase());
      if(index<0)token.dex_pools.push(pool);else if(cache.completed_pools.includes(token.token_address.toLowerCase()+':'+pool.pool.toLowerCase()))token.dex_pools[index]=pool;
    }
  }
  const requestKey=(name,args)=>crypto.createHash('sha256').update(h.serialize({name,args})).digest('hex');
  const deferred=new Map();
  const c=new Proxy(client,{get(target,name){
    if(!['multicall','readContract'].includes(name))return Reflect.get(target,name);
    return async args=>{
      const key=requestKey(name,args);
      if(cache.requests[key]!==undefined)return cacheDecode(cache.requests[key]);
      if(representative&&name==='readContract'&&deferred.has(key))throw deferred.get(key);
      if(representative&&name==='multicall'){
        const keys=args.contracts.map(q=>requestKey('readContract',{...q,blockNumber:args.blockNumber}));
        if(keys.every(k=>cache.requests[k]!==undefined||deferred.has(k)))return keys.map(k=>cache.requests[k]!==undefined?{status:'success',result:cacheDecode(cache.requests[k])}:{status:'failure',error:deferred.get(k)});
      }
      if(Date.now()>=deadline)throw new MarketBudget();
      const result=await boundedMarket(target[name](args),deadline);
      const safe=name==='multicall'?result.map(r=>r.status==='success'?{status:'success',result:r.result}:{status:'failure',error:h.safeError(r.error)}):result;
      if(name!=='multicall'||safe.every(r=>r.status==='success')){cache.requests[key]=cacheEncode(safe);save();}
      return result;
    };
  }});
  // Supplement DEX indexer discovery on Base with the canonical WETH/USDC factories.
  if (n.chain_id===8453&&!representative) {
    const queries=[];
    for (const t of tokens.filter(t=>t.token_type!=='ERC1155')) for(const quote of ['0x4200000000000000000000000000000000000006','0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913']) {
      if(t.token_address.toLowerCase()===quote.toLowerCase())continue;
      for(const protocol of ['v2','v3','aerodrome']) {
        const factory=protocol==='aerodrome'?'0x420DD381b31aEf6683db6B902084cB0FFECe40Da':deployment(8453,protocol,protocol==='v2'?'UniswapV2Factory':'UniswapV3Factory');
        if(!factory)continue;
        for(const value of protocol==='v3'?[100,500,3000,10000]:protocol==='aerodrome'?[false,true]:[null]) {
          const args=protocol==='v2'?[t.token_address,quote]:[t.token_address,quote,value];
          queries.push({t,quote,protocol,factory,call:{address:factory,abi:poolAbi,functionName:protocol==='v2'?'getPair':'getPool',args}});
        }
      }
    }
    const found=await batches(c,queries.map(q=>q.call),block,60,(checked,total)=>emitProgress(n,'factory_queries',checked,total));
    queries.forEach((q,i)=>{
      const r=found[i];
      if(r.status==='success' && r.result!==v.zeroAddress && !q.t.dex_pools.some(p=>p.pool.toLowerCase()===r.result.toLowerCase())) {
        q.t.dex_pools.push({pool:r.result,venue:q.protocol==='aerodrome'?'aerodrome':'uniswap',version_labels:[q.protocol],
          paired_tokens:[{address:q.t.token_address,symbol:q.t.symbol},{address:q.quote,symbol:q.quote.toLowerCase().endsWith('0006')?'WETH':'USDC'}],
          reported_liquidity:null,source_url:'https://basescan.org/address/'+r.result,factory_discovery:{factory:q.factory,block_number:block}});
      }
    });
    for(const t of tokens)t.factory_discovery={candidate_count:queries.filter(q=>q.t===t).length,errors:queries.filter((q,i)=>q.t===t&&found[i].status==='failure').length,block_number:block};
  }
  const supported=t=>t.dex_pools.filter(p=>['uniswap','aerodrome'].includes(p.venue));
  if(representative)for(const t of tokens){
    const key=assetKey(t),review=cache.asset_reviews[key]||{done:false,failures:0};cache.asset_reviews[key]=review;
    // A funded curve prefix may still need an intermediate quote. Give that
    // single route to the liquidation adapter instead of scanning other pools.
    if(representativeQuote(t)||seedQuotes(t).some(q=>validLeg(q,t.token_address,BigInt(t.wallet_balance_raw),t.balance_block_number,t.balance_block_hash)))review.done=true;
    const pools=supported(t);
    if(!pools.length&&t.dex_discovery_status!=='pending'){review.done=true;review.reason='No supported indexed pool. Other factories and venues remain unsearched.';}
    if(!review.pool&&pools.length){
      const score=p=>Number(p.pool.length===42)*2+Number((p.paired_tokens||[]).some(a=>a.address.toLowerCase()!==t.token_address.toLowerCase()&&terminal(n.chain_id,a.address)));
      review.pool=[...pools].sort((a,b)=>score(b)-score(a)||Number(b.reported_liquidity?.usd||0)-Number(a.reported_liquidity?.usd||0)||a.pool.toLowerCase().localeCompare(b.pool.toLowerCase()))[0].pool.toLowerCase();
    }
  }
  const selected=t=>representative?supported(t).filter(p=>!done(t)&&p.pool.toLowerCase()===cache.asset_reviews[assetKey(t)].pool):supported(t);
  const poolTotal=tokens.reduce((sum,t)=>sum+selected(t).length,0);
  let poolChecked=0;emitProgress(n,'pool_checks',0,poolTotal);
  const poolKey=(t,p)=>t.token_address.toLowerCase()+':'+p.pool.toLowerCase();
  const poolQueue=tokens.flatMap(t=>selected(t).map(p=>({t,p})))
    .sort((a,b)=>(cache.pool_attempts[poolKey(a.t,a.p)]||0)-(cache.pool_attempts[poolKey(b.t,b.p)]||0));
  const warmFailures=new Set(),warmCounted=new Set(),warmOwners=new Map();
  if(representative&&tokens.length>1){
    // Share the pool state, membership and output metadata across assets.
    // Only successful cells survive a slice; failed batches do not fan out.
    const owned=(t,q)=>{
      if(!q)return null;
      const key=requestKey('readContract',{...q,blockNumber:block});
      if(!warmOwners.has(key))warmOwners.set(key,new Set());warmOwners.get(key).add(t);return q;
    };
    const warm=async plans=>{
      const needed=key=>[...(warmOwners.get(key)||[])].some(t=>!done(t));
      const pending=[...new Map(plans.map(q=>[requestKey('readContract',{...q,blockNumber:block}),q])).entries()].filter(([k])=>cache.requests[k]===undefined&&needed(k));
      for(let start=0;start<pending.length;start+=128){
        const group=pending.slice(start,start+128).filter(([k])=>needed(k));if(!group.length)continue;
        if(Date.now()>=deadline)throw new MarketBudget();
        const rows=await boundedMarket(calls(client,group.map(([,q])=>q),block),deadline);
        rows.forEach((r,i)=>{
          const key=group[i][0];
          if(r.status==='success'){cache.requests[key]=cacheEncode(r.result);return;}
          deferred.set(key,r.error);
          for(const t of warmOwners.get(key)||[]){
            const asset=assetKey(t);warmFailures.add(asset);
            // A returned failed batch is an admitted attempt, even if the
            // slice ends before the individual pool loop. Queue waits are not.
            if(warmCounted.has(asset)||rpcFailure(r.error).schedulingFailure)continue;
            warmCounted.add(asset);const review=cache.asset_reviews[asset];review.failures++;
            if(review.failures>=2){
              review.done=true;review.reason='Selected pool reads unavailable after bounded attempts. Other venues remain unsearched.';
              t.dex_verification_error={message:review.reason};
              const pool=t.dex_pools.find(p=>p.pool.toLowerCase()===review.pool);
              if(pool)pool.rpc_verification={...pool.rpc_verification,verification:'unverified',error:{message:review.reason}};
            }
          }
        });cache.tokens=cacheEncode(tokens);save();
      }
    };
    const value=q=>{const raw=cache.requests[requestKey('readContract',{...q,blockNumber:block})];return raw===undefined?undefined:cacheDecode(raw);};
    const plan=poolQueue.filter(({p})=>p.pool.length===42);
    const state=p=>Object.fromEntries(['factory','token0','token1',p.version_labels?.includes('v3')?'liquidity':'getReserves'].map(functionName=>[functionName,value({address:p.pool,abi:poolAbi,functionName})]));
    const recognized=s=>typeof s.factory==='string'&&(deployments.some(d=>d.chainId===n.chain_id&&d.contract.toLowerCase().includes('factory')&&d.address.toLowerCase()===s.factory.toLowerCase())||n.chain_id===8453&&s.factory.toLowerCase()==='0x420dd381b31aef6683db6b902084cb0ffece40da');
    await warm(plan.flatMap(({t,p})=>['factory','token0','token1',p.version_labels?.includes('v3')?'liquidity':'getReserves'].map(functionName=>owned(t,{address:p.pool,abi:poolAbi,functionName}))));
    const parameter=p=>p.version_labels?.includes('v3')?{address:p.pool,abi:v.parseAbi(['function fee() view returns (uint24)']),functionName:'fee'}:p.venue==='aerodrome'?{address:p.pool,abi:v.parseAbi(['function stable() view returns (bool)']),functionName:'stable'}:null;
    await warm(plan.filter(({p})=>recognized(state(p))).map(({t,p})=>owned(t,parameter(p))).filter(Boolean));
    const membership=p=>{
      const s=state(p),q=parameter(p),param=q?value(q):null;
      if(!recognized(s)||!s.token0||!s.token1||q&&param===undefined)return null;
      return {address:s.factory,abi:poolAbi,functionName:p.version_labels?.includes('v3')||p.venue==='aerodrome'?'getPool':'getPair',args:q?[s.token0,s.token1,param]:[s.token0,s.token1]};
    };
    await warm(plan.map(({t,p})=>owned(t,membership(p))).filter(Boolean));
    await warm(plan.flatMap(({t,p})=>{
      const q=membership(p);if(!q||value(q)?.toLowerCase()!==p.pool.toLowerCase())return [];
      const s=state(p),output=[s.token0,s.token1].find(a=>a.toLowerCase()!==t.token_address.toLowerCase());
      return [{address:output,abi:erc20,functionName:'balanceOf',args:[p.pool]},{address:output,abi:erc20,functionName:'decimals'},{address:output,abi:erc20,functionName:'symbol'}].map(q=>owned(t,q));
    }));
  }
  for(const {t,p} of poolQueue) {
    if(!['uniswap','aerodrome'].includes(p.venue))continue;
    if(representative&&done(t)){emitProgress(n,'pool_checks',++poolChecked,poolTotal);continue;}
    const identity=poolKey(t,p);
    if(cache.completed_pools.includes(identity)){if(representative)cache.asset_reviews[assetKey(t)].done=true;emitProgress(n,'pool_checks',++poolChecked,poolTotal);continue;}
    if(Date.now()>=deadline)throw new MarketBudget();
    cache.pool_attempts[identity]=(cache.pool_attempts[identity]||0)+1;
    let retry=false,paused=false;
    try {
      if(p.pool.length===66) {
        const sv=deployment(n.chain_id,'v4','StateView');
        if(!sv){p.rpc_verification={verification:'official_state_view_unavailable'};continue;}
        const r=await calls(c,['getSlot0','getLiquidity'].map(functionName=>({address:sv,abi:poolAbi,functionName,args:[p.pool]})),block);
        if(r.some(x=>x.status==='failure'))retry=true;
        p.rpc_verification={verification:r[0].status==='success'&&r[0].result[0]>0n?'initialized_at_official_v4_state_view':'unverified',block_number:block,observed_at:stamp(),state_view:sv};
        if(r[1].status==='success')p.factory_measurement={active_liquidity_verified:r[1].result>0n,state:{liquidity:r[1].result}};
        continue;
      }
      const names=['factory','token0','token1',p.version_labels?.includes('v3')?'liquidity':'getReserves'];
      const r=await calls(c,names.map(functionName=>({address:p.pool,abi:poolAbi,functionName})),block);
      if(r.some(x=>x.status==='failure'))retry=true;
      const state={};r.forEach((x,i)=>{if(x.status==='success')state[names[i]]=x.result;});
      const factory=state.factory;
      const recognized=typeof factory==='string' && (deployments.some(d=>d.chainId===n.chain_id&&d.contract.toLowerCase().includes('factory')&&d.address.toLowerCase()===factory.toLowerCase()) ||
        (n.chain_id===8453&&p.venue==='aerodrome'&&factory.toLowerCase()==='0x420dd381b31aef6683db6b902084cb0ffece40da'));
      let membership=false;
      if(recognized&&state.token0&&state.token1) {
        let check;
        if(p.version_labels?.includes('v3')) {
          const fee=await c.readContract({address:p.pool,abi:v.parseAbi(['function fee() view returns (uint24)']),functionName:'fee',blockNumber:block});state.fee=fee;
          check={address:factory,abi:poolAbi,functionName:'getPool',args:[state.token0,state.token1,fee]};
        } else if(p.venue==='aerodrome') {
          const stable=await c.readContract({address:p.pool,abi:v.parseAbi(['function stable() view returns (bool)']),functionName:'stable',blockNumber:block});
          check={address:factory,abi:poolAbi,functionName:'getPool',args:[state.token0,state.token1,stable]};
        } else check={address:factory,abi:poolAbi,functionName:'getPair',args:[state.token0,state.token1]};
        const mapped=await c.readContract({...check,blockNumber:block});membership=mapped.toLowerCase()===p.pool.toLowerCase();
      }
      p.rpc_verification={verification:membership?'official_factory_verified':'unverified',block_number:block,observed_at:stamp(),state};
      const identity=[state.token0,state.token1].some(a=>a?.toLowerCase()===t.token_address.toLowerCase());
      const active=membership&&identity&&(state.liquidity>0n || (state.getReserves?.[0]>0n&&state.getReserves?.[1]>0n));
      p.factory_measurement={factory_verified:membership,active_liquidity_verified:!!active,state};
      if(membership&&identity) {
        const quote=[state.token0,state.token1].find(a=>a.toLowerCase()!==t.token_address.toLowerCase());
        const q=await calls(c,[{address:quote,abi:erc20,functionName:'balanceOf',args:[p.pool]},{address:quote,abi:erc20,functionName:'decimals'},{address:quote,abi:erc20,functionName:'symbol'}],block);
        if(q.some(x=>x.status==='failure'))retry=true;
        if(q.every(x=>x.status==='success')) Object.assign(p.factory_measurement,{quote_token:quote,quote_symbol:q[2].result,quote_decimals:q[1].result,quote_balance:v.formatUnits(q[0].result,q[1].result)});
        p.cashout_quote=await quotePool(c,n,t,p,block,snapshot.hash,deployments,{batchRead:contracts=>calls(c,contracts,block),fullOnly});
        if(p.cashout_quote.status==='unknown'&&p.cashout_quote.reason.startsWith('Pool quote failed'))retry=true;
      }
    }catch(e){if(e.code==='market_budget'){paused=true;throw e;}retry=true;p.rpc_verification={verification:'unverified',error:h.safeError(e)};}
    finally{
      // Budget pauses retain successful RPC prefixes, but do not mark an
      // unfinished pool as verified or as a provider failure.
      if(!paused&&Date.now()<deadline){if(!retry)cache.completed_pools.push(identity);poolChecked++;}
      if(representative&&!paused&&Date.now()<deadline){const review=cache.asset_reviews[assetKey(t)];if(retry&&!warmFailures.has(assetKey(t)))review.failures++;review.done=!retry||review.failures>=2;}
      if(retry)p.rpc_verification={...p.rpc_verification,error:{message:'Some pool reads failed. Remaining price and execution details are unknown.'}};
      cache.tokens=cacheEncode(tokens);save();emitProgress(n,'pool_checks',poolChecked,poolTotal);
    }
  }
  if(representative){
    tokens.forEach(t=>{if(done(t))delete t.market_pending;else t.market_pending=true;});
    cache.tokens=cacheEncode(tokens);save();return tokens;
  }
  if(Date.now()>=deadline)throw new MarketBudget();
  tokens.forEach(t=>{delete t.market_pending;if(t.dex_pools.some(p=>p.rpc_verification?.error)||t.factory_discovery?.errors)t.dex_verification_error={message:'Some market reads failed. Missing pool and price evidence remains unknown.'};else delete t.dex_verification_error;});cache.tokens=cacheEncode(tokens);save();
  return tokens;
  }catch(e){
    if(e.code!=='market_budget')throw e;
    tokens.forEach(t=>{if(representative&&cache?.asset_reviews?.[t.token_address.toLowerCase()+':'+t.token_type]?.done)delete t.market_pending;else t.market_pending=true;});
    if(cache){cache.tokens=cacheEncode(tokens);save();}
    return tokens;
  }
}
async function reserveChain(n,input,outputPath,deadline=Date.now()+180_000) {
  const rows=[];
  const file=path.join(path.dirname(outputPath),`reserve-checkpoint-${n.chain_id}.json`);
  let cache=fs.existsSync(file)?JSON.parse(fs.readFileSync(file)):null;
  const save=()=>{if(cache)write(file,cache);};
  try {
    if(cache&&(cache.wallet!==input.wallet.toLowerCase()||cache.chain_id!==n.chain_id||cache.bond!==n.mintclub_bond_address.toLowerCase()))throw new Error('Reserve checkpoint does not match this research request.');
    if(Date.now()>=deadline)throw new MarketBudget();
    const c=await boundedMarket(connect(n),deadline),snapshot=await boundedMarket(h.snapshotBlock(c,cache),deadline),block=snapshot.number;
    cache=cache||{wallet:input.wallet.toLowerCase(),chain_id:n.chain_id,bond:n.mintclub_bond_address.toLowerCase(),block_number:block.toString(),block_hash:snapshot.hash,nodes:{}};save();
    const queue=input.tokens.filter(t=>t.chain_id===n.chain_id&&t.mintclub).map(t=>t.token_address),seen=new Set();
    for(let i=0;i<queue.length;i++) {
      const address=queue[i],key=address.toLowerCase();
      if(seen.has(key))continue;seen.add(key);
      if(seen.size>128){rows.push({chain_id:n.chain_id,error:{message:'Reserve graph traversal limit reached'}});break;}
      try {
        if(cache.nodes[key]){const saved=cacheDecode(cache.nodes[key]);rows.push(saved);if(saved.is_curve)queue.push(saved.reserve_token);emitProgress(n,'reserves',rows.length,queue.length);continue;}
        if(Date.now()>=deadline)throw new MarketBudget();
        const exists=await boundedMarket(c.readContract({address:n.mintclub_bond_address,abi:h.bondAbi,functionName:'exists',args:[address],blockNumber:block}),deadline);
        if(!exists){const saved={chain_id:n.chain_id,address,is_curve:false,block_number:block,observed_at:stamp()};rows.push(saved);cache.nodes[key]=cacheEncode(saved);save();emitProgress(n,'reserves',rows.length,queue.length);continue;}
        const d=await boundedMarket(c.readContract({address:n.mintclub_bond_address,abi:h.bondAbi,functionName:'getDetail',args:[address],blockNumber:block}),deadline);
        const info=d.info;
        rows.push({chain_id:n.chain_id,address,is_curve:true,symbol:info.symbol,price_in_reserve:v.formatUnits(info.priceForNextMint,info.reserveDecimals),
          reserve_token:info.reserveToken,reserve_symbol:info.reserveSymbol,curve_reserve:v.formatUnits(info.reserveBalance,info.reserveDecimals),
          funded:info.reserveBalance>0n,block_number:block,observed_at:stamp(),source:mintclubUrl(n.chain_id,info.symbol,input.tokens.find(t=>t.token_address.toLowerCase()===key)?.token_type||'ERC20')});
        queue.push(info.reserveToken);
        cache.nodes[key]=cacheEncode(rows.at(-1));save();emitProgress(n,'reserves',rows.length,queue.length);
      }catch(e){if(e.code==='market_budget')throw e;rows.push({chain_id:n.chain_id,address,error:h.safeError(e),block_number:block,observed_at:stamp()});emitProgress(n,'reserves',rows.length,queue.length);}
    }
  }catch(e){if(e.code==='market_budget'){save();return {tokens:rows,market_pending:true};}rows.push({chain_id:n.chain_id,error:h.safeError(e)});}
  return {tokens:rows,market_pending:false};
}
let nextRouteDiscovery=0;
async function routePools(chain,address,deadline) {
  if(!chain)return {pools:[],unknown:'DEX discovery does not admit this network.'};
  const wait=Math.max(0,nextRouteDiscovery-Date.now());nextRouteDiscovery=Math.max(Date.now(),nextRouteDiscovery)+300;
  if(wait)await boundedMarket(new Promise(resolve=>setTimeout(resolve,wait)),deadline);
  const controller=new AbortController(),timeout=setTimeout(()=>controller.abort(),Math.min(8000,Math.max(1,deadline-Date.now())));
  try{
    const response=await boundedMarket(fetch(`https://api.dexscreener.com/token-pairs/v1/${encodeURIComponent(chain)}/${address}`,{signal:controller.signal}),deadline);
    if(!response.ok)return {pools:[],unknown:'DEX route discovery unavailable or rate limited.'};
    const reader=response.body.getReader();let size=0,chunks=[];
    for(;;){const row=await boundedMarket(reader.read(),deadline);if(row.done)break;size+=row.value.length;if(size>2_000_000){await reader.cancel();return {pools:[],unknown:'DEX route discovery response exceeded the recorded bound.'};}chunks.push(Buffer.from(row.value));}
    const body=JSON.parse(Buffer.concat(chunks).toString());
    if(!Array.isArray(body))return {pools:[],unknown:'DEX route discovery shape unavailable.'};
    const observed=stamp();
    return {pools:body.filter(p=>p.chainId===chain&&typeof p.pairAddress==='string'&&[p.baseToken,p.quoteToken].some(t=>t?.address?.toLowerCase()===address.toLowerCase()))
      .map(p=>({pool:p.pairAddress,venue:p.dexId,version_labels:Array.isArray(p.labels)?p.labels:[],paired_tokens:[p.baseToken,p.quoteToken],
        reported_liquidity:p.liquidity,reported_price_usd:p.priceUsd,source_url:p.url,observed_at:observed})),unknown:null};
  }catch(error){if(error.code==='market_budget')throw error;return {pools:[],unknown:'DEX route discovery failed; unindexed paths remain unknown.'};}
  finally{clearTimeout(timeout);controller.abort();}
}
async function liquidationChain(n,input,outputPath,deadline=Date.now()+180_000) {
  const tokens=input.tokens.filter(t=>t.chain_id===n.chain_id),file=path.join(path.dirname(outputPath),`cashout-checkpoint-${n.chain_id}.json`);
  const representative=input.market_scope==='representative_v1',rootOnly=input.cashout_root_only===true;
  const tokenKey=t=>t.token_address.toLowerCase()+':'+t.token_type;
  if(n.environment!=='mainnet')return {tokens,market_pending:false};
  let cache=fs.existsSync(file)?JSON.parse(fs.readFileSync(file)):null;
  // Local frontier steps can be replayed. Coalesce those writes, while every
  // newly acquired provider fact and every exit still gets a durable checkpoint.
  let savedAt=0,dirty=false;
  const flush=()=>{if(cache&&dirty){write(file,cache);savedAt=Date.now();dirty=false;}};
  const save=(immediate=false)=>{dirty=true;if(immediate||Date.now()-savedAt>=250)flush();};
  const restoreReviewed=token=>{
    const key=tokenKey(token),state=cache?.nodes?.[key];
    if(!representative||cache?.asset_reviews?.[key]?.done!==true||cache.schema_version!==1||cache.wallet!==input.wallet.toLowerCase()||cache.chain_id!==n.chain_id
      ||cache.bond!==n.mintclub_bond_address.toLowerCase()||cache.block_number!==String(token.balance_block_number)||cache.block_hash!==token.balance_block_hash
      ||state?.identity!==JSON.stringify([token.chain_id,token.token_address.toLowerCase(),token.token_type,String(token.wallet_balance_raw),String(token.balance_block_number),token.balance_block_hash])
      ||!Array.isArray(state.routes)||!Array.isArray(state.unknown))return false;
    token.liquidation_routes=state.routes;token.liquidation_unknown_routes=state.unknown;
    token.asset_review={scope:'representative_v1',status:representativeQuote(token)?'quoted':'unknown'};delete token.cashout_pending;return true;
  };
  try{
    const pinned=tokens.find(t=>t.balance_block_hash&&t.balance_block_number!=null);
    if(!pinned)throw new Error('Pinned holding unavailable for liquidation paths.');
    if(cache&&(cache.schema_version!==1||cache.wallet!==input.wallet.toLowerCase()||cache.chain_id!==n.chain_id||cache.bond!==n.mintclub_bond_address.toLowerCase()
        ||cache.block_number!==String(pinned.balance_block_number)||cache.block_hash!==pinned.balance_block_hash))throw new Error('Liquidation checkpoint does not match this request.');
    const client=await boundedMarket(connect(n),deadline),snapshot=await boundedMarket(h.snapshotBlock(client,cache||{block_number:String(pinned.balance_block_number),block_hash:pinned.balance_block_hash}),deadline),block=snapshot.number;
    cache=cache||{schema_version:1,wallet:input.wallet.toLowerCase(),chain_id:n.chain_id,bond:n.mintclub_bond_address.toLowerCase(),block_number:block.toString(),block_hash:snapshot.hash,requests:{},asset_pools:{},nodes:{}};save();
    cache.asset_reviews=cache.asset_reviews||{};
    if(typeof cache.asset_reviews!=='object'||Array.isArray(cache.asset_reviews)||Object.values(cache.asset_reviews).some(r=>!r||typeof r!=='object'||typeof r.done!=='boolean'||!Number.isSafeInteger(r.failures)||r.failures<0))throw new Error('Invalid saved asset review frontier.');
    let assetDeadline=deadline;
    const queryKey=args=>crypto.createHash('sha256').update(h.serialize({...args,blockNumber:block})).digest('hex');
    const deferred=new Map();
    const read=async args=>{
      const query={...args,blockNumber:block},key=queryKey(args);
      if(cache.requests[key]!==undefined)return cacheDecode(cache.requests[key]);
      if(deferred.has(key))throw deferred.get(key);
      flush();
      const value=await boundedMarket(client.readContract(query),assetDeadline);cache.requests[key]=cacheEncode(value);save(true);return value;
    };
    // Warm exact per-query facts with small Multicalls. Rich curve metadata is
    // unnecessary; a healthy member set needs a few paced RPCs instead of one
    // paced round trip for every getter of every held asset. Only successful
    // cells enter the cache. A failed transport is deferred, never fanned out.
    const prefetch=async plans=>{
      const pending=[...new Map(plans.map(p=>[queryKey(p),p])).entries()].filter(([key])=>cache.requests[key]===undefined);
      for(let start=0;start<pending.length;start+=32){
        if(Date.now()>=deadline)throw new MarketBudget();
        const group=pending.slice(start,start+32);flush();
        const rows=await boundedMarket(calls(client,group.map(([,p])=>p),block),deadline);
        rows.forEach((r,i)=>{
          if(r.status==='success')cache.requests[group[i][0]]=cacheEncode(r.result);
          else {const failure=rpcFailure(r.error);if(failure.transportFailure||failure.schedulingFailure)deferred.set(group[i][0],r.error);}
        });save(true);
      }
    };
    const members=tokens.filter(t=>t.mintclub_membership_status==='verified'&&t.balance_block_hash===snapshot.hash
      &&!(representative&&cache.asset_reviews[tokenKey(t)]?.done)&&cache.nodes[tokenKey(t)]?.root_recovery_done!==true&&!t.mintclub?.wallet_full_burn);
    const bondQuery=t=>({address:n.mintclub_bond_address,abi:h.bondAbi,functionName:'tokenBond',args:[t.token_address]});
    await prefetch(members.map(bondQuery));
    const reserves=members.map(t=>cache.requests[queryKey(bondQuery(t))]).filter(v=>v!==undefined).map(cacheDecode)
      .filter(b=>Array.isArray(b)&&v.isAddress(b[4])&&b[4]!==v.zeroAddress).map(b=>b[4]);
    await prefetch(reserves.map(address=>({address,abi:erc20,functionName:'decimals'})));
    await prefetch(members.filter(t=>cache.requests[queryKey(bondQuery(t))]!==undefined).map(t=>({address:n.mintclub_bond_address,abi:h.bondAbi,
      functionName:'getRefundForTokens',args:[t.token_address,BigInt(t.wallet_balance_raw)]})));
    const quoteAsset=async(address,amount,{mintOnly=false,knownMember=false}={})=>{
      const quotes=[];
      try{
        const exists=knownMember||await read({address:n.mintclub_bond_address,abi:h.bondAbi,functionName:'exists',args:[address]});
        if(exists===true){
          // tokenBond returns the exact reserve identity and balance without
          // calling input metadata or returning the whole bonding curve.
          const bond=await read({address:n.mintclub_bond_address,abi:h.bondAbi,functionName:'tokenBond',args:[address]});
          const reserveToken=bond[4],reserveBalance=bond[5];
          const reserveDecimals=await read({address:reserveToken,abi:erc20,functionName:'decimals'});
          const refund=await read({address:n.mintclub_bond_address,abi:h.bondAbi,functionName:'getRefundForTokens',args:[address,amount]});
          quotes.push({status:'quoted',kind:'mintclub_burn',input_address:address,input_amount_raw:amount.toString(),holding_amount_raw:amount.toString(),
            output_address:reserveToken,output_amount_raw:refund[0].toString(),output_amount:v.formatUnits(refund[0],reserveDecimals),output_decimals:reserveDecimals,
            block_number:block.toString(),block_hash:snapshot.hash,observed_at:stamp(),funded:reserveBalance>0n,reserve_balance_raw:reserveBalance.toString(),royalty_raw:refund[1].toString(),
            route_fees_included:true,price_impact_included:true,gas_included:false,execution_verified:false,transfer_tax_included:false,source_url:mintclubUrl(n.chain_id,input.tokens.find(t=>t.token_address.toLowerCase()===address.toLowerCase())?.symbol,input.tokens.find(t=>t.token_address.toLowerCase()===address.toLowerCase())?.token_type||'ERC20')});
        }else if(exists!==false)quotes.push({status:'unknown',reason:'Mint Club membership unavailable.'});
      }catch(error){if(error.code==='market_budget')throw error;const failure=rpcFailure(error);
        quotes.push({status:'unknown',reason:'Amount-specific Mint Club redemption unavailable.',retryable:true,
          failure_kind:failure.sizeLimit?'payload_limit':failure.schedulingFailure?'rpc_wait':failure.transportFailure?'transport':'contract_or_provider'});}
      if(mintOnly)return quotes;
      // Publish a usable funded redemption before exploring alternate venues.
      // The alternative DEX scope remains unknown, never verified absent.
      if(quotes.some(q=>q.status==='quoted'&&q.funded===true&&BigInt(q.output_amount_raw)>0n&&BigInt(q.reserve_balance_raw)>=BigInt(q.output_amount_raw))){
        quotes.push({status:'unknown',reason:'Alternate intermediate DEX venues have not been searched after a funded Mint Club quote.'});
        return quotes;
      }
      const key=address.toLowerCase();
      if(!cache.asset_pools[key]){flush();cache.asset_pools[key]=await routePools(input.market_chain_names?.[n.chain_id],address,assetDeadline);save(true);}
      const catalog=cache.asset_pools[key];
      if(catalog.unknown)quotes.push({status:'unknown',reason:catalog.unknown});
      const shadow={chain_id:n.chain_id,token_address:address,token_type:'ERC20',wallet_balance_raw:amount,
        balance_block_number:block,balance_block_hash:snapshot.hash,quantity_basis:'Prior amount-specific route output, not an observed wallet holding.',dex_pools:structuredClone(catalog.pools)};
      const identity=crypto.createHash('sha256').update(h.serialize([address.toLowerCase(),amount])).digest('hex');
      const [verified]=await dexChain(n,[shadow],{file:path.join(path.dirname(outputPath),`route-market-checkpoint-${n.chain_id}-${identity}.json`),wallet:input.wallet,deadline:assetDeadline,representative});
      if(verified.market_pending)throw new MarketBudget();
      for(const pool of verified.dex_pools)quotes.push(pool.cashout_quote||{status:'unknown',reason:'Pool adapter or quote unavailable.'});
      return quotes;
    };
    let retryPending=false;
    const attemptsKey=rootOnly?'root_attempts':'route_attempts';
    cache[attemptsKey]=cache[attemptsKey]||{};
    if(typeof cache[attemptsKey]!=='object'||Array.isArray(cache[attemptsKey])||Object.values(cache[attemptsKey]).some(n=>!Number.isSafeInteger(n)||n<0))throw new Error('Invalid route attempt checkpoint.');
    let progressAt=0,previousProgress=null;
    const progress=(force=false)=>{
      if(!force&&Date.now()-progressAt<1000)return;
      const routes=tokens.filter(t=>{const s=cache.nodes[tokenKey(t)];return s?.pending.length===0&&!s.root_retry_pending;}).length;
      const checked=tokens.filter(t=>cache.asset_reviews[tokenKey(t)]?.done&&!t.market_pending).length;
      const quoted=tokens.filter(t=>cache.asset_reviews[tokenKey(t)]?.done&&!t.market_pending&&representativeQuote(t,cache.nodes[tokenKey(t)]?.routes)).length;
      const signature=JSON.stringify([routes,checked,quoted]);
      if(signature===previousProgress)return;
      emitProgress(n,'cashout_routes',routes,tokens.length);
      if(representative&&!rootOnly)console.log(JSON.stringify({stage:'onchain_progress',operation:'asset_review',chain_id:n.chain_id,checked,total:tokens.length,quoted,unknown:checked-quoted}));
      previousProgress=signature;progressAt=Date.now();
    };
    progress(true);
    // Unvisited assets receive a turn before retry holes. Attempts are durable
    // scheduling facts, not successful evidence or a completion percentage.
    for(const token of [...tokens].sort((a,b)=>(cache[attemptsKey][tokenKey(a)]||0)-(cache[attemptsKey][tokenKey(b)]||0)||Number(!!b.mintclub?.funded)-Number(!!a.mintclub?.funded)||Number(b.mintclub_membership_status==='verified')-Number(a.mintclub_membership_status==='verified'))){
      const key=token.token_address.toLowerCase()+':'+token.token_type;
      const review=cache.asset_reviews[key]||{done:false,failures:0};cache.asset_reviews[key]=review;
      if(representative&&review.done){
        if(!restoreReviewed(token))throw new Error('Saved representative holding changed.');
        progress();continue;
      }
      if(representative&&!rootOnly&&token.market_pending){token.cashout_pending=true;retryPending=true;continue;}
      if(Date.now()>=deadline)throw new MarketBudget();
      // Three root reads or four intermediate reads must fit the shared
      // two-second family lane while two chains are active. Keep the overall
      // deadline authoritative and retain incomplete work at a turn boundary.
      assetDeadline=Math.min(deadline,Date.now()+18000);
      cache[attemptsKey][key]=(cache[attemptsKey][key]||0)+1;save();
      let state;const expandedBefore=cache.nodes[key]?.expanded||0;
      try{state=await expandRoutes(token,quoteAsset,{state:cache.nodes[key],rootOnly,representative,maxNodes:representative?4:32,maxBranches:representative?1:4,maxSteps:2,save:state=>{cache.nodes[key]=state;save();}});}
      catch(error){if(error.code!=='market_budget')throw error;
        token.cashout_pending=true;retryPending=true;state=cache.nodes[key];
        if(!state)continue;
      }
      token.liquidation_routes=state.routes;token.liquidation_unknown_routes=state.unknown;
      if(representative&&!rootOnly&&(state.root_retry_pending||state.pending.length&&state.expanded===expandedBefore)&&Date.now()<assetDeadline){
        review.failures++;
        if(review.failures>=2){state.root_retry_pending=false;state.pending=[];state.unknown=[...new Set([...state.unknown,'Representative redemption unavailable after bounded attempts. Other routes remain unknown.'])];save();}
      }
      if(representative&&!rootOnly&&!state.pending.length&&!state.root_retry_pending){
        review.done=true;token.asset_review={scope:'representative_v1',status:representativeQuote(token)?'quoted':'unknown'};save();
      }
      if(state.pending.length||state.root_retry_pending){token.cashout_pending=true;retryPending=true;}else delete token.cashout_pending;
      progress();
    }
    progress(true);
    return {tokens,market_pending:retryPending};
  }catch(error){
    const pending=error.code==='market_budget';
    for(const token of tokens){const state=cache?.nodes?.[token.token_address.toLowerCase()+':'+token.token_type];
      if(restoreReviewed(token))continue;
      token.liquidation_routes=state?.routes||[];token.liquidation_unknown_routes=state?.unknown||[];
      if(pending&&(!state||state.pending.length||state.root_retry_pending))token.cashout_pending=true;
      if(!pending){token.liquidation_unknown_routes.push('Liquidation path reads unavailable or checkpoint mismatch.');if(representative)token.asset_review={scope:'representative_v1',status:'unknown'};}}
    if(pending)save();return {tokens,market_pending:pending};
  }finally{flush();}
}
async function scanNetworks(input,output,baseline=false,{maxBatches=4,maxRounds=Infinity,scan=scanChain}={}) {
  const results=new Map(),lastProgress=new Map(),stalls=new Map();
  let queue=input.networks;
  let rounds=0;
  while(queue.length&&rounds++<maxRounds) {
    const rows=await parallel(queue,2,n=>scan(input,n,output,baseline,{maxBatches}));
    const next=[];
    rows.forEach((row,i)=>{
      const n=queue[i];results.set(n.chain_id,row);
      if(baseline||!row.research_pending)return;
      const progress=JSON.stringify(row.work_progress),unchanged=lastProgress.get(n.chain_id)===progress;
      stalls.set(n.chain_id,unchanged?(stalls.get(n.chain_id)||0)+1:0);lastProgress.set(n.chain_id,progress);
      if(stalls.get(n.chain_id)>=3){row.continuation_stalled=true;row.status='partial';write(path.join(output,`chain-${n.chain_id}.json`),row);}
      else next.push(n);
    });
    queue=next;
  }
  return input.networks.map(n=>results.get(n.chain_id));
}
async function main() {
  const [mode,inputPath,outputPath]=process.argv.slice(2);
  const input=JSON.parse(fs.readFileSync(inputPath));
  if(!v.isAddress(input.wallet))throw new Error('Invalid wallet address');
  if(mode==='scan'||mode==='scan-slice'||mode==='baseline') {
    const rows=await scanNetworks(input,outputPath,mode==='baseline',{maxRounds:mode==='scan-slice'?1:Infinity});
    write(path.join(outputPath,'onchain-summary.json'),{wallet:input.wallet,observed_at:stamp(),chains:rows});
  }else if(mode==='dex') {
    const deadline=Date.now()+Math.min(180_000,Math.max(0,input.market_budget_ms??180_000));
    const result=await parallel(input.networks.filter(n=>input.tokens.some(t=>t.chain_id===n.chain_id)),2,async n=>{
      const group=input.tokens.filter(t=>t.chain_id===n.chain_id);
      if(input.market_scope==='representative_v1'&&n.environment!=='mainnet')return group;
      try{return await dexChain(n,group,{file:path.join(path.dirname(outputPath),`market-checkpoint-${n.chain_id}.json`),wallet:input.wallet,deadline,representative:input.market_scope==='representative_v1'});}catch(e){group.forEach(t=>t.dex_verification_error=h.safeError(e));return group;}
    });
    const tokens=result.flat(),pending=tokens.some(t=>t.market_pending||t.dex_discovery_status==='pending');
    write(outputPath,{wallet:input.wallet,observed_at:stamp(),tokens,market_pending:pending});
    // End outstanding timed-out HTTP handles after the durable result is saved.
    if(pending)process.exit(0);
  }else if(mode==='liquidate') {
    const deadline=Date.now()+Math.min(180_000,Math.max(0,input.market_budget_ms??180_000));
    const rows=await parallel(input.networks.filter(n=>input.tokens.some(t=>t.chain_id===n.chain_id)),2,n=>liquidationChain(n,input,outputPath,deadline));
    const pending=rows.some(row=>row.market_pending);
    write(outputPath,{wallet:input.wallet,observed_at:stamp(),tokens:rows.flatMap(row=>row.tokens),market_pending:pending});
    if(pending)process.exit(0);
  }else if(mode==='reserves') {
    const deadline=Date.now()+Math.min(180_000,Math.max(0,input.market_budget_ms??180_000));
    const result=await parallel(input.networks.filter(n=>input.tokens.some(t=>t.chain_id===n.chain_id&&t.mintclub)),2,n=>reserveChain(n,input,outputPath,deadline));
    const pending=result.some(r=>r.market_pending);
    write(outputPath,{wallet:input.wallet,observed_at:stamp(),tokens:result.flatMap(r=>r.tokens),market_pending:pending});
    if(pending)process.exit(0);
  }else throw new Error('Expected scan or dex mode');
}
if(require.main===module)main().catch(e=>{console.error(h.serialize(h.safeError(e)));process.exitCode=1;});
module.exports={scanNetworks,parallel,calls,registry,connect,scanChain,batches,balanceReads,factReads,mintclubMembership,dexChain,reserveChain,liquidationChain,routePools,boundedMarket,MarketBudget};
