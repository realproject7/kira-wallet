'use strict';
const {test}=require('node:test'),assert=require('node:assert/strict');
const fs=require('node:fs'),os=require('node:os'),path=require('node:path');
const viem=require('viem'),{RpcPool,classify}=require('./rpc-pool.cjs');
const HASH='0x'+'a'.repeat(64),OTHER='0x'+'b'.repeat(64),A='0x'+'1'.repeat(40),B='0x'+'2'.repeat(40);
const transport=fn=>url=>()=>({request:(request,options)=>fn(url,request,options)});
const client=(pool,urls,fn,chain=1)=>viem.createPublicClient({transport:pool.transport(chain,urls,transport(fn))});
const fresh=options=>new RpcPool({interval:0,deadline:1000,attemptTimeout:200,...options});
test('Alchemy reads share a paced lane across hosts when the engine opts in',async()=>{
 const urls=['https://eth-mainnet.g.alchemy.com/v2/test-key','https://base-mainnet.g.alchemy.com/v2/test-key'];
 const pool=fresh({interval:80,alchemyInterval:10}),seen=[];
 const fn=async(url,r)=>{
  const state=pool.states.get((url===urls[0]?1:8453)+':'+url),lane=pool.families.get(state.family);
  seen.push({at:Date.now(),next:lane.next,method:r.method});
  return r.method==='eth_chainId'?(url===urls[0]?'0x1':'0x2105'):'0x7';
 };
 assert.deepEqual(await Promise.all([client(pool,[urls[0]],fn,1),client(pool,[urls[1]],fn,8453)].map(c=>c.getBlockNumber({cacheTime:0}))),[7n,7n]);
 assert.equal(pool.states.get('1:'+urls[0]).family,pool.states.get('8453:'+urls[1]).family);
 assert.equal(seen.length,4);
 assert(seen.every(row=>row.next-row.at<=10),'The send deadline uses the Alchemy interval.');
 for(let i=1;i<seen.length;i++)assert(seen[i].at-seen[i-1].at>=8,'Cross-chain reads retain shared pacing.');
});
test('an Alchemy account throttle stops queued reads on other hosts before fallback',async()=>{
 const eth='https://eth-mainnet.g.alchemy.com/v2/test-key',base='https://base-mainnet.g.alchemy.com/v2/test-key';
 const pool=fresh({alchemyInterval:10,publicUrls:['eth-public','base-public']}),seen=[];
 let entered,throttle;const started=new Promise(resolve=>{entered=resolve;});
 const fn=async(url,r)=>{
  seen.push([url,r.method]);
  if(url===eth&&r.method==='eth_blockNumber'){entered();return new Promise((_,reject)=>{throttle=()=>reject(Object.assign(new Error('Your app has exceeded its compute units per second capacity.'),{code:429}));});}
  if(r.method==='eth_chainId')return url.includes('base')?'0x2105':'0x1';return '0x9';
 };
 pool.state(1,eth,transport(fn),{}).verified=true;
 pool.state(8453,base,transport(fn),{}).verified=true;
 const first=client(pool,[eth,'eth-public'],fn,1).getBlockNumber({cacheTime:0});await started;
 const second=client(pool,[base,'base-public'],fn,8453).getBlockNumber({cacheTime:0});throttle();
 assert.deepEqual(await Promise.all([first,second]),[9n,9n]);
 assert(!seen.some(([url])=>url===base),'The queued Alchemy host never sends after the account throttle.');
 assert.equal(pool.states.get('8453:'+base).strikes,0);
 const lane=pool.families.get(pool.states.get('1:'+eth).family);
 assert.equal(lane.gate.busy,false);assert.equal(lane.gate.queue.length,0);
});
test('public, demo, spoofed and unrecognized custom endpoints retain the original pace',()=>{
 const real='https://eth-mainnet.g.alchemy.com/v2/test-key',fn=transport(async()=> '0x1');
 const opted=fresh({interval:2000,alchemyInterval:250,publicUrls:[real]});
 for(const url of [real,'https://eth-mainnet.g.alchemy.com/v2/docs-demo','https://eth-mainnet.g.alchemy.com.evil.example/v2/test-key','https://rpc.example/v2/test-key','http://eth-mainnet.g.alchemy.com/v2/test-key']){
  const state=opted.state(1,url,fn,{});assert.equal(opted.families.get(state.family).interval,2000);assert.equal(state.alchemy,false);
 }
 const unchanged=new RpcPool(),state=unchanged.state(1,real,fn,{});
 assert.equal(unchanged.families.get(state.family).interval,2000,'Unmodified pool callers retain their contract.');
});
test('chain identity is shared across clients and repeated reads',async()=>{
  const seen=[];const pool=fresh(),fn=async(url,r)=>{seen.push(r.method);return r.method==='eth_chainId'?'0x1':'0x7';};
  const a=client(pool,['a'],fn),b=client(pool,['a'],fn);
  await a.getChainId();await a.getBlockNumber({cacheTime:0});await b.request({method:'eth_getBalance',params:[A,'latest']});
  assert.equal(seen.filter(m=>m==='eth_chainId').length,1);assert.equal(seen.length,3);
  const wrong=client(fresh(),['bad'],async()=> '0x2');await assert.rejects(wrong.getChainId(),/identity mismatch/);
});
test('queued requests skip an endpoint cooled by a 200 JSON-RPC throttle',async()=>{
  const seen=[];const pool=fresh();const c=client(pool,['public','backup'],async(url,r)=>{
    seen.push([url,r.method]);if(r.method==='eth_chainId')return '0x1';
    if(url==='public')throw Object.assign(new Error('Rate limit exceeded'),{code:-32005});return '0x0';
  });
  const result=await Promise.all([A,B].map(address=>c.request({method:'eth_getBalance',params:[address,'0x7']})));
  assert.deepEqual(result,['0x0','0x0']);assert.equal(seen.filter(([u,m])=>u==='public'&&m==='eth_getBalance').length,1);
});
test('a custom backup gets a bounded attempt after two public providers',async()=>{
  const seen=[];const pool=fresh({publicUrls:['p1','p2','p3']});
  const c=client(pool,['p1','p2','p3','custom'],async(url,r)=>{
    if(r.method==='eth_chainId')return '0x1';seen.push(url);if(url!=='custom')throw Object.assign(new Error('throttled'),{status:429});return '0x9';
  });
  assert.equal(await c.getBlockNumber({cacheTime:0}),9n);assert.deepEqual(seen,['p1','p2','custom']);
});
test('slow public reads leave time for a cold custom backup including pacing',async()=>{
  const seen=[],pool=fresh({publicUrls:['p1','p2','p3'],interval:50,deadline:600,attemptTimeout:200});pool.pin(1,7n,HASH);
  const c=client(pool,['p1','p2','p3','custom'],async(url,r)=>{
    seen.push([url,r.method]);if(r.method==='eth_chainId')return '0x1';
    if(r.method==='eth_getBlockByNumber')return {number:'0x7',hash:HASH};
    if(url!=='custom')return new Promise(()=>{});return '0x9';
  });
  assert.equal(await c.request({method:'eth_getBalance',params:[A,'0x7']}),'0x9');
  assert(seen.some(([url,method])=>url==='p1'&&method==='eth_getBalance'));
  assert(seen.some(([url,method])=>url==='custom'&&method==='eth_getBalance'));
  assert.equal(pool.states.get('1:custom').gate.busy,false);
});
test('explicit payload size errors remain splittable without cooling the provider',async()=>{
  assert.equal(classify(Object.assign(new Error('Payload too large'),{code:-32005})),'size');
  assert.equal(classify(Object.assign(new Error('Quota exceeded'),{code:-32005})),'throttle');
  let calls=0;const pool=fresh(),c=client(pool,['public'],async(url,r)=>{
    if(r.method==='eth_chainId')return '0x1';calls++;
    if(r.params[0].data.length>6)throw Object.assign(new Error('Payload too large'),{code:-32005});return '0x1';
  });
  await assert.rejects(c.request({method:'eth_call',params:[{data:'0x'+'11'.repeat(8)},'latest']}),/large/);
  assert.equal(await c.request({method:'eth_call',params:[{data:'0x11'},'latest']}),'0x1');
  assert.equal(pool.states.get('1:public').until,0);assert.equal(calls,2);
});
test('cold healthy public qualification fits paced reads with a custom backup',async()=>{
 const seen=[],events=[],pool=fresh({publicUrls:['p1','p2'],interval:40,deadline:260,attemptTimeout:80});pool.pin(1,7n,HASH);
 const c=viem.createPublicClient({transport:pool.transport(1,['p1','p2','custom'],transport(async(url,r)=>{
  seen.push([url,r.method]);if(r.method==='eth_chainId')return '0x1';if(r.method==='eth_getBlockByNumber')return {number:'0x7',hash:HASH};return '0x9';
 }),()=>{},(index,event)=>events.push({index,...event}))});
 assert.equal(await c.request({method:'eth_getBalance',params:[A,'0x7']}),'0x9');
 assert(seen.every(([url])=>url==='p1'));assert.equal(pool.states.get('1:p1').strikes,0);
 assert(events.every(e=>e.outcome==='succeeded'));
});
test('a cold secondary qualifies after a fast primary rejection',async()=>{
 const seen=[],pool=fresh({publicUrls:['p1','p2'],interval:30,deadline:300,attemptTimeout:100});pool.pin(1,7n,HASH);
 const c=client(pool,['p1','p2','custom'],async(url,r)=>{
  seen.push(url);if(r.method==='eth_chainId')return url==='p1'?'0x2':'0x1';
  if(r.method==='eth_getBlockByNumber')return {number:'0x7',hash:HASH};return '0x9';
 });
 assert.equal(await c.request({method:'eth_getBalance',params:[A,'0x7']}),'0x9');
 assert(seen.includes('p2'));assert(!seen.includes('custom'));
});
test('local family contention does not penalize provider health',async()=>{
 const events=[],pool=fresh({publicUrls:['https://one.publicnode.com'],interval:30,deadline:150,attemptTimeout:50});
 const state=pool.state(1,'https://one.publicnode.com',transport(async()=> '0x1'),{});pool.families.get(state.family).next=Date.now()+200;
 const c=viem.createPublicClient({transport:pool.transport(1,['https://one.publicnode.com','custom'],transport(async(url,r)=>r.method==='eth_chainId'?'0x1':'0x9'),()=>{},(index,event)=>events.push(event))});
 assert.equal(await c.getBlockNumber({cacheTime:0}),9n);assert.equal(state.strikes,0);assert.equal(state.until,0);
 assert(events.some(e=>e.outcome==='local_timeout'&&e.reason==='qualification'));
});
test('reorgs cannot substitute a different height into hash-qualified evidence',async()=>{
  let current=HASH;const pool=fresh();pool.pin(1,7n,HASH);
  const c=client(pool,['a'],async(url,r)=>{
    if(r.method==='eth_chainId')return '0x1';
    if(r.method==='eth_getBlockByNumber')return {number:'0x7',hash:current};
    assert.deepEqual(r.params[1],{blockHash:HASH,requireCanonical:true});
    if(current!==HASH)throw new Error('Block is not canonical');return '0x1';
  });
  assert.equal(await c.request({method:'eth_getBalance',params:[A,'0x7']}),'0x1');current=OTHER;
  await assert.rejects(c.request({method:'eth_getBalance',params:[B,'0x7']}),/not canonical/);
  assert.equal(pool.cache.size,1);
});
test('unsupported hash-qualified reads fall back without numeric substitution',async()=>{
  const pool=fresh();pool.pin(1,7n,HASH);const seen=[];
  const c=client(pool,['a','b'],async(url,r)=>{
    if(r.method==='eth_chainId')return '0x1';if(r.method==='eth_getBlockByNumber')return {number:'0x7',hash:HASH};
    seen.push(r.params[1]);if(url==='a')throw Object.assign(new Error('cannot unmarshal object'),{code:-32602});return '0x3';
  });
  assert.equal(await c.request({method:'eth_getBalance',params:[A,'0x7']}),'0x3');assert(seen.every(tag=>tag.blockHash===HASH));
});
test('malformed optional health entries never block a healthy backup',async()=>{
  const root=fs.mkdtempSync(path.join(os.tmpdir(),'kira-rpc-malformed-')),healthFile=path.join(root,'health.json');
  try {
    fs.writeFileSync(healthFile,JSON.stringify({schema_version:1,entries:{bad:null,another:{until:'tomorrow'}}}));
    const pool=fresh({publicUrls:['public'],healthFile}),c=client(pool,['public','backup'],async(url,r)=>{
      if(r.method==='eth_chainId')return '0x1';if(url==='public')throw Object.assign(new Error('rate limit'),{status:429});return '0x3';
    });
    assert.equal(await c.getBlockNumber({cacheTime:0}),3n);assert.equal(Object.keys(JSON.parse(fs.readFileSync(healthFile)).entries).length,1);
  } finally {fs.rmSync(root,{recursive:true,force:true});}
});
test('method failures fall back but a contract revert does not cool a healthy provider',async()=>{
  let calls=0;const pool=fresh();const c=client(pool,['a','b'],async(url,r)=>{
    if(r.method==='eth_chainId')return '0x1';calls++;
    if(r.method==='eth_call')throw Object.assign(new Error('execution reverted'),{code:3});
    if(url==='a'&&r.method==='eth_getCode')throw Object.assign(new Error('method not found'),{code:-32601});return '0x1';
  });
  await assert.rejects(c.request({method:'eth_call',params:[{},'latest']}),/reverted/);assert.equal(calls,1);
  assert.equal(await c.request({method:'eth_getCode',params:[A,'latest']}),'0x1');
  assert.equal(await c.request({method:'eth_getBalance',params:[A,'latest']}),'0x1');
  assert.equal(pool.states.get('1:a').until,0);
});
test('fallback uses the pinned block and rejects a conflicting header',async()=>{
  const seen=[];const pool=fresh();pool.pin(1,7n,HASH);
  const c=client(pool,['a','b','c'],async(url,r)=>{
    seen.push([url,r.method,r.params]);if(r.method==='eth_chainId')return '0x1';
    if(r.method==='eth_getBlockByNumber')return {number:'0x7',hash:url==='b'?OTHER:HASH};
    if(url==='a')throw Object.assign(new Error('offline'),{status:503});return '0x5';
  });
  assert.equal(await c.request({method:'eth_getBalance',params:[A,'0x7']}),'0x5');
  assert(!seen.some(([u,m])=>u==='b'&&m==='eth_getBalance'));
  assert(seen.filter(([,m])=>m==='eth_getBalance').every(([, ,p])=>p[1].blockHash===HASH&&p[1].requireCanonical));
});
test('single-flight and immutable caches stay scoped to wallet and block hash',async()=>{
  let count=0;const pool=fresh();pool.pin(1,7n,HASH);pool.pin(1,8n,OTHER);
  const c=client(pool,['a'],async(url,r)=>{
    if(r.method==='eth_chainId')return '0x1';if(r.method==='eth_getBlockByNumber')return {number:r.params[0],hash:r.params[0]==='0x7'?HASH:OTHER};
    count++;await new Promise(resolve=>setTimeout(resolve,5));return r.params[0]===A?'0x0':'0x3';
  });
  const read=(address,block)=>c.request({method:'eth_getBalance',params:[address,block]});
  assert.deepEqual(await Promise.all([read(A,'0x7'),read(A,'0x7')]),['0x0','0x0']);assert.equal(count,1);
  await read(A,'0x7');assert.equal(count,1);await read(B,'0x7');await read(A,'0x8');assert.equal(count,3);
});
test('failed reads are evicted and stay failures rather than cached zero',async()=>{
  let fail=true,calls=0;const pool=fresh();pool.pin(1,7n,HASH);
  const c=client(pool,['a'],async(url,r)=>{
    if(r.method==='eth_chainId')return '0x1';if(r.method==='eth_getBlockByNumber')return {number:'0x7',hash:HASH};
    calls++;if(fail)throw Object.assign(new Error('offline'),{status:503});return '0x2';
  });
  await assert.rejects(c.request({method:'eth_getBalance',params:[A,'0x7']}),/offline/);assert.equal(pool.pending.size,0);assert.equal(pool.cache.size,0);
  fail=false;pool.states.get('1:a').until=0;
  assert.equal(await c.request({method:'eth_getBalance',params:[A,'0x7']}),'0x2');assert.equal(calls,2);
});
test('family pacing serializes requests across chain endpoints',async()=>{
  const urls=['https://one.publicnode.com','https://two.publicnode.com'],starts=[];let active=0,max=0;
  const pool=fresh({publicUrls:urls,interval:10});
  const fn=async(url,r)=>{starts.push(Date.now());max=Math.max(max,++active);await new Promise(resolve=>setTimeout(resolve,2));active--;return r.method==='eth_chainId'?'0x1':'0x2';};
  await Promise.all(urls.map(url=>client(pool,[url],fn).getBlockNumber({cacheTime:0})));
  assert.equal(max,1);assert(starts.slice(1).every((time,i)=>time-starts[i]>=8));
});
test('deadline aborts the real HTTP fetch and releases permits',async()=>{
  const {createServer}=require('node:http');let closed=false;
  const server=createServer((request,response)=>{
    let body='';request.on('data',chunk=>body+=chunk);request.on('end',()=>{
      const rpc=JSON.parse(body);
      if(rpc.method==='eth_chainId')response.end(JSON.stringify({jsonrpc:'2.0',id:rpc.id,result:'0x1'}));
      else response.on('close',()=>{closed=true;});
    });
  });
  await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
  const url='http://127.0.0.1:'+server.address().port,pool=fresh({deadline:150,attemptTimeout:1000});
  const c=viem.createPublicClient({transport:pool.transport(1,[url])});
  try {
    await assert.rejects(c.getBlockNumber({cacheTime:0}),/deadline/);
    await new Promise(resolve=>setTimeout(resolve,20));assert(closed);
    assert.equal(pool.states.get('1:'+url).gate.busy,false);assert.equal(pool.families.get('127.0.0.1').gate.busy,false);
  } finally { server.closeAllConnections();await new Promise(resolve=>server.close(resolve)); }
});
test('abortable queue drops cancelled work without leaked slots',async()=>{
  const pool=fresh();let releaseFirst;const held=new Promise(resolve=>releaseFirst=resolve);let count=0;
  const c=client(pool,['a'],async(url,r)=>{if(r.method==='eth_chainId')return '0x1';count++;if(count===1)await held;return '0x1';});
  const first=c.request({method:'eth_getBalance',params:[A,'latest']});
  await new Promise(resolve=>setTimeout(resolve,5));
  const cancel=new AbortController(),second=c.request({method:'eth_getBalance',params:[B,'latest']},{signal:cancel.signal});
  cancel.abort(new Error('cancelled'));await assert.rejects(second,/cancelled/);releaseFirst();await first;
  assert.equal(count,1);assert.equal(pool.states.get('1:a').gate.queue.length,0);
});
test('public cooldown survives subprocesses without URLs or private endpoint records',async()=>{
  const root=fs.mkdtempSync(path.join(os.tmpdir(),'kira-rpc-health-')),healthFile=path.join(root,'health.json');
  const pool=fresh({publicUrls:['public'],healthFile});
  const c=client(pool,['public','https://private.example/SECRET'],async(url,r)=>{if(r.method==='eth_chainId')return '0x1';throw Object.assign(new Error('rate limit'),{status:429});});
  try {
    await assert.rejects(c.getBlockNumber({cacheTime:0}));
    const saved=fs.readFileSync(healthFile,'utf8');assert(!saved.includes('SECRET'));assert(!saved.includes('public'));assert.equal(Object.keys(JSON.parse(saved).entries).length,1);
    const recovered=fresh({publicUrls:['public'],healthFile});let count=0;
    await assert.rejects(client(recovered,['public'],async()=>{count++;return '0x1';}).getBlockNumber({cacheTime:0}));assert.equal(count,0);
    assert.equal(count,0,'Reading local health creates no network probes.');
  } finally {fs.rmSync(root,{recursive:true,force:true});}
});
test('route outcomes retain public failures and custom success without endpoint values or arguments',async()=>{
 const events=[],urls=['public','https://private.example/SECRET-MARKER'];
 const pool=fresh({publicUrls:['public']});
 const c=viem.createPublicClient({transport:pool.transport(1,urls,transport(async(url,r)=>{
  if(r.method==='eth_chainId')return '0x1';if(url==='public')throw Object.assign(new Error('throttle SECRET-MARKER'),{status:429});return '0x3';
 }),()=>{},(index,event)=>events.push({index,...event}))});
 assert.equal(await c.getBlockNumber({cacheTime:0}),3n);
 assert.equal(await c.getBlockNumber({cacheTime:0}),3n);
 assert(events.some(e=>e.index===0&&e.outcome==='failed'&&e.http_status===429));
 assert(events.some(e=>e.index===0&&e.outcome==='skipped'));
 assert(events.some(e=>e.index===1&&e.outcome==='succeeded'));
 assert(!JSON.stringify(events).includes('SECRET-MARKER'));
 assert(!JSON.stringify(events).includes('params'));
});
test('provider-controlled route codes stay bounded while overflow retains failure and success counts',()=>{
 const {RouteRecorder}=require('./rpc-pool.cjs'),records=new RouteRecorder();
 for(let i=0;i<10000;i++)records.record(0,'public',{method:'eth_call',outcome:'failed',reason:'size',rpc_code:i,params:['SECRET-MARKER']});
 records.record(1,'custom',{method:'eth_call',outcome:'succeeded'});
 const rows=records.snapshot();
 assert(rows.length<=104);assert(JSON.stringify(rows).length<30000);
 assert.equal(rows.filter(r=>r.outcome==='failed').reduce((n,r)=>n+r.count,0),10000);
 assert.equal(rows.filter(r=>r.outcome==='succeeded').reduce((n,r)=>n+r.count,0),1);
 assert(rows.some(r=>r.aggregated_overflow));assert(!JSON.stringify(rows).includes('SECRET-MARKER'));
});
test('verification transport bypasses result cache and shared pending promises',async()=>{
 const pool=fresh();pool.pin(1,7n,HASH);let count=0;
 const fn=async(url,r)=>r.method==='eth_chainId'?'0x1':r.method==='eth_getBlockByNumber'?{number:'0x7',hash:HASH}:('0x'+(++count).toString(16));
 const regular=client(pool,['a'],fn);await regular.request({method:'eth_getBalance',params:[A,'0x7']});
 const verifier=viem.createPublicClient({transport:pool.transport(1,['a'],transport(fn),()=>{},()=>{},{cache:false})});
 assert.equal(await verifier.request({method:'eth_getBalance',params:[A,'0x7']}),'0x2');
 assert.equal(await regular.request({method:'eth_getBalance',params:[A,'0x7']}),'0x1');assert.equal(count,2);
});
