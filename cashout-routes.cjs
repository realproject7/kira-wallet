'use strict';
// Bounded, read-only liquidation paths. Every next input comes from the previous
// quoted output. A finite search never establishes that all routes were found.
const {formatUnits}=require('viem');
const catalog=require('./sources/known-tokens.json').tokens;
const terminalAssets=new Set(catalog.filter(t=>['USDC','USDC.e','USDT','USDT0','DAI','WETH','WBNB','WAVAX','WMATIC'].includes(t.symbol)).map(t=>t.chain_id+':'+t.address.toLowerCase()));
const terminal=(chain,address)=>terminalAssets.has(chain+':'+address.toLowerCase());
const address=value=>typeof value==='string'&&/^0x[0-9a-fA-F]{40}$/.test(value);
const integer=value=>{try{if(!/^(0|[1-9][0-9]{0,77})$/.test(String(value)))return null;const n=BigInt(value);return n<2n**256n?n:null;}catch{return null;}};

function validLeg(quote,input,amount,block,hash) {
  const used=integer(quote?.input_amount_raw),out=integer(quote?.output_amount_raw),decimals=quote?.output_decimals;
  return quote?.status==='quoted'&&address(quote.input_address)&&quote.input_address.toLowerCase()===input.toLowerCase()
    &&used>0n&&used<=amount&&integer(quote.holding_amount_raw)===amount&&out>0n&&address(quote.output_address)&&Number.isInteger(decimals)&&decimals>=0&&decimals<=255
    &&quote.output_amount===formatUnits(out,decimals)&&String(quote.block_number)===String(block)&&quote.block_hash===hash
    &&quote.route_fees_included===true&&quote.price_impact_included===true&&quote.gas_included===false&&!!quote.observed_at
    &&(quote.kind!=='mintclub_burn'||quote.funded===true&&integer(quote.reserve_balance_raw)>=out);
}

function seedQuotes(token) {
  const quotes=(token.dex_pools||[]).map(p=>p.cashout_quote).filter(Boolean).map(q=>({...q,input_address:token.token_address}));
  const mint=token.mintclub,full=mint?.wallet_full_burn;
  if(full&&full.gas_included===false&&!mint.wallet_full_burn_error)quotes.push({status:'quoted',kind:'mintclub_burn',input_address:token.token_address,
    input_amount_raw:String(token.wallet_balance_raw),holding_amount_raw:String(token.wallet_balance_raw),
    output_address:mint.reserve_token,output_amount_raw:String(full.net_refund_raw),output_amount:full.net_refund,
    output_decimals:mint.reserve_decimals,block_number:String(mint.block_number),block_hash:mint.block_hash,
    observed_at:mint.observed_at,route_fees_included:true,price_impact_included:true,gas_included:false,
    funded:mint.funded,reserve_balance_raw:String(mint.reserve_balance_raw),royalty_raw:String(full.royalty_raw),
    execution_verified:false,transfer_tax_included:false,source_url:mint.source_url});
  return quotes;
}

function representativeQuote(token, routes=token.liquidation_routes||[]) {
  const holding=integer(token.wallet_balance_raw),block=String(token.balance_block_number),hash=token.balance_block_hash;
  if(!holding)return null;
  for(const route of routes){
    let input=token.token_address,amount=holding;
    const visited=new Set([input.toLowerCase()]),pools=new Set();
    const legs=route.legs;
    if(!Array.isArray(legs)||!legs.length)continue;
    if(legs.every(leg=>{
      if(!validLeg(leg,input,amount,block,hash))return false;
      const output=leg.output_address.toLowerCase(),pool=leg.pool?.toLowerCase();
      if(visited.has(output)||pool&&pools.has(pool))return false;
      visited.add(output);if(pool)pools.add(pool);input=output;amount=integer(leg.output_amount_raw);return true;
    })&&terminal(token.chain_id,input)&&route.output_address?.toLowerCase()===input&&integer(route.output_amount_raw)===amount&&integer(route.holding_amount_raw)===holding)return route;
  }
  return seedQuotes(token).find(q=>validLeg(q,token.token_address,holding,block,hash)&&terminal(token.chain_id,q.output_address))||null;
}

