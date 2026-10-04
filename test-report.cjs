const assert=require('node:assert/strict');
const {report}=require('./viewer/static/workspace-model.js');
const main=(id,value,quote=null)=>({id,environment:'mainnet',value_usd:value,exit_quote:quote});
const fixture={wallets:[{key:'first',assets:[main('spot',100000),main('redeem',2000,{output_amount:'0.02',output_symbol:'WETH'}),main('zero',100,{output_amount:'0.000'}),main('tiny',null,{output_amount:'0.'+'0'.repeat(310)+'1'}),{...main('test',9000,{output_amount:'9000'}),environment:'testnet'}]},{key:'second',assets:[main('redeem',3000,{output_amount:'0.03',output_symbol:'WETH'})]}]};
const r=report(fixture);
assert.equal(r.positions.length,5);assert.equal(r.quoted.length,4);assert.equal(r.positive.length,3);assert.equal(r.zero.length,1);assert.equal(r.unquoted.length,1);
assert.equal(r.unquoted[0].asset.id,'spot'); // A market value never proves exit proceeds.
assert.equal(r.positive[0].asset.exit_quote.output_amount,'0.02');
assert.equal(r.positive[2].wallet.key,'second'); // Shared curves and separate wallets are not summed.
assert.equal(r.positive[1].asset.id,'tiny'); // Exact positive decimals cannot underflow into zero.
assert.equal(r.recoverable_usd,undefined);
assert.equal(report({wallets:[]}).quoted.length,0);
console.log('Exit report distinguishes spot value, exact quoted output, zero, testnets and independent wallet quotes.');
