'use strict';
// Explicit, bounded, read-only position collection. No signer or transaction API.
const fs=require('node:fs'),path=require('node:path'),v=require('viem');
const math=require('./position-math.cjs'),protocols=require('./sources/position-protocols.json');
const uni=require('./sources/uniswap-deployments.json').records,stakeAbi=require('./sources/position-staking-abi.json');
const sugarAbi=require('./sources/position-sugar-abi.json');
const BATCH=32,NFT_BATCH=8,MAX_TASKS=50000,MAX_POSITIONS=5000,ZERO=v.zeroAddress;
const abi=v.parseAbi([
 'function balanceOf(address) view returns(uint256)','function balanceOf(address,uint256) view returns(uint256)',
 'function decimals() view returns(uint8)','function symbol() view returns(string)','function factory() view returns(address)',
 'function totalSupply() view returns(uint256)','function token0() view returns(address)','function token1() view returns(address)',
 'function getReserves() view returns(uint256,uint256,uint256)','function stable() view returns(bool)',
 'function getPair(address,address) view returns(address)','function getPool(address,address,bool) view returns(address)',
 'function getPool(address,address) view returns(address)',
 'function getPool(address,address,uint24) view returns(address)',
 'function slot0() view returns(uint160,int24,uint16,uint16,uint16,uint32,bool)',
 'function ownerOf(uint256) view returns(address)','function tokenOfOwnerByIndex(address,uint256) view returns(uint256)',
 'function allPoolsLength() view returns(uint256)','function allPools(uint256) view returns(address)',
 'function poolsIndexLength() view returns(uint256)',
 'struct PoolData { address pool; uint48 creationTimestamp; }',
 'function poolsIndexPaginated(uint256,uint256) view returns(PoolData[])',
 'function gauges(address) view returns(address)','function gauge() view returns(address)',
 'function stakedValues(address) view returns(uint256[])','function stakedContains(address,uint256) view returns(bool)',
 'function deposits(uint256) view returns(address,uint48,int24,int24)',
 'function isVault(address) view returns(bool)','function target() view returns(address)','function counter() view returns(address)',
 'function claimForShares(uint256) view returns(uint256,uint256)',
 'function navPerNFT() view returns(uint256)','function quoteBurn(uint256) view returns(uint256)',
 'function poolLength() view returns(uint256)','function lpToken(uint256) view returns(address)',
 'function userInfo(uint256,address) view returns(uint256,uint256)',
 'function userPositionInfos(uint256) view returns(uint128,uint128,int24,int24,uint256,uint256,address,uint256,uint256)',
 'function getPositionLiquidity(uint256) view returns(uint128)',
 'function getPoolAndPositionInfo(uint256) view returns((address currency0,address currency1,uint24 fee,int24 tickSpacing,address hooks),uint256)',
 'function getSlot0(bytes32) view returns(uint160,int24,uint24,uint24)'
]);
const nftAbi=v.parseAbi(['function positions(uint256) view returns(uint96,address,address,address,uint24,int24,int24,uint128,uint256,uint256,uint128,uint128)']);
const clAbi=v.parseAbi(['function positions(uint256) view returns(uint96,address,address,address,int24,int24,int24,uint128,uint256,uint256,uint128,uint128)']);
const key=x=>String(x).toLowerCase(),valid=a=>typeof a==='string'&&/^0x[0-9a-f]{40}$/i.test(a),stamp=()=>new Date().toISOString();
const chunks=(rows,n)=>Array.from({length:Math.ceil(rows.length/n)},(_,i)=>rows.slice(i*n,(i+1)*n));
const spec=(address,functionName,args=[],custom=abi)=>({address:key(address),abi:custom,functionName,args});
const deployment=(cid,protocol,contract)=>uni.find(r=>r.chainId===cid&&r.protocol===protocol&&r.contract===contract&&r.env==='mainnet'&&r.status==='active');
function managers(cid){
 const rows=[];
 const v3=deployment(cid,'v3','NonfungiblePositionManager'),factory=deployment(cid,'v3','UniswapV3Factory');
 if(v3&&factory)rows.push({platform:'uniswap',version:'v3',manager:v3.address,factory:factory.address,type:'v3',staker:deployment(cid,'v3','UniswapV3Staker')?.address});
 const v4=deployment(cid,'v4','PositionManager'),view=deployment(cid,'v4','StateView');
 if(v4&&view)rows.push({platform:'uniswap',version:'v4',manager:v4.address,view:view.address,type:'v4'});
 rows.push(...protocols.pancakeswap.filter(p=>p.chain_id===cid).map(p=>({...p,platform:'pancakeswap',version:'v3'})));
 rows.push(...protocols.aero.filter(p=>p.chain_id===cid&&p.manager).map(p=>({...p,platform:'aerodrome'})));
 return rows;
}
function factories(cid){
 const r=deployment(cid,'v2','UniswapV2Factory'),rows=r?[{factory:r.address,platform:'uniswap',version:'v2',type:'v2'}]:[];
 if(cid===56)rows.push({factory:'0xcA143Ce32Fe78f1f7019d7d551a6402fC5350c73',platform:'pancakeswap',version:'v2',type:'v2'});
 rows.push(...protocols.aero.filter(p=>p.chain_id===cid&&p.type!=='cl').map(p=>({...p,platform:'aerodrome'})));
 return rows;
}
function atomic(file,value){fs.mkdirSync(path.dirname(file),{recursive:true,mode:0o700});fs.writeFileSync(file+'.tmp',JSON.stringify(value,(_,x)=>typeof x==='bigint'?String(x):x),{mode:0o600});fs.renameSync(file+'.tmp',file);}
class SliceEnd extends Error{}
class Reader{
 constructor(input,state,io,shared={}){
  this.input=input;this.io=io;this.shared=shared;this.contexts=new Map();this.started=Date.now();this.reads=0;
  this.priorIds=new Set((input.known_positions||[]).map(p=>p.id));
  this.maxReads=Math.min(input.max_reads||48,48);this.budget=Math.min(input.budget_ms||25000,30000);
  this.state=state||{schema_version:1,wallet:key(input.wallet),tasks:[],cursor:0,positions:{},coverage:{},blocks:{},done:0};
  if(this.state.schema_version!==1||this.state.wallet!==key(input.wallet)||!Array.isArray(this.state.tasks)||this.state.tasks.length>MAX_TASKS)throw Error('Position checkpoint identity mismatch');
  if(!state)for(const n of input.networks){if(n.environment==='mainnet')this.enqueue({kind:'seed',chain_id:n.chain_id,scope:String(n.chain_id)+':discovery'});}
 }
 enqueue(t){
  if(this.state.tasks.length>=MAX_TASKS)throw Error('Position task limit reached');t={...t};
  if(t.kind==='aeromax'){
   const pending=this.state.tasks.slice(this.state.cursor+1).find(p=>p.kind==='aeromax'&&p.manager===t.manager&&new Set([...p.ids,...t.ids]).size<=100);
   if(pending){pending.ids=[...new Set([...pending.ids,...t.ids])];return;}
  }
  if(!['vault-discover','pair-discover'].includes(t.kind))delete t.tokens;
  if(!['nft','nft-history','aeromax'].includes(t.kind))delete t.ids;
  if(t.kind!=='nft-history')for(const k of ['seen_pages','seen_hashes','page','expected'])delete t[k];
  if(!['gauge-basic','gauge-cl'].includes(t.kind))delete t.pools;
  this.state.tasks.push(t);
 }
 scope(t){return this.state.coverage[t.scope] ||= {id:t.scope,chain_id:t.chain_id,status:'checked',errors:0};}
 async context(cid){
  if(!this.contexts.has(cid)){this.tick(2);const c=await this.io.context(cid,this.state.blocks[cid]);this.contexts.set(cid,c);this.state.blocks[cid]=c.block;}
  return this.contexts.get(cid);
 }
 tick(n=1){if(this.reads+n>this.maxReads||Date.now()-this.started>=this.budget)throw new SliceEnd();this.reads+=n;}
 async multi(t,calls){if(calls.length>BATCH)throw Error('Position multicall limit exceeded');if(!calls.length)return [];const c=await this.context(t.chain_id);this.tick();return this.io.multi(c,calls);}
 async read(t,call){const rows=await this.multi(t,[call]);if(rows[0]?.status!=='success')throw Object.assign(Error('Position read unavailable'),{read_function:call.functionName,reason:rows[0]?.reason||'unknown'});return rows[0].result;}
 good(row){if(row?.status!=='success')throw Object.assign(Error('Position read unavailable'),{read_function:row?.function,reason:row?.reason||'unknown'});return row.result;}
 async token(t,address){
  if(key(address)===ZERO){const n=this.input.networks.find(n=>n.chain_id===t.chain_id),decimals=n?.native_decimals===undefined?18:n.native_decimals;if(!Number.isInteger(decimals)||decimals<0||decimals>36)throw Error('Native currency units unavailable');return {address:'native',symbol:n?.native_symbol||'ETH',decimals};}
  const id=t.chain_id+':'+key(address),cache=this.shared.tokens ||= {};
  if(cache[id])return cache[id];
  const r=await this.multi(t,[spec(address,'decimals'),spec(address,'symbol')]);const decimals=Number(this.good(r[0]));
  if(!Number.isInteger(decimals)||decimals<0||decimals>36)throw Error('Token units unavailable');
  const symbol=r[1]?.status==='success'?String(r[1].result).replace(/[\x00-\x1f]/g,'').slice(0,40):address.slice(0,10);
  return cache[id]={address:key(address),symbol,decimals};
 }
 async assets(t,addresses,amounts){const rows=[];for(let i=0;i<addresses.length;i++){const meta=t.erc1155?{address:key(addresses[i]),symbol:'NFT',decimals:0,token_type:'ERC1155',token_id:'0'}:await this.token(t,addresses[i]);rows.push({...meta,amount_raw:String(amounts[i]),amount:v.formatUnits(BigInt(amounts[i]),meta.decimals)});}return rows;}
 put(t,row){
  if(Object.keys(this.state.positions).length>=MAX_POSITIONS&&!this.state.positions[row.id])throw Error('Position result limit reached');
  const block=this.state.blocks[t.chain_id];this.state.positions[row.id]={...row,...(t.audit?{audit:{...t.audit}}:{}),scope:t.scope,chain_id:t.chain_id,observed_at:block.observed_at,block_number:block.number,block_hash:block.hash};
  if(this.state.absent_positions)this.state.absent_positions=this.state.absent_positions.filter(id=>id!==row.id);
 }
 absent(...ids){
  const rows=this.state.absent_positions ||= [];
  for(const id of ids)if(this.priorIds.has(id)&&!this.state.positions[id]&&!rows.includes(id))rows.push(id);
 }
 absentStake(t,poolId){
  const suffix=':'+key(t.address)+':'+poolId;
  this.absent(...(this.input.known_positions||[]).filter(p=>p.chain_id===t.chain_id&&p.id.endsWith(suffix)).map(p=>p.id));
 }
 async handle(t){
  this.scope(t);const cid=t.chain_id;
  if(t.kind==='seed'){
   await this.context(cid);
   const inventory=this.input.inventory_coverage?.find(c=>c.chain_id===cid);
   if(inventory&&inventory.status!=='checked')this.state.coverage[cid+':wallet-token-inventory']={id:cid+':wallet-token-inventory',chain_id:cid,status:'partial',errors:0,message:'Wallet token discovery was incomplete. Undiscovered ERC20 LP or vault receipts may be missing.'};
   for(const m of managers(cid)){
    this.enqueue({...t,...m,kind:'nft-count',scope:cid+':'+m.platform+':'+key(m.manager)});
    if(m.farm)this.enqueue({...t,...m,kind:'nft-count',inventory_address:m.farm,scope:cid+':'+m.platform+':farm:'+key(m.farm)});
   }
   if(this.input.discover!==false)for(const farm of protocols.pancake_farms||[])if(farm.chain_id===cid)this.enqueue({...t,...farm,kind:'farm-count',scope:cid+':pancake-farm:'+key(farm.address)});
   for(const m of protocols.mintclub_staking.filter(p=>p.chain_id===cid))this.enqueue({...t,...m,kind:'stake-count',scope:cid+':stake:'+key(m.address)});
   if(cid===1)this.enqueue({...t,kind:'factory',scope:'1:factory'});
   if(this.input.discover!==false)for(const a of protocols.aero.filter(p=>p.chain_id===cid))this.enqueue({...t,...a,kind:'aero-count',scope:cid+':aero:'+key(a.factory)});
   else{
    this.state.coverage[cid+':new-position-discovery']={id:cid+':new-position-discovery',chain_id:cid,status:'not_requested',errors:0,message:'Saved positions refreshed. Use Find new positions to search all pool and farm registries.'};
    for(const p of this.input.known_positions||[]){
     if(p.chain_id!==cid)continue;
     if(p.manager){const m=managers(cid).find(m=>key(m.manager)===key(p.manager));if(m)this.enqueue({...t,...m,scope:p.scope,kind:'nft',ids:[p.token_id],gauge:p.gauge,pool:p.pool,inventory_address:p.farm});}
     else if(p.farm)this.enqueue({...t,scope:p.scope,kind:'farm-known',address:p.farm,pool_id:p.pool_id});
     else if(p.pool&&p.factory)this.enqueue({...t,scope:p.scope,kind:'pair',pool:p.pool,factory:p.factory,gauge:p.gauge,platform:p.protocol||p.platform,version:p.version,type:p.version==='legacy-basic'?'basic':p.version==='v2'?'v2':'basic'});
    }
   }
   const tokens=this.input.tokens.filter(p=>p.chain_id===cid&&valid(p.address));
   const lp=protocols.lptoken.find(p=>p.chain_id===cid);
   for(const page of chunks(tokens,BATCH))if(lp)this.enqueue({...t,...lp,kind:'vault-discover',tokens:page,scope:cid+':lptoken'});
   // Symbols are presentation only. Verify canonical factories for every candidate.
   const candidates=tokens;
   if(factories(cid).length)for(const page of chunks(candidates,BATCH))this.enqueue({...t,kind:'pair-discover',tokens:page,scope:cid+':lp-tokens'});
   return;
  }
  if(t.kind==='factory'){
   const d=protocols.factory_nft,values=await this.multi(t,[spec(d.address,'balanceOf',[this.input.wallet,0n]),spec(d.address,'navPerNFT')]);
   const count=BigInt(this.good(values[0]));if(!count){this.absent('1:'+key(d.address)+':0');return;}
   const amount=count*BigInt(this.good(values[1]));
   t.audit={kind:'factory-nav',quantity:String(count),nav_per_nft_raw:String(values[1].result)};
   this.put(t,{id:'1:'+key(d.address)+':0',platform:'factory',protocol:'factory',version:'ERC-1155',label:'Factory NFT',quantity:String(count),receipt:{address:key(d.address),custody:'wallet',balance_raw:String(count),standard:'ERC1155',token_id:'0'},assets:await this.assets(t,[d.underlying],[amount]),source_url:'https://hunt.town/factory',exit_note:'NAV before the 5% burn fee; gas excluded.'});return;
  }
  if(t.kind==='vault-discover'){
   const cache=this.shared.vaults ||= {},fresh=t.tokens.filter(x=>cache[cid+':'+key(t.factory)+':'+key(x.address)]===undefined);
   const rows=await this.multi(t,fresh.map(x=>spec(t.factory,'isVault',[x.address])));
   for(let i=0;i<fresh.length;i++)cache[cid+':'+key(t.factory)+':'+key(fresh[i].address)]=this.good(rows[i])===true;
   for(const token of t.tokens)if(cache[cid+':'+key(t.factory)+':'+key(token.address)])this.enqueue({...t,kind:'vault',vault:token.address});return;
  }
  if(t.kind==='vault'){
   const values=await this.multi(t,[spec(t.vault,'factory'),spec(t.vault,'target'),spec(t.vault,'counter'),spec(t.vault,'balanceOf',[this.input.wallet])]);
   const factory=this.good(values[0]);const configured=protocols.lptoken.find(p=>p.chain_id===cid&&key(p.factory)===key(factory));
   if(!configured||!await this.read(t,spec(factory,'isVault',[t.vault])))throw Error('Unverified LP vault');
   const shares=t.shares===undefined?BigInt(this.good(values[3])):BigInt(t.shares);if(!shares){this.absent(cid+':'+key(t.vault)+':'+(t.stake_id||'wallet'));return;}
   const amounts=await this.read(t,spec(t.vault,'claimForShares',[shares]));
   t.audit={kind:'vault-claim',shares_raw:String(shares),claim_raw:amounts.map(String)};
   this.put(t,{id:cid+':'+key(t.vault)+':'+(t.stake_id||'wallet'),platform:'lptoken',protocol:'uniswap',version:'v4 vault',label:'lpTOKEN liquidity',assets:await this.assets(t,[this.good(values[1]),this.good(values[2])],amounts),receipt:{address:key(t.vault),balance_raw:String(shares),custody:t.stake_id?'mintclub-staking':'wallet'},custody_platform:t.stake_id?'mintclub-staking':null,source_url:'https://lptoken.fun/markets',exit_note:'NAV includes accrued vault assets; redemption terms and gas are separate.'});return;
  }
  if(t.kind==='pair-discover'){
   const cache=this.shared.pairs ||= {},missing=t.tokens.filter(x=>cache[cid+':'+key(x.address)]===undefined);
   const rows=await this.multi(t,missing.map(x=>spec(x.address,'factory'))),allowed=factories(cid);
   for(let i=0;i<missing.length;i++){const row=rows[i];if(row?.status==='success'||row?.reason==='contract')cache[cid+':'+key(missing[i].address)]=row.status==='success'?(allowed.find(f=>key(f.factory)===key(row.result))||null):null;else {this.scope(t).status='partial';this.scope(t).errors++;}}
   for(const token of t.tokens){const f=cache[cid+':'+key(token.address)];if(f)this.enqueue({...t,...f,kind:'pair',pool:token.address});}return;
  }
  if(t.kind==='pair'){
   const r=await this.multi(t,[spec(t.pool,'factory'),spec(t.pool,'token0'),spec(t.pool,'token1'),spec(t.pool,'totalSupply'),spec(t.pool,'getReserves'),spec(t.pool,'balanceOf',[this.input.wallet])]);
   if(key(this.good(r[0]))!==key(t.factory))throw Error('Pool factory mismatch');
   const a=this.good(r[1]),b=this.good(r[2]),balance=BigInt(this.good(r[5]));let staked=0n;
   const canonical=t.type==='v2'?await this.read(t,spec(t.factory,'getPair',[a,b])):
    t.version==='legacy-basic'?await this.read(t,spec(t.factory,'getPool',[a,b,await this.read(t,spec(t.pool,'stable'))])):
    await this.read(t,spec(t.factory,'getPool',[a,b]));
   if(key(canonical)!==key(t.pool))throw Error('Pool is not canonical for this factory');
   if(!balance)this.absent(cid+':'+key(t.pool)+':wallet');
   if(t.gauge&&key(t.gauge)!==ZERO)staked=BigInt(await this.read(t,spec(t.gauge,'balanceOf',[this.input.wallet])));
   if(t.gauge&&key(t.gauge)!==ZERO&&!staked)this.absent(cid+':'+key(t.pool)+':gauge');
   for(const [custody,quantity] of [['wallet',balance],['gauge',staked],['farm',BigInt(t.farm_shares||0)]]){
    if(!quantity)continue;const reserves=this.good(r[4]),amounts=math.shareAmounts(quantity,this.good(r[3]),[reserves[0],reserves[1]]);
    t.audit={kind:'pool-share',shares_raw:String(quantity),supply_raw:String(r[3].result),reserves_raw:[String(reserves[0]),String(reserves[1])]};
    this.put(t,{id:cid+':'+key(t.pool)+':'+custody+(custody==='farm'?':'+key(t.farm)+':'+t.pool_id:''),platform:t.platform||'aerodrome',protocol:t.platform||'aerodrome',version:t.version,label:'Liquidity pool',pool:key(t.pool),factory:key(t.factory),gauge:t.gauge?key(t.gauge):null,farm:custody==='farm'?key(t.farm):null,pool_id:t.pool_id,assets:await this.assets(t,[a,b],amounts),receipt:{address:key(t.pool),balance_raw:String(quantity),custody},custody_platform:custody==='gauge'?'aerodrome':custody==='farm'?'pancakeswap':null,source_url:t.platform==='uniswap'?'https://app.uniswap.org/portfolio':t.platform==='pancakeswap'?'https://pancakeswap.finance/liquidity':'https://aero.xyz',exit_note:'Pool reserve share; unclaimed rewards and exit costs excluded.'});
   }return;
  }
  if(t.kind==='farm-count'){
   const count=Number(await this.read(t,spec(t.address,'poolLength')));if(!Number.isSafeInteger(count)||count>20000)throw Error('Farm directory exceeds supported bound');
   for(let start=0;start<count;start+=BATCH)this.enqueue({...t,kind:'farm-scan',start,end:Math.min(start+BATCH,count)});return;
  }
  if(t.kind==='farm-scan'){
   const ids=Array.from({length:t.end-t.start},(_,i)=>BigInt(t.start+i)),rows=await this.multi(t,ids.map(id=>spec(t.address,'userInfo',[id,this.input.wallet])));
   for(let i=0;i<ids.length;i++){
    if(BigInt(this.good(rows[i])[0]))this.enqueue({...t,kind:'farm',pool_id:String(ids[i]),farm_shares:String(rows[i].result[0])});
    else this.absent(...(this.input.known_positions||[]).filter(p=>p.chain_id===cid&&p.farm&&key(p.farm)===key(t.address)&&String(p.pool_id)===String(ids[i])).map(p=>p.id));
   }return;
  }
  if(t.kind==='farm'){
   const pool=await this.read(t,spec(t.address,'lpToken',[BigInt(t.pool_id)]));
   this.enqueue({...t,kind:'pair',pool,farm:t.address,platform:'pancakeswap',version:'v2 farm',type:'v2',factory:factories(cid).find(f=>f.platform==='pancakeswap').factory});return;
  }
  if(t.kind==='farm-known'){
   const p=await this.read(t,spec(t.address,'userInfo',[BigInt(t.pool_id),this.input.wallet]));
   if(BigInt(p[0]))this.enqueue({...t,kind:'farm',farm_shares:String(p[0])});
   else this.absent(...(this.input.known_positions||[]).filter(p=>p.chain_id===cid&&p.farm&&key(p.farm)===key(t.address)&&String(p.pool_id)===String(t.pool_id)).map(p=>p.id));return;
  }
  if(t.kind==='stake-count'){
   const count=Number(await this.read(t,spec(t.address,'poolCount',[],stakeAbi))),end=Math.min(count,t.end??count);
   if(!Number.isSafeInteger(count)||count>20000)throw Error('Staking directory exceeds supported bound');
   for(let start=t.start;start<end;start+=BATCH)this.enqueue({...t,kind:'stake-scan',start,end:Math.min(start+BATCH,end)});return;
  }
  if(t.kind==='stake-scan'){
   const ids=Array.from({length:t.end-t.start},(_,i)=>BigInt(t.start+i));const rows=await this.multi(t,ids.map(id=>spec(t.address,'userPoolStake',[this.input.wallet,id],stakeAbi)));
   for(let i=0;i<ids.length;i++){
    if(BigInt(this.good(rows[i])[0])>0n)this.enqueue({...t,kind:'stake',pool_id:String(ids[i]),shares:String(rows[i].result[0])});
    else this.absentStake(t,String(ids[i]));
   }return;
  }
  if(t.kind==='stake'){
   const p=await this.read(t,spec(t.address,'pools',[BigInt(t.pool_id)],stakeAbi));const token=p.stakingToken??p[0];
   const erc20=p.isStakingTokenERC20??p[1];
   const lp=protocols.lptoken.find(p=>p.chain_id===cid);
   if(erc20&&lp&&await this.read(t,spec(lp.factory,'isVault',[token]))){this.enqueue({...t,...lp,kind:'vault',vault:token,stake_id:key(t.address)+':'+t.pool_id});return;}
   this.put(t,{id:cid+':'+key(t.address)+':'+t.pool_id,platform:'mintclub-staking',protocol:'mintclub-staking',version:t.version,pool_id:t.pool_id,label:'Staking pool #'+t.pool_id,assets:await this.assets({...t,erc1155:!erc20},[token],[BigInt(t.shares)]),source_url:protocols.mintclub_staking_url_slugs[cid]?'https://mint.club/staking/'+protocols.mintclub_staking_url_slugs[cid]+'/'+t.pool_id:'https://mint.club/staking',exit_note:'Staked principal; pending rewards are excluded.'});return;
  }
  if(t.kind==='nft-count'){
   const count=BigInt(await this.read(t,spec(t.inventory_address||t.manager,'balanceOf',[this.input.wallet])));
   (this.state.nft_expected ||= {})[t.scope]=String(count);
   if(count>BigInt(MAX_POSITIONS))throw Error('Position inventory exceeds supported bound');
   if(t.type==='v4'){if(count)this.enqueue({...t,kind:'nft-history',expected:String(count),page:null,ids:[]});return;}
   for(let start=0;start<Number(count);start+=BATCH)this.enqueue({...t,kind:'nft-enum',start,end:Math.min(start+BATCH,Number(count))});return;
  }
  if(t.kind==='nft-enum'){
   const rows=await this.multi(t,Array.from({length:t.end-t.start},(_,i)=>spec(t.inventory_address||t.manager,'tokenOfOwnerByIndex',[this.input.wallet,BigInt(t.start+i)])));
   for(const ids of chunks(rows.map(r=>String(this.good(r))),NFT_BATCH))this.enqueue({...t,kind:'nft',ids});return;
  }
  if(t.kind==='nft-history'){
   const c=await this.context(cid);this.tick();const args={fromBlock:'0x0',toBlock:v.toHex(BigInt(c.block.number)),toAddress:this.input.wallet,contractAddresses:[t.manager],category:['erc721'],maxCount:'0x64',excludeZeroValue:false,order:'asc',...(t.page?{pageKey:t.page}:{})};
   const result=await this.io.transfers(c,args);if(!Array.isArray(result.transfers)||result.transfers.length>100)throw Error('Invalid NFT index page');
   const ids=[...new Set([...t.ids,...result.transfers.filter(r=>key(r.rawContract?.address)===key(t.manager)&&/^0x[0-9a-f]+$/i.test(r.tokenId||'')).map(r=>String(BigInt(r.tokenId)))])];
   if(ids.length>10000)throw Error('NFT history exceeds supported bound');
   if(result.pageKey){
    const pages=[...(t.seen_pages||[]),...(t.page?[t.page]:[])],hash=v.keccak256(v.stringToHex(JSON.stringify(result.transfers))),hashes=t.seen_hashes||[];
    if(pages.includes(result.pageKey)||hashes.includes(hash)||pages.length>=512)throw Error('NFT index repeated or exceeded its page bound');
    this.enqueue({...t,page:result.pageKey,ids,seen_pages:pages,seen_hashes:[...hashes,hash]});
   }
   else for(const page of chunks(ids,NFT_BATCH))this.enqueue({...t,kind:'nft',ids:page});return;
  }
  if(t.kind==='nft'){
   if(t.type==='v4')return this.v4(t);
   const custom=t.type==='cl'?clAbi:nftAbi,rows=await this.multi(t,t.ids.flatMap(id=>[spec(t.manager,'ownerOf',[BigInt(id)]),spec(t.manager,'positions',[BigInt(id)],custom)]));
   for(let i=0;i<t.ids.length;i++){
    const owner=rows[i*2]?.status==='success'?key(rows[i*2].result):null;
    if(!owner&&rows[i*2]?.reason!=='contract')throw Error('NFT ownership unavailable');
    if(owner!==key(this.input.wallet)&&owner!==key(t.gauge||t.inventory_address||ZERO)){this.absent(cid+':'+key(t.manager)+':'+t.ids[i]);continue;}
    if(t.gauge&&owner===key(t.gauge)&&await this.read(t,spec(t.gauge,'stakedContains',[this.input.wallet,BigInt(t.ids[i])]))!==true){this.absent(cid+':'+key(t.manager)+':'+t.ids[i]);continue;}
    if(t.inventory_address){const farmPosition=await this.read(t,spec(t.inventory_address,'userPositionInfos',[BigInt(t.ids[i])]));if(key(farmPosition[6])!==key(this.input.wallet))throw Error('Farm beneficiary mismatch');}
    if(owner===key(this.input.wallet)||t.inventory_address&&owner===key(t.inventory_address))(this.state.nft_owned ||= {})[t.scope+':'+t.ids[i]]=true;
    const p=this.good(rows[i*2+1]);if(!BigInt(p[7])){this.absent(cid+':'+key(t.manager)+':'+t.ids[i]);continue;}
    const pool=await this.read(t,spec(t.factory,'getPool',[p[2],p[3],Number(p[4])],t.type==='cl'?v.parseAbi(['function getPool(address,address,int24) view returns(address)']):abi));
    if(key(pool)===ZERO||t.pool&&key(pool)!==key(t.pool))throw Error('NFT pool identity mismatch');
    const price=await this.read(t,spec(pool,'slot0',[],t.type==='cl'?v.parseAbi(['function slot0() view returns(uint160,int24,uint16,uint16,uint16,bool)']):abi));
    const amounts=math.liquidityAmounts(p[7],price[0],Number(p[5]),Number(p[6]));
    t.audit={kind:'concentrated-liquidity',liquidity_raw:String(p[7]),sqrt_price_x96:String(price[0]),tick_lower:Number(p[5]),tick_upper:Number(p[6])};
    const inGauge=owner===key(t.gauge||ZERO),inFarm=owner===key(t.inventory_address||ZERO);
    this.put(t,{id:cid+':'+key(t.manager)+':'+t.ids[i],platform:t.platform,protocol:t.platform,version:t.version,label:'Liquidity #'+t.ids[i],manager:key(t.manager),token_id:t.ids[i],pool:key(pool),factory:key(t.factory),gauge:inGauge?key(t.gauge):null,farm:inFarm?key(t.inventory_address):null,custody_platform:inGauge?'aerodrome':inFarm?'pancakeswap':null,assets:await this.assets(t,[p[2],p[3]],amounts),range:{lower:Number(p[5]),upper:Number(p[6]),tick:Number(price[1])},source_url:t.platform==='uniswap'?'https://app.uniswap.org/portfolio':t.platform==='pancakeswap'?'https://pancakeswap.finance/liquidity':'https://aero.xyz',exit_note:'Liquidity principal; uncollected fees, rewards and gas excluded.'});
   }
   const aero=protocols.aero.find(p=>p.chain_id===8453&&p.version==='aero-cl');
   if(cid===8453&&aero&&key(t.manager)===key(aero.manager))this.enqueue({...t,kind:'aeromax'});
   return;
  }
  if(t.kind==='aeromax'){
   if(this.shared.aeromax_retry_after>Date.now())throw Error('Project source is cooling down');
   this.tick();let response;
   try{response=await this.io.aeromax(t.ids);}catch(error){this.shared.aeromax_retry_after=Date.now()+60000;throw error;}
   if(response.retry_after){this.shared.aeromax_retry_after=Date.now()+Math.min(86400,response.retry_after)*1000;throw Error('Project source is rate limited');}
   if(!['ready','syncing'].includes(response.status)||!Array.isArray(response.positions))throw Error('Project attribution is unavailable');
   for(const meta of response.positions){
    if(!t.ids.includes(String(meta.tokenId))||!(['token0','token1','pair'].includes(meta.entryMode)||meta.entryPayment&&typeof meta.entryPayment==='object'))continue;
    const id=cid+':'+key(t.manager)+':'+meta.tokenId,row=this.state.positions[id];
    if(row){row.platform='aeromax';row.protocol='aerodrome';row.source_url='https://aeromax.fun';row.attribution={source:'https://aeromax.fun/api/positions',indexed_through_block:response.indexedThroughBlock};}
   }return;
  }
  if(t.kind==='aero-count'){
   const modern=t.version.startsWith('aero-'),count=Number(await this.read(t,spec(t.factory,modern?'poolsIndexLength':'allPoolsLength')));
   if(!Number.isSafeInteger(count)||count>50000)throw Error('Pool directory exceeds supported bound');
   if(t.sugar){
    for(let start=0;start<Math.min(count,30000);start+=128)this.enqueue({...t,kind:'aero-sugar',start,end:Math.min(start+128,count,30000)});
    for(let start=30000;start<count;start+=BATCH)this.enqueue({...t,kind:'aero-directory',start,end:Math.min(start+BATCH,count)});
   }else for(let start=0;start<count;start+=BATCH)this.enqueue({...t,kind:'aero-directory',start,end:Math.min(start+BATCH,count)});
   return;
  }
  if(t.kind==='aero-sugar'){
   const rows=await this.read(t,spec(t.sugar,'positionsByFactory',[BigInt(t.end-t.start),BigInt(t.start),this.input.wallet,t.factory],sugarAbi));
   if(rows.length>=1000){if(t.end-t.start<=1)throw Error('Pool position list may be truncated');const mid=Math.floor((t.start+t.end)/2);this.enqueue({...t,end:mid});this.enqueue({...t,start:mid});return;}
   for(const row of rows){
    const id=row.id??row[0],pool=row.lp??row[1],held=row.liquidity??row[2],staked=row.staked??row[3];
    if(!held&&!staked)continue;
    if(key(row.locker??row[15])!==ZERO||key(row.alm??row[17])!==ZERO){this.scope(t).status='partial';this.scope(t).errors++;continue;}
    const gauge=await this.read(t,spec(t.voter,'gauges',[pool]));
    if(t.type==='cl')this.enqueue({...t,kind:'nft',ids:[String(id)],gauge:staked?gauge:undefined,pool,platform:'aerodrome'});
    else this.enqueue({...t,kind:'pair',pool,gauge,platform:'aerodrome'});
   }return;
  }
  if(t.kind==='aero-directory'){
   const cache=this.shared.directories ||= {},cacheKey=cid+':'+key(t.factory)+':'+t.start;const modern=t.version.startsWith('aero-');let addresses=cache[cacheKey];
   if(!addresses||addresses.length!==t.end-t.start){
    addresses=modern?(await this.read(t,spec(t.factory,'poolsIndexPaginated',[BigInt(t.start),BigInt(t.end)]))).map(p=>p.pool):
     (await this.multi(t,Array.from({length:t.end-t.start},(_,i)=>spec(t.factory,'allPools',[BigInt(t.start+i)])))).map(r=>this.good(r));
    if(addresses.length!==t.end-t.start||addresses.some(a=>!valid(a)||key(a)===ZERO))throw Error('Pool directory is incomplete');cache[cacheKey]=addresses;
   }
   const rows=await this.multi(t,addresses.map(pool=>modern?spec(pool,'gauge'):spec(t.voter,'gauges',[pool])));
   const pools=addresses.map((pool,i)=>({pool,gauge:this.good(rows[i])}));
   if(t.type==='cl')this.enqueue({...t,kind:'gauge-cl',pools:pools.filter(p=>key(p.gauge)!==ZERO)});
   else this.enqueue({...t,kind:'gauge-basic',pools});return;
  }
  if(t.kind==='gauge-cl'){
   const rows=await this.multi(t,t.pools.map(p=>spec(p.gauge,'stakedValues',[this.input.wallet])));
   for(let i=0;i<t.pools.length;i++){const ids=this.good(rows[i]);if(ids.length>MAX_POSITIONS)throw Error('Gauge result exceeds supported bound');for(const page of chunks(ids,NFT_BATCH))this.enqueue({...t,...t.pools[i],platform:'aerodrome',kind:'nft',ids:page.map(String)});}return;
  }
  if(t.kind==='gauge-basic'){
   for(const batch of chunks(t.pools,16)){
    const rows=await this.multi(t,batch.flatMap(p=>[spec(p.pool,'balanceOf',[this.input.wallet]),...(key(p.gauge)!==ZERO?[spec(p.gauge,'balanceOf',[this.input.wallet])]:[])]));let at=0;
    for(const p of batch){const held=BigInt(this.good(rows[at++])),staked=key(p.gauge)!==ZERO?BigInt(this.good(rows[at++])):0n;if(held||staked)this.enqueue({...t,...p,kind:'pair',platform:'aerodrome'});}
   }return;
  }
  throw Error('Unknown position task');
 }
 async v4(t){
  const rows=await this.multi(t,t.ids.flatMap(id=>[spec(t.manager,'ownerOf',[BigInt(id)]),spec(t.manager,'getPoolAndPositionInfo',[BigInt(id)]),spec(t.manager,'getPositionLiquidity',[BigInt(id)])]));
  for(let i=0;i<t.ids.length;i++){
   if(rows[i*3]?.status!=='success'){
    if(rows[i*3]?.reason==='contract'){this.absent(t.chain_id+':'+key(t.manager)+':'+t.ids[i]);continue;}
    throw Error('V4 NFT ownership unavailable');
   }
   if(key(rows[i*3].result)!==key(this.input.wallet)){this.absent(t.chain_id+':'+key(t.manager)+':'+t.ids[i]);continue;}
   (this.state.nft_owned ||= {})[t.scope+':'+t.ids[i]]=true;
   const [k,info]=this.good(rows[i*3+1]),l=BigInt(this.good(rows[i*3+2]));if(!l){this.absent(t.chain_id+':'+key(t.manager)+':'+t.ids[i]);continue;}
   const pool=v.keccak256(v.encodeAbiParameters([{type:'address'},{type:'address'},{type:'uint24'},{type:'int24'},{type:'address'}],[k.currency0,k.currency1,k.fee,k.tickSpacing,k.hooks]));
   if((BigInt(pool)>>56n)!==(BigInt(info)>>56n))throw Error('V4 pool identity mismatch');
   const price=await this.read(t,spec(t.view,'getSlot0',[pool])),ticks=math.v4Ticks(info),amounts=math.liquidityAmounts(l,price[0],...ticks);
   t.audit={kind:'concentrated-liquidity',liquidity_raw:String(l),sqrt_price_x96:String(price[0]),tick_lower:ticks[0],tick_upper:ticks[1]};
   this.put(t,{id:t.chain_id+':'+key(t.manager)+':'+t.ids[i],platform:'uniswap',protocol:'uniswap',version:'v4',label:'Liquidity #'+t.ids[i],manager:key(t.manager),token_id:t.ids[i],pool,assets:await this.assets(t,[k.currency0,k.currency1],amounts),range:{lower:ticks[0],upper:ticks[1],tick:Number(price[1])},source_url:'https://app.uniswap.org/portfolio',exit_note:'Liquidity principal; hook terms, unclaimed fees and gas excluded.'});
  }
 }
 async run(save){
  let completed=0,lastSave=Date.now(),lastPositions=Object.keys(this.state.positions).length;
  while(this.state.cursor<this.state.tasks.length&&completed<32){
   // Read known balances and emit useful records before expensive registry sweeps.
   const priority=t=>t.kind==='aero-sugar'||t.version?.startsWith('legacy-')&&['aero-directory','gauge-basic','gauge-cl'].includes(t.kind)?3:['aero-directory','gauge-basic','gauge-cl','farm-scan'].includes(t.kind)?2:['aero-count','farm-count'].includes(t.kind)?1:0;
   let best=this.state.cursor;for(let i=best+1;i<this.state.tasks.length;i++)if(priority(this.state.tasks[i])<priority(this.state.tasks[best]))best=i;
   if(best!==this.state.cursor)[this.state.tasks[best],this.state.tasks[this.state.cursor]]=[this.state.tasks[this.state.cursor],this.state.tasks[best]];
   const task=this.state.tasks[this.state.cursor],tail=this.state.tasks.length;
   try{await this.handle(task);
    // Completed pagination pages must not retain another copy of the entire
    // cumulative NFT frontier. Failed tasks keep their arguments for rechecks.
    for(const field of ['tokens','ids','pools','seen_pages','seen_hashes','page'])delete task[field];
   }
   catch(error){if(error instanceof SliceEnd){this.state.tasks.length=tail;break;}const c=this.scope(task);c.status='partial';c.errors++;c.failed_step=task.kind;if(error.read_function)c.failed_function=error.read_function;if(error.reason)c.reason=error.reason;c.message='Some position reads were unavailable. Missing amounts remain unknown.';
    (this.state.failed_tasks ||= []).push({index:this.state.cursor,scope:task.scope,kind:task.kind,...(error.read_function?{function:error.read_function}:{}),reason:error.reason||'unknown'});
   }
   this.state.cursor++;this.state.done++;completed++;
   const count=Object.keys(this.state.positions).length;
   if(completed%4===0||count!==lastPositions||Date.now()-lastSave>=1000){save(this.state,this.shared);lastSave=Date.now();lastPositions=count;}
   this.io.progress?.({stage:'onchain_progress',operation:'positions',chain_id:task.chain_id,checked:this.state.cursor,total:this.state.tasks.length});
  }
  this.state.complete=this.state.cursor===this.state.tasks.length;this.state.last_slice_reads=this.reads;
  if(this.state.complete)for(const [scope,expected] of Object.entries(this.state.nft_expected||{})){
   const found=Object.keys(this.state.nft_owned||{}).filter(id=>id.startsWith(scope+':')).length;
   if(BigInt(found)!==BigInt(expected))Object.assign(this.state.coverage[scope],{status:'partial',message:'NFT index and pinned owner count differ. Discovery is incomplete.'});
  }
  save(this.state,this.shared);return this.state;
 }
}
function realIO(){
 const h=require('./onchain.cjs'),p=require('./pipeline-onchain.cjs');
 return {
  async context(cid,saved){const c=await p.connect({chain_id:cid});const header=await h.snapshotBlock(c,saved?{block_number:saved.number,block_hash:saved.hash}:null);return {c,block:{number:String(header.number),hash:header.hash,observed_at:saved?.observed_at||stamp()}};},
  async multi(context,calls){const r=await context.c.multicall({contracts:calls,blockNumber:BigInt(context.block.number),batchSize:0,multicallAddress:'0xcA11bde05977b3631167028862bE2a173976CA11'});return r.map((x,index)=>{
   if(x.status==='success')return {status:'success',result:x.result};
   let contract=false;for(let e=x.error,depth=0;e&&depth<8;e=e.cause,depth++)if(/ContractFunctionReverted|ContractFunctionZeroData|AbiDecoding/.test(e.name||''))contract=true;
   return {status:'failure',function:calls[index].functionName,reason:contract?'contract':require('./rpc-pool.cjs').classify(x.error)};
  });},
  transfers(context,args){return context.c.request({method:'alchemy_getAssetTransfers',params:[args]});},
  async aeromax(ids){
   const response=await fetch('https://aeromax.fun/api/positions?ids='+ids.map(encodeURIComponent).join(','),{signal:AbortSignal.timeout(6000),redirect:'error'});
   if(response.status===429){const header=response.headers.get('retry-after'),number=Number(header),seconds=Number.isFinite(number)?number:(Date.parse(header)-Date.now())/1000;return {retry_after:Number.isFinite(seconds)&&seconds>0?seconds:60};}
   if(!response.ok)throw Error('Project source unavailable');
   let bytes=0,body='';const decoder=new TextDecoder();for await(const chunk of response.body){bytes+=chunk.length;if(bytes>2000000)throw Error('Project response exceeds limit');body+=decoder.decode(chunk,{stream:true});}
   return JSON.parse(body+decoder.decode());
  },
  progress(event){console.log(JSON.stringify(event));}
 };
}
if(require.main===module){
 const input=JSON.parse(fs.readFileSync(process.argv[2])),file=process.argv[3],sharedFile=process.argv[4];
 const read=p=>{try{return JSON.parse(fs.readFileSync(p));}catch{return null;}};
 const shared=read(sharedFile)||{},before=JSON.stringify(shared),reader=new Reader(input,read(file),realIO(),shared);
 reader.run(state=>atomic(file,state)).then(()=>{
  for(const name of ['tokens','vaults','pairs','directories']){
   const table=shared[name];if(!table)continue;const keys=Object.keys(table);for(const k of keys.slice(0,Math.max(0,keys.length-20000)))delete table[k];
  }
  if(JSON.stringify(shared)!==before)atomic(sharedFile,shared);
  process.exit(0);
 }).catch(()=>process.exit(1));
}
module.exports={Reader,managers,factories,math,abi,stakeAbi,BATCH,MAX_POSITIONS};