async function expandRoutes(token,quoteAsset,{state,save=()=>{},maxLegs=4,maxNodes=32,maxBranches=4,maxSteps=Infinity,rootOnly=false,representative=false}={}) {
  const holding=integer(token.wallet_balance_raw),block=String(token.balance_block_number),hash=token.balance_block_hash;
  if(!holding||!address(token.token_address)||!/^0x[0-9a-fA-F]{64}$/.test(hash||''))throw new Error('Pinned route holding unavailable');
  const identity=JSON.stringify([token.chain_id,token.token_address.toLowerCase(),token.token_type,holding.toString(),block,hash]);
  if(state&&state.identity!==identity)throw new Error('Liquidation route checkpoint does not match the pinned holding');
  if(state&&(!Array.isArray(state.pending)||!Array.isArray(state.routes)||!Array.isArray(state.unknown)||!Number.isSafeInteger(state.expanded)||state.expanded<0
      ||state.root_quotes!==undefined&&!Array.isArray(state.root_quotes)
      ||state.pending.some(node=>!address(node.address)||!integer(node.amount)||!Array.isArray(node.legs)||node.legs.length>=maxLegs||!Array.isArray(node.visited))))throw new Error('Invalid liquidation route frontier');
  const finishRepresentative=()=>{
    if(!representative||!representativeQuote(token,state.routes))return false;
    state.pending=[];state.root_retry_pending=false;
    state.unknown=[...new Set([...state.unknown,'One representative route is recorded. Alternative routes and the best achievable output remain unverified.'])];save(state);return true;
  };
  if(state&&finishRepresentative())return state;
  // Pool verification can add root quotes after an early burn-only pass. A
  // completed empty frontier must not hide those new amount-specific seeds.
  const seeds=seedQuotes(token),signature=JSON.stringify(seeds.map(q=>[q.status,q.kind,q.pool?.toLowerCase(),q.input_amount_raw,q.holding_amount_raw,
    q.output_address?.toLowerCase(),q.output_amount_raw,q.output_decimals,q.output_amount,q.block_number,q.block_hash,q.funded,q.reserve_balance_raw,
    q.route_fees_included,q.price_impact_included,q.gas_included]).sort((a,b)=>JSON.stringify(a).localeCompare(JSON.stringify(b))));
  if(state&&state.seed_signature!==signature)state=null;
  state=state||{identity,pending:[{address:token.token_address.toLowerCase(),amount:holding.toString(),legs:[],visited:[token.token_address.toLowerCase()]}],routes:[],unknown:[],expanded:0};
  state.seed_signature=signature;
  save(state);
  // A verified member can lack a root burn quote after a bulk detail/refund
  // failure. Recover it through the normal paced, pinned read lane. Existing
  // routes survive retries and successful root evidence survives restart.
  const recoverRoot=token.mintclub_membership_status==='verified'&&!seeds.some(q=>q.kind==='mintclub_burn'&&validLeg(q,token.token_address,holding,block,hash));
  if(recoverRoot&&!state.root_recovery_done){
    state.root_retry_pending=true;save(state);
    const recovered=await quoteAsset(token.token_address,holding,{mintOnly:true,knownMember:true});
    state.root_quotes=recovered.filter(q=>validLeg(q,token.token_address,holding,block,hash));
    state.root_retry_pending=recovered.some(q=>q.retryable===true);
    state.root_recovery_done=!state.root_retry_pending;
    state.root_error_kind=recovered.find(q=>q.retryable)?.failure_kind||null;
    if(state.root_quotes.length&&!state.pending.some(node=>node.legs.length===0))
      state.pending.unshift({address:token.token_address.toLowerCase(),amount:holding.toString(),legs:[],visited:[token.token_address.toLowerCase()]});
    state.unknown=[...new Set([...state.unknown,...recovered.filter(q=>q.status!=='quoted').map(q=>q.reason).filter(Boolean)])];save(state);
  }
  let steps=0;
  while(state.pending.length&&steps<maxSteps){
    const node=state.pending[0];
    if(rootOnly&&node.legs.length)break;
    if(state.expanded>=maxNodes){state.unknown.push('Bounded route node limit reached; other liquidation paths remain unknown.');state.pending=[];save(state);break;}
    // Leave the current node on the frontier if a time budget interrupts its
    // reads. Successful RPC evidence and earlier route prefixes are retained.
    const quotes=node.legs.length?await quoteAsset(node.address,BigInt(node.amount)):[...seeds,...(state.root_quotes||[])];
    const valid=quotes.filter(q=>validLeg(q,node.address,BigInt(node.amount),block,hash));
    if(valid.length!==quotes.length)state.unknown.push('Some route quotes failed or did not match the pinned amount and fee contract.');
    if(!valid.length)state.unknown.push('No qualified amount-specific route at a recorded asset; absence is unproven.');
    if(!valid.length&&(node.legs.length===0&&state.root_retry_pending||quotes.some(q=>q.retryable===true))){save(state);break;}
    valid.sort((a,b)=>Number(terminal(token.chain_id,b.output_address))-Number(terminal(token.chain_id,a.output_address)));
    if(valid.length>maxBranches)state.unknown.push('Bounded route branch limit reached; other routes remain unknown.');
    for(const quote of valid.slice(0,representative?1:maxBranches)){
      const output=quote.output_address.toLowerCase(),legs=[...node.legs,quote];
      const repeatedPool=quote.pool&&node.legs.some(leg=>leg.pool?.toLowerCase()===quote.pool.toLowerCase());
      if(node.visited.includes(output)||repeatedPool){state.unknown.push('Cyclic or reused-pool path not composed from unchanged pool states.');continue;}
      if(terminal(token.chain_id,output)){
        const route={status:'quoted',kind:'liquidation_path',input_amount_raw:legs[0].input_amount_raw,
        holding_amount_raw:holding.toString(),output_address:output,output_amount_raw:quote.output_amount_raw,output_amount:quote.output_amount,
        output_decimals:quote.output_decimals,block_number:block,block_hash:hash,observed_at:quote.observed_at,
        route_fees_included:true,price_impact_included:true,gas_included:false,execution_verified:false,transfer_tax_included:false,legs};
        const key=r=>JSON.stringify(r.legs.map(q=>[q.kind,q.pool?.toLowerCase(),q.input_address.toLowerCase(),q.input_amount_raw,q.output_address.toLowerCase(),q.output_amount_raw]));
        if(!state.routes.some(r=>key(r)===key(route)))state.routes.push(route);
      }
      else if(legs.length>=maxLegs)state.unknown.push('Bounded liquidation leg limit reached; terminal cash proceeds remain unknown.');
      else state.pending.push({address:output,amount:quote.output_amount_raw,legs,visited:[...node.visited,output]});
    }
    state.pending.shift();state.expanded++;steps++;state.unknown=[...new Set(state.unknown)];save(state);
    if(finishRepresentative())break;
  }
  return state;
}
module.exports={terminal,validLeg,seedQuotes,representativeQuote,expandRoutes};
