'use strict';
/* Organization and saved-record navigation only. No discovery on a read. */
const FolderUI=(()=>{
  let scope=null,draft=null,busy=false,memberPage=0,shownMembers=[],cachedOverview=null,selectionAnchor=null,rangeClick=false,managerNotice='';
  const empty={revision:0,folders:[],assignments:{},unfiled_count:0};
  const stale=()=>!!draft&&(data().revision!==draft.revision||state?.wallet_management?.revision!==draft.walletRevision);
  const data=()=>state?.wallet_folders||empty;
  const label=id=>id==='unfiled'?'Unfiled':data().folders.find(f=>f.id===id)?.name||'Folder';
  const path=(tail='home')=>'#/'+(scope?'folder/'+scope+(tail==='home'?'':'/'+tail):tail);
  const folderPath=id=>'#/folder/'+id;
  function route(parts){const parsed=KiraFolders.parse(parts);if(scope!==parsed.id)cachedOverview=null;scope=parsed.id;return parsed.parts;}
  function wallets(){return scope&&view()?view().wallets:KiraFolders.members(state?.wallets||[],data(),scope);}
  function view(){return scope?routeData.overview?.folder_id===scope?routeData.overview:cachedOverview?.folder_id===scope&&cachedOverview.data_revision===state?.data_revision?cachedOverview:null:state;}
  function acceptOverview(value){cachedOverview=value;}
  function breadcrumb(){return scope?[{label:'Home',href:'#/home'},{label:label(scope),href:folderPath(scope)}]:[{label:'Home',href:'#/home'}];}
  function walletPath(key){return scope&&(data().assignments[key]||'unfiled')===scope?path('wallet/'+key):'#/wallet/'+key;}
  const folderGlyph='<svg class="ui-icon" viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="M3 7V5a1 1 0 0 1 1-1h5l2 3h9a1 1 0 0 1 1 1v11H3z"/></svg>';
  function render(){
    if(!state)return;
    const saved=data(),available=typeof localSession!=='undefined'&&localSession?.controls===true;
    const options=[{id:'',name:'All wallets',wallet_count:state.wallets.length},{id:'unfiled',name:'Unfiled',wallet_count:saved.unfiled_count},...saved.folders];
    $('folder-list').innerHTML=options.map(f=>`<a href="${f.id?folderPath(f.id):'#/home'}" class="folder-link" ${f.id===(scope||'')?'aria-current="page"':''} title="${escapeHTML(f.name)}"><span>${folderGlyph}<span>${escapeHTML(f.name)}</span></span><small>${f.wallet_count}</small></a>`).join('');
    $('folder-scope').innerHTML=options.map(f=>`<option value="${f.id}">${escapeHTML(f.name)} (${f.wallet_count})</option>`).join('');$('folder-scope').value=scope||'';
    for(const id of ['manage-folders','create-folder-nav','wallet-folder-button'])$(id).hidden=!available;
    $('empty-folder-manage').hidden=!available;
    $('manage-folders').textContent='Manage wallets';
    $('home-scope-name').textContent=scope?label(scope):'All wallets';
    $('home-folder-empty').hidden=!scope||!view()||!!wallets().length;
    $('home-view-all').href=path('tokens');
    for(const link of document.querySelectorAll('[data-view="home"],[data-view="tokens"]'))link.href=path(link.dataset.view);
    if(selectedView==='home'){
      document.title=scope?label(scope)+' · Kira Wallet':'Home · Kira Wallet';
      if(scope){$('home-empty').hidden=true;$('setup-path').hidden=true;$('home-summary').hidden=!view();}
    }
    const current=typeof currentWallet==='function'?currentWallet():null;
    if(scope&&selectedView==='wallet'&&current&&(saved.assignments[current.key]||'unfiled')!==scope){navigate('#/wallet/'+current.key);return;}
    if(current)$('wallet-folder-name').textContent=label(saved.assignments[current.key]||'unfiled');
    if(!busy&&draft&&$('folder-manager').open&&stale()){$('folder-manager-stale').hidden=false;$('folder-members-move').disabled=true;}
    if(typeof WalletManagement!=='undefined')WalletManagement.render();
    if(typeof KiraSelect!=='undefined')KiraSelect.refresh();
  }
  function openSearch(){
    if(!state)return;
    $('find-wallet-query').value='';renderSearch();$('find-wallet-dialog').showModal();$('find-wallet-query').focus();
  }
  function renderSearch(){
    const result=KiraFolders.find(state?.wallets||[],$('find-wallet-query').value);
    $('find-wallet-count').textContent=result.total?(result.total+' wallet'+(result.total===1?'':'s')+(result.total>20?' · first 20 shown':'')):'No saved wallet matches this name or address.';
    $('find-wallet-results').innerHTML=result.rows.map(w=>`<li><button type="button" data-find-wallet="${escapeHTML(w.key)}"><span class="card-wallet-icon">${folderGlyph}</span><span><strong>${escapeHTML(w.name)}</strong><small>${escapeHTML(w.address)}</small></span><span class="finder-folder">${escapeHTML(label(data().assignments[w.key]||'unfiled'))}</span></button></li>`).join('');
  }
  async function write(operation,input){
    const result=await submitOperation(operation,input,{refresh:false});
    state.wallet_folders=await readAPI('/api/folders');render();
    if(operation==='folder.delete'&&scope===input.folder_id){navigate('#/home');readRoute();}
    await poll();await loadRoute(true);
    return result;
  }
  const managerData=()=>draft?.saved||data();
  const managerLabel=id=>!id?'All wallets':id==='unfiled'?'Unfiled':managerData().folders.find(f=>f.id===id)?.name||'Folder';
  function capture(id=scope,keepSelection=false){
    const previous=keepSelection?draft?.selected:new Set(),saved=data(),registered=new Set((state?.wallets||[]).map(w=>w.key));
    draft={id:id==='unfiled'||saved.folders.some(f=>f.id===id)?id:null,revision:saved.revision,saved,
      walletRevision:state?.wallet_management?.revision,wallets:[...(state?.wallets||[])],selected:new Set([...(previous||[])].filter(key=>registered.has(key)))};
    memberPage=0;selectionAnchor=null;$('folder-manager-stale').hidden=true;$('folder-manager-error').textContent='';
    renderManager();$('folder-member-list').scrollTop=0;
  }
  function openManager(id=scope){
    if(!localSession?.controls||!state||busy)return;
    $('folder-member-search').value='';$('organizer-folder-search').value='';managerNotice='';capture(id);
    $('folder-manager').showModal();$('folder-member-search').focus();
  }
  function renderManagerNav(){
    if(!draft)return;
    const saved=managerData(),query=$('organizer-folder-search').value.trim().toLocaleLowerCase();
    const options=[{id:'',name:'All wallets',wallet_count:draft.wallets.length},{id:'unfiled',name:'Unfiled',wallet_count:saved.unfiled_count},...saved.folders.filter(f=>f.name.toLocaleLowerCase().includes(query))];
    $('folder-manager-nav').innerHTML=options.map(f=>`<button type="button" data-organize-folder="${f.id}" title="${escapeHTML(f.name)}" ${f.id===(draft.id||'')?'aria-current="true"':''}><span>${folderGlyph}<span>${escapeHTML(f.name)}</span></span><small>${f.wallet_count}</small></button>`).join('');
  }
  function renderManager(){
    if(!draft)return;
    renderManagerNav();
    $('folder-current-title').textContent=managerLabel(draft.id);$('folder-current-title').title=managerLabel(draft.id);
    const count=KiraFolders.members(draft.wallets,managerData(),draft.id).length;
    $('folder-current-count').textContent=count+' wallet'+(count===1?'':'s');
    $('folder-open-overview').href=draft.id?folderPath(draft.id):'#/home';
    for(const id of ['folder-rename','folder-remove'])$(id).hidden=!draft.id||draft.id==='unfiled';
    const target=$('folder-bulk-target').value;
    $('folder-bulk-target').innerHTML='<option value="">Move to folder…</option><option value="unfiled">Unfiled</option>'+managerData().folders.map(f=>`<option value="${f.id}">${escapeHTML(f.name)}</option>`).join('');
    $('folder-bulk-target').value=target==='unfiled'||managerData().folders.some(f=>f.id===target)?target:'';
    renderMembers();
  }
  function currentPage(){return KiraFolders.organize(draft.wallets,managerData(),draft.id,$('folder-member-search').value,memberPage);}
  function selectionSummary(){
    if(!draft)return;
    const count=draft.selected.size,pageSelected=shownMembers.filter(w=>draft.selected.has(w.key)).length;
    const target=$('folder-bulk-target').value,moves=KiraFolders.movable(draft.selected,managerData(),target),outdated=stale();
    $('folder-selected-count').textContent=count?count+' selected':'No wallets selected';
    $('folder-member-clear').hidden=!count;
    $('wallet-bulk-remove').disabled=busy||outdated||!count||!draft.walletRevision;
    $('folder-members-move').textContent=busy?'Moving…':moves.length?'Move '+moves.length+' wallet'+(moves.length===1?'':'s'):'Move wallets';
    $('folder-members-move').disabled=busy||outdated||!moves.length||count>1000;
    $('folder-bulk-target').disabled=busy||!count;
    const outside=count-pageSelected;
    $('folder-selection-note').textContent=count>=1000?'1,000-wallet limit. Move or clear this selection first.':count&&target&&!moves.length?'Already in '+managerLabel(target)+'. Choose another folder.':count?(outside?outside+' selected outside this page.':'Choose a destination, then move.'):(managerNotice||'');
    $('folder-page-check').checked=!!shownMembers.length&&pageSelected===shownMembers.length;
    $('folder-page-check').indeterminate=pageSelected>0&&pageSelected<shownMembers.length;
    $('folder-page-check').disabled=busy||!shownMembers.length;
    const page=currentPage();
    $('folder-select-banner').hidden=!(pageSelected===shownMembers.length&&pageSelected&&page.total>shownMembers.length);
    $('folder-select-description').textContent='All '+shownMembers.length+' wallets on this page selected.';
    $('folder-member-select-all').textContent='Select all '+page.total+' matches';
    $('folder-member-select-all').disabled=busy||count+page.matches.filter(w=>!draft.selected.has(w.key)).length>1000||page.matches.every(w=>draft.selected.has(w.key));
    if(typeof KiraSelect!=='undefined')KiraSelect.refresh();
  }
  function renderMembers(){
    if(!draft)return;
    const page=currentPage();memberPage=page.page;shownMembers=page.rows;
    $('folder-member-list').innerHTML=shownMembers.map(w=>`<label class="folder-member"><input type="checkbox" data-folder-wallet="${escapeHTML(w.key)}" aria-label="Select ${escapeHTML(w.name)}" ${draft.selected.has(w.key)?'checked':''} ${busy?'disabled':''}><span class="organizer-wallet-identity"><strong>${escapeHTML(w.name)}</strong><small title="${escapeHTML(w.address)}">${escapeHTML(w.address)}</small></span><span class="folder-member-source">${folderGlyph}<span>${escapeHTML(managerLabel(managerData().assignments[w.key]||'unfiled'))}</span></span></label>`).join('')||`<div class="organizer-empty">${folderGlyph}<h4>${$('folder-member-search').value?'No matching wallets':draft.id==='unfiled'?'All wallets are organized':'This folder is ready'}</h4><p>${$('folder-member-search').value?'Try a different name, tag or address.':draft.id==='unfiled'?'Every registered wallet has a folder.':'Choose All wallets or Unfiled to select wallets, then move them here.'}</p>${$('folder-member-search').value?'<button type="button" class="quiet-button" data-clear-organizer-search>Clear search</button>':'<button type="button" class="quiet-button" data-organize-folder="unfiled">Browse Unfiled</button>'}</div>`;
    $('folder-member-page').textContent=page.total?((memberPage*50+1)+'–'+Math.min((memberPage+1)*50,page.total)+' of '+page.total):'0 wallets';
    $('folder-member-prev').disabled=busy||memberPage===0;$('folder-member-next').disabled=busy||memberPage===page.pages-1;
    selectionSummary();
  }
  async function change(action){
    if(busy)return;busy=true;$('folder-manager-error').textContent='';$('folder-manager-fields').disabled=true;selectionSummary();
    try{await action();}
    catch(error){$('folder-manager-error').textContent=error.message;try{state.wallet_folders=await readAPI('/api/folders');}catch{}}
    finally{busy=false;$('folder-manager-fields').disabled=false;if(draft){renderMembers();$('folder-manager-stale').hidden=!stale();}}
  }
  function openName(rename=false){
    if(busy||!draft)return;
    const dialog=$('folder-name-dialog');dialog.dataset.folder=rename?draft.id:'';dialog.dataset.revision=draft.revision;
    $('folder-name-title').textContent=rename?'Rename folder':'New folder';$('folder-name-save').textContent=rename?'Save name':'Create folder';
    $('folder-name-value').value=rename?managerLabel(draft.id):'';$('folder-name-error').textContent='';dialog.showModal();$('folder-name-value').focus();
    if(rename)$('folder-name-value').select();
  }
  function openMove(){
    const wallet=currentWallet();if(!wallet||!localSession?.controls)return;
    $('folder-move-dialog').dataset.wallet=wallet.key;$('folder-move-dialog').dataset.revision=data().revision;
    $('folder-move-wallet').textContent=wallet.name;
    $('folder-move-select').innerHTML='<option value="unfiled">Unfiled</option>'+data().folders.map(f=>`<option value="${f.id}">${escapeHTML(f.name)}</option>`).join('');
    $('folder-move-select').value=data().assignments[wallet.key]||'unfiled';$('folder-move-error').textContent='';$('folder-move-dialog').showModal();
    if(typeof KiraSelect!=='undefined')KiraSelect.refresh();
  }
  function prepareAdd(){
    const previous=$('new-wallet-folder').value;
    $('new-wallet-folder').innerHTML='<option value="unfiled">Unfiled</option>'+data().folders.map(f=>`<option value="${f.id}">${escapeHTML(f.name)}</option>`).join('');
    $('new-wallet-folder').value=[...$('new-wallet-folder').options].some(o=>o.value===previous)?previous:scope&&scope!=='unfiled'?scope:'unfiled';
    if(!$('new-wallet-address').value&&!$('new-wallet-tag').value)$('new-wallet-folder').value=scope||'unfiled';
  }
  async function afterAdd(address,folder,revision){
    if(!folder||folder==='unfiled')return;
    try{await write('folder.assign',{folder_id:folder,wallets:[address],...(Number.isInteger(revision)?{expected_revision:revision}:{})});}
    catch{toast('Wallet saved. Folder assignment was not confirmed. Use Move to folder on the saved wallet.',8000);}
  }
  function init(){
    $('open-wallet-finder').addEventListener('click',openSearch);
    $('find-wallet-dialog').addEventListener('keydown',event=>{if(event.key==='Escape'&&!event.isComposing){event.preventDefault();event.stopPropagation();$('find-wallet-dialog').close();}});
    document.addEventListener('keydown',event=>{if((event.metaKey||event.ctrlKey)&&event.key.toLowerCase()==='k'&&!document.querySelector('dialog[open]')){event.preventDefault();openSearch();}});
    $('find-wallet-query').addEventListener('input',renderSearch);
    $('find-wallet-query').addEventListener('keydown',event=>{if(event.isComposing)return;const buttons=$('find-wallet-results').querySelectorAll('button');if(event.key==='ArrowDown'&&buttons.length){event.preventDefault();buttons[0].focus();}if(event.key==='Enter'&&buttons.length){event.preventDefault();buttons[0].click();}});
    $('find-wallet-results').addEventListener('keydown',event=>{const buttons=[...$('find-wallet-results').querySelectorAll('button')],index=buttons.indexOf(event.target.closest('button'));if(index<0)return;if(event.key==='ArrowDown'||event.key==='ArrowUp'){event.preventDefault();const next=index+(event.key==='ArrowDown'?1:-1);if(next<0)$('find-wallet-query').focus();else buttons[Math.min(next,buttons.length-1)].focus();}});
    $('find-wallet-results').addEventListener('click',event=>{const button=event.target.closest('[data-find-wallet]');if(button){$('find-wallet-dialog').close();navigate('#/wallet/'+button.dataset.findWallet);}});
    $('folder-scope').addEventListener('change',event=>navigate(event.target.value?folderPath(event.target.value):'#/home'));
    $('create-folder-nav').addEventListener('click',()=>openManager());$('manage-folders').addEventListener('click',()=>openManager());$('empty-folder-manage').addEventListener('click',()=>openManager());
    $('folder-manager-reload').addEventListener('click',()=>change(async()=>{state.wallet_folders=await readAPI('/api/folders');capture(draft.id,true);render();}));
    $('folder-open-overview').addEventListener('click',()=>$('folder-manager').close());
    function selectFolder(event){const button=event.target.closest('[data-organize-folder]');if(!button||busy)return;draft.id=button.dataset.organizeFolder||null;memberPage=0;selectionAnchor=null;$('folder-member-search').value='';renderManager();$('folder-member-list').scrollTop=0;}
    $('folder-manager-nav').addEventListener('click',selectFolder);
    $('organizer-folder-search').addEventListener('input',renderManagerNav);
    $('folder-new').addEventListener('click',()=>openName());$('folder-rename').addEventListener('click',()=>openName(true));
    formAction($('folder-name-form'),$('folder-name-error'),async()=>{
      if(busy)return;
      const dialog=$('folder-name-dialog'),id=dialog.dataset.folder;busy=true;$('folder-manager-fields').disabled=true;
      try{
        const result=await write(id?'folder.rename':'folder.create',{...(id?{folder_id:id}:{}),name:$('folder-name-value').value,expected_revision:Number(dialog.dataset.revision)});
        capture(draft.id,true);if(!id)$('folder-bulk-target').value=result.folder_id;
        managerNotice=id?'Folder name updated.':'Folder created. Select wallets and move them here.';renderManager();dialog.close();
      }finally{busy=false;$('folder-manager-fields').disabled=false;selectionSummary();}
    });
    $('folder-members-form').addEventListener('submit',event=>{event.preventDefault();if($('folder-members-move').disabled)return;change(async()=>{
      const target=$('folder-bulk-target').value,keys=KiraFolders.movable(draft.selected,managerData(),target),destination=managerLabel(target);
      if(!keys.length||draft.selected.size>1000)return;
      await write('folder.assign',{folder_id:target,wallets:keys,expected_revision:draft.revision});
      managerNotice=keys.length+' wallet'+(keys.length===1?'':'s')+' moved to '+destination+'.';capture(draft.id);toast(managerNotice);
    });});
    $('folder-bulk-target').addEventListener('change',selectionSummary);
    $('folder-member-search').addEventListener('input',()=>{memberPage=0;selectionAnchor=null;renderMembers();$('folder-member-list').scrollTop=0;});
    $('folder-member-list').addEventListener('click',event=>{selectFolder(event);if(event.target.closest('[data-clear-organizer-search]')){$('folder-member-search').value='';memberPage=0;renderMembers();$('folder-member-search').focus();}if(event.target.matches('[data-folder-wallet]'))rangeClick=event.shiftKey;});
    $('folder-member-list').addEventListener('change',event=>{const box=event.target.closest('[data-folder-wallet]');if(!box||busy)return;draft.selected=KiraFolders.selectRange(draft.selected,shownMembers,selectionAnchor,box.dataset.folderWallet,box.checked,rangeClick);selectionAnchor=box.dataset.folderWallet;managerNotice='';if(rangeClick){rangeClick=false;renderMembers();}else{box.checked=draft.selected.has(box.dataset.folderWallet);selectionSummary();}});
    $('folder-page-check').addEventListener('change',event=>{for(const wallet of shownMembers){if(event.target.checked){if(draft.selected.size<1000)draft.selected.add(wallet.key);}else draft.selected.delete(wallet.key);}renderMembers();});
    $('folder-member-select-all').addEventListener('click',()=>{const page=currentPage();if(draft.selected.size+page.matches.filter(w=>!draft.selected.has(w.key)).length>1000)return;for(const wallet of page.matches){if(draft.selected.size<1000)draft.selected.add(wallet.key);}renderMembers();});
    $('folder-member-clear').addEventListener('click',()=>{draft.selected.clear();selectionAnchor=null;renderMembers();});
    $('folder-member-prev').addEventListener('click',()=>{memberPage--;selectionAnchor=null;renderMembers();$('folder-member-list').scrollTop=0;});$('folder-member-next').addEventListener('click',()=>{memberPage++;selectionAnchor=null;renderMembers();$('folder-member-list').scrollTop=0;});
    $('folder-remove').addEventListener('click',()=>{$('folder-remove-dialog').dataset.folder=draft.id;$('folder-remove-dialog').dataset.revision=draft.revision;$('folder-remove-name').textContent=managerLabel(draft.id);$('folder-remove-dialog').showModal();});
    formAction($('folder-remove-form'),$('folder-remove-error'),async()=>{if(busy)return;busy=true;$('folder-manager-fields').disabled=true;try{const dialog=$('folder-remove-dialog');await write('folder.delete',{folder_id:dialog.dataset.folder,expected_revision:Number(dialog.dataset.revision)});dialog.close();capture(null,true);managerNotice='Folder removed. Its wallets are now Unfiled.';selectionSummary();}finally{busy=false;$('folder-manager-fields').disabled=false;selectionSummary();}});
    $('wallet-folder-button').addEventListener('click',openMove);
    formAction($('folder-move-form'),$('folder-move-error'),async()=>{const dialog=$('folder-move-dialog');await write('folder.assign',{folder_id:$('folder-move-select').value,wallets:[dialog.dataset.wallet],expected_revision:Number(dialog.dataset.revision)});dialog.close();});
    render();
  }
  function selection(){return draft?{wallets:draft.wallets.filter(w=>draft.selected.has(w.key)),revision:draft.walletRevision}:null;}
  function refreshManager(){capture(draft?.id??scope);}
  window.addEventListener('DOMContentLoaded',init);
  return {get id(){return scope;},route,path,folderPath,label,wallets,view,acceptOverview,breadcrumb,walletPath,render,prepareAdd,afterAdd,selection,refreshManager};
})();
