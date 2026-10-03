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
function endpoints(chainId){return runtime.endpoints[String(chainId)] || [];}
function client(chainId,url=endpoints(chainId)[0]) {
  if(!url)throw new Error('No configured RPC endpoint for this chain.');
  return viem.createPublicClient({transport:viem.http(url,{timeout:12000,retryCount:0})});
}
async function connect(chainId){
  let error;
  for(const url of endpoints(chainId)){
    try{const c=client(chainId,url);if(await c.getChainId()!==chainId)throw new Error('RPC chain identity mismatch');return c;}
    catch(e){error=e;}
  }
  throw error || new Error('No configured RPC endpoint for this chain.');
}
const serialize=data=>JSON.stringify(data,(_,v)=>typeof v==='bigint'?v.toString():v,2);
function safeError(error){
  let message=error.shortMessage || error.message || error.name || 'RPC failure';
  for(const value of runtime.secrets)if(value)message=message.split(value).join('[redacted]');
  message=message.replace(/https?:\/\/[^\s"<>]+/g,'[RPC URL]');
  message=message.replace(/(bearer\s+)[^\s,;"<>]+/gi,'$1[redacted]');
  message=message.replace(/(authorization|api[-_]?key|bearer)([\s:=]+)[^\s,;"<>]+/gi,'$1$2[redacted]');
  return {error_type:error.name,message:message.slice(0,500)};
}
module.exports={viem,root,assets,networks,bondAbi,endpoints,client,connect,serialize,safeError};
