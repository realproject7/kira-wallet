const fs=require('fs');
const h=require('../onchain.cjs');
const pipeline=require('../pipeline-onchain.cjs');
async function collect(snapshot){
 const allRows=snapshot.tokens.filter(t=>t.mintclub);
 const output=[],errors=[];
 const blocks={};
 for(const chainId of [...new Set(allRows.map(t=>t.chain_id))]){
 try{
 const rows=allRows.filter(t=>t.chain_id===chainId);
 const c=await h.connect(chainId),block=(await h.snapshotBlock(c)).number;blocks[chainId]=block.toString();
 for(let i=0;i<rows.length;i+=8){
  const batch=rows.slice(i,i+8);
  const res=await pipeline.calls(c,batch.map(t=>({address:t.mintclub.bond_address,abi:h.bondAbi,functionName:'getDetail',args:[t.token_address]})),block);
  res.forEach((r,j)=>{
   if(r.status==='success'){const v=r.result.info;output.push({chain_id:chainId,address:batch[j].token_address,basis:'Curve spot',curve_price_in_reserve:h.viem.formatUnits(v.priceForNextMint,v.reserveDecimals),curve_reserve:h.viem.formatUnits(v.reserveBalance,v.reserveDecimals),reserve_token:v.reserveToken,reserve_symbol:v.reserveSymbol,funded:v.reserveBalance>0n,source:require('../market-links.cjs').mintclubUrl(chainId,batch[j].symbol,batch[j].token_type||'ERC20'),observed_at:new Date().toISOString(),block_number:block.toString()});}
   else output.push({chain_id:chainId,address:batch[j].token_address,error:h.safeError(r.error)});
  });
 }
 }catch(error){errors.push({chain_id:chainId,error:h.safeError(error)});}
 }
 return {observed_at:new Date().toISOString(),blocks,tokens:output,errors};
}
if(require.main===module)collect(JSON.parse(fs.readFileSync(process.argv[2])))
 .then(result=>console.log(h.serialize(result))).catch(e=>{console.log(h.serialize(h.safeError(e)));process.exitCode=1;});
module.exports={collect};
