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
const {RpcPool}=require('./rpc-pool.cjs');
const pool=new RpcPool({publicUrls:networks.flatMap(n=>n.public_rpc||[]),healthFile:runtime.health_file});
function endpoints(chainId){return runtime.endpoints[String(chainId)] || [];}
const endpointReads=new WeakMap();
const clientState=new WeakMap();
function resilientTransport(chainId,urls,transport=viem.http,onSuccess=()=>{}) {
  return pool.transport(chainId,urls,transport,onSuccess);
}
function client(chainId,url) {
  const urls=endpoints(chainId);
  const index=url==null?0:urls.indexOf(url);
  const ordered=url==null?urls:index<0?[url]:urls.slice(index);
  const used=new Set();
  const state={chainId,last:null};
  const c=viem.createPublicClient({transport:resilientTransport(chainId,ordered,viem.http,(i,endpoint)=>{used.add(urls.indexOf(ordered[i]));state.last=endpoint;})});
  clientState.set(c,state);
  endpointReads.set(c,used);return c;
}
async function connect(chainId){
  const c=client(chainId);await c.getChainId();return c;
}
async function snapshotBlock(c,saved=null){
  const header=await c.getBlock(saved?{blockNumber:BigInt(saved.block_number)}:{blockTag:'latest'}),state=clientState.get(c);
  if(!state||header.number==null)throw new Error('Snapshot block identity unavailable.');
  if(saved&&header.hash!==saved.block_hash)throw new Error('Saved snapshot block is no longer canonical. Start a new holdings analysis.');
  pool.pin(state.chainId,header.number,header.hash,state.last);
  return {number:header.number,hash:header.hash};
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
module.exports={viem,root,assets,networks,bondAbi,endpoints,client,connect,snapshotBlock,resilientTransport,rpcEndpointsUsed,serialize,safeError};
