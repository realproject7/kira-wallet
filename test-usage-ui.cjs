'use strict';
// Alchemy usage in Workspace settings, on the Activity tile and in a task's details.
const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const KiraView=require('./viewer/static/workspace-model.js');
const jobs=fs.readFileSync('viewer/static/jobs.js','utf8');
const usageSource=jobs.slice(jobs.indexOf('// Alchemy usage.'),jobs.indexOf("$('rpc-add').addEventListener('click'"));
const escapeHTML=s=>String(s??'').replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('"','&quot;');
const ago=minutes=>new Date(Date.now()-minutes*60000).toISOString();
const kira={totals:{today:{cu:244370,requests:9619},last_7_days:{cu:2544370,requests:113619},this_month:{cu:3694370,requests:165619}},
  last_run:{id:'batch-1',kind:'batch',cu:241000,requests:9500,wallets:76,scope:'fast',first:ago(125),last:ago(120)},basis:"Kira's own Alchemy requests, priced from Alchemy's compute unit costs. Other apps on the same account are not included."};
const official={checked_at:ago(4),ok:true,summary_checked_at:ago(4),summary:{month_to_date:{cu:4210000,usd:0},last_7_days:{cu:2900000,usd:0},last_30_days:{cu:6800000,usd:0},
  billing_period:{startTime:'2026-11-01T00:00:00.000Z',endTime:'2026-12-01T00:00:00.000Z'},data_through:ago(10),usage_limit:{unit:'CU',limit:30000000,used:4210000,remaining:25790000,percent_used:14.03}}};
// The local app adds the month's allowance (the cap, or the Free plan's units) and its reset.
const allowance={unit:'CU',limit:30000000,used:4210000,basis:'cap',resets_at:'2026-12-01T00:00:00.000Z'};

function harness(view,{controls=true,demo=false}={}){
  const nodes=new Map(),calls=[];
  const node=id=>{if(!nodes.has(id))nodes.set(id,{id,hidden:false,disabled:false,innerHTML:'',textContent:'',value:0,attributes:{},listeners:{},
    setAttribute(k,v){this.attributes[k]=v;},addEventListener(k,fn){this.listeners[k]=fn;},scrollIntoView(){this.scrolled=true;}});return nodes.get(id);};
  const context={$:node,escapeHTML,stamp:value=>'stamp:'+value,state:{demo,wallets:[]},localSession:{controls},Intl,Date,Number,Math,Promise,JSON,crypto:{randomUUID:()=>'uuid-1'},
    AbortSignal:{timeout:ms=>({ms})},requestAnimationFrame:fn=>fn(),openWorkspaceSettings:section=>calls.push(['open',section]),
    localAPI:async(path,options)=>{calls.push([path,options&&JSON.parse(options.body||'null')]);if(typeof context.answer==='function')return context.answer(path,options);return view;}};
  vm.createContext(context);vm.runInContext(usageSource,context);
  return {context,node,calls,run:code=>vm.runInContext(code,context)};
}
const settle=()=>new Promise(resolve=>setImmediate(resolve));

