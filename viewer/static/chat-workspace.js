'use strict';
let chatExpanded=false, historySelection=null, historyEpoch=0;
function pendingWalletJob(wallet) {
  return jobList.find(job=>KiraView.active(job)&&['wallet.add','wallet.refresh','prices.refresh'].includes(job.operation)&&String(job.input.wallet||job.input.address||'').toLowerCase()===wallet.key);
}
function renderResearchChat() {
  const active=jobList.filter(job=>KiraView.active(job)&&['wallet.add','wallet.refresh','prices.refresh'].includes(job.operation)).sort((a,b)=>(a.state!=='running')-(b.state!=='running')||a.created_at.localeCompare(b.created_at));
  const working=Boolean(chatTurn)||active.some(job=>job.state==='running');
  $('chat-form').dataset.working=String(working);
  $('kira-panel').dataset.speaking=String(working);
  const tray=$('chat-research');tray.hidden=!active.length;
  tray.innerHTML=active.slice(0,2).map(job=>{
    const p=KiraView.jobPresentation(job,Date.now(),jobsConnected);
    const key=String(job.input.wallet||job.input.address||'').toLowerCase();
    const name=state?.wallets.find(w=>w.key===key)?.name||job.input.tag||'Wallet research';
    const counts=job.events?.at(-1)?.counts||{};
    const detail=['checked','held'].filter(k=>Number.isFinite(counts[k])).map(k=>counts[k]+' '+k).join(' · ');
    return `<a class="chat-research-row" href="#/activity"><span class="spinner" aria-hidden="true"></span><span><strong>${escapeHTML(name)}</strong><span>${escapeHTML(jobStage(job))}${detail?' · '+escapeHTML(detail):''}</span><small data-job-timer="${escapeHTML(job.job_id)}">${escapeHTML(p.timerLabel)} ${KiraView.duration(p.elapsed)}</small>${p.freshness?'<small>'+escapeHTML(p.freshness)+'</small>':''}</span><span aria-hidden="true">↗</span></a>`;
  }).join('')+(active.length>2?`<a class="text-button" href="#/activity">${active.length-2} more in Activity</a>`:'');
}
function expandChat(expand,animate=true) {
  const dock=document.querySelector('.kira-dock');const before=dock.getBoundingClientRect();chatExpanded=expand;
  dock.classList.toggle('expanded',expand);dock.setAttribute('role',expand?'dialog':'complementary');
  if(expand){dock.setAttribute('aria-modal','true');dock.setAttribute('aria-label','Expanded Kira Chat');}else {dock.removeAttribute('aria-modal');dock.setAttribute('aria-label','Kira Chat');}
  $('chat-backdrop').hidden=!expand;
  $('chat-expand').setAttribute('aria-expanded',String(expand));
  $('chat-expand').setAttribute('aria-label',expand?'Collapse chat':'Expand chat');$('chat-expand').title=expand?'Collapse chat':'Expand chat';
  $('chat-expand').innerHTML='<svg class="ui-icon" viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="'+(expand?'M3 9h6V3m6 0v6h6M9 21v-6H3m18 0h-6v6':'M9 3H3v6m12-6h6v6M3 15v6h6m12-6v6h-6')+'"/></svg>';
  for(const selector of ['.sidebar','.topbar','.workspace-tabs','.evidence-pane'])document.querySelector(selector).inert=expand;
  document.body.classList.toggle('chat-expanded',expand);
  const after=dock.getBoundingClientRect();
  if(animate&&!matchMedia('(prefers-reduced-motion: reduce)').matches&&dock.animate)dock.animate([{transform:`translate(${before.left-after.left}px,${before.top-after.top}px) scale(${before.width/after.width},${before.height/after.height})`},{transform:'none'}],{duration:240,easing:'cubic-bezier(.23,1,.32,1)'});
  $('chat-expand').focus();
}
$('chat-expand').addEventListener('click',event=>expandChat(!chatExpanded,event.detail!==0));
$('chat-backdrop').addEventListener('click',()=>expandChat(false));
document.querySelector('.kira-dock').addEventListener('click',event=>{if(chatExpanded&&event.target.closest('a[href^="#/"]'))expandChat(false,false);});
document.addEventListener('keydown',event=>{
  if(!chatExpanded||document.querySelector('dialog[open]'))return;
  if(event.key==='Escape'){event.preventDefault();expandChat(false,false);return;}
  if(event.key==='Tab'){
    const nodes=[...document.querySelector('.kira-dock').querySelectorAll('button:not([hidden]):not(:disabled),textarea:not(:disabled),a[href]')].filter(node=>node.getClientRects().length);
    if(event.shiftKey&&document.activeElement===nodes[0]){event.preventDefault();nodes.at(-1)?.focus();}
    else if(!event.shiftKey&&document.activeElement===nodes.at(-1)){event.preventDefault();nodes[0]?.focus();}
  }
});
function updateComposerReserve(){
  const scroller=$('conversation-scroll'),follow=scroller.clientHeight>0&&scroller.scrollHeight-scroller.clientHeight-scroller.scrollTop<80;
  document.querySelector('.kira-dock').style.setProperty('--composer-reserve',($('chat-form').getBoundingClientRect().height+38)+'px');
  if(follow)scroller.scrollTop=scroller.scrollHeight;
}
if(typeof ResizeObserver!=='undefined')new ResizeObserver(updateComposerReserve).observe($('chat-form'));
$('chat-history-button').addEventListener('click',async()=>{
  const epoch=++historyEpoch;historySelection=null;$('chat-history-preview').hidden=true;$('chat-history-list').hidden=false;
  $('chat-history-list').textContent='Loading conversations…';$('chat-history-error').textContent='';
  $('chat-history-note').textContent=agentState?.config?.retain_history?'Saved on this computer.':'Memory-only chats last until the app stops. Enable local saving in model settings to keep future chats.';
  $('chat-history-dialog').showModal();
  try{
    const rows=await localAPI('/api/chat/history');if(epoch!==historyEpoch)return;
    $('chat-history-list').innerHTML=rows.map(row=>`<button class="chat-history-row" type="button" data-conversation="${escapeHTML(row.id)}"><strong>${escapeHTML(row.title)}</strong><span>${escapeHTML(row.provider==='codex'?'Codex':'Claude')} · ${escapeHTML(row.updated_at?stamp(row.updated_at):'Earlier conversation')} · ${row.saved?'Saved locally':'In memory'}${row.current?' · Current':''}</span></button>`).join('')||'<p>No previous conversations yet.</p>';
  }catch(error){if(epoch===historyEpoch)$('chat-history-error').textContent=error.message;}
});
$('chat-history-dialog').addEventListener('close',()=>historyEpoch++);
$('chat-history-list').addEventListener('click',async event=>{
  const id=event.target.closest('[data-conversation]')?.dataset.conversation;if(!id)return;
  const epoch=++historyEpoch;$('chat-history-error').textContent='';
  try{
    const row=await localAPI('/api/chat/history?id='+encodeURIComponent(id));if(epoch!==historyEpoch)return;historySelection=row;
    $('chat-history-list').hidden=true;$('chat-history-preview').hidden=false;
    $('chat-history-thread').innerHTML=row.messages.map(m=>`<article class="chat-message ${m.role==='user'?'user':'assistant'}"><strong>${m.role==='user'?'YOU':'KIRA'}</strong>${m.role==='user'?'<p>'+escapeHTML(m.text)+'</p>':'<div class="markdown-body">'+KiraMarkdown.render(m.text)+'</div>'}</article>`).join('');
    $('chat-history-continue').hidden=!row.can_continue;$('chat-history-continue').disabled=Boolean(chatTurn);
    if(!row.can_continue)$('chat-history-error').textContent='Different model or wallet access. You can read this conversation here.';
  }catch(error){if(epoch===historyEpoch)$('chat-history-error').textContent=error.message;}
});
$('chat-history-back').addEventListener('click',()=>{$('chat-history-list').hidden=false;$('chat-history-preview').hidden=true;$('chat-history-error').textContent='';historySelection=null;historyEpoch++;});
$('chat-history-continue').addEventListener('click',async()=>{
  if(!historySelection?.can_continue||chatTurn||chatRequest)return;
  const id=historySelection.conversation_id;$('chat-history-continue').disabled=true;
  try{
    await agentPost('/api/chat/open',{id});chatEpoch++;chatTurn=null;chatRequest=null;chatRetry=null;
    await loadAgent();$('chat-history-dialog').close();$('conversation-scroll').scrollTop=$('conversation-scroll').scrollHeight;$('kira-draft').focus();
  }catch(error){$('chat-history-error').textContent=error.message;}finally{$('chat-history-continue').disabled=false;}
});
renderResearchChat();
