const fs = require('node:fs');
const path = require('node:path');
const {spawnSync}=require('node:child_process');
const viem = require('viem');
const assets=__dirname;
const resolved=spawnSync(process.env.KIRA_PYTHON || 'python3',[path.join(assets,'kira_config.py')],{encoding:'utf8'});
if(resolved.status!==0)throw new Error('Provider configuration could not be resolved. Run kira doctor.');
const runtime=JSON.parse(resolved.stdout);
const root=runtime.data_root;
const networks=JSON.parse(fs.readFileSync(path.join(assets,'sources/rpc-candidates.json')));
const bondAbi=JSON.parse(fs.readFileSync(path.join(assets,'sources/mintclub-bond-abi.json')));
const {RpcPool,RouteRecorder}=require('./rpc-pool.cjs');
// Alchemy reads spend from one compute-unit budget below the Free plan's 300 per second.
// Other hosts keep one read in flight, a second apart.
// A 4,096-call read can take several seconds, and a read may queue behind the budget.
const pool=new RpcPool({publicUrls:networks.flatMap(n=>n.public_rpc||[]),healthFile:runtime.health_file,interval:1000,
  alchemyInterval:40,alchemySlots:8,alchemyBudget:{rate:250,capacity:1500},attemptTimeout:10000,deadline:30000});
function endpoints(chainId){return runtime.endpoints[String(chainId)] || [];}
const endpointReads=new WeakMap();
const endpointOutcomes=new WeakMap();
const clientState=new WeakMap();
function resilientTransport(chainId,urls,transport=viem.http,onSuccess=()=>{},onOutcome=()=>{},policy={}) {
  return pool.transport(chainId,urls,transport,onSuccess,onOutcome,policy);
}
function client(chainId,url,override=null,transport=viem.http,fresh=false) {
  const urls=endpoints(chainId);
  const index=url==null?0:urls.indexOf(url);
  const ordered=override|| (url==null?urls:index<0?[url]:urls.slice(index));
  const used=new Set();
  const outcomes=new RouteRecorder();
  const state={chainId,last:null,lastUrl:null,transport};
  const c=viem.createPublicClient({transport:resilientTransport(chainId,ordered,transport,(i,endpoint)=>{used.add(urls.indexOf(ordered[i]));state.last=endpoint;state.lastUrl=ordered[i];},(i,event)=>{
    const endpoint=urls.indexOf(ordered[i]),endpointClass=pool.publicUrls.has(ordered[i])?'public':'custom';
    outcomes.record(endpoint,endpointClass,event);
  },fresh?{cache:false}:{})});
  endpointOutcomes.set(c,outcomes);
  clientState.set(c,state);
  endpointReads.set(c,used);return c;
}
function peerClient(c){
  const state=clientState.get(c);
  if(!state)return null;
  // The second node is any other endpoint this run can use: not the one that answered, nor one set aside.
  const urls=endpoints(state.chainId).filter(url=>url!==state.lastUrl&&!pool.disabled(state.chainId,url));
  return urls.length&&urls.length<endpoints(state.chainId).length?client(state.chainId,undefined,urls,state.transport,true):null;
}
// An Alchemy app endpoint: its lane takes several reads at once. Other endpoints read one at a time.
function alchemyEndpoint(url){try{const u=new URL(url);return u.protocol==='https:'&&/^[a-z0-9-]+\.g\.alchemy\.com$/.test(u.hostname)&&!pool.publicUrls.has(url);}catch{return false;}}
function verificationClient(c){const state=clientState.get(c);return state?client(state.chainId,undefined,null,state.transport,true):null;}
async function connect(chainId){
  const c=client(chainId);await c.getChainId();return c;
}
// A saved block's header is read once per process. Sell estimate steps reconnect for every
// wallet, network and route; each endpoint still checks the hash before its first read there.
const pinnedHeaders=new Map();
async function snapshotBlock(c,saved=null){
  const state=clientState.get(c),key=saved&&state?state.chainId+':'+String(saved.block_number):null;
  let header=key?pinnedHeaders.get(key):null,read=false;
  if(!header){header=await c.getBlock(saved?{blockNumber:BigInt(saved.block_number)}:{blockTag:'latest'});read=true;}
  if(!state||header.number==null)throw new Error('Snapshot block identity unavailable.');
  if(saved&&header.hash!==saved.block_hash)throw new Error('Saved snapshot block is no longer canonical. Start a new holdings analysis.');
  if(key&&read)pinnedHeaders.set(key,header);
  pool.pin(state.chainId,header.number,header.hash,read?state.last:null);
  return {number:header.number,hash:header.hash,timestamp:header.timestamp};
}
const serialize=data=>JSON.stringify(data,(_,v)=>typeof v==='bigint'?v.toString():v,2);
function safeError(error){
  let message=error.shortMessage || error.message || error.name || 'RPC failure';
  for(const value of runtime.secrets)if(value)message=message.split(value).join('[redacted]');
  message=message.replace(/https?:\/\/[^\s"<>]+/g,'[RPC URL]');
  message=message.replace(/(bearer\s+)[^\s,;"<>]+/gi,'$1[redacted]');
  message=message.replace(/(authorization|api[-_]?key|bearer)([\s:=]+)[^\s,;"<>]+/gi,'$1$2[redacted]');
  const diagnostic={error_type:error.name,message:message.slice(0,500)};
  for(let cause=error,depth=0;cause&&depth<6;cause=cause.cause,depth++){
    if(Number.isInteger(cause.status))diagnostic.http_status=cause.status;
    if(Number.isInteger(cause.code))diagnostic.rpc_code=cause.code;
  }
  return diagnostic;
}
function rpcEndpointsUsed(c){return [...(endpointReads.get(c)||[])].filter(i=>i>=0).sort((a,b)=>a-b);}
function rpcRoutes(c){return endpointOutcomes.get(c)?.snapshot()||[];}
function endpointIssues(chainId){return pool.issues(chainId);}
// Each process adds one line per batch of work to the month's usage ledger; the app sums them.
function flushUsage(){
  const usage=pool.takeUsage();if(!usage.requests)return;
  const at=new Date().toISOString();
  const line={at,source:'node',job:process.env.KIRA_JOB_ID||null,batch:process.env.KIRA_BATCH_ID||null,cu:usage.cu,requests:usage.requests,methods:usage.methods};
  try{fs.mkdirSync(path.join(root,'usage'),{recursive:true,mode:0o700});fs.appendFileSync(path.join(root,'usage','alchemy-'+at.slice(0,7)+'.jsonl'),JSON.stringify(line)+'\n',{mode:0o600});}
  catch{/* Usage is an estimate for the operator; it never fails research. */}
}
process.on('exit',flushUsage);
module.exports={viem,root,assets,networks,bondAbi,endpoints,alchemyEndpoint,client,peerClient,verificationClient,connect,snapshotBlock,resilientTransport,rpcEndpointsUsed,rpcRoutes,endpointIssues,flushUsage,serialize,safeError};
