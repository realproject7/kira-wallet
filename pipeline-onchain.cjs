// Read-only wallet analysis. Credentials stay in the RPC helper process.
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');
const h = require('./onchain.cjs');
const v = h.viem;
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
  fs.writeFileSync(file + '.tmp', h.serialize(data) + '\n');
  fs.renameSync(file + '.tmp', file);
};
async function parallel(items, workers, fn) {
  const results = new Array(items.length); let next = 0;
  await Promise.all(Array.from({length:Math.min(workers, items.length)}, async () => {
    for (;;) {const i = next++; if (i >= items.length) return; results[i] = await fn(items[i], i);}
  }));
  return results;
}
async function connect(n) {
  if(!h.endpoints(n.chain_id).length)throw new Error('No RPC endpoint configured; public fallback is disabled.');
  const c=h.client(n.chain_id);
  if(await c.getChainId()!==n.chain_id)throw new Error('RPC chain identity mismatch');
  endpointIdentity.set(c,h.rpcEndpointsUsed(c)[0]??0);return c;
}
function rpcFailure(error) {
  let sizeLimit=false,transportFailure=false;
  for(let cause=error,depth=0;cause&&depth<10;cause=cause.cause,depth++) {
    if(['HttpRequestError','TimeoutError'].includes(cause.name))transportFailure=true;
    if(cause.status===413||/\b(batch|payload|response|request body)\b.*\b(large|size|limit|exceed)/i.test(cause.shortMessage||cause.message||'')||/gas.*(cap|limit).*exceed|exceed.*gas.*(cap|limit)/i.test(cause.shortMessage||cause.message||''))sizeLimit=true;
    if(cause.status===429)return {sizeLimit:false,transportFailure:true};
  }
  return {sizeLimit,transportFailure};
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
async function balanceReads(c,tokens,wallet,block,checkpoint,file,n) {
  checkpoint.balance_times=checkpoint.balance_times||{};
  const key=t=>t.address.toLowerCase()+':'+t.token_type;
  const pending=tokens.filter(t=>checkpoint.balances[key(t)]===undefined);
  let checked=tokens.length-pending.length;
  emitProgress(n,'balances',checked,tokens.length);
  const failures=new Map();
  for(let start=0;start<pending.length;start+=128) {
    const plan=pending.slice(start,start+128);
    const rows=await calls(c,plan.map(t=>({address:t.address,abi:t.token_type==='ERC1155'?erc1155:erc20,
      functionName:'balanceOf',args:t.token_type==='ERC1155'?[wallet,0n]:[wallet]})),block);
    rows.forEach((r,i)=>{if(r.status==='success'){checkpoint.balances[key(plan[i])]=r.result.toString();checkpoint.balance_times[key(plan[i])]=stamp();}else failures.set(key(plan[i]),r);});
    write(file,checkpoint);checked+=plan.length;emitProgress(n,'balances',checked,tokens.length);
  }
  return tokens.map(t=>checkpoint.balances[key(t)]!==undefined?{status:'success',result:BigInt(checkpoint.balances[key(t)]),observed_at:checkpoint.balance_times[key(t)]||checkpoint.observed_at}:failures.get(key(t)));
}
async function registry(c, n, block) {
  const count = Number(await c.readContract({address:n.mintclub_bond_address,abi:h.bondAbi,functionName:'tokenCount',blockNumber:block}));
  const cacheFile = path.join(h.root,'cache/mintclub-registry',`${n.chain_id}-${n.mintclub_bond_address.toLowerCase()}.json`);
  let entries = [], cacheReused = 0;
  if (fs.existsSync(cacheFile)) {
    const cache = JSON.parse(fs.readFileSync(cacheFile));
    if (cache.chain_id === n.chain_id && typeof cache.bond_address==='string' && cache.bond_address.toLowerCase() === n.mintclub_bond_address.toLowerCase() && Array.isArray(cache.entries) && cache.entries.length <= count && cache.entries.every((t,i)=>t&&t.index===i&&v.isAddress(t.address)&&[0,18].includes(t.decimals)&&['ERC20','ERC1155'].includes(t.token_type))) {
      const old = cache.entries;
      const checks = old.length ? await calls(c,[0,old.length-1].map(i => ({address:n.mintclub_bond_address,abi:h.bondAbi,functionName:'tokens',args:[BigInt(i)]})),block) : [];
      if (!old.length || checks.every((r,i) => r.status==='success' && r.result.toLowerCase()===old[i ? old.length-1 : 0].address.toLowerCase())) {
        entries = old; cacheReused = old.length;
      }
    }
  }
  for(let start=entries.length;start<count;start+=128) {
    const length=Math.min(128,count-start);
    const addresses=await calls(c,Array.from({length},(_,i)=>({address:n.mintclub_bond_address,abi:h.bondAbi,functionName:'tokens',args:[BigInt(start+i)]})),block);
    const additions=addresses.map((r,i)=>({index:start+i,address:r.status==='success'?r.result:null,error:r.status==='success'?null:h.safeError(r.error)}));
    const valid=additions.filter(t=>t.address);
    const decimals=await calls(c,valid.map(t=>({address:t.address,abi:erc20,functionName:'decimals'})),block);
    valid.forEach((t,i)=>{const r=decimals[i];t.decimals=r.status==='success'?r.result:null;t.token_type=t.decimals===18?'ERC20':t.decimals===0?'ERC1155':'unknown';if(t.token_type==='unknown')t.error=r.status==='failure'?h.safeError(r.error):{message:'Unexpected Mint Club decimals'};});
    const failed=additions.some(t=>!t.address||t.error);
    entries.push(...additions);
    // Persist each verified identity prefix. No quantities or wallet-specific data.
    if(!failed)write(cacheFile,{chain_id:n.chain_id,bond_address:n.mintclub_bond_address,observed_at:stamp(),block_number:block,entries});
    emitProgress(n,'registry',entries.length,count);
    if(failed)break;
  }

  return {count,entries,cache_reused:cacheReused,errors:entries.filter(t => t.error || !t.address).length+(entries.length<count?1:0)};
}
async function scanChain(input, n, output, baseline=false) {
  const file = path.join(output,`${baseline?'baseline-':''}chain-${n.chain_id}.json`);
  const candidates=input.candidates.filter(t=>t.chain_id===n.chain_id).map(t=>t.address.toLowerCase()).sort();
  const fingerprint=crypto.createHash('sha256').update(h.serialize([n.mintclub_bond_address,candidates])).digest('hex');
  // A resumed run retains its fixed-block completed evidence, never wallet-independent balances.
  if (fs.existsSync(file)) {
    const previous = JSON.parse(fs.readFileSync(file));
    if (previous.wallet.toLowerCase()===input.wallet.toLowerCase() && previous.candidate_fingerprint===fingerprint && (previous.status==='complete'||baseline&&previous.phase==='baseline')) {emitChain(previous);return previous;}
  }
  const row = {wallet:input.wallet,chain_id:n.chain_id,network:n.network,phase:baseline?'baseline':'enrichment',observed_at:stamp(),status:'unavailable',tokens:[],native_balance:null};
  emitProgress(n,'balances',0,null);
  let rpcClient;
  try {
    const checkpointFile=path.join(output,`${baseline?'baseline-':''}balance-checkpoint-${n.chain_id}.json`);
    let checkpoint=fs.existsSync(checkpointFile)?JSON.parse(fs.readFileSync(checkpointFile)):null;
    if(checkpoint&&(checkpoint.wallet!==input.wallet.toLowerCase()||checkpoint.chain_id!==n.chain_id||checkpoint.fingerprint!==fingerprint&&(!checkpoint.candidates||checkpoint.candidates.some(a=>!candidates.includes(a)))))
      throw new Error('Saved balance checkpoint does not match this research request. Start a new holdings analysis.');
    const c = await connect(n), snapshot = await h.snapshotBlock(c,checkpoint),block=snapshot.number;rpcClient=c;
    checkpoint=checkpoint||{wallet:input.wallet.toLowerCase(),chain_id:n.chain_id,block_number:block.toString(),block_hash:snapshot.hash,observed_at:stamp(),balances:{}};
    checkpoint.fingerprint=fingerprint;checkpoint.candidates=candidates;row.candidate_fingerprint=fingerprint;
    row.preferred_endpoint_index=endpointIdentity.get(c);
    row.block_number = block;
    row.block_hash = snapshot.hash;
    if(checkpoint.native_balance===undefined)checkpoint.native_balance=v.formatUnits(await c.getBalance({address:input.wallet,blockNumber:block}),18);
    row.native_balance=checkpoint.native_balance;row.observed_at=checkpoint.observed_at;write(checkpointFile,checkpoint);
    row.rpc_status = 'available';
    // Check discovered and built-in candidates before expensive cold registry work.
    const initial=new Map(input.candidates.filter(t=>t.chain_id===n.chain_id).map(t=>[t.address.toLowerCase(),{...t,token_type:'ERC20'}]));
    const allCandidates=[...initial.values()];
    const initialTokens=baseline?allCandidates.slice(0,128):allCandidates;
    if(baseline){initial.clear();for(const t of initialTokens)initial.set(t.address.toLowerCase(),t);}
    const initialBalances=await balanceReads(c,initialTokens,input.wallet,block,checkpoint,checkpointFile,n);
    const firstReads=new Map(initialTokens.map((t,i)=>[t.address.toLowerCase(),initialBalances[i]]));
    let reg;
    try {reg = baseline?{count:null,entries:[],errors:0,cache_reused:0}:await registry(c,n,block);} catch (e) {row.registry_error = h.safeError(e); reg = {count:null,entries:[],errors:1,cache_reused:0};}
    const plans = new Map();
    for (const [key,t] of initial) plans.set(key,t);
    for (const t of reg.entries.filter(t => t.address && t.token_type && t.token_type!=='unknown')) {
      plans.set(t.address.toLowerCase(),{...plans.get(t.address.toLowerCase()),...t,registered_mintclub:true});
    }
    const tokens = [...plans.values()];
    const remaining=tokens.filter(t=>!firstReads.has(t.address.toLowerCase())||t.token_type==='ERC1155');
    if(remaining.length)emitProgress(n,'balances',0,remaining.length);
    const later=await balanceReads(c,remaining,input.wallet,block,checkpoint,checkpointFile,n);
    remaining.forEach((t,i)=>firstReads.set(t.address.toLowerCase(),later[i]));
    const balances=tokens.map(t=>firstReads.get(t.address.toLowerCase()));
    const errors = []; let checked = 0, erc20Checked = 0, erc1155Checked = 0;
    const held = [];
    tokens.forEach((t,i) => {
      const r = balances[i];
      if (r.status==='failure') {errors.push({address:t.address,registered_mintclub:!!t.registered_mintclub,error:h.safeError(r.error)}); return;}
      if (t.registered_mintclub) {checked++; if(t.token_type==='ERC20')erc20Checked++;else erc1155Checked++;}
      if (r.result>0n) held.push({...t,balance_raw:r.result});
    });
    row.candidate_scan={total:allCandidates.length,deferred:allCandidates.length-initialTokens.length,checked:initialBalances.filter(r=>r.status==='success').length,complete:initialTokens.length===allCandidates.length&&initialBalances.every(r=>r.status==='success')};
    if(baseline&&held.length){
      const exists=await batches(c,held.map(t=>({address:n.mintclub_bond_address,abi:h.bondAbi,functionName:'exists',args:[t.address]})),block);
      held.forEach((t,i)=>{t.registered_mintclub=exists[i].status==='success'&&exists[i].result===true;});
    }
    const metadata=await batches(c,held.flatMap(t=>['decimals','symbol','name'].map(functionName=>({address:t.address,abi:erc20,functionName}))),block,128,(checked,total)=>emitProgress(n,'metadata',checked,total));
    const curves=held.filter(t=>t.registered_mintclub);
    const details=await batches(c,curves.map(t=>({address:n.mintclub_bond_address,abi:h.bondAbi,functionName:'getDetail',args:[t.address]})),block,128,(checked)=>emitProgress(n,'curves',checked,curves.length*2));
    const refunds=await batches(c,curves.map(t=>({address:n.mintclub_bond_address,abi:h.bondAbi,functionName:'getRefundForTokens',args:[t.address,t.balance_raw]})),block,128,(checked)=>emitProgress(n,'curves',curves.length+checked,curves.length*2));
    const curveRows=new Map(curves.map((t,i)=>[t.address.toLowerCase(),{detail:details[i],refund:refunds[i]}]));
    row.registry_scan = {registry_count:reg.count,registry_errors:reg.errors,checked,erc20_checked:erc20Checked,erc1155_checked:erc1155Checked,
      cache_reused:reg.cache_reused,balance_errors:errors.filter(t=>t.registered_mintclub).length,
      positive_balances:held.filter(t=>t.registered_mintclub).length,block_number:block,complete:!baseline && reg.errors===0 && checked===reg.count,phase:baseline?'deferred':'checked',
      source:'On-chain Mint Club bond tokenCount()/tokens(index), then direct wallet balance calls',bond_address:n.mintclub_bond_address};
    row.registry_scan.error_examples=reg.entries.filter(t=>t.error||!t.address).slice(0,5).map(t=>({index:t.index,error:t.error||{message:'Registry address unavailable'}}));
    row.balance_errors = errors;
    for (const [heldIndex,t] of held.entries()) {
      const item = {chain_id:n.chain_id,network:n.network,token_address:t.address,token_type:t.token_type,token_id:t.token_type==='ERC1155'?'0':null,
        wallet_balance_raw:t.balance_raw,balance_block_number:block,balance_observed_at:firstReads.get(t.address.toLowerCase())?.observed_at||checkpoint.observed_at,indexer_price_references:t.prices||[],mintclub:null,dex_pools:[]};
      const meta=metadata.slice(heldIndex*3,heldIndex*3+3);
      item.decimals = meta[0].status==='success'?meta[0].result:t.decimals;
      item.dex_liquidity_found=false;
      item.symbol = meta[1].status==='success'?meta[1].result:t.symbol||t.address.slice(0,10);
      item.name = meta[2].status==='success'?meta[2].result:t.name||item.symbol;
      item.wallet_balance = Number.isInteger(item.decimals)?v.formatUnits(t.balance_raw,item.decimals):null;
      if (item.wallet_balance===null) item.metadata_error = 'Token decimals unavailable; quantity remains unknown.';
      if (t.registered_mintclub) {
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
            wallet_full_burn_error:quoteError,block_number:block,observed_at:stamp(),source_url:`https://mint.club/token/${n.network}/${t.address}`};
        } catch(e) {item.mintclub_error=h.safeError(e);}
      }
      row.tokens.push(item);
    }
    row.status = row.registry_scan.complete && errors.length===0?'complete':'partial';
  } catch(e) {row.error=h.safeError(e);}
  row.rpc_endpoint_indices=h.rpcEndpointsUsed(rpcClient);
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
async function dexChain(n, tokens, {file,wallet,deadline=Date.now()+180_000}={}) {
  const fingerprint=crypto.createHash('sha256').update(h.serialize(tokens.map(t=>[t.chain_id,t.token_address.toLowerCase(),t.token_type,t.balance_block_number,t.wallet_balance_raw]))).digest('hex');
  let cache=file&&fs.existsSync(file)?JSON.parse(fs.readFileSync(file)):null;
  if(cache&&(cache.wallet!==wallet.toLowerCase()||cache.chain_id!==n.chain_id||cache.fingerprint!==fingerprint))
    throw new Error('Market checkpoint does not match this research request.');
  const save=()=>{if(file)write(file,cache);};
  try {
  if(Date.now()>=deadline)throw new MarketBudget();
  const client=await boundedMarket(connect(n),deadline),snapshot=await boundedMarket(h.snapshotBlock(client,cache),deadline),block=snapshot.number;
  cache=cache||{wallet:wallet.toLowerCase(),chain_id:n.chain_id,fingerprint,block_number:block.toString(),block_hash:snapshot.hash,requests:{},completed_pools:[],tokens:cacheEncode(tokens)};
  const saved=cacheDecode(cache.tokens);
  for(const token of tokens){
    const previous=saved.find(t=>t.token_address.toLowerCase()===token.token_address.toLowerCase());
    for(const pool of previous?.dex_pools||[]){
      const index=token.dex_pools.findIndex(p=>p.pool.toLowerCase()===pool.pool.toLowerCase());
      if(index<0)token.dex_pools.push(pool);else if(cache.completed_pools.includes(token.token_address.toLowerCase()+':'+pool.pool.toLowerCase()))token.dex_pools[index]=pool;
    }
  }
  const c=new Proxy(client,{get(target,name){
    if(!['multicall','readContract'].includes(name))return Reflect.get(target,name);
    return async args=>{
      const key=crypto.createHash('sha256').update(h.serialize({name,args})).digest('hex');
      if(cache.requests[key])return cacheDecode(cache.requests[key]);
      if(Date.now()>=deadline)throw new MarketBudget();
      const result=await boundedMarket(target[name](args),deadline);
      const safe=name==='multicall'?result.map(r=>r.status==='success'?{status:'success',result:r.result}:{status:'failure',error:h.safeError(r.error)}):result;
      if(name!=='multicall'||safe.every(r=>r.status==='success')){cache.requests[key]=cacheEncode(safe);save();}
      return result;
    };
  }});
  // Supplement DEX indexer discovery on Base with the canonical WETH/USDC factories.
  if (n.chain_id===8453) {
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
    const found=await batches(c,queries.map(q=>q.call),block,60,(checked,total)=>emitProgress(n,'markets',checked,total));
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
  const poolTotal=tokens.reduce((sum,t)=>sum+t.dex_pools.filter(p=>['uniswap','aerodrome'].includes(p.venue)).length,0);
  let poolChecked=0;emitProgress(n,'markets',0,poolTotal);
  for(const t of tokens) for(const p of t.dex_pools) {
    if(!['uniswap','aerodrome'].includes(p.venue))continue;
    const identity=t.token_address.toLowerCase()+':'+p.pool.toLowerCase();
    if(cache.completed_pools.includes(identity)){emitProgress(n,'markets',++poolChecked,poolTotal);continue;}
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
          const fee=await c.readContract({address:p.pool,abi:v.parseAbi(['function fee() view returns (uint24)']),functionName:'fee',blockNumber:block});
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
        if(q.every(x=>x.status==='success')) Object.assign(p.factory_measurement,{quote_token:quote,quote_symbol:q[2].result,quote_balance:v.formatUnits(q[0].result,q[1].result)});
      }
    }catch(e){if(e.code==='market_budget'){paused=true;throw e;}retry=true;p.rpc_verification={verification:'unverified',error:h.safeError(e)};}
    finally{
      // Budget pauses retain successful RPC prefixes, but do not mark an
      // unfinished pool as verified or as a provider failure.
      if(!paused&&Date.now()<deadline){if(!retry)cache.completed_pools.push(identity);poolChecked++;}
      if(retry)p.rpc_verification={...p.rpc_verification,error:{message:'Some pool reads failed. Remaining price and execution details are unknown.'}};
      cache.tokens=cacheEncode(tokens);save();emitProgress(n,'markets',poolChecked,poolTotal);
    }
  }
  if(Date.now()>=deadline)throw new MarketBudget();
  tokens.forEach(t=>{delete t.market_pending;if(t.dex_pools.some(p=>p.rpc_verification?.error)||t.factory_discovery?.errors)t.dex_verification_error={message:'Some market reads failed. Missing pool and price evidence remains unknown.'};else delete t.dex_verification_error;});cache.tokens=cacheEncode(tokens);save();
  return tokens;
  }catch(e){
    if(e.code!=='market_budget')throw e;
    tokens.forEach(t=>t.market_pending=true);
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
          funded:info.reserveBalance>0n,block_number:block,observed_at:stamp(),source:`https://mint.club/token/${n.network}/${address}`});
        queue.push(info.reserveToken);
        cache.nodes[key]=cacheEncode(rows.at(-1));save();emitProgress(n,'reserves',rows.length,queue.length);
      }catch(e){if(e.code==='market_budget')throw e;rows.push({chain_id:n.chain_id,address,error:h.safeError(e),block_number:block,observed_at:stamp()});emitProgress(n,'reserves',rows.length,queue.length);}
    }
  }catch(e){if(e.code==='market_budget'){save();return {tokens:rows,market_pending:true};}rows.push({chain_id:n.chain_id,error:h.safeError(e)});}
  return {tokens:rows,market_pending:false};
}
async function main() {
  const [mode,inputPath,outputPath]=process.argv.slice(2);
  const input=JSON.parse(fs.readFileSync(inputPath));
  if(!v.isAddress(input.wallet))throw new Error('Invalid wallet address');
  if(mode==='scan'||mode==='baseline') {
    const rows=await parallel(input.networks,2,n=>scanChain(input,n,outputPath,mode==='baseline'));
    write(path.join(outputPath,'onchain-summary.json'),{wallet:input.wallet,observed_at:stamp(),chains:rows});
  }else if(mode==='dex') {
    const deadline=Date.now()+Math.min(180_000,Math.max(0,input.market_budget_ms??180_000));
    const result=await parallel(input.networks.filter(n=>input.tokens.some(t=>t.chain_id===n.chain_id)),2,async n=>{
      const group=input.tokens.filter(t=>t.chain_id===n.chain_id);
      try{return await dexChain(n,group,{file:path.join(path.dirname(outputPath),`market-checkpoint-${n.chain_id}.json`),wallet:input.wallet,deadline});}catch(e){group.forEach(t=>t.dex_verification_error=h.safeError(e));return group;}
    });
    const tokens=result.flat(),pending=tokens.some(t=>t.market_pending||t.dex_discovery_status==='pending');
    write(outputPath,{wallet:input.wallet,observed_at:stamp(),tokens,market_pending:pending});
    // End outstanding timed-out HTTP handles after the durable result is saved.
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
module.exports={parallel,calls,registry,connect,scanChain,batches,balanceReads,dexChain,reserveChain,boundedMarket,MarketBudget};
