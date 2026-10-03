const fs=require('fs');
const h=require('../onchain.cjs');
const file=process.argv[2];
(async()=>{
 const snapshot=JSON.parse(fs.readFileSync(file));
 const allRows=snapshot.tokens.filter(t=>t.mintclub);
 const output=[];
 const blocks={};
 for(const chainId of [...new Set(allRows.map(t=>t.chain_id))]){
 const rows=allRows.filter(t=>t.chain_id===chainId);
 const c=await h.connect(chainId),block=await c.getBlockNumber();blocks[chainId]=block.toString();
 for(let i=0;i<rows.length;i+=5){
  const batch=rows.slice(i,i+5);
  const res=await c.multicall({contracts:batch.map(t=>({address:t.mintclub.bond_address,abi:h.bondAbi,functionName:'getDetail',args:[t.token_address]})),multicallAddress:'0xcA11bde05977b3631167028862bE2a173976CA11',batchSize:0,blockNumber:block});
  res.forEach((r,j)=>{
   if(r.status==='success'){const v=r.result.info;output.push({chain_id:chainId,address:batch[j].token_address,basis:'Curve spot',curve_price_in_reserve:h.viem.formatUnits(v.priceForNextMint,v.reserveDecimals),curve_reserve:h.viem.formatUnits(v.reserveBalance,v.reserveDecimals),reserve_symbol:v.reserveSymbol,observed_at:new Date().toISOString(),block_number:block.toString()});}
   else output.push({chain_id:chainId,address:batch[j].token_address,error:h.safeError(r.error)});
  });
 }
 }
 // MEMBER is absent from the market index. Read its verified V3 pool price.
 const member=snapshot.tokens.find(t=>t.chain_id===8453&&t.symbol.toLowerCase()==='member');
 if(member){
  const c=await h.connect(8453),block=await c.getBlockNumber();
  const pool='0xA4eFE9e8E2A2D5A2aC46805f233b8e49d0e11955';
  const abi=h.viem.parseAbi(['function slot0() view returns (uint160,int24,uint16,uint16,uint16,uint8,bool)','function token0() view returns (address)','function token1() view returns (address)']);
  const result=await c.multicall({contracts:['slot0','token0','token1'].map(functionName=>({address:pool,abi,functionName})),multicallAddress:'0xcA11bde05977b3631167028862bE2a173976CA11',batchSize:0,blockNumber:block});
  if(result.every(r=>r.status==='success')){
   const ratio=(Number(result[0].result[0])/2**96)**2;
   const price=result[1].result.toLowerCase()===member.token_address.toLowerCase()?ratio:1/ratio;
   output.push({chain_id:8453,address:member.token_address,basis:'DEX market',price_in_weth:price,source:'https://basescan.org/address/'+pool,observed_at:new Date().toISOString(),block_number:block.toString()});
  }
 }
 console.log(h.serialize({observed_at:new Date().toISOString(),blocks,tokens:output}));
})().catch(e=>{console.log(h.serialize(h.safeError(e)));process.exitCode=1;});
