'use strict';
let portfolioSubmitting=false;
function renderPortfolioActions(){
  const available=localSession?.controls===true&&!!state?.wallets.length&&!state?.demo;
  $('portfolio-actions').hidden=!available;
  for(const id of ['refresh-portfolio','analyze-portfolio'])$(id).disabled=!available||portfolioSubmitting;
}
async function submitPortfolio(operation){
  if(portfolioSubmitting||!localSession?.controls||state?.demo)return;
  if(setupReadiness?.discovery_key_available!==true){await openDataConnections();return;}
  portfolioSubmitting=true;renderPortfolioActions();
  $('portfolio-action-status').textContent='Queuing wallet research…';
  try{
    const receipt=await submitOperation(operation,{});
    const reasons={already_running:'already running',already_analyzed:'already analyzed',holdings_refresh_required:'need a holdings refresh first'};
    const counts={};for(const row of receipt.skipped)counts[row.reason]=(counts[row.reason]||0)+1;
    const skipped=Object.entries(counts).map(([reason,count])=>count+' '+(reasons[reason]||reason)).join(' · ');
    $('portfolio-action-status').textContent=receipt.jobs.length+' wallet jobs accepted. '+(skipped?skipped+'. ':'')+
      (receipt.errors.length?receipt.errors.length+' could not be queued. Retry this action or check Activity. ':'')+'Follow progress in Activity; wallets run one at a time.';
    if(receipt.jobs.length)navigate('#/activity');
  }catch(error){$('portfolio-action-status').textContent=error.message;}
  finally{portfolioSubmitting=false;renderPortfolioActions();}
}
$('refresh-portfolio').addEventListener('click',()=>submitPortfolio('portfolio.refresh'));
$('analyze-portfolio').addEventListener('click',()=>submitPortfolio('portfolio.analyzeSell'));
renderPortfolioActions();
