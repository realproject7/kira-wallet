// Bounded direct-pool quotes. No route discovery, partial-input search or swaps.
const fs=require('node:fs');
const h=require('./onchain.cjs'),p=require('./pipeline-onchain.cjs');
const abi=h.viem.parseAbi(['function balanceOf(address) view returns(uint256)']);
async function collect(input,save=()=>{}) {
  const deadline=Date.now()+Math.min(20000,Math.max(0,input.budget_ms??20000));
  const result={status:'checked',records:[]};
  const tokens=input.tokens.slice(0,12);
  const networks=[...input.networks].sort((a,b)=>tokens.findIndex(t=>t.chain_id===a.chain_id)-tokens.findIndex(t=>t.chain_id===b.chain_id));
  for(const network of networks){
    const selected=tokens.filter(t=>t.chain_id===network.chain_id);
    if(!selected.length||network.environment!=='mainnet'||[5112,54176].includes(network.chain_id))continue;
    if(Date.now()>=deadline){result.status='partial';break;}
    try{
      const client=await p.boundedMarket(p.connect(network),deadline);
      const block=await p.boundedMarket(h.snapshotBlock(client),deadline);
      const balances=await p.boundedMarket(p.calls(client,selected.map(t=>({address:t.token_address,abi,functionName:'balanceOf',args:[input.wallet]})),block.number),deadline);
      const ready=[];
      for(let i=0;i<selected.length;i++){
        const t=selected[i],balance=balances[i];
        const row={chain_id:t.chain_id,address:t.token_address.toLowerCase(),pool:t.dex_pools[0].pool.toLowerCase(),
          wallet_balance_raw:t.wallet_balance_raw,checked_at:new Date().toISOString(),status:'unknown'};
        result.records.push(row);
        if(balance?.status!=='success'){row.reason='Holding check unavailable';continue;}
        if(String(balance.result)!==t.wallet_balance_raw){row.reason='Balance changed; refresh holdings';continue;}
        Object.assign(row,{balance_block_number:String(block.number),balance_block_hash:block.hash,balance_observed_at:row.checked_at});
        // Only the independently rechecked quantity gets the fresh block pin.
        ready.push({...structuredClone(t),balance_block_number:row.balance_block_number,balance_block_hash:block.hash});
      }
      save(result);
      if(ready.length){
        await p.dexChain(network,ready,{wallet:input.wallet,deadline,representative:true,fullOnly:true});
        for(const t of ready){
          const row=result.records.find(r=>r.chain_id===t.chain_id&&r.address===t.token_address.toLowerCase());
          const quote=t.dex_pools[0]?.cashout_quote;
          if(quote?.status==='quoted'&&quote.partial_input===false){row.status='quoted';row.quote=quote;}
          else row.reason=Date.now()>=deadline?'Quote budget reached':'Selected pool quote unavailable';
        }
      }
    }catch(error){result.status='partial';result.error=h.safeError(error);}
    save(result);
  }
  if(result.records.length<tokens.length||result.records.some(r=>r.status!=='quoted'))result.status='partial';
  save(result);return result;
}
if(require.main===module){
  const input=JSON.parse(fs.readFileSync(process.argv[2])),output=process.argv[3];
  collect(input,result=>{fs.writeFileSync(output+'.tmp',h.serialize(result));fs.renameSync(output+'.tmp',output);})
    .then(()=>process.exit(0)).catch(()=>process.exit(1));
}
module.exports={collect};
