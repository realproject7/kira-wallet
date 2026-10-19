const assert=require('node:assert/strict'),{mintclubUrl}=require('./market-links.cjs');
for(const [symbol,type,expected] of [['PLOT','ERC20','token/base/PLOT'],['MINIBD','ERC1155','nft/base/MINIBD'],['A/B #?','ERC20','token/base/A%2FB%20%23%3F']])assert.equal(mintclubUrl(8453,symbol,type),'https://mint.club/'+expected);
assert.equal(mintclubUrl(8453,'0x'+'1'.repeat(40)),null);assert.equal(mintclubUrl(8453,'..'),null);
const h=require('./onchain.cjs'),p=require('./pipeline-onchain.cjs'),{discover}=require('./market-discovery.cjs');
const original={connect:p.connect,calls:p.calls,snapshot:h.snapshotBlock};
(async()=>{
 p.connect=async()=>({});h.snapshotBlock=async()=>({number:123n,hash:'0x'+'a'.repeat(64)});
 p.calls=async(_,requests)=>requests.map(q=>({status:'success',result:q.args[2]===3000?'0x37428B026d346A0a938d900B5d29C2be3DE31086':h.viem.zeroAddress}));
 const t={chain_id:8453,token_type:'ERC20',token_address:'0x'+'1'.repeat(40),symbol:'RM'},saved=[];
 const r=await discover({tokens:[t],networks:[{chain_id:8453}]},x=>saved.push(structuredClone(x)));
 assert.equal(r.status,'checked');assert.equal(r.checked,r.total);assert.equal(r.markets[0].pools.length,1);
 assert.equal(r.markets[0].pools[0].fee_bps,30);assert.equal(r.markets[0].pools[0].reported_liquidity,null);
 assert.equal(r.markets[0].pools[0].factory_discovery.block_number,'123');assert.ok(saved.length>1);
 p.calls=async()=>{throw new Error('RPC unavailable');};const failed=await discover({tokens:[t],networks:[{chain_id:8453}]},()=>{});assert.equal(failed.status,'partial');
 console.log('Canonical routes and metadata-only factory discovery passed.');
})().finally(()=>{p.connect=original.connect;p.calls=original.calls;h.snapshotBlock=original.snapshot;}).catch(e=>{console.error(e);process.exitCode=1;});
