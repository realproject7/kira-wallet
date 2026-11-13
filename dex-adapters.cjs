'use strict';
// Official factory identities, shared by discovery and amount-specific quotes.
const records=require('./sources/dex-adapters.json').records;
function venue(pool){
 const name=String(pool.venue||'').toLowerCase();
 if(['pancakeswap','pancakeswap-v2','pancakeswap-v3'].includes(name))return 'pancakeswap';
 if(['aero','aero-slipstream','aerodrome','aerodrome-slipstream'].includes(name))return 'aero';
 return name;
}
function adapter(chain,pool,factory){return records.find(r=>r.chain_id===chain&&r.venue===venue(pool)&&r.factory.toLowerCase()===factory?.toLowerCase());}
function supported(chain,pool){
 if(!/^0x[0-9a-fA-F]{40}$/.test(pool.pool||''))return false;
 const labels=pool.version_labels||[];
 if(venue(pool)==='pancakeswap')return chain===56&&labels.some(v=>['v2','v3'].includes(v))&&!labels.some(v=>/infinity|stable/i.test(v));
 return venue(pool)==='aero'&&records.some(r=>r.chain_id===chain&&r.venue==='aero');
}
function concentrated(pool){return (pool.version_labels||[]).some(v=>['v3','slipstream','cl','aero-cl'].includes(v));}
module.exports={records,venue,adapter,supported,concentrated};
