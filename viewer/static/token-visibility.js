'use strict';
/* Explicit visibility changes reuse the existing immediate policy operation. */
var TokenVisibility = (()=>{
  let busy=false,notice=0,timer=null;
  const refresh=async()=>{await poll();await loadRoute(true);};
  function dismiss(){clearTimeout(timer);$('policy-undo').hidden=true;}
  function showUndo(changes,message){
    const id=++notice,node=$('policy-undo');clearTimeout(timer);node.hidden=false;node.innerHTML='';
    const text=document.createElement('span');text.textContent=message;node.append(text);
    const undo=document.createElement('button');undo.type='button';undo.className='undo-button';undo.textContent='Undo';
    const close=document.createElement('button');close.type='button';close.className='undo-close';close.setAttribute('aria-label','Dismiss notification');close.textContent='×';
    node.append(undo,close);
    const expire=()=>{clearTimeout(timer);timer=setTimeout(()=>{if(id===notice)dismiss();},10000);};
    node.onmouseenter=()=>clearTimeout(timer);node.onmouseleave=expire;node.onfocusin=()=>clearTimeout(timer);node.onfocusout=expire;
    close.addEventListener('click',dismiss);
    undo.addEventListener('click',async()=>{
      clearTimeout(timer);undo.disabled=true;close.disabled=true;
      const result=await change(changes.map(c=>({...c,mode:c.previous})),{undo:false});
      if(id!==notice)return;
      if(result.failed.length){
        changes=result.failed.map(c=>({...c,mode:c.originalMode}));
        text.textContent=result.failed.length+' changes need retry.';undo.textContent='Retry undo';undo.disabled=false;close.disabled=false;
      }else{dismiss();toast('Changes undone.');}
    });
    expire();
  }
  async function change(changes,{undo=true,onProgress=()=>{}}={}){
    if(busy)return {succeeded:[],failed:changes};
    busy=true;
    const succeeded=[],failed=[];
    try{
      renderView();
      for(const [index,item] of changes.entries()){
        onProgress(index+1,changes.length);
        try{
          const [chain,address]=item.id.split(':');
          await submitOperation('token.policy',{chain_id:Number(chain),address,mode:item.mode},{refresh:false});
          succeeded.push(item);
        }catch(error){failed.push({...item,originalMode:item.mode,error:error.message});}
      }
      try{await refresh();}catch{toast('Reload to check the latest saved portfolio.',6000);}
      if(undo&&succeeded.length){
        const hiding=succeeded.every(c=>c.mode==='exclude');
        showUndo(succeeded,succeeded.length+' '+(succeeded.length===1?'token':'tokens')+(hiding?' hidden from your portfolio.':' restored to automatic classification.'));
      }
      if(failed.length)toast(failed.length+' changes could not be confirmed. Retry or check Hidden.',6000);
      return {succeeded,failed};
    }finally{busy=false;renderView();}
  }
  return {change,dismiss,get busy(){return busy;}};
})();

