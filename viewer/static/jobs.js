'use strict';
let localSession=null, jobList=[], jobsSignature='', localPolling=false;
let discoverySettingsRevision='';
const pendingActions=new Set();
const jobLabels={'wallet.add':'Wallet research','wallet.refresh':'Holdings refresh','prices.refresh':'Price refresh','wallet.setTags':'Wallet names','settings.rpc':'RPC settings','settings.discovery':'Token discovery'};
const stageLabels={queued:'Waiting to start',starting:'Opening saved evidence',registered:'Wallet registered',discovery:'Token discovery',chain:'Checking on-chain holdings',dex_discovery:'Checking markets',token_images:'Preparing token artwork',published:'Evidence saved',failed:'Research stopped',stopped:'Research stopped',interrupted:'Ready for recovery'};
async function localAPI(path,options={}){
  const response=await fetch(path,{cache:'no-store',...options,headers:{'X-Kira-Session':localSession?.token||'',...options.headers},signal:options.signal||AbortSignal.timeout(12000)});
  if(response.status===403){localSession=null;throw new Error('The local session changed. Reopen this action after reconnecting.');}
  const data=await response.json();if(!response.ok)throw new Error(data.error?.message||'The local action could not be completed.');return data;
}
async function submitOperation(operation,input){
  const fingerprint=JSON.stringify({operation,input});if(pendingActions.has(fingerprint))throw new Error('This request is already being submitted.');
  pendingActions.add(fingerprint);
  const storageKey='kira-request:'+fingerprint;
  const key=sessionStorage.getItem(storageKey)||crypto.randomUUID();sessionStorage.setItem(storageKey,key);
  try{
    const result=await localAPI('/api/operations',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({schema_version:1,operation,input,idempotency_key:key})});
    sessionStorage.removeItem(storageKey);toast('Saved '+(jobLabels[operation]||'job').toLowerCase());await pollJobs();return result;
  }finally{pendingActions.delete(fingerprint);}
}
function refreshControlState(){
  const enabled=localSession?.controls===true;
  $('research-controls').hidden=!enabled;$('empty-add-wallet').hidden=!enabled;$('wallet-actions').hidden=!enabled;
  $('service-mode').textContent=enabled?'Local controls':'Watch only';
  const sample=state?.demo===true;
  for(const id of ['open-wallet','empty-add-wallet','refresh-wallet','refresh-prices']){
    const active=id.startsWith('refresh')&&jobList.some(j=>['queued','running'].includes(j.state)&&j.input.wallet===selectedWallet);
    $(id).disabled=(sample&&id.startsWith('refresh'))||active||(id==='refresh-prices'&&!currentWallet()?.analysed_at);
    $(id).title=sample?'Sample research cannot contact providers.':active?'A research job is already active for this wallet.':'';
  }
  $('discovery-refresh').disabled=$('refresh-wallet').disabled;
  if(typeof renderWatching==='function')renderWatching();
}
let jobsPage=1, jobsConnected=true, lastJobsPoll=null;
function renderJobs(){
  const active=jobList.filter(KiraView.active);
  $('activity-count').textContent=active.length||'';
  $('jobs-summary').textContent=active.length?active.length+' in progress':jobList.length+(jobList.length===1?' saved job':' saved jobs');
  $('jobs-freshness').textContent=!localSession?.controls?'Activity needs a local control session.':!jobsConnected?'Reconnecting. Last recorded states shown.':lastJobsPoll?'Checked '+stamp(lastJobsPoll):'Loading saved jobs…';
  const filter=$('job-filter').value;
  const filtered=jobList.filter(j=>filter==='all'||(filter==='active'?KiraView.active(j):filter==='attention'?['partial','interrupted','failed'].includes(j.state):j.state===filter));
  const pages=Math.max(1,Math.ceil(filtered.length/20));jobsPage=Math.min(jobsPage,pages);
  $('jobs-page').textContent=jobsPage+' / '+pages;$('jobs-prev').disabled=jobsPage===1;$('jobs-next').disabled=jobsPage===pages;
  const rows=filtered.slice((jobsPage-1)*20,jobsPage*20);
  $('jobs-list').innerHTML=rows.map(j=>{
    const presentation=KiraView.jobPresentation(j,Date.now(),jobsConnected);
    const counts=j.events?.at(-1)?.counts||{},context=j.events?.at(-1)?.context;
    const evidence=[...Object.entries(counts).filter(([name])=>name!=='block_number').map(([name,count])=>`${name.replaceAll('_',' ')} ${count}`),...(context?.block_number?['block '+context.block_number]:[])].join(' · ');
    const controls=KiraView.active(j)?`<button class="quiet-button" data-job-action="cancel" data-job-id="${escapeHTML(j.job_id)}" ${j.cancel_requested?'disabled':''}>${j.cancel_requested?'Stopping…':'Stop'}</button>`:['interrupted','failed','cancelled'].includes(j.state)?`<button class="quiet-button" data-job-action="resume" data-job-id="${escapeHTML(j.job_id)}">Resume saved work</button>`:'';
    const link=j.input.wallet||j.input.address;
    const name=state?.wallets.find(w=>w.key===link?.toLowerCase())?.name||(j.operation==='wallet.add'?j.input.tag:null);
    const recorded=(j.events||[]).map(event=>{const context=event.context;const detail=Object.entries(event.counts||{}).filter(([name])=>name!=='block_number').map(([name,value])=>name.replaceAll('_',' ')+': '+value).join(' · ');return `<li><strong>${escapeHTML(stageLabels[event.stage]||event.stage)}</strong><span>${stamp(event.observed_at)} · ${escapeHTML(detail)}${context?.block_number?' · block '+escapeHTML(context.block_number):''}</span></li>`;}).join('');
    const stages=recorded?`<details class="job-stages"><summary>Recorded stages · ${j.events.length}</summary><ol>${recorded}</ol></details>`:'';
    return `<article class="job-row"><div class="job-identity"><span class="job-state ${escapeHTML(j.state)}">${presentation.spinner?'<span class="spinner" aria-hidden="true"></span>':''}${escapeHTML(presentation.label)}</span><strong>${escapeHTML(jobLabels[j.operation]||j.operation)}</strong>${link?`<a href="#/wallet/${escapeHTML(link.toLowerCase())}">${escapeHTML(name||shortAddress(link))}</a>`:''}<p>${escapeHTML(stageLabels[j.stage]||j.stage)}${j.state==='partial'?' · coverage gaps remain':''}</p><p class="job-timer" data-job-timer="${escapeHTML(j.job_id)}">${presentation.timerLabel} ${KiraView.duration(presentation.elapsed)}</p>${evidence?`<p class="job-evidence">${escapeHTML(evidence)}</p>`:''}${presentation.freshness?`<p class="job-freshness">${escapeHTML(presentation.freshness)}</p>`:''}${j.errors?.length?`<p class="job-error">${escapeHTML(j.errors[0].message)}</p>`:''}${stages}<small>Last update ${stamp(j.updated_at)} · attempt ${j.attempt} · ${escapeHTML(j.job_id.slice(0,8))}</small></div><div class="job-actions">${controls}</div></article>`;
  }).join('')||'<div class="empty"><h3>'+(!localSession?.controls?'Activity is not available in this session':'No jobs in this view')+'</h3><p>Research jobs appear here when a local action starts.</p></div>';
  $('active-work').hidden=active.length===0||selectedView==='activity';
  $('active-work').innerHTML=active.slice(0,2).map(j=>{
    const p=KiraView.jobPresentation(j,Date.now(),jobsConnected);
    return `<div><a href="#/activity"><strong>${p.spinner?'<span class="spinner" aria-hidden="true"></span>':''}${escapeHTML(p.label)} · ${escapeHTML(jobLabels[j.operation]||j.operation)}</strong><small data-job-timer="${escapeHTML(j.job_id)}">${p.timerLabel} ${KiraView.duration(p.elapsed)}</small></a><p>${escapeHTML(stageLabels[j.stage]||j.stage)}${p.freshness?' · '+escapeHTML(p.freshness):''}</p></div>`;
  }).join('')+(active.length>2?'<small>'+ (active.length-2)+' more jobs in Activity</small>':'');
  if(typeof renderBriefing==='function')renderBriefing();
  if(typeof renderWallets==='function'&&state)renderWallets();
}
function tickJobTimers(){
  if(document.hidden)return;
  document.querySelectorAll('[data-job-timer]').forEach(node=>{const job=jobList.find(j=>j.job_id===node.dataset.jobTimer);if(!job)return;const p=KiraView.jobPresentation(job,Date.now(),jobsConnected);node.textContent=p.timerLabel+' '+KiraView.duration(p.elapsed);});
}
$('job-filter').addEventListener('change',()=>{jobsPage=1;renderJobs();});
$('jobs-prev').addEventListener('click',()=>{jobsPage--;renderJobs();});
$('jobs-next').addEventListener('click',()=>{jobsPage++;renderJobs();});
setInterval(tickJobTimers,1000);
async function pollJobs(){
  if(localPolling)return;localPolling=true;
  try{
    if(!localSession){const response=await fetch('/api/session',{cache:'no-store',signal:AbortSignal.timeout(5000)});if(!response.ok)return;localSession=await response.json();}
    refreshControlState();if(!localSession.controls){renderJobs();return;}
    const jobs=await localAPI('/api/jobs');jobList=jobs;const reconnected=!jobsConnected;jobsConnected=true;lastJobsPoll=new Date().toISOString();
    const setting=jobs.filter(j=>j.operation==='settings.discovery'&&j.state==='succeeded').map(j=>j.job_id+':'+j.updated_at).sort().join(',');
    if(setting!==discoverySettingsRevision){discoverySettingsRevision=setting;if(typeof loadSetupReadiness==='function')await loadSetupReadiness();}
    const signature=JSON.stringify(jobs)+JSON.stringify(jobs.map(j=>KiraView.jobPresentation(j).quiet));if(signature!==jobsSignature||reconnected){jobsSignature=signature;renderJobs();}else{$('jobs-freshness').textContent='Checked '+stamp(lastJobsPoll);}
    refreshControlState();
  }catch{jobsConnected=false;renderJobs();}
  finally{localPolling=false;}
}
for(const button of document.querySelectorAll('[data-close-dialog]'))button.addEventListener('click',()=>button.closest('dialog').close());
function openAdd(){if(!localSession?.controls)return;if(!watchingSubmission)$('wallet-form-error').textContent='';if(typeof renderWatching==='function')renderWatching();$('wallet-dialog').showModal();if(typeof loadSetupReadiness==='function')loadSetupReadiness();}
$('open-wallet').addEventListener('click',openAdd);$('empty-add-wallet').addEventListener('click',openAdd);
function formAction(form,error,action){
  form.addEventListener('submit',async e=>{e.preventDefault();error.textContent='';const buttons=[...form.querySelectorAll('button[type="submit"]')];if(buttons.some(b=>b.disabled))return;buttons.forEach(b=>b.disabled=true);
    try{await action();}catch(failure){error.textContent=failure.message;}finally{buttons.forEach(b=>b.disabled=false);}
  });
}
$('wallet-form').addEventListener('submit',async event=>{
  event.preventDefault();if(watchingSubmitting||$('wallet-register').disabled)return;
  $('wallet-form-error').textContent='';
  try{
    const input=Object.freeze({...watchingRegistrationInput()});watchingSubmission=input;watchingSubmitting=true;renderWatching();
    await submitOperation('wallet.add',input);
    watchingSubmission=null;
    $('wallet-dialog').close();$('wallet-form').reset();watchingConnection.clearSelection();
    navigate('#/activity');
  }catch(error){$('wallet-form-error').textContent=error.message;}
  finally{watchingSubmitting=false;renderWatching();}
});
$('refresh-wallet').addEventListener('click',async()=>{try{await submitOperation('wallet.refresh',{wallet:selectedWallet});}catch(error){toast(error.message);}});
$('refresh-prices').addEventListener('click',async()=>{try{await submitOperation('prices.refresh',{wallet:selectedWallet});}catch(error){toast(error.message);}});
$('edit-tags').addEventListener('click',()=>{if(!currentWallet())return;$('tags-dialog').dataset.wallet=selectedWallet;$('tag-values').value=currentWallet().tags.join('\n');$('tags-error').textContent='';$('tags-dialog').showModal();});
formAction($('tags-form'),$('tags-error'),async()=>{await submitOperation('wallet.setTags',{wallet:$('tags-dialog').dataset.wallet,tags:$('tag-values').value.split('\n').filter(t=>t.length)});$('tags-dialog').close();});
$('jobs-list').addEventListener('click',async event=>{const button=event.target.closest('[data-job-action]');if(!button)return;button.disabled=true;try{await submitOperation('job.'+button.dataset.jobAction,{job_id:button.dataset.jobId});}catch(error){button.disabled=false;toast(error.message);}});
$('open-settings').addEventListener('click',async()=>{try{const config=await localAPI('/api/settings');$('rpc-mode').value=config.rpc.mode;$('rpc-custom-only').checked=!config.rpc.allow_public_fallback;$('rpc-references').value=Object.entries(config.rpc.chains).map(([chain,row])=>chain+' '+row.url_env).join('\n');$('discovery-provider').value=config.discovery.provider;$('discovery-key').value=config.discovery.key_env;$('settings-error').textContent='';if(typeof KiraSelect!=='undefined')KiraSelect.refresh();$('settings-dialog').showModal();if(typeof loadSetupReadiness==='function')loadSetupReadiness();}catch(error){toast(error.message);}});
$('discovery-settings').addEventListener('click',()=>$('open-settings').click());
$('wallet-discovery-settings').addEventListener('click',()=>{$('wallet-dialog').close();$('open-settings').click();});
$('discovery-refresh').addEventListener('click',()=>$('refresh-wallet').click());
formAction($('rpc-form'),$('settings-error'),async()=>{const lines=$('rpc-references').value.split('\n').filter(s=>s.trim());const chains=lines.map(line=>{const parts=line.trim().split(/\s+/);if(parts.length!==2)throw new Error('Enter a chain ID and environment variable name on each line.');return {chain_id:Number(parts[0]),url_env:parts[1]};});await submitOperation('settings.rpc',{mode:$('rpc-mode').value,allow_public_fallback:!$('rpc-custom-only').checked,chains});});
formAction($('discovery-form'),$('settings-error'),async()=>{await submitOperation('settings.discovery',{provider:$('discovery-provider').value,key_env:$('discovery-key').value});if(typeof loadSetupReadiness==='function')await loadSetupReadiness();});
$('view-history').addEventListener('click',async()=>{try{const rows=await localAPI('/api/snapshots?wallet='+encodeURIComponent(selectedWallet));$('history-list').innerHTML=rows.map(row=>`<article class="history-row"><strong>${stamp(row.compiled_at)}</strong><span>${escapeHTML(row.status==='completed'?'Saved':'Saved with coverage gaps')}</span><small>${escapeHTML(row.snapshot_id)}</small></article>`).join('')||'<p>No analysis has been published yet.</p>';$('compare-form').hidden=rows.length<2;for(const id of ['compare-before','compare-after'])$(id).innerHTML=rows.map(row=>`<option value="${escapeHTML(row.snapshot_id)}">${stamp(row.compiled_at)} · ${escapeHTML(row.snapshot_id.split('/').at(-1))}</option>`).join('');$('compare-after').selectedIndex=Math.max(0,rows.length-1);$('comparison-result').textContent='';$('history-error').textContent='';$('history-dialog').showModal();}catch(error){toast(error.message);}});
formAction($('compare-form'),$('history-error'),async()=>{const comparison=await localAPI('/api/compare?before='+encodeURIComponent($('compare-before').value)+'&after='+encodeURIComponent($('compare-after').value));$('comparison-result').innerHTML=`<p>${escapeHTML(comparison.note)}</p><p>Coverage observations ${comparison.coverage_changed?'changed':'unchanged'} · native price references ${comparison.price_references_changed?'changed':'unchanged'}</p><div class="table-wrap"><table><thead><tr><th>Token / chain</th><th>Earlier balance</th><th>Later balance</th><th>Change</th></tr></thead><tbody>${comparison.positions.map(p=>`<tr><td>${escapeHTML(p.symbol||shortAddress(p.address))} · ${p.chain_id}<small>${escapeHTML(p.presence.replaceAll('_',' '))}${p.price_references_changed?' · price references changed':''}${p.valuation_method_changed?' · method changed':''}</small></td><td>${escapeHTML(p.before_balance??'Unknown')}</td><td>${escapeHTML(p.after_balance??'Unknown')}</td><td>${escapeHTML(p.balance_delta??'Unknown')}</td></tr>`).join('')}</tbody></table></div>`;});
window.addEventListener('hashchange',()=>{refreshControlState();renderJobs();});
document.addEventListener('visibilitychange',()=>{if(!document.hidden)pollJobs();});
pollJobs();setInterval(pollJobs,2500);
