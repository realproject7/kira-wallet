'use strict';
// TickMath constants/formula: Uniswap v3-sdk, MIT, see THIRD_PARTY_NOTICES.md.
const Q96=1n<<96n;
const factors=['fffcb933bd6fad37aa2d162d1a594001','fff97272373d413259a46990580e213a','fff2e50f5f656932ef12357cf3c7fdcc','ffe5caca7e10e4e61c3624eaa0941cd0','ffcb9843d60f6159c9db58835c926644','ff973b41fa98c081472e6896dfb254c0','ff2ea16466c96a3843ec78b326b52861','fe5dee046a99a2a811c461f1969c3053','fcbe86c7900a88aedcffc83b479aa3a4','f987a7253ac413176f2b074cf7815e54','f3392b0822b70005940c7a398e4b70f3','e7159475a2c29b7443b29c7fa6e889d9','d097f3bdfd2022b8845ad8f792aa5825','a9f746462d870fdf8a65dc1f90e061e5','70d869a156d2a1b890bb3df62baf32f7','31be135f97d08fd981231505542fcfa6','9aa508b5b7a84e1c677de54f3e99bc9','5d6af8dedb81196699c329225ee604','2216e584f5fa1ea926041bedfe98','48a170391f7dc42444e8fa2'];
function sqrtRatioAtTick(tick){
 if(!Number.isInteger(tick)||Math.abs(tick)>887272)throw Error('Invalid position tick');
 const abs=Math.abs(tick);let ratio=1n<<128n;
 for(let i=0;i<factors.length;i++)if(abs&(1<<i))ratio=ratio*BigInt('0x'+factors[i])>>128n;
 if(tick>0)ratio=((1n<<256n)-1n)/ratio;
 return (ratio>>32n)+(ratio% (1n<<32n)?1n:0n);
}
function liquidityAmounts(liquidity,sqrtPrice,tickLower,tickUpper){
 const l=BigInt(liquidity),p=BigInt(sqrtPrice),a=sqrtRatioAtTick(tickLower),b=sqrtRatioAtTick(tickUpper);
 if(l<0n||a>=b||p<=0n||p>=(1n<<160n))throw Error('Invalid liquidity state');
 const amount0=(lo,hi)=>l*(hi-lo)*Q96/hi/lo,amount1=(lo,hi)=>l*(hi-lo)/Q96;
 return p<=a?[amount0(a,b),0n]:p>=b?[0n,amount1(a,b)]:[amount0(p,b),amount1(a,p)];
}
function v4Ticks(info){return [8n,32n].map(shift=>{const v=Number(BigInt(info)>>shift&0xffffffn);return v&0x800000?v-0x1000000:v;});}
function shareAmounts(shares,supply,reserves){
 shares=BigInt(shares);supply=BigInt(supply);
 if(shares<0n||supply<=0n||shares>supply||reserves.some(v=>BigInt(v)<0n))throw Error('Invalid share claim');
 return reserves.map(v=>BigInt(v)*shares/supply);
}
module.exports={sqrtRatioAtTick,liquidityAmounts,v4Ticks,shareAmounts};
