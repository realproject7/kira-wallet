'use strict';
const WalletManagement=(()=>{
 let plan=null,reviewPage=0,busy=false,archive=null,loadEpoch=0,searchTimer;
 const countLabel=n=>n+' wallet'+(n===1?'':'s');
 const info=()=>state?.wallet_management||{removed_count:0,revision:null};
 function render(){
  const n=info().removed_count,button=$('wallet-removed-open');button.hidden=!n||!localSession?.controls;
  button.textContent='Removed wallets ('+n+')';button.disabled=busy;
  $('wallet-remove-one').hidden=!localSession?.controls;
 }
 function showReview(){
  const rows=plan.wallets.slice(reviewPage*50,reviewPage*50+50),n=plan.wallets.length;
  $('wallet-remove-title').textContent='Remove '+countLabel(n)+'?';$('wallet-remove-confirm').textContent='Remove '+countLabel(n);
  $('wallet-remove-list').innerHTML=rows.map(w=>`<li><span><strong>${escapeHTML(w.name)}</strong><small title="${escapeHTML(w.address)}">${escapeHTML(w.address)}</small></span><small>${escapeHTML(FolderUI.label(state.wallet_folders.assignments[w.key]||'unfiled'))}</small></li>`).join('');
  $('wallet-remove-page').textContent=(reviewPage*50+1)+'–'+Math.min((reviewPage+1)*50,n)+' of '+n;
  $('wallet-remove-prev').disabled=busy||reviewPage===0;$('wallet-remove-next').disabled=busy||(reviewPage+1)*50>=n;
 }
 function openRemoval(selection){
  if(busy||!localSession?.controls||!selection?.wallets.length||!selection.revision)return;
  plan={wallets:[...selection.wallets],revision:selection.revision};reviewPage=0;
  $('wallet-remove-error').textContent='';$('wallet-remove-review').hidden=true;showReview();$('wallet-remove-dialog').showModal();
 }
 async function refresh(){
  await poll();
  if(selectedView==='wallet'&&!state.wallets.some(w=>w.key===selectedWallet))navigate(FolderUI.path());
  await loadRoute(true);FolderUI.refreshManager();render();
 }
 async function remove(){
  if(busy||!plan)return;const selected=plan;busy=true;$('folder-manager-fields').disabled=true;
  try{
   await submitOperation('wallet.remove',{wallets:selected.wallets.map(w=>w.key),expected_revision:selected.revision},{refresh:false});
   $('wallet-remove-dialog').close();navigate(FolderUI.path());await refresh();
   toast(countLabel(selected.wallets.length)+' removed. Restore them from Removed wallets.',7000);
  }catch(error){$('wallet-remove-review').hidden=false;throw error;}
  finally{busy=false;$('folder-manager-fields').disabled=false;render();}
 }
 function archiveSelection(){
  if(!archive)return;const n=archive.selected.size,pageSelected=archive.rows.filter(w=>archive.selected.has(w.key)).length;
  $('wallet-restore-selected').textContent=n?countLabel(n)+' selected':'No wallets selected';$('wallet-restore-clear').hidden=!n;
  $('wallet-restore-submit').textContent=n?'Restore '+countLabel(n):'Restore wallets';$('wallet-restore-submit').disabled=busy||archive.loading||!n;
  $('wallet-removed-page-check').checked=!!archive.rows.length&&pageSelected===archive.rows.length;
  $('wallet-removed-page-check').indeterminate=pageSelected>0&&pageSelected<archive.rows.length;
  $('wallet-removed-page-check').disabled=busy||archive.loading||!archive.rows.length;
 }
 function renderArchive(){
  $('wallet-removed-list').innerHTML=archive.rows.map(w=>`<label class="removed-wallet-row"><input type="checkbox" data-restore-wallet="${escapeHTML(w.key)}" aria-label="Restore ${escapeHTML(w.name)}" ${archive.selected.has(w.key)?'checked':''} ${busy?'disabled':''}><span><strong>${escapeHTML(w.name)}</strong><small title="${escapeHTML(w.address)}">${escapeHTML(w.address)}</small></span><time datetime="${escapeHTML(w.removed_at)}">${stamp(w.removed_at)}</time></label>`).join('')||'<div class="removed-wallet-empty"><strong>No removed wallets'+($('wallet-removed-query').value?' match this search':'')+'</strong><p>'+($('wallet-removed-query').value?'Try a different name or address.':'Wallets you remove from Kira will appear here.')+'</p></div>';
  $('wallet-removed-page').textContent=archive.total?(archive.offset+1)+'–'+(archive.offset+archive.rows.length)+' of '+archive.total:'0 wallets';
  $('wallet-removed-prev').disabled=busy||archive.loading||archive.offset===0;$('wallet-removed-next').disabled=busy||archive.loading||archive.next===null;
  archiveSelection();
 }
 async function loadArchive(){
  if(!archive)return;const epoch=++loadEpoch;archive.loading=true;archiveSelection();
  try{
   const page=await localAPI('/api/removed-wallets?limit=50&offset='+archive.offset+'&query='+encodeURIComponent($('wallet-removed-query').value));
   if(epoch!==loadEpoch||!$('wallet-removed-dialog').open)return;
   if(archive.revision&&archive.revision!==page.revision){archive.selected.clear();$('wallet-restore-error').textContent='The list changed. Review and select wallets again.';}
   Object.assign(archive,{rows:page.wallets,total:page.matched_count,next:page.next_offset,revision:page.revision});
  }catch(error){if(epoch===loadEpoch)$('wallet-restore-error').textContent=error.message;}
  finally{if(epoch===loadEpoch&&archive){archive.loading=false;renderArchive();}}
 }
 function openArchive(){
  if(busy)return;archive={rows:[],selected:new Map(),offset:0,next:null,total:0,revision:null,loading:true};
  $('wallet-removed-query').value='';$('wallet-restore-error').textContent='';$('wallet-removed-list').textContent='Loading removed wallets…';
  $('wallet-removed-dialog').showModal();archiveSelection();loadArchive();$('wallet-removed-query').focus();
 }
 async function restore(){
  if(busy||!archive?.selected.size)return;busy=true;$('folder-manager-fields').disabled=true;archiveSelection();
  try{
   const n=archive.selected.size;await submitOperation('wallet.restore',{wallets:[...archive.selected.keys()],expected_revision:archive.revision},{refresh:false});
   archive.selected.clear();archive.revision=null;archive.offset=0;await refresh();await loadArchive();toast(countLabel(n)+' restored.');
  }catch(error){await loadArchive();throw error;}
  finally{busy=false;$('folder-manager-fields').disabled=false;archiveSelection();render();}
 }
 function bind(form,error,action){
  form.addEventListener('submit',async event=>{event.preventDefault();if(busy)return;error.textContent='';
   const controls=[...form.querySelectorAll('button,input')];controls.forEach(el=>el.disabled=true);
   try{await action();}catch(failure){error.textContent=failure.message;}
   finally{controls.forEach(el=>el.disabled=false);if(form.id==='wallet-restore-form')renderArchive();else if(plan)showReview();}
  });
 }
 function init(){
  $('wallet-bulk-remove').addEventListener('click',()=>openRemoval(FolderUI.selection()));
  $('wallet-remove-one').addEventListener('click',()=>{const w=currentWallet();if(w)openRemoval({wallets:[w],revision:info().revision});});
  $('wallet-remove-prev').addEventListener('click',()=>{reviewPage--;showReview();});$('wallet-remove-next').addEventListener('click',()=>{reviewPage++;showReview();});
  bind($('wallet-remove-form'),$('wallet-remove-error'),remove);
  $('wallet-remove-review').addEventListener('click',async()=>{const keys=new Set(plan.wallets.map(w=>w.key));await poll();plan={wallets:state.wallets.filter(w=>keys.has(w.key)),revision:info().revision};if(!plan.wallets.length){$('wallet-remove-dialog').close();return;}reviewPage=0;showReview();$('wallet-remove-error').textContent='';$('wallet-remove-review').hidden=true;});
  $('wallet-removed-open').addEventListener('click',openArchive);
  $('wallet-removed-query').addEventListener('input',()=>{clearTimeout(searchTimer);archive.offset=0;searchTimer=setTimeout(loadArchive,200);});
  $('wallet-removed-reload').addEventListener('click',()=>{archive.offset=0;loadArchive();});
  $('wallet-removed-prev').addEventListener('click',()=>{archive.offset=Math.max(0,archive.offset-50);loadArchive();});$('wallet-removed-next').addEventListener('click',()=>{if(archive.next!==null){archive.offset=archive.next;loadArchive();}});
  $('wallet-removed-list').addEventListener('change',event=>{const box=event.target.closest('[data-restore-wallet]');if(!box||busy)return;const key=box.dataset.restoreWallet;if(box.checked&&archive.selected.size<1000)archive.selected.set(key,archive.rows.find(w=>w.key===key));else archive.selected.delete(key);box.checked=archive.selected.has(key);archiveSelection();});
  $('wallet-removed-page-check').addEventListener('change',event=>{for(const w of archive.rows){if(event.target.checked&&archive.selected.size<1000)archive.selected.set(w.key,w);else if(!event.target.checked)archive.selected.delete(w.key);}renderArchive();});
  $('wallet-restore-clear').addEventListener('click',()=>{archive.selected.clear();renderArchive();});
  $('wallet-removed-dialog').addEventListener('close',()=>{clearTimeout(searchTimer);loadEpoch++;});
  for(const id of ['wallet-remove-dialog','wallet-removed-dialog'])$(id).addEventListener('cancel',event=>{if(busy)event.preventDefault();});
  bind($('wallet-restore-form'),$('wallet-restore-error'),restore);render();
 }
 window.addEventListener('DOMContentLoaded',init);
 return {render};
})();
