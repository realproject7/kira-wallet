// Read-only factory metadata. No balances, swap quotes, signatures or transactions.
const fs=require('fs'),path=require('path');
const h=require('./onchain.cjs'),p=require('./pipeline-onchain.cjs'),v=h.viem;
const deployments=require('./sources/uniswap-deployments.json').records;
const explorers={1:'https://etherscan.io',56:'https://bscscan.com',8453:'https://basescan.org',10:'https://optimistic.etherscan.io',42161:'https://arbiscan.io',4663:'https://robinhoodchain.blockscout.com',57073:'https://explorer.inkonchain.com'};
const dex=require('./dex-adapters.cjs'),known=require('./sources/known-tokens.json').tokens;
const abi=v.parseAbi(['function getPair(address,address) view returns(address)','function getPool(address,address,uint24) view returns(address)','function getPool(address,address,bool) view returns(address)','function getPool(address,address) view returns(address)']);
function plans(tokens){
 const requests=[];
 for(const t of tokens.filter(t=>t.chain_id===8453&&t.token_type!=='ERC1155')){
  const quotes=new Map([['0x4200000000000000000000000000000000000006','WETH'],['0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913','USDC']]);
  if(t.mintclub?.reserve_token)quotes.set(t.mintclub.reserve_token.toLowerCase(),t.mintclub.reserve_symbol);
  for(const [quote,symbol] of quotes){
   if(quote===t.token_address.toLowerCase())continue;
   for(const protocol of ['v2','v3','aerodrome']){
    const factory=protocol==='aerodrome'?'0x420DD381b31aEf6683db6B902084cB0FFECe40Da':deployments.find(r=>r.chainId===8453&&r.protocol===protocol&&r.contract===(protocol==='v2'?'UniswapV2Factory':'UniswapV3Factory'))?.address;
    if(!factory)continue;
    for(const fee of protocol==='v3'?[100,500,3000,10000]:protocol==='aerodrome'?[false,true]:[null])requests.push({t,quote,symbol,protocol,factory,fee,call:{address:factory,abi,functionName:protocol==='v2'?'getPair':'getPool',args:protocol==='v2'?[t.token_address,quote]:[t.token_address,quote,fee]}});
   }
  }
 }
 for(const t of tokens.filter(t=>t.token_type!=='ERC1155')){
  const assets=known.filter(k=>k.chain_id===t.chain_id),symbols=t.chain_id===56?['WBNB','USDT']:['WETH','USDC'];
  const quotes=symbols.map(s=>assets.find(t=>t.symbol===s)).filter(Boolean);
  for(const q of quotes){
   if(q.address.toLowerCase()===t.token_address.toLowerCase())continue;
   for(const a of dex.records.filter(a=>a.chain_id===t.chain_id)){
    const values=a.type==='v3'?[100,500,2500,10000]:a.type==='cl'?[1,50,100,200,2000]:[null];
    for(const fee of values){
     const poolAbi=a.type==='cl'?v.parseAbi(['function getPool(address,address,int24) view returns(address)']):abi;
     requests.push({t,quote:q.address,symbol:q.symbol,protocol:a.type,factory:a.factory,fee,adapter:a,
      call:{address:a.factory,abi:poolAbi,functionName:a.type==='v2'?'getPair':'getPool',args:fee===null?[t.token_address,q.address]:[t.token_address,q.address,fee]}});
    }
   }
  }
 }
 return requests;
}
async function discover(input,save){
 const deadline=Date.now()+Math.min(input.budget_ms||45000,60000),result={status:'checked',markets:[],checked:0,total:0};
 const requests=plans(input.tokens);result.total=requests.length;save(result);if(!requests.length)return result;
 const grouped=new Map();
 for(const chain of [...new Set(requests.map(q=>q.t.chain_id))]){
 try{
  const chainRequests=requests.filter(q=>q.t.chain_id===chain);
  const c=await p.boundedMarket(p.connect(input.networks.find(n=>n.chain_id===chain)),deadline);
  const block=await p.boundedMarket(h.snapshotBlock(c),deadline);
  for(let i=0;i<chainRequests.length;i+=128){
   const batch=chainRequests.slice(i,i+128),rows=await p.boundedMarket(p.calls(c,batch.map(q=>q.call),block.number),deadline);
   for(let j=0;j<rows.length;j++){
    const row=rows[j],q=batch[j];result.checked++;
    if(row.status!=='success'){result.status='partial';continue;}
    if(!v.isAddress(row.result)||row.result===v.zeroAddress)continue;
    const id=q.t.chain_id+':'+q.t.token_address.toLowerCase(),pools=grouped.get(id)||[];
    if(!pools.some(pool=>pool.pool.toLowerCase()===row.result.toLowerCase()))pools.push({pool:row.result,pool_kind:'address',venue:q.adapter?.venue||(q.protocol==='aerodrome'?'aerodrome':'uniswap'),version_labels:q.adapter?[q.protocol==='cl'?'v3':q.protocol==='basic'?'v2':q.protocol,...(q.adapter.venue==='aero'?['aero']:[])]:[q.protocol],fee_bps:q.protocol==='v3'?q.fee/100:q.adapter?.fee_bps??null,
     paired_tokens:[{address:q.t.token_address,symbol:q.t.symbol},{address:q.quote,symbol:q.symbol}],reported_liquidity:null,
     observed_at:new Date().toISOString(),source_url:q.adapter?explorers[q.t.chain_id]+'/address/'+row.result:q.protocol==='aerodrome'?'https://basescan.org/address/'+row.result:'https://app.uniswap.org/explore/pools/base/'+row.result,
     factory_discovery:{factory:q.factory,...(q.adapter?{adapter:q.adapter.kind,venue:q.adapter.venue}:{}),block_number:block.number.toString(),block_hash:block.hash}});
    grouped.set(id,pools);
   }
   result.markets=[...grouped].map(([id,pools])=>({id,pools}));save(result);
  }
 }catch(error){result.status='partial';result.error=h.safeError(error);}
 if(Date.now()>=deadline)break;
 }
 if(result.checked<result.total)result.status='partial';
 save(result);return result;
}
if(require.main===module){const input=JSON.parse(fs.readFileSync(process.argv[2])),output=process.argv[3];discover(input,result=>{fs.writeFileSync(output+'.tmp',h.serialize(result));fs.renameSync(output+'.tmp',output);}).then(()=>process.exit(0)).catch(()=>process.exit(1));}
module.exports={plans,discover};
