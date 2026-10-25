const {test}=require('node:test'),assert=require('node:assert/strict');
const h=require('./onchain.cjs'),p=require('./pipeline-onchain.cjs');
const {collect}=require('./viewer/refresh-curve-prices.cjs');
test('an unrelated MEMBER symbol never triggers an unrelated pool read',async()=>{
 const original=h.connect;
 try{
  h.connect=async()=>assert.fail('A symbol is not a contract identity');
  assert.deepEqual((await collect({tokens:[{chain_id:8453,token_address:'0x'+'1'.repeat(40),symbol:'MEMBER'}]})).tokens,[]);
 }finally{h.connect=original;}
});
test('one failed chain preserves curve observations on other chains',async()=>{
 const original={connect:h.connect,snapshotBlock:h.snapshotBlock,calls:p.calls};
 try{
  h.connect=async cid=>{if(cid===1)throw Error('Synthetic provider failure');return {};};
  h.snapshotBlock=async()=>({number:5n});
  p.calls=async()=>[{status:'success',result:{info:{priceForNextMint:2n,reserveDecimals:0,reserveBalance:100n,
   reserveToken:'0x'+'3'.repeat(40),reserveSymbol:'FIX'}}}];
  const result=await collect({tokens:[1,8453].map(chain_id=>({chain_id,symbol:'FIX',token_type:'ERC20',
   token_address:'0x'+'1'.repeat(40),mintclub:{bond_address:'0x'+'2'.repeat(40)}}))});
  assert.equal(result.tokens.length,1);assert.equal(result.tokens[0].chain_id,8453);
  assert.equal(result.tokens[0].curve_price_in_reserve,'2');assert.equal(result.errors[0].chain_id,1);
 }finally{h.connect=original.connect;h.snapshotBlock=original.snapshotBlock;p.calls=original.calls;}
});
