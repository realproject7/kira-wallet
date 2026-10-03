// Read-only wallet analysis. Credentials stay in the RPC helper process.
const fs = require('fs');
const path = require('path');
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
const emitChain = row => console.log(JSON.stringify({stage:'chain',chain_id:row.chain_id,status:row.status,endpoint_index:row.endpoint_index,
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
  const choices=h.endpoints(n.chain_id).map(url=>()=>h.client(n.chain_id,url));
  let error;
  for (const [index,create] of choices.entries()) {
    try {const c = create(); if (await c.getChainId() !== n.chain_id) throw new Error('RPC chain identity mismatch'); endpointIdentity.set(c,index);return c;}
    catch (e) {error = e;}
  }
  throw error || new Error('No RPC endpoint configured; public fallback is disabled.');
}
async function calls(c, contracts, block) {
  if (!contracts.length) return [];
  try {
    return await c.multicall({contracts,blockNumber:block,batchSize:0,multicallAddress:MULTICALL});
  } catch (e) {
    if (['HttpRequestError','TimeoutError'].includes(e.name)) return contracts.map(()=>({status:'failure',error:e}));
    if (contracts.length > 1) {
      const mid = Math.ceil(contracts.length/2);
      return [...await calls(c,contracts.slice(0,mid),block), ...await calls(c,contracts.slice(mid),block)];
    }
    try {return [{status:'success',result:await c.readContract({...contracts[0],blockNumber:block})}];}
    catch (inner) {return [{status:'failure',error:inner}];}
  }
}
async function batches(c, contracts, block, size=100) {
  const plans = [];
  for (let i=0; i<contracts.length; i+=size) plans.push(contracts.slice(i,i+size));
  return (await parallel(plans,3,b => calls(c,b,block))).flat();
}
async function registry(c, n, block) {
  const count = Number(await c.readContract({address:n.mintclub_bond_address,abi:h.bondAbi,functionName:'tokenCount',blockNumber:block}));
  const cacheFile = path.join(h.root,'cache/mintclub-registry',`${n.chain_id}-${n.mintclub_bond_address.toLowerCase()}.json`);
  let entries = [], cacheReused = 0;
  if (fs.existsSync(cacheFile)) {
    const cache = JSON.parse(fs.readFileSync(cacheFile));
    if (cache.chain_id === n.chain_id && cache.bond_address.toLowerCase() === n.mintclub_bond_address.toLowerCase() && cache.entries.length <= count) {
      const old = cache.entries;
      const checks = old.length ? await calls(c,[0,old.length-1].map(i => ({address:n.mintclub_bond_address,abi:h.bondAbi,functionName:'tokens',args:[BigInt(i)]})),block) : [];
      if (!old.length || checks.every((r,i) => r.status==='success' && r.result.toLowerCase()===old[i ? old.length-1 : 0].address.toLowerCase())) {
        entries = old; cacheReused = old.length;
      }
    }
  }
  const start = entries.length;
  const addresses = await batches(c,Array.from({length:count-start},(_,i) => ({address:n.mintclub_bond_address,abi:h.bondAbi,functionName:'tokens',args:[BigInt(start+i)]})),block);
  const additions = addresses.map((r,i) => ({index:start+i,address:r.status==='success'?r.result:null,error:r.status==='success'?null:h.safeError(r.error)}));
  const valid = additions.filter(t => t.address);
  const decimals = await batches(c,valid.map(t => ({address:t.address,abi:erc20,functionName:'decimals'})),block);
  valid.forEach((t,i) => {
    const r = decimals[i];
    t.decimals = r.status==='success'?r.result:null;
    // The official Mint Club clones have fixed ERC20 decimals 18 or ERC1155 decimals 0.
    t.token_type = t.decimals===18?'ERC20':t.decimals===0?'ERC1155':'unknown';
    if (t.token_type==='unknown') t.error = r.status==='failure'?h.safeError(r.error):{message:'Unexpected Mint Club decimals'};
  });
  entries = [...entries,...additions];
  if (entries.every(t => t.address && t.token_type!=='unknown' && !t.error)) {
    write(cacheFile,{chain_id:n.chain_id,bond_address:n.mintclub_bond_address,observed_at:stamp(),block_number:block,entries});
  }
  return {count,entries,cache_reused:cacheReused,errors:entries.filter(t => t.error || !t.address).length};
}
async function scanChain(input, n, output) {
  const file = path.join(output,`chain-${n.chain_id}.json`);
  // A resumed run retains its fixed-block completed evidence, never wallet-independent balances.
  if (fs.existsSync(file)) {
    const previous = JSON.parse(fs.readFileSync(file));
    if (previous.wallet.toLowerCase()===input.wallet.toLowerCase() && previous.status==='complete') {emitChain(previous);return previous;}
  }
  const row = {wallet:input.wallet,chain_id:n.chain_id,network:n.network,observed_at:stamp(),status:'unavailable',tokens:[],native_balance:null};
  try {
    const c = await connect(n), block = await c.getBlockNumber();
    row.endpoint_index=endpointIdentity.get(c);
    row.block_number = block;
    row.native_balance = v.formatUnits(await c.getBalance({address:input.wallet,blockNumber:block}),18);
    row.rpc_status = 'available';
    let reg;
    try {reg = await registry(c,n,block);} catch (e) {row.registry_error = h.safeError(e); reg = {count:null,entries:[],errors:1,cache_reused:0};}
    const plans = new Map();
    for (const t of input.candidates.filter(t => t.chain_id===n.chain_id)) plans.set(t.address.toLowerCase(), {...t,token_type:'ERC20'});
    for (const t of reg.entries.filter(t => t.address && t.token_type && t.token_type!=='unknown')) {
      plans.set(t.address.toLowerCase(),{...plans.get(t.address.toLowerCase()),...t,registered_mintclub:true});
    }
    const tokens = [...plans.values()];
    const balances = await batches(c,tokens.map(t => ({address:t.address,abi:t.token_type==='ERC1155'?erc1155:erc20,functionName:'balanceOf',args:t.token_type==='ERC1155'?[input.wallet,0n]:[input.wallet]})),block);
    const errors = []; let checked = 0, erc20Checked = 0, erc1155Checked = 0;
    const held = [];
    tokens.forEach((t,i) => {
      const r = balances[i];
      if (r.status==='failure') {errors.push({address:t.address,registered_mintclub:!!t.registered_mintclub,error:h.safeError(r.error)}); return;}
      if (t.registered_mintclub) {checked++; if(t.token_type==='ERC20')erc20Checked++;else erc1155Checked++;}
      if (r.result>0n) held.push({...t,balance_raw:r.result});
    });
    row.registry_scan = {registry_count:reg.count,registry_errors:reg.errors,checked,erc20_checked:erc20Checked,erc1155_checked:erc1155Checked,
      cache_reused:reg.cache_reused,balance_errors:errors.filter(t=>t.registered_mintclub).length,
      positive_balances:held.filter(t=>t.registered_mintclub).length,block_number:block,complete:reg.errors===0 && checked===reg.count,
      source:'On-chain Mint Club bond tokenCount()/tokens(index), then direct wallet balance calls',bond_address:n.mintclub_bond_address};
    row.balance_errors = errors;
    for (const t of held) {
      const item = {chain_id:n.chain_id,network:n.network,token_address:t.address,token_type:t.token_type,token_id:t.token_type==='ERC1155'?'0':null,
        wallet_balance_raw:t.balance_raw,balance_block_number:block,balance_observed_at:stamp(),indexer_price_references:t.prices||[],mintclub:null,dex_pools:[]};
      const meta = await calls(c,['decimals','symbol','name'].map(functionName=>({address:t.address,abi:erc20,functionName})),block);
      item.decimals = meta[0].status==='success'?meta[0].result:t.decimals;
      item.symbol = meta[1].status==='success'?meta[1].result:t.symbol||t.address.slice(0,10);
      item.name = meta[2].status==='success'?meta[2].result:t.name||item.symbol;
      item.wallet_balance = Number.isInteger(item.decimals)?v.formatUnits(t.balance_raw,item.decimals):null;
      if (item.wallet_balance===null) item.metadata_error = 'Token decimals unavailable; quantity remains unknown.';
      if (t.registered_mintclub) {
        try {
          const detail = await c.readContract({address:n.mintclub_bond_address,abi:h.bondAbi,functionName:'getDetail',args:[t.address],blockNumber:block});
          const info = detail.info;
          let refund=null,quoteError=null;
          try {refund = await c.readContract({address:n.mintclub_bond_address,abi:h.bondAbi,functionName:'getRefundForTokens',args:[t.address,t.balance_raw],blockNumber:block});}
          catch(e){quoteError=h.safeError(e);}
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
    row.observed_at=stamp();
  } catch(e) {row.error=h.safeError(e);}
  write(file,row);
  emitChain(row);
  return row;
}
function deployment(chain,protocol,name) {
  return deployments.find(r=>r.chainId===chain && r.protocol===protocol && r.contract.toLowerCase()===name.toLowerCase())?.address;
}
async function dexChain(n, tokens) {
  const c=await connect(n),block=await c.getBlockNumber();
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
    const found=await batches(c,queries.map(q=>q.call),block,60);
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
  for(const t of tokens) for(const p of t.dex_pools) {
    if(!['uniswap','aerodrome'].includes(p.venue))continue;
    try {
      if(p.pool.length===66) {
        const sv=deployment(n.chain_id,'v4','StateView');
        if(!sv){p.rpc_verification={verification:'official_state_view_unavailable'};continue;}
        const r=await calls(c,['getSlot0','getLiquidity'].map(functionName=>({address:sv,abi:poolAbi,functionName,args:[p.pool]})),block);
        p.rpc_verification={verification:r[0].status==='success'&&r[0].result[0]>0n?'initialized_at_official_v4_state_view':'unverified',block_number:block,observed_at:stamp(),state_view:sv};
        if(r[1].status==='success')p.factory_measurement={active_liquidity_verified:r[1].result>0n,state:{liquidity:r[1].result}};
        continue;
      }
      const names=['factory','token0','token1',p.version_labels?.includes('v3')?'liquidity':'getReserves'];
      const r=await calls(c,names.map(functionName=>({address:p.pool,abi:poolAbi,functionName})),block);
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
        if(q.every(x=>x.status==='success')) Object.assign(p.factory_measurement,{quote_token:quote,quote_symbol:q[2].result,quote_balance:v.formatUnits(q[0].result,q[1].result)});
      }
    }catch(e){p.rpc_verification={verification:'unverified',error:h.safeError(e)};}
  }
  return tokens;
}
async function main() {
  const [mode,inputPath,outputPath]=process.argv.slice(2);
  const input=JSON.parse(fs.readFileSync(inputPath));
  if(!v.isAddress(input.wallet))throw new Error('Invalid wallet address');
  if(mode==='scan') {
    const rows=await parallel(input.networks,4,n=>scanChain(input,n,outputPath));
    write(path.join(outputPath,'onchain-summary.json'),{wallet:input.wallet,observed_at:stamp(),chains:rows});
  }else if(mode==='dex') {
    const result=await parallel(input.networks.filter(n=>input.tokens.some(t=>t.chain_id===n.chain_id)),4,async n=>{
      const group=input.tokens.filter(t=>t.chain_id===n.chain_id);
      try{return await dexChain(n,group);}catch(e){group.forEach(t=>t.dex_verification_error=h.safeError(e));return group;}
    });
    write(outputPath,{wallet:input.wallet,observed_at:stamp(),tokens:result.flat()});
  }else if(mode==='reserves') {
    const result=await parallel(input.networks.filter(n=>input.tokens.some(t=>t.chain_id===n.chain_id&&t.mintclub)),4,async n=>{
      const rows=[];
      try {
        const c=await connect(n),block=await c.getBlockNumber();
        const queue=input.tokens.filter(t=>t.chain_id===n.chain_id&&t.mintclub).map(t=>t.token_address),seen=new Set();
        for(let i=0;i<queue.length;i++) {
          const address=queue[i],key=address.toLowerCase();
          if(seen.has(key))continue;seen.add(key);
          if(seen.size>128){rows.push({chain_id:n.chain_id,error:{message:'Reserve graph traversal limit reached'}});break;}
          try {
            const exists=await c.readContract({address:n.mintclub_bond_address,abi:h.bondAbi,functionName:'exists',args:[address],blockNumber:block});
            if(!exists){rows.push({chain_id:n.chain_id,address,is_curve:false,block_number:block,observed_at:stamp()});continue;}
            const d=await c.readContract({address:n.mintclub_bond_address,abi:h.bondAbi,functionName:'getDetail',args:[address],blockNumber:block});
            const info=d.info;
            rows.push({chain_id:n.chain_id,address,is_curve:true,symbol:info.symbol,price_in_reserve:v.formatUnits(info.priceForNextMint,info.reserveDecimals),
              reserve_token:info.reserveToken,reserve_symbol:info.reserveSymbol,curve_reserve:v.formatUnits(info.reserveBalance,info.reserveDecimals),
              funded:info.reserveBalance>0n,block_number:block,observed_at:stamp(),source:`https://mint.club/token/${n.network}/${address}`});
            queue.push(info.reserveToken);
          }catch(e){rows.push({chain_id:n.chain_id,address,error:h.safeError(e),block_number:block,observed_at:stamp()});}
        }
      }catch(e){rows.push({chain_id:n.chain_id,error:h.safeError(e)});}
      return rows;
    });
    write(outputPath,{wallet:input.wallet,observed_at:stamp(),tokens:result.flat()});
  }else throw new Error('Expected scan or dex mode');
}
if(require.main===module)main().catch(e=>{console.error(h.serialize(h.safeError(e)));process.exitCode=1;});
module.exports={parallel,calls,registry,connect};
