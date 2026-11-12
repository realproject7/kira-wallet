'use strict';
let portfolioSubmitting=false;
function renderPortfolioActions(){
  const available=localSession?.controls===true&&!!state?.wallets.length&&!state?.demo;
  $('portfolio-actions').hidden=!available;
  for(const id of ['refresh-portfolio','analyze-portfolio'])$(id).disabled=!available||portfolioSubmitting;
  const wallets=state?.wallets||[],known=wallets.some(w=>w.sell_analysis),jobs=typeof jobList==='undefined'?[]:jobList;
  const busy=new Set(jobs.filter(j=>['queued','running'].includes(j.state)&&['wallet.add','wallet.refresh','prices.refresh'].includes(j.operation)).map(j=>String(j.input?.wallet||j.input?.address||'').toLowerCase()));
  const eligible=wallets.filter(w=>w.sell_analysis?.needs_analysis&&!busy.has(w.key)).length;
  if(known){
    $('analyze-portfolio').disabled=!available||portfolioSubmitting||!eligible;
    const retained=wallets.filter(w=>w.sell_analysis?.status==='current').length;
    const pending=wallets.filter(w=>['holdings_required','holdings_pending','unverified'].includes(w.sell_analysis?.status)).length;
    const dates=wallets.map(w=>w.sell_analysis?.last_analyzed_at).filter(Boolean).sort();
    $('analyze-portfolio').textContent=eligible?'Update sell estimates ('+eligible+')':busy.size?'Research in progress':pending?'Waiting for holdings':'Sell estimates saved';
    $('portfolio-sell-status').textContent=eligible+' wallets need analysis · '+retained+' unchanged'+(busy.size?' · '+busy.size+' queued or running':'')+(pending?' · '+pending+' awaiting verified holdings':'')+'. Unchanged wallets are skipped.'+(dates.length?' Last sell analysis '+stamp(dates.at(-1))+'.':'');
  }
}
async function submitPortfolio(operation){
  if(portfolioSubmitting||!localSession?.controls||state?.demo)return;
  if(setupReadiness?.discovery_key_available!==true){await openDataConnections();return;}
  portfolioSubmitting=true;renderPortfolioActions();
  $('portfolio-action-status').textContent='Queuing wallet research…';
  try{
    const receipt=await submitOperation(operation,{});
    const reasons={already_running:'already running',already_analyzed:'already analyzed',unchanged_holdings:'unchanged; saved estimates retained',holdings_unverified:'need verified holdings',holdings_refresh_required:'need a holdings refresh first'};
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
