'use strict';
let h402Loaded=false,h402Busy=false,h402Revision=0,h402Saved=null,h402Pending=null;
function renderH402(value,preserveChoice=false){
  if(!preserveChoice||!h402Saved||$('h402-enabled').checked===h402Saved.enabled)$('h402-enabled').checked=value.enabled;
  h402Saved=value;
  const labels={disabled:value.installed?'Installed, not enabled for this workspace.':'Not enabled. Install h402 only if you want extra tools.',not_installed:'Enabled, but h402 was not found. Install it with your agent, then check again.',available:'Available'+(value.version?' · h402 '+value.version:'')+'. Your agent chooses when to use it.',unavailable:'h402 was found, but its version check failed. Ask your agent to check the installation.'};
  $('h402-summary').textContent=labels[value.status]||'Installation status is unknown.';
  $('h402-prompt').value=value.install_prompt;
  $('h402-copy').disabled=false;$('h402-copy').textContent='Copy install prompt';
  h402Loaded=true;
}
async function loadH402Settings(preserveChoice=false,settings=null){
  if(h402Busy)return;
  const revision=++h402Revision;
  h402Loaded=false;$('h402-fields').disabled=true;$('h402-error').textContent='';
  $('h402-summary').textContent='Checking h402…';
  try{const config=await (settings||localAPI('/api/settings'));if(revision===h402Revision)renderH402(config.integrations.h402,preserveChoice);}
  catch{if(revision===h402Revision)$('h402-error').textContent='Could not check h402. Reopen settings to retry.';}
  finally{if(revision===h402Revision)$('h402-fields').disabled=!h402Loaded;}
}
async function saveH402Preference(event){
  event.preventDefault();if(h402Busy||!h402Loaded)return;
  const enabled=$('h402-enabled').checked;
  h402Busy=true;h402Revision++;$('h402-fields').disabled=true;$('h402-error').textContent='';
  try{
    if(!h402Pending){const job=await submitOperation('settings.h402',{enabled});h402Pending={id:job.job_id,enabled};}
    $('h402-status').textContent='Preference queued. Waiting for the saved result…';
    for(let attempt=0;attempt<20;attempt++){
      const job=await localAPI('/api/jobs/'+encodeURIComponent(h402Pending.id));
      if(['succeeded','failed','cancelled','interrupted','partial'].includes(job.state)){
        const pending=h402Pending;
        if(job.state!=='succeeded'){h402Pending=null;throw Error('Preference was not saved. Review Activity and retry.');}
        const config=await localAPI('/api/settings');renderH402(config.integrations.h402);
        h402Pending=null;
        $('h402-status').textContent=pending.enabled===enabled?'Preference saved.':'The earlier preference was saved. Review your choice and save again.';
        return;
      }
      await new Promise(resolve=>setTimeout(resolve,400));
    }
    throw Error('Preference is still queued. Save again to check the same request, or view Activity.');
  }catch(error){$('h402-error').textContent=error.message;}
  finally{h402Busy=false;$('h402-fields').disabled=!h402Loaded;}
}
$('h402-form').addEventListener('submit',saveH402Preference);
$('h402-recheck').addEventListener('click',()=>loadH402Settings(true));
$('h402-copy').addEventListener('click',async()=>{
  try{await navigator.clipboard.writeText($('h402-prompt').value);$('h402-copy').textContent='Copied';}
  catch{$('h402-copy').textContent='Select the prompt to copy it';}
});
