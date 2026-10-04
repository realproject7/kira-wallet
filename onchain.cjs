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
const endpointReads=new WeakMap();
function resilientTransport(chainId,urls,transport=viem.http,onSuccess=()=>{}) {
  if(!urls.length)throw new Error('No configured RPC endpoint for this chain.');
  const choices=urls.map((url,index)=>options=>{
    const inner=transport(url,{timeout:8000,retryCount:0})(options);
    let verified=null;
    return {...inner,request:async request=>{
      if(!verified)verified=inner.request({method:'eth_chainId'}).then(id=>{
        if(Number(BigInt(id))!==chainId)throw new Error('RPC chain identity mismatch');
      }).catch(error=>{verified=null;throw error;});
      await verified;
      const result=await inner.request(request);
      if(request.method==='eth_chainId'&&Number(BigInt(result))!==chainId){verified=null;throw new Error('RPC chain identity mismatch');}
      onSuccess(index);
      return result;
    }};
  });
  return viem.fallback(choices,{rank:false,retryCount:0});
}
function client(chainId,url) {
  const urls=endpoints(chainId);
  const index=url==null?0:urls.indexOf(url);
  const ordered=url==null?urls:index<0?[url]:urls.slice(index);
  const used=new Set();
  const c=viem.createPublicClient({transport:resilientTransport(chainId,ordered,viem.http,i=>used.add(urls.indexOf(ordered[i])))});
  endpointReads.set(c,used);return c;
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
function rpcEndpointsUsed(c){return [...(endpointReads.get(c)||[])].filter(i=>i>=0).sort((a,b)=>a-b);}
module.exports={viem,root,assets,networks,bondAbi,endpoints,client,connect,resilientTransport,rpcEndpointsUsed,serialize,safeError};
