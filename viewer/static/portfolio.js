'use strict';
let portfolioSubmitting=false;
function renderPortfolioActions(){
  const scoped=typeof FolderUI!=='undefined'&&FolderUI.id;
  const wallets=(scoped?FolderUI.view()?.wallets:state?.wallets)||[];
  const available=localSession?.controls===true&&!!wallets.length&&!state?.demo;
  $('portfolio-actions').hidden=!available;
  for(const id of ['refresh-portfolio','fast-refresh-portfolio','analyze-portfolio'])$(id).disabled=!available||portfolioSubmitting;
  const known=wallets.some(w=>w.sell_analysis),jobs=typeof jobList==='undefined'?[]:jobList,keys=new Set(wallets.map(w=>w.key));
  $('refresh-portfolio').textContent=scoped?'Refresh folder holdings':'Refresh all holdings';
  const busy=new Set(jobs.filter(j=>['queued','running'].includes(j.state)&&['wallet.add','wallet.refresh','prices.refresh'].includes(j.operation)).map(j=>String(j.input?.wallet||j.input?.address||'').toLowerCase()).filter(key=>keys.has(key)));
  const eligible=wallets.filter(w=>w.sell_analysis?.needs_analysis&&!busy.has(w.key)).length;
  if(known){
    $('analyze-portfolio').disabled=!available||portfolioSubmitting||!eligible;
    const retained=wallets.filter(w=>w.sell_analysis?.status==='current').length;
    const pending=wallets.filter(w=>['holdings_required','holdings_pending','unverified'].includes(w.sell_analysis?.status)).length;
    const dates=wallets.map(w=>w.sell_analysis?.last_analyzed_at).filter(Boolean).sort();
    $('analyze-portfolio').textContent=eligible?'Update sell estimates ('+eligible+')':busy.size?'Research in progress':pending?'Waiting for holdings':'Sell estimates saved';
    $('portfolio-sell-status').textContent=retained+' unchanged'+(busy.size?' · '+busy.size+' in progress':'')+(!busy.size&&pending?' · '+pending+' awaiting holdings':'')+(dates.length?' · Last analysis '+stamp(dates.at(-1)):'');
    $('portfolio-sell-status').title=eligible+' wallets need analysis. Unchanged wallets are skipped. '+pending+' await verified holdings. Research runs one wallet at a time.';
  }
}
async function submitPortfolio(operation,options={}){
  if(portfolioSubmitting||!localSession?.controls||state?.demo)return;
  if(setupReadiness?.discovery_key_available!==true){await openDataConnections();return;}
  portfolioSubmitting=true;renderPortfolioActions();
  const folder=typeof FolderUI!=='undefined'?FolderUI.id:null;
  const scopeName=folder?FolderUI.label(folder):'All wallets';
  const fast=options.scope==='fast';
  $('portfolio-action-status').textContent=(fast?'Queuing fast refresh for ':'Queuing wallet research for ')+scopeName+'…';
  try{
    const receipt=await submitOperation(operation,{...(folder?{folder_id:folder}:{}),...(fast?{scope:'fast'}:{})});
    const reasons={already_running:'already running',already_analyzed:'already analyzed',unchanged_holdings:'unchanged; saved estimates retained',holdings_unverified:'need verified holdings',holdings_refresh_required:'need a holdings refresh first'};
    const counts={};for(const row of receipt.skipped)counts[row.reason]=(counts[row.reason]||0)+1;
    const skipped=Object.entries(counts).map(([reason,count])=>count+' '+(reasons[reason]||reason)).join(' · ');
    $('portfolio-action-status').textContent=scopeName+': '+receipt.jobs.length+' wallet jobs accepted. '+(skipped?skipped+'. ':'')+
      (receipt.errors.length?receipt.errors.length+' could not be queued. Retry this action or check Activity. ':'')+'Follow progress in Activity; wallets run one at a time.';
    if(receipt.jobs.length)navigate('#/activity');
  }catch(error){$('portfolio-action-status').textContent=error.message;}
  finally{portfolioSubmitting=false;renderPortfolioActions();}
}
$('refresh-portfolio').addEventListener('click',()=>submitPortfolio('portfolio.refresh'));
$('fast-refresh-portfolio').addEventListener('click',()=>submitPortfolio('portfolio.refresh',{scope:'fast'}));
$('analyze-portfolio').addEventListener('click',()=>submitPortfolio('portfolio.analyzeSell'));
renderPortfolioActions();
