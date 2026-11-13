'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const nodes=new Map();
function $(id){if(!nodes.has(id))nodes.set(id,{textContent:'',hidden:false,disabled:false,listeners:{},addEventListener(event,callback){this.listeners[event]=callback;}});return nodes.get(id);}
let resolve,requests=0,connections=0;
const context={$,localSession:{controls:true},state:{wallets:[{key:'synthetic'}],demo:false},setupReadiness:{discovery_key_available:true},
  submitOperation:async()=>{requests++;return new Promise(done=>{resolve=done;});},navigate(){},openDataConnections:async()=>{connections++;}};
vm.createContext(context);vm.runInContext(fs.readFileSync('viewer/static/portfolio.js','utf8'),context);
(async()=>{
  const pending=context.submitPortfolio('portfolio.refresh');
  assert.equal($('refresh-portfolio').disabled,true);
  await context.submitPortfolio('portfolio.refresh');assert.equal(requests,1);
  resolve({jobs:[{job_id:'synthetic'}],skipped:[{reason:'already_running'},{reason:'holdings_refresh_required'}],errors:[]});await pending;
  assert.match($('portfolio-action-status').textContent,/1 wallet jobs accepted/);
  assert.match($('portfolio-action-status').textContent,/1 already running/);
  assert.match($('portfolio-action-status').textContent,/1 need a holdings refresh first/);
  assert.equal($('refresh-portfolio').disabled,false);
  context.submitOperation=async()=>{throw new Error('Connection lost. Retry the same request.');};
  await context.submitPortfolio('portfolio.analyzeSell');assert.match($('portfolio-action-status').textContent,/Connection lost/);assert.equal($('analyze-portfolio').disabled,false);
  context.setupReadiness.discovery_key_available=false;await context.submitPortfolio('portfolio.refresh');assert.equal(connections,1);
  context.state.wallets=[{key:'unchanged',sell_analysis:{status:'current',needs_analysis:false}},{key:'changed',sell_analysis:{status:'changed',needs_analysis:true}},{key:'new',sell_analysis:{status:'not_analyzed',needs_analysis:true}},{key:'pending',sell_analysis:{status:'holdings_pending',needs_analysis:false}}];
  context.renderPortfolioActions();assert.equal($('analyze-portfolio').textContent,'Update sell estimates (2)');
  assert.match($('portfolio-sell-status').textContent,/1 unchanged · 1 awaiting holdings/);assert.match($('portfolio-sell-status').title,/2 wallets need analysis/);
  context.jobList=[{state:'queued',operation:'wallet.refresh',input:{wallet:'changed'}}];context.renderPortfolioActions();
  assert.equal($('analyze-portfolio').textContent,'Update sell estimates (1)');
  context.state.wallets=context.state.wallets.slice(0,1);context.renderPortfolioActions();
  assert.equal($('analyze-portfolio').disabled,true);assert.equal($('refresh-portfolio').disabled,false);
  context.localSession.controls=false;context.renderPortfolioActions();assert.equal($('portfolio-actions').hidden,true);
  await context.submitPortfolio('portfolio.refresh');assert.equal(requests,1);
  context.localSession.controls=true;context.state.demo=true;context.renderPortfolioActions();assert.equal($('portfolio-actions').hidden,true);
  console.log('Portfolio controls prevent double submission, retain errors and honor read-only and sample modes.');
})().catch(error=>{console.error(error);process.exitCode=1;});
const activity={$,selectedView:'home',jobList:[{job_id:'queued',state:'queued',created_at:'2026-11-01',input:{}},{job_id:'running',state:'running',created_at:'2026-11-02',input:{}},{job_id:'later',state:'queued',created_at:'2026-11-03',input:{}}],state:{wallets:[]},KiraView:{active:j=>['queued','running'].includes(j.state),jobPresentation:()=>({}),jobTimeText:()=>''},jobsConnected:true,escapeHTML:String,jobStage:j=>j.job_id,jobControls:()=>'',jobLabels:{},Date};
vm.createContext(activity);
const jobsSource=fs.readFileSync('viewer/static/jobs.js','utf8');
vm.runInContext(jobsSource.slice(jobsSource.indexOf('function renderActiveWork(){'),jobsSource.indexOf('async function loadActivity(){')),activity);
activity.renderActiveWork();
assert.equal(($('active-work').innerHTML.match(/class="active-work-row"/g)||[]).length,1);
assert.match($('active-work').innerHTML,/running/);assert.match($('active-work').innerHTML,/All tasks \(3\)/);