test('without an Access Key the panel shows Kira\'s estimate, the connect command and networks to enable',async()=>{
  const h=harness({kira,official:null,access_key:false,networks_not_enabled:[{network:'robinhood-mainnet',name:'Robinhood Chain',chain_id:4663}],schema_version:1});
  await h.run('loadUsage(true)');
  assert.deepEqual(h.calls,[['/api/usage',undefined]]);
  assert.equal(h.node('alchemy-usage').hidden,false);assert.equal(h.node('activity-usage').hidden,false);
  const stats=h.node('usage-kira').innerHTML.replace(/<[^>]*>/g,' ').replace(/\s+/g,' ').trim();
  assert.equal(stats,'Today ≈ 244K CU 7 days ≈ 2.54M CU This month ≈ 3.69M CU');
  assert.equal(h.node('usage-last-run').textContent,'Last run ≈ 241K CU for 76 wallets · 2 h ago');
  assert.equal(h.node('usage-account').hidden,true);assert.equal(h.node('usage-check').hidden,true);assert.equal(h.node('usage-connect').hidden,false);
  assert.equal(h.node('usage-checked').textContent,'');
  assert.equal(h.node('usage-networks').hidden,false);
  assert.equal(h.node('usage-networks-text').textContent,'Robinhood Chain is not enabled in your Alchemy app. Kira reads it from public RPC.');
  assert.equal(h.node('activity-usage-value').textContent,'≈ 3.69M CU');assert.equal(h.node('activity-usage-bar').hidden,true);
  assert.equal(h.node('activity-usage-of').hidden,true);assert.equal(h.node('activity-usage-label').textContent,'Alchemy this month');
  assert.match(h.node('activity-usage').title,/Kira's own estimate this month/);
  assert.equal(h.node('usage-meter').hidden,true,'The top bar shows account usage only.');
  assert.match(h.node('usage-basis').textContent,/Other apps on the same account are not included/);
});

test('with an Access Key the account month, limit, reset and check time lead, on the tile and the top bar too',async()=>{
  const h=harness({kira,official,allowance,access_key:true,networks_not_enabled:[],schema_version:1});
  await h.run('loadUsage(true)');
  const account=h.node('usage-account').innerHTML;
  assert.equal(h.node('usage-account').hidden,false);
  assert.match(account,/Alchemy account · this month<\/span><strong>4.21M CU<\/strong>/);
  assert.match(account,/<progress class="allocation-progress usage-progress" value="4210000" max="30000000" aria-label="14% of the monthly limit used">/);
  assert.equal(account.replace(/<[^>]*>/g,'').split('CU').slice(1).join('CU').trim(),'14% of 30M CU · Resets Dec 1 · 7 days 2.9M CU · 30 days 6.8M CU');
  assert.equal(h.node('usage-checked').textContent,'Checked 4 min ago');
  assert.equal(h.node('usage-check').hidden,false);assert.equal(h.node('usage-connect').hidden,true);assert.equal(h.node('usage-networks').hidden,true);
  assert.equal(h.node('activity-usage-value').textContent,'14%');assert.equal(h.node('activity-usage-of').hidden,false);assert.equal(h.node('activity-usage-of').textContent,'of 30M CU');
  assert.equal(h.node('activity-usage-label').textContent,'Alchemy · resets Dec 1');assert.equal(h.node('activity-usage').title,'4.21M of 30M CU used this month. Resets Dec 1.');
  assert.equal(h.node('activity-usage-bar').hidden,false);assert.equal(h.node('activity-usage-bar').value,4210000/30000000*100);
  assert.equal(h.node('activity-usage-bar').attributes['aria-label'],'14% of the monthly limit used');
  await h.run('loadUsage()');assert.equal(h.calls.length,1,'A fresh view is reused for half a minute.');
  h.node('activity-usage').listeners.click();assert.deepEqual(h.calls.at(-1),['open','data']);assert.equal(h.node('alchemy-usage').scrolled,true);
  // The top bar meter: the share of the month, its amounts, reset and check time on hover.
  assert.equal(h.node('usage-meter').hidden,false);assert.equal(h.node('usage-meter-value').textContent,'14%');
  assert.equal(h.node('usage-meter-bar').hidden,false);assert.equal(h.node('usage-meter-bar').value,4210000/30000000*100);
  assert.equal(h.node('usage-meter').title,'4.21M of 30M CU used this month. Resets Dec 1. Checked 4 min ago.');
  assert.equal(h.node('usage-meter').attributes['aria-label'],'Alchemy usage. 4.21M of 30M CU used this month. Resets Dec 1. Checked 4 min ago. Open usage details.');
  h.calls.length=0;h.node('usage-meter').listeners.click();assert.deepEqual(h.calls,[['open','data']]);
});

test('a refused check names the fix and keeps the last good numbers; tiny use reads as under one percent',async()=>{
  const failed={...official,ok:false,checked_at:ago(1),summary_checked_at:ago(180),error:{status:401,message:'Invalid token [redacted]',hint:'Alchemy did not accept the Access Key. Create one in the dashboard Security tab with Usage read access, then run kira connect alchemy-usage.'}};
  failed.summary={...official.summary,month_to_date:{cu:90000,usd:0},usage_limit:{...official.summary.usage_limit,used:90000}};
  const h=harness({kira:{...kira,last_run:null},official:failed,allowance:{...allowance,used:90000},access_key:true,networks_not_enabled:[{name:'Robinhood Chain'},{name:'Ink'},{name:null,chain_id:7}],schema_version:1});
  await h.run('loadUsage(true)');
  assert.equal(h.node('usage-checked').textContent,'Alchemy did not accept the Access Key. Create one in the dashboard Security tab with Usage read access, then run kira connect alchemy-usage. Showing the check from 3 h ago.');
  assert.match(h.node('usage-account').innerHTML,/<span>&lt;1% of 30M CU<\/span>/);
  assert.equal(h.node('usage-last-run').textContent,'No Alchemy requests recorded yet.');
  assert.equal(h.node('usage-networks-text').textContent,'Robinhood Chain, Ink and Network 7 are not enabled in your Alchemy app. Kira reads them from public RPC.');
});

test('Check now asks the local app once, shows the new totals or the reason it could not',async()=>{
  const h=harness({kira,official:null,access_key:true,networks_not_enabled:[],schema_version:1});
  await h.run('loadUsage(true)');
  h.context.answer=(path,options)=>path==='/api/operations'?{status:'completed',operation:'alchemy.usageCheck',usage:{kira,official,access_key:true,networks_not_enabled:[],schema_version:1}}:null;
  const first=h.node('usage-check').listeners.click();h.node('usage-check').listeners.click();
  assert.equal(h.node('usage-check').disabled,true);assert.equal(h.node('usage-checked').textContent,'Checking with Alchemy…');
  await first;await settle();
  const posts=h.calls.filter(([path])=>path==='/api/operations');
  assert.deepEqual(posts,[['/api/operations',{schema_version:1,operation:'alchemy.usageCheck',input:{},idempotency_key:'uuid-1'}]]);
  assert.equal(h.node('usage-check').disabled,false);assert.equal(h.node('usage-checked').textContent,'Checked 4 min ago');
  assert.equal(h.node('activity-usage-value').textContent,'4.21M CU');
  h.context.answer=path=>{if(path==='/api/operations')throw new Error('Connect an Alchemy Access Key first: run kira connect alchemy-usage in your terminal.');};
  await h.node('usage-check').listeners.click();
  assert.equal(h.node('usage-checked').textContent,'Connect an Alchemy Access Key first: run kira connect alchemy-usage in your terminal.');
  assert.equal(h.node('usage-check').disabled,false);
});

test('the Free plan allowance is named, and a paid month without a cap shows its total without a bar',async()=>{
  const free={...official,summary:{...official.summary,usage_limit:null}};
  const h=harness({kira,official:free,allowance:{...allowance,basis:'free_plan'},access_key:true,networks_not_enabled:[],schema_version:1});
  await h.run('loadUsage(true)');
  assert.match(h.node('usage-account').innerHTML,/<span>14% of 30M CU \(Free plan\)<\/span> · <span>Resets Dec 1<\/span>/);
  assert.equal(h.node('usage-meter').title,'4.21M of 30M CU (Free plan) used this month. Resets Dec 1. Checked 4 min ago.');
  const paid={...free,summary:{...free.summary,month_to_date:{cu:4210000,usd:'2.21'}}};
  const p=harness({kira,official:paid,allowance:{unit:null,limit:null,used:null,basis:null,resets_at:'2026-12-01T00:00:00.000Z'},access_key:true,networks_not_enabled:[],schema_version:1});
  await p.run('loadUsage(true)');
  assert.equal(p.node('usage-meter').hidden,false);assert.equal(p.node('usage-meter-bar').hidden,true);assert.equal(p.node('usage-meter-value').textContent,'4.21M CU');
  assert.equal(p.node('activity-usage-value').textContent,'4.21M CU');assert.equal(p.node('activity-usage-of').hidden,true);assert.equal(p.node('activity-usage-bar').hidden,true);
  assert.equal(p.node('activity-usage-label').textContent,'Alchemy · resets Dec 1');
  assert.match(p.node('usage-account').innerHTML,/<span>Resets Dec 1<\/span> · <span>\$2.21<\/span>/);assert.doesNotMatch(p.node('usage-account').innerHTML,/<progress/);
});

test('the top bar reads saved usage at start, when tasks change and every five minutes, and never asks Alchemy',async()=>{
  const h=harness({kira,official,allowance,access_key:true,networks_not_enabled:[],schema_version:1});
  await h.run('pollUsage(false)');assert.equal(h.calls.length,1,'The first poll reads usage.');
  await h.run('pollUsage(false)');assert.equal(h.calls.length,1,'A fresh read is kept.');
  await h.run('pollUsage(true)');assert.equal(h.calls.length,1,'Task changes within half a minute reuse the read.');
  await h.run('usageReadAt=Date.now()-31000;pollUsage(true)');assert.equal(h.calls.length,2,'A task change reads again after half a minute.');
  await h.run('usageReadAt=Date.now()-299000;pollUsage(false)');assert.equal(h.calls.length,2);
  await h.run('usageReadAt=Date.now()-300000;pollUsage(false)');assert.equal(h.calls.length,3,'Five minutes later it reads again.');
  assert.ok(h.calls.every(([path])=>path==='/api/usage'),'Polling reads saved records only.');
});

test('a sample or read-only workspace never asks for usage',async()=>{
  for(const options of [{demo:true},{controls:false}]){
    const h=harness({kira},options);
    assert.equal(await h.run('loadUsage(true)'),null);
    assert.deepEqual(h.calls,[]);
  }
  const h=harness(null);h.context.answer=()=>{throw new Error('offline');};
  assert.equal(await h.run('loadUsage(true)'),null);
  assert.equal(h.node('alchemy-usage').hidden,true);assert.equal(h.node('activity-usage').hidden,true);
});

test('a task\'s details show what it used, and a batch says it shares one total',async()=>{
  const now=new Date().toISOString(),A='0x'+'1'.repeat(40);
  const base={job_id:'job-a',input:{wallet:A},operation:'wallet.refresh',analysis_phase:'baseline',created_at:now,updated_at:now,started_at:now,state:'succeeded',attempt:1,events:[],result:null};
  const nodes=new Map(),requests=[];
  const node=id=>{if(!nodes.has(id))nodes.set(id,{id,value:'all',innerHTML:'',textContent:'',dataset:{},hidden:false,open:false,scrollTop:0,attributes:{},listeners:{},
    querySelectorAll:()=>[],querySelector:()=>null,setAttribute(k,v){this.attributes[k]=v;},addEventListener(k,fn){this.listeners[k]=fn;},showModal(){this.open=true;},close(){this.open=false;},focus(){}});return nodes.get(id);};
  const answers={'job-a':{cu:241000,requests:9500,batch_wallets:76},'job-b':{cu:3370,requests:119}};
  const context={KiraView,$:node,state:{wallets:[{key:A,name:'Savings'}]},jobList:[base,{...base,job_id:'job-b'},{...base,job_id:'job-c',operation:'settings.rpc'}],activityData:null,activityEpoch:0,jobsPage:1,selectedView:'activity',
    workspaceStatus:{active_job_count:0},jobsConnected:true,lastJobsPoll:Date.now(),localSession:{controls:true},document:{activeElement:null,querySelectorAll:()=>[]},
    escapeHTML,jobLabels:{},shortAddress:s=>s.slice(0,8),stamp:s=>s,jobControls:()=>'',assetProgressText:()=>'',jobStage:()=>'',researchStage:e=>e.stage,
    loadActivity:async()=>{},handleScanAction:()=>{},setTimeout:()=>1,clearTimeout(){},Date,
    usageAmount:(cu,estimate)=>(estimate&&cu>0?'≈ ':'')+new Intl.NumberFormat('en-US',{notation:'compact',maximumSignificantDigits:3}).format(cu)+' CU',
    localAPI:async path=>{requests.push(path);return {job:answers[decodeURIComponent(path.split('job=')[1])]??null,schema_version:1};}};
  vm.createContext(context);vm.runInContext(fs.readFileSync('viewer/static/activity.js','utf8'),context);
  const facts=()=>node('activity-detail-body').innerHTML.match(/<dl class="activity-facts">[\s\S]*?<\/dl>/)[0].replace(/<[^>]*>/g,' ').replace(/\s+/g,' ').trim();
  vm.runInContext("openActivityDetails('job-a')",context);await settle();
  assert.deepEqual(requests,['/api/usage?job=job-a']);
  assert.match(facts(),/Alchemy ≈ 241K CU · 76-wallet batch$/);
  assert.match(node('activity-detail-body').innerHTML,/<div class="activity-usage-fact"><dt>Alchemy<\/dt>/);
  vm.runInContext('renderActivityDetails()',context);await settle();assert.equal(requests.length,1,'A finished task is read once.');
  vm.runInContext("$('activity-detail').close();openActivityDetails('job-b')",context);await settle();
  assert.match(facts(),/Alchemy ≈ 3.37K CU$/);
  vm.runInContext("$('activity-detail').close();openActivityDetails('job-c')",context);await settle();
  assert.equal(requests.length,2,'Settings tasks do not read Alchemy.');assert.doesNotMatch(facts(),/Alchemy/);
});
