'use strict';
let localSession=null, jobList=[], jobsSignature='', localPolling=false;
let recentJobs=[],activeJobs=[],walletJobs=[],activityData=null,activityEpoch=0,walletJobsEpoch=0;
let workspaceStatus=null,workspacePolling=false,workspaceTimer=null,lastJobsRevision=null;
let discoverySettingsRevision='';
const pendingActions=new Set();
const scanBusyJobs=new Set();
let scanAnnouncement='';
let observedResearchStates=new Map();
const jobLabels={'wallet.add':'Wallet research','wallet.refresh':'Holdings refresh','prices.refresh':'Price refresh','wallet.setTags':'Wallet names','settings.rpc':'RPC settings','settings.discovery':'Token discovery','settings.provider':'Data provider connection','settings.importEnv':'Local connection setup'};
const stageLabels={queued:'Waiting to start',starting:'Opening saved evidence',registered:'Wallet registered',discovery:'Token discovery',chain:'Checking on-chain holdings',onchain_progress:'Reading on-chain records',first_evidence:'First results available',dex_discovery:'Checking markets',token_images:'Preparing token artwork',published:'Evidence saved',failed:'Research stopped',stopped:'Research stopped',interrupted:'Ready for recovery'};
function researchStage(event) {
  if(event.stage==='price_refresh')return ({native:'Checking native asset prices',markets:'Checking market prices',index:'Checking indexed prices',curves:'Checking curve prices',discovery:'Finding additional markets',reserves:'Checking reserve prices',quotes:'Checking sale estimates',artwork:'Updating token artwork',saving:'Saving price observations'})[event.context?.phase]||'Refreshing prices';
  if(event.stage==='market_paused')return 'Balances saved · market checks continue';
  if(event.stage==='research_paused')return 'Partial results saved · research continues';
  const label=stageLabels[event.stage]||event.stage;
  if(event.stage!=='onchain_progress')return label;
  const operations={balances:'Checking token balances',registry:'Discovering Mint Club tokens',metadata:'Reading token details',curves:'Checking curve backing',markets:'Checking markets',reserves:'Checking reserve prices',mintclub_membership:'Checking Mint Club membership',history:'Discovering transfer history',market_discovery:'Finding token markets',factory_queries:'Finding pools',pool_checks:'Verifying pools',cashout_routes:'Checking sell estimates',asset_review:'Saving asset checks'};
  const counts=event.counts||{},context=event.context||{};
  const chain=(typeof state==='undefined'?[]:state?.wallets||[]).flatMap(w=>w.chains||[]).find(c=>c.id===context.chain_id);
  return (context.operation==='asset_inventory'?'Saving discovered asset counts':operations[context.operation]||label)+(context.chain_id?' · '+(chain?.name||'network '+context.chain_id):'')+(context.provider==='etherscan_keyless_erc1155_id0'?' · ERC1155 ID0':'');
}
function jobStage(job) {
  const event=job.events?.at(-1);
  if(job.state==='queued')return (job.analysis_phase==='enrichment'?'Sell analysis · ':job.analysis_phase==='baseline'?'Holdings · ':'')+(job.continuation?.not_before*1000>Date.now()?'Waiting to continue':'Waiting to start');
  return (job.analysis_phase==='enrichment'?'Sell analysis · ':job.analysis_phase==='baseline'?'Holdings · ':'')+researchStage(event&&event.stage===job.stage?event:{stage:job.stage||'starting'});
}
function assetProgressText(progress) {
  const a=progress.assets;
  return a?a.checked.toLocaleString()+' / '+a.total.toLocaleString()+' assets reviewed · '+a.quoted.toLocaleString()+' sell estimates · '+a.unknown.toLocaleString()+' unresolved checks':'';
}
function scanButton(action,id,label,primary=false,disabled=false) {
  const busy=scanBusyJobs.has(id);
  return `<button type="button" class="${primary?'primary':'quiet'}-button" data-job-action="${action}" data-job-id="${escapeHTML(id)}" ${disabled||busy||!jobsConnected?'disabled':''}>${escapeHTML(busy?(action==='cancel'?'Pausing…':action==='deepen'?'Starting…':'Resuming…'):label)}</button>`;
}
function jobControls(job) {
  if(!localSession?.controls||state?.demo)return '';
  if(KiraView.active(job))return scanButton('cancel',job.job_id,job.cancel_requested?(job.scan_policy?'Pausing…':'Stopping…'):job.scan_policy?'Pause scan':'Stop',false,job.cancel_requested);
  const key=String(job.input.wallet||job.input.address||'').toLowerCase(),session=KiraView.researchSession(jobList,{key});
  if(session?.job.job_id===job.job_id&&session.action)return scanButton(session.action,job.job_id,session.actionLabel,session.action==='deepen');
  if(!['wallet.add','wallet.refresh'].includes(job.operation)&&['interrupted','failed','cancelled'].includes(job.state))return scanButton('resume',job.job_id,'Resume saved work');
  return '';
}
function renderWalletScan() {
  const card=$('wallet-scan'),analysis=$('wallet-analysis'),wallet=typeof currentWallet==='function'?currentWallet():null;
  card.hidden=!wallet;analysis.hidden=true;if(!wallet)return;
  const status=KiraView.walletStatus(jobList,wallet),session=KiraView.researchSession(jobList,wallet),lookup=status.lookup;
  const deep=!!session?.isDeep,canWrite=localSession?.controls&&!state?.demo;
  const sameWallet=card.dataset.wallet===wallet.key;
  const detailsOpen=sameWallet&&card.querySelector('details')?.open,aboutOpen=sameWallet&&analysis.querySelector('details')?.open;
  const focused=[card,analysis].some(el=>el.contains(document.activeElement))?{id:document.activeElement.id,job:document.activeElement.dataset.jobId}:null;
  card.dataset.mode=status.mode;card.dataset.wallet=wallet.key;
  const pending=lookup&&KiraView.active(lookup.job),disconnected=localSession?.controls&&!jobsConnected;
  const lookupAction=canWrite&&lookup?.action&&lookup.action!=='deepen'?scanButton(lookup.action,lookup.job.job_id,lookup.actionLabel,false,pending&&lookup.job.cancel_requested):'';
  const progressHTML=job=>{
    if(!job)return '';
    const working=KiraView.active(job),progress=KiraView.jobProgress(job,Date.now(),jobsConnected);
    return `${working?`<p><strong>${escapeHTML(jobStage(job))}</strong> · <span data-job-timer="${escapeHTML(job.job_id)}">${KiraView.jobTimeText(job,Date.now(),jobsConnected)}</span></p>${progress.count?`<p>${escapeHTML(progress.count)}</p>`:''}${progress.total&&!progress.cumulative?`<progress value="${progress.checked}" max="${progress.total}" aria-label="${escapeHTML(progress.count)}"></progress>`:''}${progress.eta?`<p data-job-estimate="${escapeHTML(job.job_id)}">${escapeHTML(progress.eta)}</p>`:''}`:''}${progress.assets?`<p>${escapeHTML(assetProgressText(progress))}</p>`:''}`;
  };
  const secondary=disconnected?'Connection lost':pending?jobStage(lookup.job):wallet.analysed_at?'Saved '+stamp(wallet.analysed_at):'';
  card.innerHTML=`<div class="wallet-status-row"><details class="wallet-status-details" ${detailsOpen?'open':''}><summary id="wallet-scan-title"><span class="wallet-status-label"><span class="wallet-status-dot ${pending&&jobsConnected?'is-working':''}" data-mode="${status.mode}" aria-hidden="true"></span><span class="status-prefix">Holdings</span>${escapeHTML(status.label)}</span><span class="status-chevron" aria-hidden="true">⌄</span></summary><div class="wallet-status-body">
    <p>${escapeHTML(status.description)}</p>${progressHTML(lookup?.job)}
    ${disconnected?'<p>Connection lost. This is the last recorded status. Actions are available after reconnecting.</p>':''}
    ${wallet.analysed_at?'<p>See network coverage below for missing checks.</p>':''}
    <a class="text-link" href="#/activity">View activity ↗</a></div></details>
    ${secondary?`<span class="wallet-status-note">${escapeHTML(secondary)}</span>`:''}${lookupAction}</div>
    ${lookup?.failure?`<p class="status-failure">${escapeHTML(lookup.failure)}</p>`:''}`;
  const optional=canWrite&&session?.action==='deepen',showDeep=deep&&session.mode!=='saved';analysis.hidden=!(optional||showDeep);
  analysis.dataset.mode=deep?session.mode:'ready';
  const job=session?.job,working=!!job&&KiraView.active(job);
  const action=canWrite&&session?.action?scanButton(session.action,job.job_id,session.actionLabel,optional,working&&job.cancel_requested):'';
  analysis.innerHTML=optional||showDeep?`<div class="analysis-card-heading"><div class="analysis-copy"><div class="analysis-title-row"><h2 id="wallet-analysis-title" tabindex="-1">${escapeHTML(deep?session.title:'Your holdings are ready')}</h2>${optional?'<span class="analysis-optional">Optional analysis</span>':''}</div><p>${escapeHTML(deep?session.description:'Balances and available prices are saved. Explore additional sale and redemption estimates when you need them.')}</p></div>${action?`<div class="analysis-card-action">${action}</div>`:''}</div>
    ${deep?`<div class="analysis-progress">${session.failure?`<p class="status-failure">${escapeHTML(session.failure)}</p>`:''}${progressHTML(job)}</div>`:''}
    ${disconnected?'<p class="analysis-connection">Connection lost. Actions are available after reconnecting.</p>':''}
    <div class="analysis-card-footer"><details class="analysis-explainer" ${aboutOpen?'open':''}><summary id="analysis-explainer-toggle">About sell-route analysis</summary><p>Checks additional sale and redemption routes for your full balances. This is optional and can take time. It does not look for more tokens or execute trades. Estimates exclude gas and do not guarantee execution or the best price. You can pause and resume.</p></details><a class="text-link" href="#/activity">Activity ↗</a></div>`:'';
  if(focused){const next=focused.job?[...card.querySelectorAll('[data-job-id]'),...analysis.querySelectorAll('[data-job-id]')].find(el=>el.dataset.jobId===focused.job):focused.id&&$(focused.id);(next||$('wallet-scan-title')).focus({preventScroll:true});}
  const announcement=wallet.key+':'+status.mode+':'+(deep?session.mode:'')+':'+disconnected;
  if(announcement!==scanAnnouncement){scanAnnouncement=announcement;$('scan-announcement').textContent=[status.label,deep&&session.title,session?.failure,disconnected&&'Connection lost'].filter(Boolean).join('. ');}
}
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
    sessionStorage.removeItem(storageKey);
    const scanMessage=operation==='job.deepen'?'Sell-route analysis queued. Your holdings stay available.':operation==='job.resume'?'Scan queued to resume from saved work.':operation==='job.cancel'?'Pause requested. Saved results stay available.':null;
    toast(scanMessage||(operation.startsWith('settings.')?'Queued ':'Saved ')+(jobLabels[operation]||'job').toLowerCase());await pollJobs();await pollWorkspace();return result;
  }finally{pendingActions.delete(fingerprint);}
}
function refreshControlState(){
  const enabled=localSession?.controls===true;
  $('research-controls').hidden=!enabled;$('empty-add-wallet').hidden=!enabled;$('wallet-actions').hidden=!enabled;
  $('wallet-secondary-actions').hidden=!enabled;
  $('wallet-tools').hidden=!enabled&&!currentWallet()?.report_url;
  $('service-mode').textContent=enabled?'Local controls':'Watch only';
  const sample=state?.demo===true;
  for(const id of ['open-wallet','empty-add-wallet','refresh-wallet','refresh-prices']){
    const prices=id==='refresh-prices';
    const active=id.startsWith('refresh')&&jobList.find(j=>KiraView.active(j)&&
      (j.input.wallet||j.input.address)?.toLowerCase()===selectedWallet&&(!prices||j.operation==='prices.refresh'));
    const missing=prices&&!currentWallet()?.analysed_at;
    $(id).disabled=(sample&&id.startsWith('refresh'))||!!active||missing;
    if(prices)$('refresh-prices-label').textContent=active?.state==='queued'?'Prices queued…':active?'Refreshing prices…':'Refresh prices';
    $(id).title=sample?'Sample research cannot contact providers.':active?(prices?'A price refresh is already '+active.state+' for this wallet.':'A research job is already active for this wallet.'):missing?'Wait for the first saved report before refreshing prices.':prices?'Update prices for the saved report. Detailed research pauses briefly and resumes automatically.':'';
  }
  $('discovery-refresh').disabled=$('refresh-wallet').disabled;
  if(typeof renderWatching==='function')renderWatching();
}
let jobsPage=1, jobsConnected=true, lastJobsPoll=null;
function notifyResearchCompletions(){
  const completed=KiraView.completedSellAnalyses(observedResearchStates,jobList);
  observedResearchStates=new Map(jobList.map(job=>[job.job_id,job.state]));
  if(completed.length)toast(completed.length===1?'Sell analysis saved. Results and remaining unknowns are in Activity.':completed.length+' sell analyses saved. Details are in Activity.',6000);
}
function renderJobs(){
  notifyResearchCompletions();
  const active=jobList.filter(KiraView.active).sort((a,b)=>(a.state!=='running')-(b.state!=='running'));
  $('activity-count').textContent=(workspaceStatus?.active_job_count??active.length)||'';
  $('jobs-summary').textContent=active.length?active.length+' in progress':jobList.length+(jobList.length===1?' saved job':' saved jobs');
  $('jobs-freshness').textContent=!localSession?.controls?'Activity needs a local control session.':!jobsConnected?'Reconnecting. Last recorded states shown.':lastJobsPoll?'Checked '+stamp(lastJobsPoll):'Loading saved jobs…';
  const filter=$('job-filter').value;
  const filtered=jobList.filter(j=>filter==='all'||(filter==='active'?KiraView.active(j):filter==='attention'?['partial','interrupted','failed'].includes(j.state):j.state===filter));
  const history=selectedView==='activity'&&activityData;
  const total=history?history.total:filtered.length;
  const pages=Math.max(1,Math.ceil(total/20));jobsPage=Math.min(jobsPage,pages);
  $('jobs-page').textContent=jobsPage+' / '+pages;$('jobs-prev').disabled=jobsPage===1;$('jobs-next').disabled=jobsPage===pages;
  const rows=history?history.jobs:filtered.slice((jobsPage-1)*20,jobsPage*20);
  $('jobs-list').innerHTML=rows.map(j=>{
    const presentation=KiraView.jobPresentation(j,Date.now(),jobsConnected),progress=KiraView.jobProgress(j,Date.now(),jobsConnected);
    const counts=j.events?.at(-1)?.counts||{},context=j.events?.at(-1)?.context;
    const evidence=progress.count?(Number.isSafeInteger(counts.pending_ranges)?counts.pending_ranges+' block ranges still pending':''):[...Object.entries(counts).filter(([name])=>name!=='block_number').map(([name,count])=>`${name.replaceAll('_',' ')} ${count}`),...(context?.block_number?['block '+context.block_number]:[])].join(' · ');
    const controls=jobControls(j);
    const link=j.input.wallet||j.input.address;
    const name=state?.wallets.find(w=>w.key===link?.toLowerCase())?.name||(j.operation==='wallet.add'?j.input.tag:null);
    const recorded=(j.events||[]).map(event=>{const context=event.context;const detail=Object.entries(event.counts||{}).filter(([name])=>name!=='block_number').map(([name,value])=>name.replaceAll('_',' ')+': '+value).join(' · ');return `<li><strong>${escapeHTML(researchStage(event))}</strong><span>${stamp(event.observed_at)} · ${escapeHTML(detail)}${context?.block_number?' · block '+escapeHTML(context.block_number):''}</span></li>`;}).join('');
    const stages=recorded?`<details class="job-stages"><summary>Recorded stages · ${j.events.length}</summary><ol>${recorded}</ol></details>`:'';
    return `<article class="job-row"><div class="job-identity"><span class="job-state ${escapeHTML(j.state)}">${presentation.spinner?'<span class="spinner" aria-hidden="true"></span>':''}${escapeHTML(presentation.label)}</span><strong>${escapeHTML(jobLabels[j.operation]||j.operation)}</strong>${link?`<a href="#/wallet/${escapeHTML(link.toLowerCase())}">${escapeHTML(name||shortAddress(link))}</a>`:''}<p>${escapeHTML(jobStage(j))}${j.state==='partial'?' · coverage gaps remain':''}</p><p class="job-timer" data-job-timer="${escapeHTML(j.job_id)}">${KiraView.jobTimeText(j,Date.now(),jobsConnected)}</p>${progress.assets?`<p class="job-progress">${escapeHTML(assetProgressText(progress))}</p>`:''}${progress.count&&!progress.cumulative?`<p class="job-progress">${escapeHTML(progress.count)}</p>`:''}<p class="job-estimate" data-job-estimate="${escapeHTML(j.job_id)}">${escapeHTML(progress.eta)}</p>${progress.saved?`<p class="job-saved">${escapeHTML(progress.saved)}</p>`:''}${evidence?`<p class="job-evidence">${escapeHTML(evidence)}</p>`:''}${presentation.freshness?`<p class="job-freshness">${escapeHTML(presentation.freshness)}</p>`:''}${j.errors?.length?`<p class="job-error">${escapeHTML(KiraView.jobErrorMessage(j))}</p>`:''}${stages}<small>Last update ${stamp(j.updated_at)} · attempt ${j.attempt} · ${escapeHTML(j.job_id.slice(0,8))}</small></div><div class="job-actions">${controls}</div></article>`;
  }).join('')||'<div class="empty"><h3>'+(!localSession?.controls?'Activity is not available in this session':'No jobs in this view')+'</h3><p>Research jobs appear here when a local action starts.</p></div>';
  $('active-work').hidden=true;$('active-work').innerHTML='';
  renderActiveWork();
  if(typeof renderWallets==='function'&&state)renderWallets();
  renderWalletScan();
}
function tickJobTimers(){
  if(document.hidden)return;
  document.querySelectorAll('[data-job-timer]').forEach(node=>{const job=jobList.find(j=>j.job_id===node.dataset.jobTimer);if(!job)return;node.textContent=KiraView.jobTimeText(job,Date.now(),jobsConnected);});
  document.querySelectorAll('[data-job-estimate]').forEach(node=>{const job=jobList.find(j=>j.job_id===node.dataset.jobEstimate);if(job)node.textContent=KiraView.jobProgress(job,Date.now(),jobsConnected).eta;});
}
$('job-filter').addEventListener('change',()=>{jobsPage=1;loadActivity();});
$('jobs-prev').addEventListener('click',()=>{jobsPage--;loadActivity();});
$('jobs-next').addEventListener('click',()=>{jobsPage++;loadActivity();});
setInterval(()=>{if(!document.hidden&&jobList.some(KiraView.active))tickJobTimers();},1000);
function pendingWalletJob(wallet){return jobList.find(job=>KiraView.active(job)&&['wallet.add','wallet.refresh','prices.refresh'].includes(job.operation)&&String(job.input?.wallet||job.input?.address||'').toLowerCase()===wallet.key);}
function mergeJobs(){const rows=new Map();for(const job of [...recentJobs,...activeJobs,...walletJobs,...(activityData?.jobs||[])]){const prior=rows.get(job.job_id);if(!prior||(job.sequence??0)>=(prior.sequence??0))rows.set(job.job_id,job);}jobList=[...rows.values()].sort((a,b)=>b.created_at.localeCompare(a.created_at));}
function renderActiveWork(){
  const active=jobList.filter(KiraView.active).slice(0,5),panel=$('active-work');
  panel.hidden=!active.length;panel.innerHTML=active.map(job=>{
    const name=state?.wallets.find(w=>w.key===String(job.input?.wallet||job.input?.address||'').toLowerCase())?.name||job.input?.tag||jobLabels[job.operation]||'Research';
    const p=KiraView.jobPresentation(job,Date.now(),jobsConnected);
    return '<div class="active-work-row"><a href="#/activity"><span>'+ (p.spinner?'<span class="spinner" aria-hidden="true"></span>':'')+'<strong>'+escapeHTML(name)+'</strong> · '+escapeHTML(jobStage(job))+'</span><small data-job-timer="'+escapeHTML(job.job_id)+'">'+escapeHTML(KiraView.jobTimeText(job))+'</small></a><div class="job-actions">'+jobControls(job)+'</div></div>';
  }).join('');
}
async function loadActivity(){
  if(!localSession?.controls)return;
  const epoch=++activityEpoch,page=jobsPage,filter=$('job-filter').value;
  $('jobs-prev').disabled=true;$('jobs-next').disabled=true;
  try{
    const result=await localAPI('/api/job-history?offset='+((page-1)*20)+'&limit=20&state='+encodeURIComponent(filter));
    if(epoch!==activityEpoch||selectedView!=='activity')return;
    activityData=result;mergeJobs();renderJobs();
  }catch(error){if(epoch===activityEpoch){$('jobs-freshness').textContent=error.message;toast(error.message);}}
}
async function loadWalletJobs(wallet){
  if(!localSession?.controls)return;
  const epoch=++walletJobsEpoch;
  try{const result=await localAPI('/api/job-history?wallet='+encodeURIComponent(wallet)+'&offset=0&limit=50');
    if(epoch!==walletJobsEpoch||selectedView!=='wallet'||selectedWallet!==wallet)return;
    walletJobs=result.jobs;mergeJobs();renderJobs();
  }catch{/* Keep the last recorded job state until the next successful check. */}
}
async function pollJobs(){
  if(localPolling||!localSession?.controls)return;localPolling=true;
  try{
    recentJobs=await localAPI('/api/jobs?limit=50');
    const missing=(workspaceStatus?.active_jobs||[]).filter(active=>!recentJobs.some(job=>job.job_id===active.job_id));
    activeJobs=await Promise.all(missing.map(job=>localAPI('/api/jobs/'+encodeURIComponent(job.job_id))));
    mergeJobs();const reconnected=!jobsConnected;jobsConnected=true;lastJobsPoll=new Date().toISOString();
    const setting=recentJobs.filter(j=>j.operation.startsWith('settings.')&&j.state==='succeeded').map(j=>j.job_id+':'+j.updated_at).sort().join(',');
    if(setting!==discoverySettingsRevision){discoverySettingsRevision=setting;if(typeof loadSetupReadiness==='function')await loadSetupReadiness();}
    const signature=JSON.stringify(jobList)+JSON.stringify(jobList.map(j=>KiraView.jobPresentation(j).quiet));
    if(signature!==jobsSignature||reconnected){jobsSignature=signature;renderJobs();}else $('jobs-freshness').textContent='Checked '+stamp(lastJobsPoll);
    if(selectedView==='activity')await loadActivity();
    if(selectedView==='wallet')await loadWalletJobs(selectedWallet);
    refreshControlState();
  }catch{jobsConnected=false;renderJobs();}
  finally{localPolling=false;}
}
function scheduleWorkspacePoll(){
  clearTimeout(workspaceTimer);
  if(!document.hidden)workspaceTimer=setTimeout(pollWorkspace,workspaceStatus?.active_job_count?2500:10000);
}
async function pollWorkspace(){
  if(workspacePolling||document.hidden)return;workspacePolling=true;
  try{
    if(!localSession){const response=await fetch('/api/session',{cache:'no-store',signal:AbortSignal.timeout(5000)});if(!response.ok)throw Error('Local session unavailable');localSession=await response.json();}
    const next=await readAPI('/api/status');workspaceStatus=next;
    if((!state||state.data_revision!==next.data_revision)&&await poll()===false)throw Error('Saved research unavailable');
    if(localSession.controls&&(lastJobsRevision!==next.jobs_revision||!jobsConnected)){await pollJobs();if(jobsConnected)lastJobsRevision=next.jobs_revision;}
    if(localSession.controls&&typeof loadSetupReadiness==='function'&&!setupReadiness&&Date.now()>=setupRetryAfter)await loadSetupReadiness();
    if(localSession.controls&&typeof loadOws==='function'&&!owsState&&!state?.demo)await loadOws().catch(()=>{});
    refreshControlState();$('connection').textContent='Connected';
  }catch{$('connection').textContent='Reconnecting';if(!state){$('load-error').hidden=false;$('content').hidden=true;}}
  finally{workspacePolling=false;scheduleWorkspacePoll();}
}
for(const button of document.querySelectorAll('[data-close-dialog]'))button.addEventListener('click',()=>button.closest('dialog').close());
function openAdd(){if(!localSession?.controls)return;if(setupReadiness?.discovery_key_available!==true){openDataConnections();return;}if(!watchingSubmission)$('wallet-form-error').textContent='';if(typeof renderWatching==='function')renderWatching();$('wallet-dialog').showModal();if(typeof loadSetupReadiness==='function')loadSetupReadiness();}
$('open-wallet').addEventListener('click',openAdd);$('empty-add-wallet').addEventListener('click',openAdd);
function formAction(form,error,action){
  form.addEventListener('submit',async e=>{e.preventDefault();error.textContent='';const buttons=[...form.querySelectorAll('button[type="submit"]')];if(buttons.some(b=>b.disabled))return;buttons.forEach(b=>b.disabled=true);
    try{await action();}catch(failure){error.textContent=failure.message;}finally{buttons.forEach(b=>b.disabled=false);if(form.id==='provider-form')renderConnectionForm();}
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
$('refresh-wallet').addEventListener('click',async()=>{if(setupReadiness?.discovery_key_available!==true){await openDataConnections(false,true,selectedWallet);return;}try{await submitOperation('wallet.refresh',{wallet:selectedWallet});}catch(error){toast(error.message);}});
$('refresh-prices').addEventListener('click',async()=>{if(setupReadiness?.discovery_key_available!==true){await openDataConnections(false,true,selectedWallet);return;}try{await submitOperation('prices.refresh',{wallet:selectedWallet});}catch(error){toast(error.message);}});
$('edit-tags').addEventListener('click',()=>{if(!currentWallet())return;$('tags-dialog').dataset.wallet=selectedWallet;$('tag-values').value=currentWallet().tags.join('\n');$('tags-error').textContent='';$('tags-dialog').showModal();});
formAction($('tags-form'),$('tags-error'),async()=>{await submitOperation('wallet.setTags',{wallet:$('tags-dialog').dataset.wallet,tags:$('tag-values').value.split('\n').filter(t=>t.length)});$('tags-dialog').close();});
async function handleScanAction(event) {
  const button=event.target.closest('[data-job-action]');if(!button||button.disabled||!jobsConnected)return;
  const id=button.dataset.jobId,action=button.dataset.jobAction;
  if($('wallet-analysis').contains(button))$('wallet-analysis-title').focus({preventScroll:true});
  else if($('wallet-scan').contains(button))$('wallet-scan-title').focus({preventScroll:true});
  if(scanBusyJobs.has(id))return;scanBusyJobs.add(id);button.disabled=true;
  button.textContent=action==='cancel'?'Pausing…':action==='deepen'?'Starting…':'Resuming…';
  try{if(action==='refresh'){const job=jobList.find(j=>j.job_id===id);await submitOperation('wallet.refresh',{wallet:job.input.wallet||job.input.address});}else await submitOperation('job.'+action,{job_id:id});}
  catch(error){toast(error.message);}
  finally{scanBusyJobs.delete(id);renderJobs();}
}
$('jobs-list').addEventListener('click',handleScanAction);
$('wallet-scan').addEventListener('click',handleScanAction);
$('wallet-analysis').addEventListener('click',handleScanAction);
document.addEventListener('click',event=>{const menu=$('wallet-tools');if(menu.open&&(!menu.contains(event.target)||event.target.closest('.wallet-tools-menu button, .wallet-tools-menu a')))menu.open=false;});
document.addEventListener('keydown',event=>{const menu=$('wallet-tools');if(event.key==='Escape'&&menu.open){menu.open=false;$('wallet-tools-toggle').focus();}});
$('active-work').addEventListener('click',handleScanAction);
let connectionConfig = null, connectionReadiness = null, connectionRevision = 0, workspaceSettingsRevision = 0, pendingSetting = null, settingSaving = false, settingSaved = false, settingFailed = false, connectionWallet = null;
function connectionSummary(config) {
  return config.discovery.provider==='alchemy'?'Alchemy selected · all-network holdings':'Alchemy connection required for research';
}
function renderConnectionForm() {
  const available=connectionReadiness?.local_key_available===true&&$('discovery-key').value===connectionConfig?.discovery.key_env;
  const connected=available&&connectionReadiness?.discovery_key_available===true;
  $('provider-save').disabled=settingSaving||!available;
  $('provider-save').textContent=connected?'Done':'Connect Alchemy';
  $('settings-done').hidden=connected;
  $('provider-key-status').textContent=connected?'Alchemy is connected. Holdings lookups will confirm access on each network.':available?'Local key found. Connect it to start.':'Run the command above, then check the connection.';
  $('settings-refresh').hidden=!connectionWallet||!connected;
  $('settings-refresh').disabled=settingSaving||jobList.some(j=>KiraView.active(j)&&j.input?.wallet===connectionWallet);
}
let rpcRows=[],rpcNetworks=[],rpcSaving=false,rpcLoaded=false;
function renderRpcRows(){
  $('rpc-rows').innerHTML=rpcRows.map((row,index)=>{
    const network=rpcNetworks.find(item=>item.chain_id===row.chain_id);
    return '<div class="rpc-row"><label>'+escapeHTML(network?.name||'Network '+row.chain_id)+'<input data-rpc-reference="'+index+'" value="'+escapeHTML(row.url_env)+'" pattern="[A-Za-z_][A-Za-z0-9_]*" maxlength="100" required autocomplete="off"></label><button class="quiet-button" type="button" data-rpc-remove="'+index+'" aria-label="Remove '+escapeHTML(network?.name||'network '+row.chain_id)+' reference">Remove</button></div>';
  }).join('')||'<p class="form-note">No custom references saved.</p>';
}
function loadRpcSettings(config){
  const rpc=config.rpc||{};
  rpcNetworks=config.rpc_networks||[];
  rpcRows=Object.entries(rpc.chains||{}).map(([chain_id,entry])=>({chain_id:Number(chain_id),url_env:entry.url_env||''}));
  $('rpc-mode').value=rpc.mode||'public';$('rpc-priority').value=rpc.priority||'public_first';$('rpc-fallback').checked=rpc.allow_public_fallback!==false;
  $('rpc-network').innerHTML=rpcNetworks.map(network=>'<option value="'+network.chain_id+'">'+escapeHTML(network.name)+'</option>').join('');
  $('rpc-reference').value='';renderRpcRows();rpcLoaded=true;$('rpc-fields').disabled=false;
}
function rpcSettingsInput(){
  if(!rpcLoaded)throw Error('Wait for saved RPC settings before making changes.');
  const mode=$('rpc-mode').value,priority=$('rpc-priority').value,seen=new Set();
  if(!['public','custom'].includes(mode)||!['public_first','custom_first'].includes(priority))throw Error('Choose a connection mode and priority.');
  if(rpcRows.length>30)throw Error('Use at most 30 network references.');
  const chains=rpcRows.map(row=>{
    if(!Number.isSafeInteger(row.chain_id)||row.chain_id<=0||seen.has(row.chain_id))throw Error('Use one reference per network.');
    if(!/^[A-Za-z_][A-Za-z0-9_]{0,99}$/.test(row.url_env))throw Error('Enter an environment variable name, such as ETHEREUM_RPC_URL. URLs and keys are not accepted.');
    seen.add(row.chain_id);return {...row};
  });
  if(mode==='custom'&&!chains.length)throw Error('Add at least one network reference for custom RPC.');
  return {mode,chains,allow_public_fallback:$('rpc-fallback').checked,priority};
}
async function saveRpcSettings(){
  if(rpcSaving)return;
  const input=rpcSettingsInput();rpcSaving=true;$('rpc-fields').disabled=true;$('rpc-status').textContent='Submitting RPC settings…';$('rpc-activity').hidden=true;
  try{await submitOperation('settings.rpc',input);$('rpc-status').textContent='RPC settings submitted. Check Activity for the saved result.';$('rpc-activity').hidden=false;}
  catch(error){$('rpc-status').textContent='Could not confirm the settings result. Retry checks the same request.';throw error;}
  finally{rpcSaving=false;$('rpc-fields').disabled=!rpcLoaded;}
}
async function openWorkspaceSettings(){
  if(!localSession?.controls||rpcSaving)return;
  const revision=++workspaceSettingsRevision;
  if(!$('workspace-settings-dialog').open)$('workspace-settings-dialog').showModal();
  rpcLoaded=false;$('rpc-fields').disabled=true;$('rpc-error').textContent='';$('rpc-status').textContent='';$('rpc-activity').hidden=true;
  $('workspace-data-summary').textContent='Checking the saved connection…';
  try{const config=await localAPI('/api/settings');if(revision===workspaceSettingsRevision&&$('workspace-settings-dialog').open){$('workspace-data-summary').textContent=connectionSummary(config);loadRpcSettings(config);}}
  catch{if(revision===workspaceSettingsRevision)$('workspace-data-summary').textContent='Could not check the data connection. Reopen to retry.';}
}
$('rpc-add').addEventListener('click',()=>{
  $('rpc-error').textContent='';const chain_id=Number($('rpc-network').value),url_env=$('rpc-reference').value.trim();
  if(!rpcNetworks.some(network=>network.chain_id===chain_id)){$('rpc-error').textContent='Choose a supported network.';return;}
  if(rpcRows.some(row=>row.chain_id===chain_id)){$('rpc-error').textContent='This network already has a reference. Edit its existing row.';return;}
  if(!/^[A-Za-z_][A-Za-z0-9_]{0,99}$/.test(url_env)){$('rpc-error').textContent='Enter an environment variable name only.';return;}
  if(rpcRows.length>=30){$('rpc-error').textContent='Use at most 30 network references.';return;}
  rpcRows.push({chain_id,url_env});$('rpc-reference').value='';renderRpcRows();
});
$('rpc-rows').addEventListener('input',event=>{if(event.target.dataset.rpcReference!==undefined){const row=rpcRows[Number(event.target.dataset.rpcReference)];if(row)row.url_env=event.target.value;}});
$('rpc-rows').addEventListener('click',event=>{const button=event.target.closest('[data-rpc-remove]');if(button){rpcRows.splice(Number(button.dataset.rpcRemove),1);renderRpcRows();}});
formAction($('rpc-form'),$('rpc-error'),saveRpcSettings);
async function openDataConnections(advanced = false, recommend = false, walletKey = null) {
  if (!localSession?.controls) return;
  const revision = ++connectionRevision;
  connectionWallet = !$('wallet-dialog').open ? walletKey || (selectedView==='wallet' ? currentWallet()?.key || null : null) : null;
  $('settings-error').textContent = ''; $('provider-status').textContent = pendingSetting ? 'A saved request is pending. Save again to check its result.' : '';
  $('provider-save').disabled = true; $('provider-recheck').disabled = true; $('settings-dialog').showModal();
  $('settings-done').textContent = $('wallet-dialog').open ? 'Back to wallet' : 'Close';
  $('connection-advanced').open = advanced;
  try {
    const [config, readiness] = await Promise.all([localAPI('/api/settings'), localAPI('/api/onboarding')]);
    if (revision !== connectionRevision || !$('settings-dialog').open) return;
    connectionConfig = config; connectionReadiness = readiness;
    $('data-provider').value='alchemy';
    $('discovery-key').value = config.discovery.key_env;
    $('provider-status').textContent = pendingSetting ? 'A saved request is pending. Save again to check its result.' : 'Saved connection: '+connectionSummary(config);
    renderConnectionForm(); $('provider-recheck').disabled = settingSaving;
  } catch (error) { if (revision === connectionRevision) $('settings-error').textContent = error.message; }
}
async function saveConnectionSetting(operation, input) {
  if (settingSaving) throw new Error('A settings request is already being checked. Wait for its result.');
  settingSaving = true; settingSaved = false; settingFailed = false;
  connectionRevision++; $('provider-recheck').disabled = true;
  try {
    await finishConnectionSetting(operation,input);
  } catch (error) {
    $('provider-status').textContent = settingSaved ? 'Connection saved. Status could not be refreshed; retry checks the same request.' : pendingSetting ? 'The saved request is pending. Retry checks the same request.' : settingFailed ? 'Connection settings were not saved.' : 'Could not confirm the settings request. Check Activity or retry the same choices.';
    throw settingSaved ? new Error('Settings were saved. Reopen or retry to refresh the connection status.') : error;
  }
  finally { settingSaving = false; $('provider-recheck').disabled = false; if(connectionConfig)renderConnectionForm(); }
}
async function finishConnectionSetting(operation, input) {
  const signature = JSON.stringify({operation,input});
  if (!pendingSetting) {
    const accepted = await submitOperation(operation, input);
    pendingSetting = {id:accepted.job_id,signature};
  }
  const pending = pendingSetting;
  $('provider-status').textContent = 'Connection settings are queued. Waiting for the saved result…';
  for (let attempt = 0; attempt < 20; attempt++) {
    const result = await localAPI('/api/jobs/' + encodeURIComponent(pending.id));
    if (['succeeded','failed','cancelled','interrupted','partial'].includes(result.state)) {
      if (result.state !== 'succeeded') { settingFailed = true; if (pendingSetting === pending) pendingSetting = null; throw new Error(result.errors?.[0]?.message || 'Connection settings were not saved. Review Activity and retry.'); }
      if (pending.signature !== signature) { if (pendingSetting === pending) pendingSetting = null; throw new Error('The previous settings request finished. Review your new choices and save again.'); }
      settingSaved = true;
      $('provider-status').textContent = 'Connection saved. Refresh holdings to check the new coverage.';
      if (typeof loadSetupReadiness === 'function') await loadSetupReadiness();
      connectionConfig = await localAPI('/api/settings'); connectionReadiness = await localAPI('/api/onboarding');
      renderConnectionForm(); if (pendingSetting === pending) pendingSetting = null; return;
    }
    await new Promise(resolve => setTimeout(resolve, 400));
  }
  throw new Error('Settings are still queued. Check Activity or save again to check the same request.');
}
$('open-settings').addEventListener('click',openWorkspaceSettings);
$('settings-data').addEventListener('click',()=>openDataConnections());
$('discovery-settings').addEventListener('click',()=>openDataConnections(false,true));
$('home-discovery-settings').addEventListener('click',()=>openDataConnections(false,true,$('home-discovery-settings').dataset.wallet));
$('wallet-discovery-settings').addEventListener('click',()=>openDataConnections(false,true));
$('settings-done').addEventListener('click',()=>$('settings-dialog').close());
$('workspace-settings-dialog').addEventListener('close',()=>{workspaceSettingsRevision++;});
$('rpc-activity').addEventListener('click',()=>{$('workspace-settings-dialog').close();});
$('settings-dialog').addEventListener('close',()=>{connectionRevision++; if ($('workspace-settings-dialog').open) openWorkspaceSettings();});
$('provider-recheck').addEventListener('click',async()=>{
  if(settingSaving||!connectionConfig||$('provider-recheck').disabled)return;
  const revision = connectionRevision; $('provider-recheck').disabled = true; $('settings-error').textContent = '';
  try {
    const [config,readiness]=await Promise.all([localAPI('/api/settings'),localAPI('/api/onboarding')]);
    if(revision!==connectionRevision||!$('settings-dialog').open)return;
    $('data-provider').value='alchemy';
    if($('discovery-key').value===connectionConfig.discovery.key_env)$('discovery-key').value=config.discovery.key_env;
    connectionConfig=config;connectionReadiness=readiness;
    if(!pendingSetting)$('provider-status').textContent='Saved connection: '+connectionSummary(config);
    renderConnectionForm();
  } catch(error) { if(revision===connectionRevision)$('settings-error').textContent=error.message; }
  finally { if(revision===connectionRevision)$('provider-recheck').disabled=settingSaving; }
});
$('settings-refresh').addEventListener('click',async()=>{
  if(!connectionWallet||$('settings-refresh').disabled)return;
  $('settings-refresh').disabled=true;
  try { await submitOperation('wallet.refresh',{wallet:connectionWallet});$('settings-dialog').close();navigate('#/activity'); }
  catch(error) { $('settings-error').textContent=error.message;renderConnectionForm(); }
});
$('discovery-key').addEventListener('input',renderConnectionForm);
$('discovery-refresh').addEventListener('click',()=>$('refresh-wallet').click());
formAction($('provider-form'),$('settings-error'),async()=>{
  if(connectionReadiness?.discovery_key_available&&$('discovery-key').value===connectionConfig?.discovery.key_env){$('settings-dialog').close();return;}
  await saveConnectionSetting('settings.provider',{provider:'alchemy',key_env:$('discovery-key').value.trim()});
});
let historyRows=[];
function renderHistory(){
  const intermediate=historyRows.filter(row=>row.phase==='initial');
  let rows=$('history-intermediate').checked?historyRows:historyRows.filter(row=>row.phase!=='initial');
  // A first lookup may only have progress evidence so far. Keep its latest save visible.
  if(!rows.length&&intermediate.length)rows=intermediate.slice(-1);
  $('history-options').hidden=!intermediate.length;
  const label=row=>row.phase==='initial'?'In progress':row.phase==='sell'?'Sell analysis':row.phase==='holdings'?'Holdings':'Saved analysis';
  $('history-list').innerHTML=[...rows].reverse().map(row=>`<article class="history-row"><strong>${stamp(row.compiled_at)}</strong><span>${escapeHTML(label(row))} · ${escapeHTML(row.status==='completed'?'Saved':'Saved with coverage gaps')}</span></article>`).join('')||'<p>No analysis has been published yet.</p>';
  $('compare-form').hidden=rows.length<2;
  for(const id of ['compare-before','compare-after'])$(id).innerHTML=rows.map(row=>`<option value="${escapeHTML(row.snapshot_id)}">${stamp(row.compiled_at)} · ${escapeHTML(label(row))}</option>`).join('');
  $('compare-before').selectedIndex=Math.max(0,rows.length-2);$('compare-after').selectedIndex=Math.max(0,rows.length-1);
  $('comparison-result').textContent='';$('history-error').textContent='';
}
$('history-intermediate').addEventListener('change',renderHistory);
$('view-history').addEventListener('click',async()=>{try{historyRows=await localAPI('/api/snapshots?wallet='+encodeURIComponent(selectedWallet));$('history-intermediate').checked=false;renderHistory();$('history-dialog').showModal();}catch(error){toast(error.message);}});
formAction($('compare-form'),$('history-error'),async()=>{const comparison=await localAPI('/api/compare?before='+encodeURIComponent($('compare-before').value)+'&after='+encodeURIComponent($('compare-after').value));$('comparison-result').innerHTML=`<p>${escapeHTML(comparison.note)}</p><p>Coverage observations ${comparison.coverage_changed?'changed':'unchanged'} · native price references ${comparison.price_references_changed?'changed':'unchanged'}</p><div class="table-wrap"><table><thead><tr><th>Token / chain</th><th>Earlier balance</th><th>Later balance</th><th>Change</th></tr></thead><tbody>${comparison.positions.map(p=>`<tr><td>${escapeHTML(p.symbol||shortAddress(p.address))} · ${p.chain_id}<small>${escapeHTML(p.presence.replaceAll('_',' '))}${p.price_references_changed?' · price references changed':''}${p.valuation_method_changed?' · method changed':''}</small></td><td>${escapeHTML(p.before_balance??'Unknown')}</td><td>${escapeHTML(p.after_balance??'Unknown')}</td><td>${escapeHTML(p.balance_delta??'Unknown')}</td></tr>`).join('')}</tbody></table></div>`;});
window.addEventListener('hashchange',()=>{activityEpoch++;walletJobsEpoch++;activityData=null;walletJobs=[];mergeJobs();refreshControlState();renderJobs();});
document.addEventListener('visibilitychange',()=>{clearTimeout(workspaceTimer);if(!document.hidden)pollWorkspace();});
pollWorkspace();
