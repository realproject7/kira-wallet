'use strict';
let activityDetailId=null,activityDetailSignature='',activityWalletOptions='',activitySearchTimer;
const activityIcons={
  holdings:'<path d="M4 6h14a2 2 0 0 1 2 2v11H5a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h12v2M15 11h5v5h-5z"/>',
  sell:'<path d="M4 8h15m-4-4 4 4-4 4M20 16H5m4-4-4 4 4 4"/>',
  prices:'<path d="m3 17 6-6 4 3 8-10M15 4h6v6"/>',
  settings:'<path d="M4 7h16M4 17h16M8 4v6M16 14v6"/>',
  arrow:'<path d="m9 5 7 7-7 7"/>',check:'<path d="m5 12 4 4L19 6"/>',clock:'<circle cx="12" cy="12" r="8"/><path d="M12 7v5l3 2"/>'
};
function activityIcon(kind){return '<svg class="ui-icon" viewBox="0 0 24 24" fill="none" aria-hidden="true">'+(activityIcons[kind]||activityIcons.settings)+'</svg>';}
function activityTask(job){return job.analysis_phase==='enrichment'?'Sell estimates':job.operation==='wallet.add'?'Wallet lookup':job.operation==='wallet.refresh'?(job.input?.scope==='fast'?'Fast refresh':'Holdings refresh'):job.operation==='prices.refresh'?'Price refresh':jobLabels[job.operation]||'Workspace update';}
function activityKind(job){return job.analysis_phase==='enrichment'?'sell':job.operation==='positions.refresh'?'holdings':job.operation==='prices.refresh'?'prices':['wallet.add','wallet.refresh'].includes(job.operation)?'holdings':'settings';}
function activityWallet(job){const key=String(job.input?.wallet||job.input?.address||'').toLowerCase(),wallet=state?.wallets.find(w=>w.key===key);return {key,wallet,name:wallet?.name||job.input?.tag||(key?shortAddress(key):'Workspace')};}
function activityBadge(job){
  const labels={queued:'Queued',running:'In progress',partial:'Saved with gaps',succeeded:'Saved',failed:'Failed',interrupted:'Interrupted',cancelled:job.scan_policy||job.operation==='positions.refresh'?'Paused':'Stopped'};
  const label=job.cancel_requested&&KiraView.active(job)?'Pausing':labels[job.state]||'Unknown';
  return '<span class="activity-badge '+escapeHTML(job.state)+'"><span class="activity-status-dot" aria-hidden="true"></span>'+escapeHTML(label)+'</span>';
}
function activityTime(value){return value?'<time datetime="'+escapeHTML(value)+'" title="'+escapeHTML(new Date(value).toLocaleString())+'">'+escapeHTML(stamp(value))+'</time>':'—';}
function activityOutcome(job){
  const {wallet}=activityWallet(job),session=wallet&&KiraView.researchSession(jobList,wallet);
  if(!session||session.job.job_id!==job.job_id)return '';
  return ({current:'Estimates retained',changed:'Holdings changed',unverified:'Verify holdings first'})[wallet.sell_analysis?.status]||'';
}
function activityCounts(){
  if(activityData?.counts)return activityData.counts;
  return {all:jobList.length,active:jobList.filter(KiraView.active).length,attention:jobList.filter(j=>['failed','interrupted'].includes(j.state)).length,succeeded:jobList.filter(j=>['succeeded','partial'].includes(j.state)).length,cancelled:jobList.filter(j=>j.state==='cancelled').length};
}
function activityQuickAction(job){return KiraView.active(job)||['failed','interrupted','cancelled'].includes(job.state)?jobControls(job):'';}
function activityRow(job){
  const {name}=activityWallet(job),p=KiraView.jobPresentation(job,Date.now(),jobsConnected),outcome=activityOutcome(job);
  return `<article class="activity-row" aria-label="${escapeHTML(name+' · '+activityTask(job))}">
    <div class="activity-task"><span class="activity-task-icon activity-kind-${activityKind(job)}">${activityIcon(activityKind(job))}</span><div><button type="button" class="activity-task-name" data-activity-detail="${escapeHTML(job.job_id)}" aria-haspopup="dialog">${escapeHTML(name)}</button><span class="activity-task-type">${escapeHTML(activityTask(job))}</span></div></div>
    <div class="activity-result">${activityBadge(job)}${outcome?'<small>'+escapeHTML(outcome)+'</small>':''}</div>
    <div class="activity-started"><span class="activity-mobile-label">Started</span>${activityTime(job.created_at)}</div>
    <div class="activity-duration"><span class="activity-mobile-label">Duration</span><span data-activity-duration="${escapeHTML(job.job_id)}" title="${escapeHTML(KiraView.jobTimeText(job,Date.now(),jobsConnected))}">${escapeHTML(KiraView.duration(p.elapsed))}</span></div>
    <div class="activity-row-actions">${activityQuickAction(job)}<button type="button" class="activity-detail-trigger" data-activity-detail="${escapeHTML(job.job_id)}" aria-label="${escapeHTML('View '+name+' '+activityTask(job)+' details')}" aria-haspopup="dialog">${activityIcon('arrow')}</button></div>
  </article>`;
}
function renderActivityCurrent(){
  const panel=$('activity-current'),all=jobList.filter(KiraView.active).sort((a,b)=>(b.state==='running')-(a.state==='running')||a.created_at.localeCompare(b.created_at));
  const job=all[0];panel.hidden=!job;if(!job){panel.innerHTML='';return;}
  const {name}=activityWallet(job),progress=KiraView.jobProgress(job,Date.now(),jobsConnected),presentation=KiraView.jobPresentation(job,Date.now(),jobsConnected);
  const total=workspaceStatus?.active_job_count??all.length;
  const count=progress.assets?assetProgressText(progress):progress.count;
  panel.innerHTML=`<div class="activity-current-label"><h2>In progress</h2><span>${total} ${total===1?'task':'tasks'} · Across workspace</span></div><div class="activity-run"><div class="activity-run-top"><span class="activity-task-icon">${activityIcon(activityKind(job))}</span><div class="activity-run-identity"><button type="button" class="activity-task-name" data-activity-detail="${escapeHTML(job.job_id)}" aria-haspopup="dialog">${escapeHTML(name)}</button><span class="activity-task-type">${escapeHTML(activityTask(job))}</span></div>${activityBadge(job)}<div class="activity-run-action">${activityQuickAction(job)}</div></div><div class="activity-run-progress"><p>${escapeHTML(jobStage(job))}</p>${count?'<span>'+escapeHTML(count)+'</span>':''}${job.state==='running'&&progress.total&&!progress.cumulative?`${progress.assets&&progress.count?'<small class="activity-step-label">Current step · '+escapeHTML(progress.count)+'</small>':''}<progress value="${progress.checked}" max="${progress.total}" aria-label="Current step checks"></progress>`:''}</div><div class="activity-run-footer"><span data-job-timer="${escapeHTML(job.job_id)}">${escapeHTML(KiraView.jobTimeText(job,Date.now(),jobsConnected))}</span>${presentation.freshness?'<span>'+escapeHTML(presentation.freshness)+'</span>':'<span>Saved results stay available.</span>'}<button class="text-button" type="button" data-activity-detail="${escapeHTML(job.job_id)}">View details ${activityIcon('arrow')}</button></div></div>${total>1?`<button type="button" class="activity-queue" data-activity-filter="active">${activityIcon('clock')}<span>${total-1} more ${total===2?'task':'tasks'} queued or running <small>Queued wallets run in batches</small></span>${activityIcon('arrow')}</button>`:''}`;
}
function renderActivity(){
  const selected=$('job-filter').value||'all',counts=activityCounts(),history=selectedView==='activity'&&activityData;
  // Before the area's history loads, the recent tasks shown are still the area's own.
  const areaKey=typeof areaWallet!=='undefined'?areaWallet:null;
  const folderKeys=!areaKey&&typeof FolderUI!=='undefined'&&FolderUI.id?new Set(FolderUI.wallets().map(w=>w.key)):null;
  const inArea=j=>{const key=activityWallet(j).key;return areaKey?key===areaKey:!folderKeys||folderKeys.has(key);};
  const filtered=jobList.filter(inArea).filter(j=>selected==='all'||selected==='active'&&KiraView.active(j)||selected==='attention'&&['failed','interrupted'].includes(j.state)||selected==='succeeded'&&['succeeded','partial'].includes(j.state)||selected==='cancelled'&&j.state==='cancelled');
  const total=history?history.total:filtered.length,pages=Math.max(1,Math.ceil(total/20));jobsPage=Math.max(1,Math.min(jobsPage,pages));
  $('jobs-summary').textContent=(counts.all??0)+' recorded '+(counts.all===1?'task':'tasks');
  $('jobs-freshness').textContent=!localSession?.controls?'Local session required':!jobsConnected?'Reconnecting · showing saved status':lastJobsPoll?'Connected · checked '+stamp(lastJobsPoll):'Loading activity…';
  $('jobs-freshness').dataset.connected=String(jobsConnected);
  document.querySelectorAll('[data-activity-count]').forEach(node=>{node.textContent=counts[node.dataset.activityCount]??'';});
  document.querySelectorAll('#activity-tabs [data-activity-filter]').forEach(button=>button.setAttribute('aria-pressed',String(button.dataset.activityFilter===selected)));
  const pool=folderKeys?FolderUI.wallets():state?.wallets||[];
  const options='<option value="all">All wallets</option>'+pool.map(w=>'<option value="'+escapeHTML(w.key)+'">'+escapeHTML(w.name)+'</option>').join('');
  if(options!==activityWalletOptions){const value=$('activity-wallet').value;activityWalletOptions=options;$('activity-wallet').innerHTML=options;$('activity-wallet').value=pool.some(w=>w.key===value)?value:'all';}
  const walletFilter=$('activity-wallet').closest?.('label');if(walletFilter)walletFilter.hidden=!!areaKey;
  $('activity-clear').hidden=selected==='all'&&!$('activity-query').value&&$('activity-wallet').value==='all';
  $('jobs-page').textContent=jobsPage+' / '+pages;$('jobs-prev').disabled=jobsPage<=1;$('jobs-next').disabled=jobsPage>=pages;
  const offset=history?history.offset:(jobsPage-1)*20,rows=history?history.jobs:filtered.slice(offset,offset+20);
  $('activity-range').textContent=total?(offset+1)+'–'+(offset+rows.length)+' of '+total+' tasks':'0 tasks';
  if(selectedView==='activity'&&typeof loadUsage==='function')loadUsage();
  const focused=document.activeElement?.closest?.('[data-activity-detail], [data-job-action]'),focusId=focused?.dataset.activityDetail||focused?.dataset.jobId,focusAction=focused?.dataset.jobAction;
  const focusScope=focused?.closest?.('#activity-current')?'#activity-current':'#jobs-list';
  const detailVisible=$('activity-detail').open;
  $('jobs-list').innerHTML=rows.map(activityRow).join('')||`<div class="activity-empty">${activityIcon(selected==='attention'?'check':'clock')}<h3>${!localSession?.controls?'Connect to your local workspace':selected==='attention'?'No tasks need attention':selected==='active'?'No research in progress':'No activity found'}</h3><p>${!localSession?.controls?'Open the local app to see saved research.':selected==='attention'?'Failed or interrupted tasks appear here when a retry is needed.':'Try another filter, or refresh holdings from your portfolio.'}</p></div>`;
  renderActivityCurrent();
  if(!detailVisible&&focusId){const next=[...document.querySelectorAll(focusScope+' [data-activity-detail], '+focusScope+' [data-job-action]')].find(node=>(node.dataset.activityDetail||node.dataset.jobId)===focusId&&node.dataset.jobAction===focusAction);next?.focus({preventScroll:true});}
  if(activityDetailId)renderActivityDetails();
}
// Alchemy compute units one task used, from Kira's usage ledger. A batch shares one total.
const activityUsage=new Map(),USAGE_TASKS=new Set(['wallet.add','wallet.refresh','prices.refresh','positions.refresh']);
function activityUsageText(job){
  const value=activityUsage.get(job.job_id)?.value;if(!value?.requests)return '';
  return (typeof usageAmount==='function'?usageAmount(value.cu,true):'≈ '+value.cu+' CU')+(value.batch_wallets>1?' · '+value.batch_wallets+'-wallet batch':'');
}
function loadActivityUsage(job){
  if(!USAGE_TASKS.has(job.operation)||typeof localAPI!=='function'||typeof localSession==='undefined'||!localSession?.controls)return;
  const known=activityUsage.get(job.job_id),active=KiraView.active(job);
  if(known&&(known.pending||(active?Date.now()-known.at<15000:known.state===job.state)))return;
  activityUsage.set(job.job_id,{...known,pending:true});
  localAPI('/api/usage?job='+encodeURIComponent(job.job_id)).then(result=>result.job,()=>known?.value||null)
    .then(value=>{activityUsage.set(job.job_id,{value,state:job.state,at:Date.now()});if(activityDetailId===job.job_id)renderActivityDetails();});
}
function renderActivityDetails(){
  const job=jobList.find(j=>j.job_id===activityDetailId);if(!job)return;
  loadActivityUsage(job);const usage=activityUsageText(job);
  const {name,key,wallet}=activityWallet(job),progress=KiraView.jobProgress(job,Date.now(),jobsConnected);
  const signature=JSON.stringify([job,usage,wallet?.sell_analysis,jobsConnected,localSession?.controls,typeof scanBusyJobs==='undefined'?false:scanBusyJobs.has(job.job_id)]);
  if(signature===activityDetailSignature)return;activityDetailSignature=signature;
  const body=$('activity-detail-body'),scroll=body.scrollTop,opened=[...body.querySelectorAll('details[open]')].map(el=>el.dataset.activitySection);
  const focused=document.activeElement?.dataset.jobAction;
  $('activity-detail-title').textContent=name;
  const saved=['succeeded','partial'].includes(job.state),deep=job.analysis_phase==='enrichment';
  const description=job.state==='partial'?(deep?'Available sell estimates are saved. Some routes remain unknown.':'Available results are saved. Some network or token checks remain incomplete.'):job.state==='succeeded'?'This task finished and its results are saved.':job.state==='queued'?'Queued locally. Wallet research runs one at a time.':KiraView.active(job)?'Research continues locally. Your saved results stay available.':['interrupted','cancelled'].includes(job.state)?'Progress is saved. Resume this task when you are ready.':'This task stopped. Saved holdings remain available.';
  const controls=jobControls(job);
  const events=(job.events||[]).slice().reverse().map(event=>{const numbers=Object.entries(event.counts||{}).filter(([name])=>name!=='block_number').map(([name,value])=>name.replaceAll('_',' ')+' '+value).join(' · ');return '<li><span class="activity-event-dot" aria-hidden="true"></span><div><strong>'+escapeHTML(researchStage(event))+'</strong><small>'+activityTime(event.observed_at)+(numbers?' · '+escapeHTML(numbers):'')+'</small></div></li>';}).join('');
  const relevant=wallet&&KiraView.researchSession(jobList,wallet)?.job.job_id===job.job_id;
  body.innerHTML=`<div class="activity-detail-context"><span>${escapeHTML(activityTask(job))}</span>${activityBadge(job)}</div><p class="activity-detail-description">${escapeHTML(description)}</p>${job.errors?.length?'<div class="activity-detail-error">'+escapeHTML(KiraView.jobErrorMessage(job))+'</div>':''}${!jobsConnected?'<p class="activity-detail-error">Connection lost. Actions are available after reconnecting.</p>':''}
    <dl class="activity-facts"><div><dt>Started</dt><dd>${activityTime(job.started_at||job.created_at)}</dd></div><div><dt>${saved?'Last saved':'Last update'}</dt><dd>${activityTime(job.events?.at(-1)?.observed_at||job.updated_at)}</dd></div><div><dt>Duration</dt><dd data-job-timer="${escapeHTML(job.job_id)}">${escapeHTML(KiraView.jobTimeText(job,Date.now(),jobsConnected))}</dd></div><div><dt>Task</dt><dd>${escapeHTML(activityTask(job))}</dd></div>${usage?'<div class="activity-usage-fact"><dt>Alchemy</dt><dd>'+escapeHTML(usage)+'</dd></div>':''}</dl>
    ${progress.assets?'<section class="activity-detail-section"><h3>Analysis coverage</h3><p>'+escapeHTML(assetProgressText(progress))+'</p></section>':''}
    ${relevant&&wallet.sell_analysis?.last_analyzed_at?'<section class="activity-detail-section"><h3>Saved sell estimates</h3><p>Last analysis '+activityTime(wallet.sell_analysis.last_analyzed_at)+'. '+escapeHTML(activityOutcome(job))+'. Quotes retain their original observation times.</p></section>':''}
    <div class="activity-detail-actions">${controls}${key?'<a class="quiet-button" href="#/wallet/'+escapeHTML(key)+'" data-activity-wallet-link>View wallet '+activityIcon('arrow')+'</a>':''}</div>
    <details class="activity-log" data-activity-section="stages"><summary>Recorded stages <span>${job.events?.length||0}</span></summary><p class="form-note">Most recent first. Up to 100 stages are retained per task.</p><ol>${events||'<li>No stage updates recorded yet.</li>'}</ol></details>
    <details class="activity-technical" data-activity-section="technical"><summary>Technical details</summary><dl><dt>Task ID</dt><dd><code>${escapeHTML(job.job_id)}</code></dd><dt>Attempt</dt><dd>${job.attempt}</dd>${job.result?.snapshot_id?'<dt>Saved snapshot</dt><dd><code>'+escapeHTML(job.result.snapshot_id)+'</code></dd>':''}</dl></details>`;
  for(const section of body.querySelectorAll('details'))section.open=opened.includes(section.dataset.activitySection);
  body.scrollTop=scroll;
  if(focused){const action=body.querySelector('[data-job-action="'+focused+'"]');(action&&!action.disabled?action:$('activity-detail-close')).focus({preventScroll:true});}
}
function openActivityDetails(id){
  if(!jobList.some(j=>j.job_id===id))return;
  activityDetailId=id;activityDetailSignature='';$('activity-detail-body').innerHTML='';$('activity-detail-body').scrollTop=0;
  renderActivityDetails();if(!$('activity-detail').open)$('activity-detail').showModal();
}
function chooseActivityFilter(value){$('job-filter').value=value;jobsPage=1;loadActivity();}
function clearActivityFilters(){clearTimeout(activitySearchTimer);$('activity-query').value='';$('activity-wallet').value='all';chooseActivityFilter('all');if(typeof KiraSelect!=='undefined')KiraSelect.refresh();}
$('activity-view').addEventListener('click',event=>{
  const filter=event.target.closest('[data-activity-filter]');if(filter){chooseActivityFilter(filter.dataset.activityFilter);return;}
  const detail=event.target.closest('[data-activity-detail]');if(detail)openActivityDetails(detail.dataset.activityDetail);
});
$('activity-current').addEventListener('click',event=>{if(event.target.closest('[data-job-action]'))handleScanAction(event);});
$('activity-wallet').addEventListener('change',()=>{jobsPage=1;loadActivity();});
$('activity-query').addEventListener('input',()=>{clearTimeout(activitySearchTimer);activityEpoch++;activitySearchTimer=setTimeout(()=>{jobsPage=1;loadActivity();},200);});
$('activity-clear').addEventListener('click',clearActivityFilters);
$('activity-detail-close').addEventListener('click',()=>$('activity-detail').close());
$('activity-detail').addEventListener('click',event=>{
  if(event.target.closest('[data-activity-wallet-link]'))$('activity-detail').close();
  if(event.target.closest('[data-job-action]'))handleScanAction(event);
});
$('activity-detail').addEventListener('close',()=>{
  const id=activityDetailId;activityDetailId=null;activityDetailSignature='';
  const button=[...document.querySelectorAll('#jobs-list [data-activity-detail]')].find(node=>node.dataset.activityDetail===id);
  (button||$('activity-title')).focus({preventScroll:true});
});

$('activity-retry').addEventListener('click',()=>loadActivity());
