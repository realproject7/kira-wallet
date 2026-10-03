'use strict';
let localSession=null, jobList=[], jobsSignature='', localPolling=false;
const pendingActions=new Set();
const jobLabels={'wallet.add':'Wallet research','wallet.refresh':'Holdings refresh','prices.refresh':'Price refresh','wallet.setTags':'Wallet names','settings.rpc':'RPC settings','settings.discovery':'Token discovery'};
const stageLabels={queued:'Waiting to start',starting:'Opening saved evidence',registered:'Wallet registered',discovery:'Token discovery',chain:'Checking on-chain holdings',dex_discovery:'Checking markets',token_images:'Preparing token artwork',published:'Evidence saved',failed:'Research stopped',stopped:'Research stopped',interrupted:'Ready for recovery'};
async function localAPI(path,options={}){
  const response=await fetch(path,{cache:'no-store',...options,headers:{'X-Kira-Session':localSession?.token||'',...options.headers},signal:AbortSignal.timeout(12000)});
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
    $(id).disabled=sample||active||(id==='refresh-prices'&&!currentWallet()?.analysed_at);
    $(id).title=sample?'Sample research cannot contact providers.':active?'A research job is already active for this wallet.':'';
  }
}
function renderJobs(){
  $('research-jobs').hidden=!localSession?.controls||jobList.length===0;
  const active=jobList.filter(j=>['queued','running'].includes(j.state));
  $('jobs-summary').textContent=active.length?active.length+' active':'Saved locally';
  $('jobs-list').innerHTML=jobList.slice(0,8).map(j=>{
    const counts=j.events?.at(-1)?.counts||{};
    const context=j.events?.at(-1)?.context;
    const evidence=[...Object.entries(counts).filter(([name])=>name!=='block_number').map(([name,count])=>`${name.replaceAll('_',' ')} ${count}`),...(context?.block_number?['block '+context.block_number]:[])].join(' · ');
    const controls=['queued','running'].includes(j.state)?`<button class="quiet-button" data-job-action="cancel" data-job-id="${escapeHTML(j.job_id)}" ${j.cancel_requested?'disabled':''}>${j.cancel_requested?'Stopping…':'Stop'}</button>`:['interrupted','failed','cancelled'].includes(j.state)?`<button class="quiet-button" data-job-action="resume" data-job-id="${escapeHTML(j.job_id)}">Resume saved work</button>`:'';
    const link=j.input.wallet||j.input.address;
    const recorded=(j.events||[]).map(event=>{const context=event.context;const detail=Object.entries(event.counts||{}).filter(([name])=>name!=='block_number').map(([name,value])=>name.replaceAll('_',' ')+': '+value).join(' · ');return `<li><strong>${escapeHTML(stageLabels[event.stage]||event.stage)}</strong><span>${escapeHTML(detail)}${context?.block_number?' · block '+escapeHTML(context.block_number):''}</span></li>`;}).join('');
    const stages=recorded?`<details class="job-stages"><summary>Recorded stages</summary><ol>${recorded}</ol></details>`:'';
    return `<article class="job-row"><div class="job-identity"><span class="job-state ${escapeHTML(j.state)}">${escapeHTML(j.state)}</span><strong>${escapeHTML(jobLabels[j.operation]||j.operation)}</strong>${link?`<a href="#/wallet/${escapeHTML(link.toLowerCase())}">${escapeHTML(shortAddress(link))}</a>`:''}<p>${escapeHTML(stageLabels[j.stage]||j.stage)}${j.state==='partial'?' · coverage gaps remain':''}</p>${evidence?`<p class="job-evidence">${escapeHTML(evidence)}</p>`:''}${j.errors?.length?`<p class="job-error">${escapeHTML(j.errors[0].message)}</p>`:''}${stages}<small>${stamp(j.updated_at)} · attempt ${j.attempt} · ${escapeHTML(j.job_id.slice(0,8))}</small></div><div class="job-actions">${controls}</div></article>`;
  }).join('');
}
async function pollJobs(){
  if(localPolling)return;localPolling=true;
  try{
    if(!localSession){const response=await fetch('/api/session',{cache:'no-store',signal:AbortSignal.timeout(5000)});if(!response.ok)return;localSession=await response.json();}
    refreshControlState();if(!localSession.controls)return;
    const jobs=await localAPI('/api/jobs');jobList=jobs;
    const signature=JSON.stringify(jobs);if(signature!==jobsSignature){jobsSignature=signature;renderJobs();}
    refreshControlState();
  }catch{if(localSession?.controls)$('jobs-summary').textContent='Reconnecting to saved jobs';}
  finally{localPolling=false;}
}
for(const button of document.querySelectorAll('[data-close-dialog]'))button.addEventListener('click',()=>button.closest('dialog').close());
function openAdd(){if(!localSession?.controls)return;$('wallet-form-error').textContent='';$('wallet-dialog').showModal();}
$('open-wallet').addEventListener('click',openAdd);$('empty-add-wallet').addEventListener('click',openAdd);
function formAction(form,error,action){
  form.addEventListener('submit',async e=>{e.preventDefault();error.textContent='';const buttons=[...form.querySelectorAll('button[type="submit"]')];if(buttons.some(b=>b.disabled))return;buttons.forEach(b=>b.disabled=true);
    try{await action();}catch(failure){error.textContent=failure.message;}finally{buttons.forEach(b=>b.disabled=false);}
  });
}
formAction($('wallet-form'),$('wallet-form-error'),async()=>{const result=await submitOperation('wallet.add',{address:$('new-wallet-address').value,tag:$('new-wallet-tag').value});$('wallet-dialog').close();$('wallet-form').reset();navigate('#/wallet/'+result.input.address.toLowerCase());});
$('refresh-wallet').addEventListener('click',async()=>{try{await submitOperation('wallet.refresh',{wallet:selectedWallet});}catch(error){toast(error.message);}});
$('refresh-prices').addEventListener('click',async()=>{try{await submitOperation('prices.refresh',{wallet:selectedWallet});}catch(error){toast(error.message);}});
$('edit-tags').addEventListener('click',()=>{if(!currentWallet())return;$('tags-dialog').dataset.wallet=selectedWallet;$('tag-values').value=currentWallet().tags.join('\n');$('tags-error').textContent='';$('tags-dialog').showModal();});
formAction($('tags-form'),$('tags-error'),async()=>{await submitOperation('wallet.setTags',{wallet:$('tags-dialog').dataset.wallet,tags:$('tag-values').value.split('\n').filter(t=>t.length)});$('tags-dialog').close();});
$('jobs-list').addEventListener('click',async event=>{const button=event.target.closest('[data-job-action]');if(!button)return;button.disabled=true;try{await submitOperation('job.'+button.dataset.jobAction,{job_id:button.dataset.jobId});}catch(error){button.disabled=false;toast(error.message);}});
$('open-settings').addEventListener('click',async()=>{try{const config=await localAPI('/api/settings');$('rpc-mode').value=config.rpc.mode;$('rpc-fallback').checked=config.rpc.allow_public_fallback;$('rpc-references').value=Object.entries(config.rpc.chains).map(([chain,row])=>chain+' '+row.url_env).join('\n');$('discovery-provider').value=config.discovery.provider;$('discovery-key').value=config.discovery.key_env;$('settings-error').textContent='';$('settings-dialog').showModal();}catch(error){toast(error.message);}});
formAction($('rpc-form'),$('settings-error'),async()=>{const lines=$('rpc-references').value.split('\n').filter(s=>s.trim());const chains=lines.map(line=>{const parts=line.trim().split(/\s+/);if(parts.length!==2)throw new Error('Enter a chain ID and environment variable name on each line.');return {chain_id:Number(parts[0]),url_env:parts[1]};});await submitOperation('settings.rpc',{mode:$('rpc-mode').value,allow_public_fallback:$('rpc-fallback').checked,chains});});
formAction($('discovery-form'),$('settings-error'),async()=>{await submitOperation('settings.discovery',{provider:$('discovery-provider').value,key_env:$('discovery-key').value});});
$('view-history').addEventListener('click',async()=>{try{const rows=await localAPI('/api/snapshots?wallet='+encodeURIComponent(selectedWallet));$('history-list').innerHTML=rows.map(row=>`<article class="history-row"><strong>${stamp(row.compiled_at)}</strong><span>${escapeHTML(row.status==='completed'?'Saved':'Saved with coverage gaps')}</span><small>${escapeHTML(row.snapshot_id)}</small></article>`).join('')||'<p>No analysis has been published yet.</p>';$('compare-form').hidden=rows.length<2;for(const id of ['compare-before','compare-after'])$(id).innerHTML=rows.map(row=>`<option value="${escapeHTML(row.snapshot_id)}">${stamp(row.compiled_at)} · ${escapeHTML(row.snapshot_id.split('/').at(-1))}</option>`).join('');$('compare-after').selectedIndex=Math.max(0,rows.length-1);$('comparison-result').textContent='';$('history-error').textContent='';$('history-dialog').showModal();}catch(error){toast(error.message);}});
formAction($('compare-form'),$('history-error'),async()=>{const comparison=await localAPI('/api/compare?before='+encodeURIComponent($('compare-before').value)+'&after='+encodeURIComponent($('compare-after').value));$('comparison-result').innerHTML=`<p>${escapeHTML(comparison.note)}</p><p>Coverage ${comparison.coverage_changed?'changed':'unchanged'} · native price references ${comparison.price_references_changed?'changed':'unchanged'}</p><div class="table-wrap"><table><thead><tr><th>Token / chain</th><th>Earlier balance</th><th>Later balance</th><th>Change</th></tr></thead><tbody>${comparison.positions.map(p=>`<tr><td>${escapeHTML(p.symbol||shortAddress(p.address))} · ${p.chain_id}<small>${escapeHTML(p.presence.replaceAll('_',' '))}${p.price_references_changed?' · price references changed':''}${p.valuation_method_changed?' · method changed':''}</small></td><td>${escapeHTML(p.before_balance??'Unknown')}</td><td>${escapeHTML(p.after_balance??'Unknown')}</td><td>${escapeHTML(p.balance_delta??'Unknown')}</td></tr>`).join('')}</tbody></table></div>`;});
window.addEventListener('hashchange',refreshControlState);
document.addEventListener('visibilitychange',()=>{if(!document.hidden)pollJobs();});
pollJobs();setInterval(pollJobs,2500);