var TokenManager = (()=>{
  let active=false,rows=[],scope=null,selected=new Map(),failed=[],progress='';
  const allowed=()=>typeof localSession!=='undefined'&&localSession?.controls===true;
  function reset(){selected.clear();failed=[];progress='';}
  function sync(next,filters){
    const key=JSON.stringify(filters);
    if(scope!==key){reset();scope=key;}
    rows=next;
    if(!routeLoading&&!TokenVisibility.busy&&!failed.length){
      const ids=new Set(rows.map(a=>a.id));for(const id of selected.keys())if(!ids.has(id))selected.delete(id);
    }
  }
  function checkbox(asset){
    return `<label class="token-selection"><input type="checkbox" data-token-select="${escapeHTML(asset.id)}" aria-label="Select ${escapeHTML(asset.symbol)} on chain ${asset.chain_id}" ${selected.has(asset.id)?'checked':''} ${TokenVisibility.busy?'disabled':''}><span class="sr-only">Select token</span></label>`;
  }
  function render(){
    const button=$('manage-tokens'),bar=$('token-selection-bar');
    button.hidden=!allowed();button.textContent=active?'Done':'Manage tokens';button.setAttribute('aria-pressed',String(active));button.disabled=TokenVisibility.busy;
    for(const id of ['all-token-search','all-token-network','all-token-pricing','all-token-sort','all-token-testnets'])$(id).disabled=TokenVisibility.busy;
    document.querySelectorAll('[data-catalog-min]').forEach(button=>{button.disabled=TokenVisibility.busy;});
    if(TokenVisibility.busy){$('tokens-prev').disabled=true;$('tokens-next').disabled=true;}
    const status=$('all-token-status').value,summary=(typeof FolderUI!=='undefined'?FolderUI.view():state)?.dashboard?.asset_policy_summary||{};
    $('token-catalog-panel').setAttribute('aria-labelledby','asset-tab-'+status);
    document.querySelectorAll('[data-asset-status]').forEach(tab=>{
      const current=tab.dataset.assetStatus===status;tab.setAttribute('aria-selected',String(current));tab.tabIndex=current?0:-1;tab.disabled=TokenVisibility.busy;
    });
    document.querySelectorAll('[data-status-count]').forEach(count=>{count.textContent=$('all-token-testnets').checked?'':(summary[count.dataset.statusCount+'_count']??'');});
    $('token-status-note').textContent=({portfolio:'Hidden and review assets are excluded from portfolio totals.',review:'These reported estimates are outside your totals. Review the evidence before including an asset.',excluded:'Hidden across every registered wallet and excluded from totals. Restore applies the automatic review rules.',all:'All saved holdings. Hidden and review assets remain outside portfolio totals.'})[status];
    if(typeof FolderUI!=='undefined'&&FolderUI.id)$('token-status-note').textContent+=' Token visibility changes apply across all wallets.';
    const empty=$('all-token-empty');
    if(!$('all-token-search').value&&$('all-token-network').value==='all'&&!catalogMinimum){
      empty.querySelector('h3').textContent=({excluded:'No hidden tokens',review:'No assets need review',portfolio:'No tokens in your portfolio',all:'No recorded tokens'})[status];
      empty.querySelector('p').textContent=({excluded:'Tokens you hide appear here. Restore them whenever you want.',review:'Assets with recorded valuation warnings appear here.',portfolio:'Check Hidden or Needs review to see assets outside your portfolio.',all:'Add a wallet and refresh its holdings to start.'})[status];
    }else{empty.querySelector('h3').textContent='No tokens match these filters';empty.querySelector('p').textContent='Try another network, lower the minimum value or clear the search.';}
    bar.hidden=!active;
    if(!active)return;
    const all=rows.length>0&&rows.every(a=>selected.has(a.id)),some=rows.some(a=>selected.has(a.id));
    const restoring=status==='excluded',count=selected.size;
    bar.innerHTML=`<div class="selection-summary"><label><input type="checkbox" data-select-token-page aria-label="Select tokens on this page" ${all?'checked':''} ${TokenVisibility.busy?'disabled':''}><span>${TokenVisibility.busy?escapeHTML(progress||'Saving changes…'):count?count+' selected':'Select tokens on this page'}</span></label><span class="selection-scope">${failed.length?failed.length+' changes need retry':'This page only · every registered wallet'}</span></div><div class="selection-actions">${failed.length?'<button class="primary-button" type="button" data-retry-token-changes '+(TokenVisibility.busy?'disabled':'')+'>Retry changes</button>':`<button class="primary-button" type="button" data-apply-token-selection ${!count||TokenVisibility.busy?'disabled':''}>${restoring?'Restore selected':'Hide selected'}</button>`}<button class="quiet-button" type="button" data-clear-token-selection ${!count||TokenVisibility.busy?'disabled':''}>Clear</button></div>`;
    const selectAll=bar.querySelector('[data-select-token-page]');if(selectAll)selectAll.indeterminate=some&&!all;
  }
  function rerender(){renderCatalog();}
  function toggle(){if(TokenVisibility.busy)return;active=!active;reset();rerender();}
  async function apply(retry=false){
    const mode=$('all-token-status').value==='excluded'?'auto':'exclude';
    const changes=retry?failed:[...selected.values()].map(a=>({id:a.id,mode,previous:a.valuation_policy?.mode||'auto'}));
    if(!changes.length||TokenVisibility.busy)return;
    const result=await TokenVisibility.change(changes,{onProgress:(done,total)=>{progress=(mode==='exclude'?'Hiding ':'Restoring ')+done+' of '+total+'…';render();}});
    for(const item of result.succeeded)selected.delete(item.id);
    failed=result.failed;progress='';rerender();
  }
  $('manage-tokens').addEventListener('click',toggle);
  document.addEventListener('change',event=>{
    if(event.target.matches('[data-token-select]')){
      const asset=rows.find(a=>a.id===event.target.dataset.tokenSelect);if(!asset||TokenVisibility.busy)return;
      event.target.checked?selected.set(asset.id,asset):selected.delete(asset.id);render();
    }else if(event.target.matches('[data-select-token-page]')){
      if(TokenVisibility.busy)return;selected.clear();if(event.target.checked)rows.forEach(a=>selected.set(a.id,a));rerender();$('token-selection-bar').querySelector('[data-select-token-page]')?.focus({preventScroll:true});
    }
  });
  document.addEventListener('click',event=>{
    const tab=event.target.closest('[data-asset-status]');
    if(tab){
      if(TokenVisibility.busy)return;
      tab.focus({preventScroll:true});
      $('all-token-status').value=tab.dataset.assetStatus;reset();$('all-token-status').dispatchEvent(new Event('change',{bubbles:true}));render();return;
    }
    if(event.target.closest('[data-apply-token-selection]'))apply();
    if(event.target.closest('[data-retry-token-changes]'))apply(true);
    if(event.target.closest('[data-clear-token-selection]')&&!TokenVisibility.busy){reset();rerender();}
  });
  document.addEventListener('keydown',event=>{
    const tab=event.target.closest('[data-asset-status]');
    if(tab&&['ArrowLeft','ArrowRight','Home','End'].includes(event.key)){
      event.preventDefault();const tabs=[...document.querySelectorAll('[data-asset-status]')],index=tabs.indexOf(tab);
      const next=event.key==='Home'?0:event.key==='End'?tabs.length-1:(index+(event.key==='ArrowRight'?1:-1)+tabs.length)%tabs.length;
      if(!TokenVisibility.busy){tabs[next].click();tabs[next].focus();}
    }else if(event.key==='Escape'&&active&&!TokenVisibility.busy){active=false;reset();rerender();$('manage-tokens').focus();}
  });
  return {sync,checkbox,render,toggle,apply,get active(){return active;}};
})();
