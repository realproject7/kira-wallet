'use strict';
// Exercise the persisted-state presentation and real click controller without
// provider calls. The browser acceptance also covers layout and real HTTP.
const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const KiraView=require('./viewer/static/workspace-model.js');
const A='0x'+'1'.repeat(40),wallet={key:A,analysed_at:'2026-10-15T00:00:00Z',assets:[{}],unpriced_count:1};
const basic={job_id:'basic',operation:'wallet.refresh',input:{wallet:A},analysis_phase:'baseline',scan_policy:'optional_depth_v1',state:'partial',created_at:'2026-10-15T00:00:00Z',result:{snapshot_id:'saved'},events:[],attempt:1};
const deep={...basic,job_id:'deep',analysis_phase:'enrichment',parent_job_id:'basic',state:'running',created_at:'2026-10-15T00:01:00Z',result:null};
test('basic saved results offer optional depth without implying complete coverage',()=>{
 const p=KiraView.researchSession([basic],wallet);
 assert.equal(p.mode,'ready');assert.equal(p.action,'deepen');assert.match(p.description,/optional/);assert.equal(p.basicReady,true);
 assert.equal(KiraView.researchSession([basic],{key:'other'}),null);
 const interrupted=KiraView.researchSession([{...basic,state:'interrupted'}],wallet);
 assert.equal(interrupted.action,'resume');assert.equal(interrupted.basicReady,false);
});
test('deep waits, pause, disconnect recovery and new basic generations stay distinct',()=>{
 const p=KiraView.researchSession([deep,basic],wallet);assert.equal(p.action,'cancel');assert.equal(p.isDeep,true);
 const paused=KiraView.researchSession([{...deep,state:'cancelled'},basic],wallet);
 assert.equal(paused.mode,'paused');assert.equal(paused.action,'resume');assert.match(paused.description,/without starting over/);
 const waiting=KiraView.researchSession([{...deep,state:'queued',continuation:{not_before:Date.now()/1000+120}},basic],wallet);
 assert.match(waiting.title,/waiting to continue/);
 const stalled=KiraView.researchSession([{...deep,state:'interrupted',errors:[{code:'no_progress'}]},basic],wallet);
 assert.equal(stalled.actionLabel,'Retry saved scan');assert.match(stalled.description,/no new progress/);
 const newer={...basic,job_id:'new-basic',state:'queued',created_at:'2026-10-15T00:02:00Z'};
 assert.equal(KiraView.researchSession([basic,deep,newer],wallet).job.job_id,'new-basic');
 const done=KiraView.researchSession([{...deep,state:'partial'},basic],wallet);
 assert.equal(done.mode,'saved');assert.equal(done.action,null);assert.match(done.description,/unknown/);
});
function harness(){
 const nodes=new Map();let focus=null,rendered=0;
 const el=id=>{if(!nodes.has(id))nodes.set(id,{hidden:false,dataset:{},textContent:'',innerHTML:'',contains:node=>!!node&&node===focus,querySelector:()=>null,querySelectorAll:()=>[],focus(){},addEventListener(){}});return nodes.get(id);};
 const context=vm.createContext({KiraView,$:el,document:{get activeElement(){return focus;}},currentWallet:()=>wallet,state:{wallets:[wallet]},jobList:[basic],jobsConnected:true,localSession:{controls:true},
  escapeHTML:s=>String(s).replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('"','&quot;'),stamp:s=>s,Date,
  renderJobs:()=>{rendered++;},toast(){}});
 const source=fs.readFileSync('viewer/static/jobs.js','utf8');
 vm.runInContext(source.slice(0,source.indexOf('async function localAPI(')),context);
 vm.runInContext(source.slice(source.indexOf('async function handleScanAction('),source.indexOf("$('jobs-list').addEventListener('click',handleScanAction)")),context);
 vm.runInContext('localSession={controls:true};jobList=globalThis.testJobs||[]',context); // Reset below after lexical declarations.
 context.setJobs=jobs=>{context.testJobs=jobs;vm.runInContext('jobList=testJobs',context);};context.setJobs([basic]);
 return {context,el,setJobs:context.setJobs,run:s=>vm.runInContext(s,context),renders:()=>rendered};
}
test('wallet card keeps unknowns visible and disables writes while disconnected or read-only',()=>{
 const h=harness();h.run('renderWalletScan()');assert.match(h.el('wallet-scan').innerHTML,/Start deep scan/);
 assert.match(h.el('wallet-scan').innerHTML,/1 position saved · 1 unpriced/);
 assert.match(h.el('wallet-scan').innerHTML,/no overall time limit/);
 h.context.jobsConnected=false;h.run('renderWalletScan()');assert.match(h.el('wallet-scan').innerHTML,/Reconnecting/);assert.match(h.el('wallet-scan').innerHTML,/disabled/);
 h.run('localSession={controls:false};renderWalletScan()');assert.doesNotMatch(h.el('wallet-scan').innerHTML,/data-job-action/);
 h.run('localSession={controls:true};state.demo=true;renderWalletScan()');assert.doesNotMatch(h.el('wallet-scan').innerHTML,/data-job-action/);
 h.context.jobsConnected=true;h.run('state.demo=false');h.context.testJobs=[deep,basic];h.setJobs?.(h.context.testJobs);
 h.run('jobList=testJobs;renderWalletScan()');assert.match(h.el('wallet-scan').innerHTML,/Overall remaining time is unknown/);assert.doesNotMatch(h.el('wallet-scan').innerHTML,/<progress/);
 h.setJobs([{...deep,state:'cancelled',cancel_requested:true},basic]);h.run('renderWalletScan()');
 assert.match(h.el('wallet-scan').innerHTML,/Resume deep scan/);assert.doesNotMatch(h.el('wallet-scan').innerHTML,/disabled/);
 h.setJobs([{...deep,state:'queued',stage:'stopped',events:[{stage:'onchain_progress',counts:{checked:7,total:20},context:{operation:'pool_checks',attempt:deep.attempt}}]},basic]);h.run('renderWalletScan()');
 assert.match(h.el('wallet-scan').innerHTML,/Waiting to start/);assert.doesNotMatch(h.el('wallet-scan').innerHTML,/Research stopped|7 \/ 20|<progress|are being checked/);
});
test('cumulative reviews remain visible through step resets, pause and resume',()=>{
 const h=harness(),asset_progress={'8453':{total:100,checked:72,quoted:12,unknown:60},'1':{total:20,checked:9,quoted:2,unknown:7}};
 assert.deepEqual(KiraView.assetProgress({...deep,asset_progress:{...asset_progress,'137':{total:50,checked:0,quoted:0,unknown:0}}}),{total:170,checked:81,quoted:14,unknown:67});
 for(const state of ['running','cancelled','queued','partial']){
  const job={...deep,state,asset_progress,events:[{stage:'onchain_progress',counts:{checked:0,total:10},context:{operation:'pool_checks',attempt:2}}]};
  assert.deepEqual(KiraView.jobProgress(job).assets,{total:120,checked:81,quoted:14,unknown:67});
  h.setJobs([job,basic]);h.run('renderWalletScan()');const html=h.el('wallet-scan').innerHTML;
  assert.match(html,/81 \/ 120 assets reviewed/);assert.match(html,/>14<\/strong> sell estimates/);assert.match(html,/>67<\/strong> unresolved checks/);
  assert.match(html,/the total can grow/);
 }
 assert.equal(KiraView.assetProgress({...deep,asset_progress:{'1':{total:2,checked:2,quoted:2,unknown:1}}}),null);
});
test('one click stays in flight through double clicks, preserves job identity and allows retry after failure',async()=>{
 const h=harness(),calls=[];let release;
 h.context.submitOperation=(operation,input)=>{calls.push({operation,input});return new Promise(resolve=>{release=resolve;});};
 const button={disabled:false,dataset:{jobAction:'deepen',jobId:'basic'}},event={target:{closest:()=>button}};
 h.context.event=event;const pending=h.run('handleScanAction(event)');await h.run('handleScanAction(event)');
 assert.equal(calls.length,1);assert.equal(button.disabled,true);assert.equal(calls[0].operation,'job.deepen');assert.equal(calls[0].input.job_id,'basic');
 release({job_id:'deep'});await pending;assert.equal(h.run('scanBusyJobs.size'),0);
 button.disabled=false;h.context.submitOperation=async()=>{throw Error('Temporary failure');};await h.run('handleScanAction(event)');assert.equal(h.run('scanBusyJobs.size'),0);
 assert.equal(h.renders(),2);
});
