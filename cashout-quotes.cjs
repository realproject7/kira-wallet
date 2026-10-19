'use strict';
// Read-only, amount-specific pool quotes. These do not simulate token transfers.
const {parseAbi,formatUnits}=require('viem');
const v3Abi=parseAbi(['function quoteExactInputSingle((address tokenIn,address tokenOut,uint256 amountIn,uint24 fee,uint160 sqrtPriceLimitX96) params) returns (uint256 amountOut,uint160 sqrtPriceX96After,uint32 initializedTicksCrossed,uint256 gasEstimate)']);
const aeroAbi=parseAbi(['function getAmountOut(uint256 amountIn,address tokenIn) view returns (uint256)']);
const address=value=>typeof value==='string'&&/^0x[0-9a-fA-F]{40}$/.test(value);
const integer=value=>{try{if(!/^[0-9]+$/.test(String(value)))return null;return BigInt(value);}catch{return null;}};

function v2AmountOut(amount,reserveIn,reserveOut) {
  if(amount<=0n||reserveIn<=0n||reserveOut<=0n)throw new Error('Pool quote input or reserves unavailable');
  const withFee=amount*997n;
  return withFee*reserveOut/(reserveIn*1000n+withFee);
}
function inputAmounts(balance) {
  // A full-input quote can revert because of a pool's limits. Smaller inputs
  // can establish a qualifying route, but failure of this finite search never
  // proves that no other input or route can realize the threshold.
  return [...new Set([balance,...[1n,2n,3n,4n,6n,8n].map(bits=>balance>>bits)].filter(n=>n>0n))];
}
function contractRevert(error) {
  let reverted=false;
  for(let cause=error,depth=0;cause&&depth<10;cause=cause.cause,depth++) {
    if(['HttpRequestError','TimeoutError'].includes(cause.name)||cause.status||[-32005,-32603].includes(cause.code))return false;
    if(['ContractFunctionRevertedError','ExecutionRevertedError'].includes(cause.name)||cause.code===3)reverted=true;
  }
  return reverted;
}
async function quotePool(client,network,token,pool,block,blockHash,deployments,{batchRead,fullOnly=false}={}) {
  const state=pool.factory_measurement?.state||{},balance=integer(token.wallet_balance_raw);
  const unknown=reason=>({status:'unknown',reason,gas_included:false,execution_verified:false});
  if(!balance||!address(token.token_address)||!address(state.token0)||!address(state.token1)||state.token0.toLowerCase()===state.token1.toLowerCase()
      ||pool.rpc_verification?.verification!=='official_factory_verified'||!pool.factory_measurement?.active_liquidity_verified
      ||String(token.balance_block_number)!==String(block)||token.balance_block_hash!==blockHash)
    return unknown('Verified pool and same-block holding evidence required');
  const is0=state.token0.toLowerCase()===token.token_address.toLowerCase();
  if(!is0&&state.token1.toLowerCase()!==token.token_address.toLowerCase())return unknown('Pool token identity mismatch');
  const output=is0?state.token1:state.token0,measured=pool.factory_measurement;
  if(!address(measured.quote_token)||measured.quote_token.toLowerCase()!==output.toLowerCase()||!Number.isInteger(measured.quote_decimals)||measured.quote_decimals<0||measured.quote_decimals>255)
    return unknown('Output token metadata unavailable');
  const canonical=protocol=>deployments.find(d=>d.chainId===network.chain_id&&d.protocol===protocol&&d.contract===(protocol==='v2'?'UniswapV2Factory':'UniswapV3Factory')&&d.address.toLowerCase()===state.factory?.toLowerCase());
  const quoter=deployments.find(d=>d.chainId===network.chain_id&&d.protocol==='v3'&&d.contract==='QuoterV2'&&d.status==='active');
  let kind,quote,request,decode;
  if(canonical('v3')&&quoter&&Number.isInteger(state.fee)&&state.fee>=0&&state.fee<1_000_000) {
    kind='uniswap_v3_quoter';
    request=amount=>({address:quoter.address,abi:v3Abi,functionName:'quoteExactInputSingle',args:[{tokenIn:token.token_address,tokenOut:output,amountIn:amount,fee:state.fee,sqrtPriceLimitX96:0n}]});
    decode=result=>{
      // QuoterV2's default limit is MIN_SQRT_RATIO+1 / MAX_SQRT_RATIO-1
      // (Uniswap v3-core TickMath). At that boundary input can be unspent.
      if(fullOnly){
        const after=integer(result[1]);
        if(after===null||after<=4295128740n||after>=1461446703485210103287273052203988822378723970341n)
          throw Error('Full input consumption is not established at the pool price limit');
      }
      return result[0];
    };
  }else if(network.chain_id===8453&&state.factory?.toLowerCase()==='0x420dd381b31aef6683db6b902084cb0ffece40da'&&pool.venue==='aerodrome') {
    kind='aerodrome_pool';
    request=amount=>({address:pool.pool,abi:aeroAbi,functionName:'getAmountOut',args:[amount,token.token_address]});
    decode=result=>result;
  }else if(canonical('v2')&&Array.isArray(state.getReserves)) {
    const reserveIn=integer(state.getReserves[is0?0:1]),reserveOut=integer(state.getReserves[is0?1:0]);
    if(!reserveIn||!reserveOut)return unknown('Pool reserves unavailable');
    kind='uniswap_v2_reserves';quote=async amount=>v2AmountOut(amount,reserveIn,reserveOut);
  }else return unknown('Quote adapter unavailable for this verified pool');
  if(request)quote=async amount=>decode(await client.readContract({...request(amount),blockNumber:block}));
  const amounts=fullOnly?[balance]:inputAmounts(balance);let failures=0,buffer=[];
  for(let index=0;index<amounts.length;index++) {
    const amount=amounts[index];
    let result;
    try{
      // Keep the usual full-input fast path. Only fallback inputs are grouped,
      // in their original order. QuoterV2 reverts its internal pool swap, so
      // each exact-input call observes the same state in a read-only aggregate.
      if(index>0&&request&&batchRead){
        if(!buffer.length){
          const group=amounts.slice(index,index+3);
          buffer=await batchRead(group.map(request));
          if(!Array.isArray(buffer)||buffer.length!==group.length)throw Error('Malformed quote batch');
        }
        const row=buffer.shift();
        if(row.status!=='success')throw row.error||Error('Quote batch unavailable');
        result=integer(decode(row.result));
      }else result=integer(await quote(amount));
    }
    catch(error){if(error.code==='market_budget')throw error;failures++;if(contractRevert(error))continue;break;}
    if(result===null){failures++;continue;}
    if(result>0n)return {status:'quoted',kind,input_amount_raw:amount.toString(),input_amount_is_maximum:kind==='uniswap_v3_quoter',
      holding_amount_raw:balance.toString(),output_amount_raw:result.toString(),output_amount:formatUnits(result,measured.quote_decimals),
      input_address:token.token_address.toLowerCase(),pool:pool.pool,output_address:output.toLowerCase(),output_symbol:measured.quote_symbol,
      output_decimals:measured.quote_decimals,block_number:String(block),block_hash:blockHash,
      observed_at:new Date().toISOString(),route_fees_included:true,price_impact_included:true,gas_included:false,
      execution_verified:false,transfer_tax_included:false,partial_input:amount<balance,source_url:pool.source_url};
  }
  return unknown(failures?'Pool quote failed; smaller-input and other routes remain unknown':'Sampled inputs returned zero; other routes remain unknown');
}
module.exports={v2AmountOut,inputAmounts,quotePool};
