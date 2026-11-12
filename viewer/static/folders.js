'use strict';
/* Organization and saved-record navigation only. No discovery on a read. */
const FolderUI=(()=>{
  let scope=null,draft=null,busy=false,memberPage=0,shownMembers=[],cachedOverview=null;
  const empty={revision:0,folders:[],assignments:{},unfiled_count:0};
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
    $('manage-folders').textContent=scope&&scope!=='unfiled'?'Manage folder':'Manage folders';
    $('home-scope-name').textContent=scope?label(scope):'All wallets';
    $('home-folder-empty').hidden=!scope||!view()||!!wallets().length;
    $('home-view-all').href=path('tokens');
    for(const link of document.querySelectorAll('[data-view="home"],[data-view="tokens"]'))link.href=path(link.dataset.view);
    if(selectedView==='home'){
      document.title=scope?label(scope)+' · Kira Wallet':'Home · Kira Wallet';
      $('home-heading').querySelector('h1').textContent=scope?label(scope):'Your portfolio';
      $('home-description').textContent=scope?'Saved balances and estimates for the wallets in this folder.':'Saved balances, prices and coverage. Refresh when you need a new observation.';
      if(scope){$('home-empty').hidden=true;$('setup-path').hidden=true;$('home-summary').hidden=!view();}
    }
    const current=typeof currentWallet==='function'?currentWallet():null;
    if(scope&&selectedView==='wallet'&&current&&(saved.assignments[current.key]||'unfiled')!==scope){navigate('#/wallet/'+current.key);return;}
    if(current)$('wallet-folder-name').textContent=label(saved.assignments[current.key]||'unfiled');
    if(!busy&&draft&&$('folder-manager').open&&saved.revision!==draft.revision){$('folder-manager-stale').hidden=false;}
    if(typeof KiraSelect!=='undefined')KiraSelect.refresh();
  }
  function openSearch(){
    if(!state)return;
    $('find-wallet-query').value='';renderSearch();$('find-wallet-dialog').showModal();$('find-wallet-query').focus();
  }
  function renderSearch(){
    const result=KiraFolders.find(state?.wallets||[],$('find-wallet-query').value);
    $('find-wallet-count').textContent=result.total?(result.total+' matching wallet'+(result.total===1?'':'s')+(result.total>20?' · First 20 shown. Refine your search.':'')):'No saved wallet matches this name or address.';
    $('find-wallet-results').innerHTML=result.rows.map(w=>`<li><button type="button" data-find-wallet="${escapeHTML(w.key)}"><span class="card-wallet-icon">${folderGlyph}</span><span><strong>${escapeHTML(w.name)}</strong><small>${escapeHTML(w.address)}</small></span><span class="finder-folder">${escapeHTML(label(data().assignments[w.key]||'unfiled'))}</span></button></li>`).join('');
  }
  async function write(operation,input){
    const result=await submitOperation(operation,input,{refresh:false});
    state.wallet_folders=await readAPI('/api/folders');render();
    if(operation==='folder.delete'&&scope===input.folder_id){navigate('#/home');readRoute();}
    await poll();await loadRoute(true);
    return result;
  }
  function capture(id){
    memberPage=0;
    draft=id?{id,revision:data().revision,selected:new Set((state?.wallets||[]).filter(w=>data().assignments[w.key]===id).map(w=>w.key)),dirty:false}:null;
    if(draft)draft.original=new Set(draft.selected);
    $('folder-manager-stale').hidden=true;$('folder-member-search').value='';$('folder-manager-error').textContent='';
    $('folder-editor').hidden=!draft;
    $('folder-save-footer').hidden=!draft;
    $('folder-create-panel').open=!data().folders.length;
    $('folder-manage-select').innerHTML=data().folders.map(f=>`<option value="${f.id}">${escapeHTML(f.name)}</option>`).join('');
    $('folder-manage-select').disabled=!data().folders.length;
    if(draft){$('folder-manage-select').value=id;$('folder-rename-value').value=label(id);$('folder-open-overview').href=folderPath(id);renderMembers();}
    else{$('folder-member-list').innerHTML='';}
    if(typeof KiraSelect!=='undefined')KiraSelect.refresh();
  }
  function openManager(id=scope,create=false){
    if(!localSession?.controls||!state||busy)return;
    capture(data().folders.some(f=>f.id===id)?id:data().folders[0]?.id);
    $('folder-manager').showModal();
    if(create||!draft){$('folder-create-panel').open=true;$('folder-create-name').focus();}else $('folder-member-search').focus();
  }
  function allMatches(){return matchingWallets(state?.wallets||[],$('folder-member-search').value);}
  function draftCount(){
    if(!draft)return;
    draft.dirty=draft.selected.size!==draft.original.size||[...draft.selected].some(key=>!draft.original.has(key));
    $('folder-selected-count').textContent=draft.selected.size+' wallets selected';
    $('folder-members-save').textContent=busy?'Saving…':'Save wallets ('+draft.selected.size+')';
    $('folder-members-save').disabled=busy||!draft.dirty||draft.selected.size>1000;
    $('folder-manage-select').disabled=busy||draft.dirty;
    $('folder-draft-note').textContent=draft.selected.size>1000?'Choose up to 1,000 wallets per action.':draft.dirty?'Unsaved wallet changes. Save or reload before switching folders.':'Each wallet belongs to one folder. Selecting a wallet from another folder moves it here.';
    if(typeof KiraSelect!=='undefined')KiraSelect.refresh();
  }
  function sourceText(key,selected){const previous=data().assignments[key];return previous&&previous!==draft.id?(selected?'Moves from ':'')+label(previous):previous===draft.id?(selected?'In this folder':'Moves to Unfiled'):(selected?'Moves from Unfiled':'Unfiled');}
  function renderMembers(){
    if(!draft)return;
    const matches=allMatches(),pages=Math.max(1,Math.ceil(matches.length/50));memberPage=Math.min(memberPage,pages-1);shownMembers=matches.slice(memberPage*50,memberPage*50+50);
    $('folder-member-list').innerHTML=shownMembers.map(w=>`<label class="folder-member"><input type="checkbox" data-folder-wallet="${escapeHTML(w.key)}" ${draft.selected.has(w.key)?'checked':''} ${busy?'disabled':''}><span><strong>${escapeHTML(w.name)}</strong><small>${escapeHTML(w.address)}</small></span><span class="folder-member-source">${escapeHTML(sourceText(w.key,draft.selected.has(w.key)))}</span></label>`).join('')||'<p class="panel-empty">No wallets match this search.</p>';
    $('folder-member-page').textContent=matches.length?((memberPage*50+1)+'–'+Math.min((memberPage+1)*50,matches.length)+' of '+matches.length):'No matches';
    $('folder-member-prev').disabled=busy||memberPage===0;$('folder-member-next').disabled=busy||memberPage===pages-1;
    $('folder-member-select-all').textContent='Select all matches ('+matches.length+')';$('folder-member-select-all').disabled=busy||matches.length>1000||!matches.length;
    draftCount();
  }
  async function change(action){
    if(busy)return;busy=true;$('folder-manager-error').textContent='';$('folder-manager-fields').disabled=true;if(draft)draftCount();
    try{await action();}
    catch(error){$('folder-manager-error').textContent=error.message;}
    finally{busy=false;$('folder-manager-fields').disabled=false;if(draft){renderMembers();$('folder-manager-stale').hidden=data().revision===draft.revision;}}
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
    $('create-folder-nav').addEventListener('click',()=>openManager(null,true));$('manage-folders').addEventListener('click',()=>openManager());$('empty-folder-manage').addEventListener('click',()=>openManager());
    $('folder-manager-reload').addEventListener('click',()=>change(async()=>{state.wallet_folders=await readAPI('/api/folders');capture(data().folders.some(f=>f.id===draft?.id)?draft.id:data().folders[0]?.id);render();}));
    $('folder-open-overview').addEventListener('click',()=>$('folder-manager').close());
    $('folder-manage-select').addEventListener('change',event=>capture(event.target.value));
    $('folder-create-form').addEventListener('submit',event=>{event.preventDefault();change(async()=>{if(draft?.dirty)throw Error('Save or reload wallet changes before creating another folder.');const created=await write('folder.create',{name:$('folder-create-name').value,expected_revision:data().revision});$('folder-create-name').value='';capture(created.folder_id);});});
    $('folder-rename-form').addEventListener('submit',event=>{event.preventDefault();change(async()=>{const result=await write('folder.rename',{folder_id:draft.id,name:$('folder-rename-value').value,expected_revision:draft.revision});draft.revision=result.revision;$('folder-manager-stale').hidden=true;});});
    $('folder-members-form').addEventListener('submit',event=>{event.preventDefault();change(async()=>{const id=draft.id;await write('folder.setMembers',{folder_id:id,wallets:[...draft.selected],expected_revision:draft.revision});capture(id);toast('Folder wallets saved');});});
    $('folder-member-search').addEventListener('input',()=>{memberPage=0;renderMembers();});
    $('folder-member-list').addEventListener('change',event=>{const box=event.target.closest('[data-folder-wallet]');if(!box)return;box.checked?draft.selected.add(box.dataset.folderWallet):draft.selected.delete(box.dataset.folderWallet);draft.dirty=true;box.closest('label').querySelector('.folder-member-source').textContent=sourceText(box.dataset.folderWallet,box.checked);draftCount();});
    $('folder-member-select-all').addEventListener('click',()=>{for(const wallet of allMatches())draft.selected.add(wallet.key);draft.dirty=true;renderMembers();});
    $('folder-member-clear').addEventListener('click',()=>{draft.selected.clear();draft.dirty=true;renderMembers();});
    $('folder-member-prev').addEventListener('click',()=>{memberPage--;renderMembers();});$('folder-member-next').addEventListener('click',()=>{memberPage++;renderMembers();});
    $('folder-remove').addEventListener('click',()=>{$('folder-remove-name').textContent=label(draft.id);$('folder-remove-dialog').showModal();});
    formAction($('folder-remove-form'),$('folder-remove-error'),async()=>{const id=draft.id;await write('folder.delete',{folder_id:id,expected_revision:draft.revision});$('folder-remove-dialog').close();capture(data().folders[0]?.id);if(scope===id)navigate('#/home');});
    $('wallet-folder-button').addEventListener('click',openMove);
    formAction($('folder-move-form'),$('folder-move-error'),async()=>{const dialog=$('folder-move-dialog');await write('folder.assign',{folder_id:$('folder-move-select').value,wallets:[dialog.dataset.wallet],expected_revision:Number(dialog.dataset.revision)});dialog.close();});
    render();
  }
  window.addEventListener('DOMContentLoaded',init);
  return {get id(){return scope;},route,path,folderPath,label,wallets,view,acceptOverview,breadcrumb,walletPath,render,prepareAdd,afterAdd};
})();
