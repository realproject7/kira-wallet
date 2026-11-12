(function(root){
  'use strict';
  const fold=value=>String(value||'').trim().toLocaleLowerCase();
  function parse(parts){
    if(parts[0]!=='folder')return {id:null,parts};
    if(!/^(?:[0-9a-f]{32}|unfiled)$/.test(parts[1]||''))return {id:null,parts:['home']};
    return {id:parts[1],parts:parts.length>2?parts.slice(2):['home']};
  }
  function members(wallets,catalog,id){return !id?wallets:wallets.filter(w=>(catalog.assignments[w.key]||'unfiled')===id);}
  function find(wallets,query='',limit=20){
    const text=fold(query),cap=Math.min(50,Math.max(1,limit)),buckets=[[],[],[]];let total=0;
    for(const wallet of wallets){
      const values=[wallet.name,wallet.key,wallet.address,...(wallet.tags||[])].map(fold);
      if(text&&!values.some(value=>value.includes(text)))continue;
      total++;
      const rank=!text?2:values.includes(text)?0:fold(wallet.name).startsWith(text)?1:2;
      if(buckets[rank].length<cap)buckets[rank].push(wallet);
    }
    return {total,rows:buckets.flat().slice(0,cap)};
  }
  const api={parse,members,find};
  if(typeof module!=='undefined')module.exports=api;else root.KiraFolders=api;
})(typeof window!=='undefined'?window:this);
