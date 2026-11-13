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
  function organize(wallets,catalog,id,query='',page=0){
    const text=fold(query),matches=members(wallets,catalog,id).filter(w=>!text||[w.name,w.address,w.key,...(w.tags||[])].some(value=>fold(value).includes(text)));
    const pages=Math.max(1,Math.ceil(matches.length/50)),index=Math.max(0,Math.min(page,pages-1));
    return {matches,total:matches.length,page:index,pages,rows:matches.slice(index*50,index*50+50)};
  }
  function movable(selected,catalog,target){return target?[...selected].filter(key=>(catalog.assignments[key]||'unfiled')!==target):[];}
  function selectRange(selected,rows,anchor,key,checked,extend=false){
    const next=new Set(selected),start=rows.findIndex(w=>w.key===anchor),end=rows.findIndex(w=>w.key===key);
    const keys=extend&&start>=0&&end>=0?rows.slice(Math.min(start,end),Math.max(start,end)+1).map(w=>w.key):[key];
    for(const value of keys){if(checked){if(next.size<1000)next.add(value);}else next.delete(value);}
    return next;
  }
  const api={parse,members,find,organize,movable,selectRange};
  if(typeof module!=='undefined')module.exports=api;else root.KiraFolders=api;
})(typeof window!=='undefined'?window:this);
