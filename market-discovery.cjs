// Read-only factory metadata. No balances, swap quotes, signatures or transactions.
const fs=require('fs'),path=require('path');
const h=require('./onchain.cjs'),p=require('./pipeline-onchain.cjs'),v=h.viem;
const deployments=require('./sources/uniswap-deployments.json').records;
const abi=v.parseAbi(['function getPair(address,address) view returns(address)','function getPool(address,address,uint24) view returns(address)','function getPool(address,address,bool) view returns(address)']);
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
 return requests;
}
async function discover(input,save){
 const deadline=Date.now()+Math.min(input.budget_ms||45000,60000),result={status:'checked',markets:[],checked:0,total:0};
 const requests=plans(input.tokens);result.total=requests.length;save(result);if(!requests.length)return result;
 const grouped=new Map();
 try{
  const c=await p.boundedMarket(p.connect(input.networks.find(n=>n.chain_id===8453)),deadline);
  const block=await p.boundedMarket(h.snapshotBlock(c),deadline);result.block_number=block.number.toString();result.block_hash=block.hash;
  for(let i=0;i<requests.length;i+=128){
   const batch=requests.slice(i,i+128),rows=await p.boundedMarket(p.calls(c,batch.map(q=>q.call),block.number),deadline);
   for(let j=0;j<rows.length;j++){
    const row=rows[j],q=batch[j];result.checked++;
    if(row.status!=='success'){result.status='partial';continue;}
    if(!v.isAddress(row.result)||row.result===v.zeroAddress)continue;
    const id='8453:'+q.t.token_address.toLowerCase(),pools=grouped.get(id)||[];
    if(!pools.some(pool=>pool.pool.toLowerCase()===row.result.toLowerCase()))pools.push({pool:row.result,pool_kind:'address',venue:q.protocol==='aerodrome'?'aerodrome':'uniswap',version_labels:[q.protocol],fee_bps:q.protocol==='v3'?q.fee/100:null,
     paired_tokens:[{address:q.t.token_address,symbol:q.t.symbol},{address:q.quote,symbol:q.symbol}],reported_liquidity:null,
     observed_at:new Date().toISOString(),source_url:q.protocol==='aerodrome'?'https://basescan.org/address/'+row.result:'https://app.uniswap.org/explore/pools/base/'+row.result,
     factory_discovery:{factory:q.factory,block_number:block.number.toString(),block_hash:block.hash}});
    grouped.set(id,pools);
   }
   result.markets=[...grouped].map(([id,pools])=>({id,pools}));save(result);
  }
 }catch(error){result.status='partial';result.error=h.safeError(error);}
 save(result);return result;
}
if(require.main===module){const input=JSON.parse(fs.readFileSync(process.argv[2])),output=process.argv[3];discover(input,result=>{fs.writeFileSync(output+'.tmp',h.serialize(result));fs.renameSync(output+'.tmp',output);}).then(()=>process.exit(0)).catch(()=>process.exit(1));}
module.exports={plans,discover};
