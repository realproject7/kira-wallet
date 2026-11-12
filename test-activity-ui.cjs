'use strict';
const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const KiraView=require('./viewer/static/workspace-model.js');
const A='0x'+'1'.repeat(40),B='0x'+'2'.repeat(40),now=new Date().toISOString();
const base={job_id:'saved-baseline',input:{wallet:A},operation:'wallet.refresh',analysis_phase:'baseline',scan_policy:'alchemy_inventory_v1',created_at:now,updated_at:now,state:'partial',attempt:1,events:[{stage:'published',observed_at:now,counts:{raw_internal_counter:100}}],result:{snapshot_id:'snapshots/saved'}};
function harness(){
 const nodes=new Map(),filters=['all','active','attention','succeeded','cancelled'],calls=[];
 const node=id=>{
  if(!nodes.has(id))nodes.set(id,{id,value:id==='activity-query'?'':'all',innerHTML:'',textContent:'',dataset:{},hidden:false,open:false,scrollTop:0,attributes:{},listeners:{},
   querySelectorAll:()=>[],querySelector:()=>null,setAttribute(k,v){this.attributes[k]=v;},addEventListener(k,fn){this.listeners[k]=fn;},showModal(){this.open=true;},close(){this.open=false;this.listeners.close?.();},focus(){}});
  return nodes.get(id);
 };
 const counts=filters.map(value=>{const n=node('count-'+value);n.dataset.activityCount=value;return n;}),tabs=filters.map(value=>{const n=node('tab-'+value);n.dataset.activityFilter=value;return n;});
 const context={KiraView,$:node,state:{wallets:[{key:A,name:'Savings',sell_analysis:{status:'current',last_analyzed_at:now}},{key:B,name:'Research'}]},jobList:[base],activityData:null,activityEpoch:0,jobsPage:1,selectedView:'activity',workspaceStatus:{active_job_count:0},jobsConnected:true,lastJobsPoll:now,localSession:{controls:true},jobLabels:{},
  document:{activeElement:null,querySelectorAll:selector=>selector==='[data-activity-count]'?counts:selector.startsWith('#activity-tabs')?tabs:[]},
  escapeHTML:s=>String(s??'').replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('"','&quot;'),shortAddress:s=>s.slice(0,8),stamp:s=>s,
  jobControls:()=>'<button data-job-action="deepen">Calculate sell estimates</button>',assetProgressText:p=>p.assets?.checked+' assets reviewed',jobStage:()=> 'Checking balances',researchStage:e=>e.stage,
  loadActivity:async()=>{calls.push({state:node('job-filter').value,wallet:node('activity-wallet').value,query:node('activity-query').value});},handleScanAction:()=>{calls.push('write');},setTimeout:fn=>{context.debounce=fn;return 1;},clearTimeout(){},Date};
 vm.createContext(context);vm.runInContext(fs.readFileSync('viewer/static/activity.js','utf8'),context);
 return {context,node,counts,tabs,calls,run:code=>vm.runInContext(code,context)};
}
test('history is compact, counts cover saved history and diagnostics wait for details',()=>{
 const h=harness();h.context.activityData={jobs:[base],total:90,offset:0,counts:{all:90,active:0,succeeded:90,attention:0,cancelled:0}};h.run('renderActivity()');
 assert.equal(h.node('jobs-summary').textContent,'90 recorded tasks');assert.equal(h.counts[0].textContent,90);
 const html=h.node('jobs-list').innerHTML,visible=html.replace(/<[^>]*>/g,'');
 assert.match(visible,/Savings/);assert.match(visible,/Holdings refresh/);assert.match(visible,/Saved with gaps/);assert.match(visible,/Estimates retained/);
 assert.doesNotMatch(visible,/raw_internal_counter|Attempt|saved-baseline|Recorded stages|Calculate sell estimates/);
 assert.match(html,/aria-haspopup="dialog"/);
 h.run("openActivityDetails('saved-baseline')");assert.equal(h.node('activity-detail').open,true);
 assert.match(h.node('activity-detail-body').innerHTML,/Recorded stages/);assert.match(h.node('activity-detail-body').innerHTML,/Technical details/);
 assert.match(h.node('activity-detail-body').innerHTML,/Calculate sell estimates/);
});
test('running work stays separate from history with truthful progress and queue size',()=>{
 const h=harness();h.context.jobList=[{...base,job_id:'running',state:'running',result:null,analysis_phase:'enrichment',asset_progress:{'1':{total:80,checked:32,quoted:8,unknown:24}}},base];h.context.workspaceStatus.active_job_count=9;h.run('renderActivity()');
 assert.equal(h.node('activity-current').hidden,false);assert.match(h.node('activity-current').innerHTML,/9 tasks/);assert.match(h.node('activity-current').innerHTML,/8 more tasks/);
 assert.match(h.node('activity-current').innerHTML,/32 assets reviewed/);assert.doesNotMatch(h.node('activity-current').innerHTML,/40%|Overall/);
});
test('filters, wallet selection and search read activity without submitting research',async()=>{
 const h=harness();h.node('activity-view').listeners.click({target:{closest:selector=>selector==='[data-activity-filter]'?{dataset:{activityFilter:'attention'}}:null}});
 assert.equal(h.calls[0].state,'attention');assert.equal(h.context.jobsPage,1);
 h.node('activity-wallet').value=B;await h.node('activity-wallet').listeners.change();assert.equal(h.calls[1].wallet,B);
 h.node('activity-query').value='Research';h.node('activity-query').listeners.input();assert.equal(h.context.activityEpoch,1);h.context.debounce();assert.equal(h.calls[2].query,'Research');
 h.run('clearActivityFilters()');assert.equal(h.node('job-filter').value,'all');assert.equal(h.node('activity-wallet').value,'all');assert.equal(h.node('activity-query').value,'');
 assert.ok(h.calls.every(c=>c!=='write'));
});
test('empty and disconnected states keep their meaning and escape untrusted wallet text',()=>{
 const h=harness();h.node('job-filter').value='attention';h.context.jobList=[];h.run('renderActivity()');assert.match(h.node('jobs-list').innerHTML,/No tasks need attention/);
 h.context.jobsConnected=false;h.run('renderActivity()');assert.match(h.node('jobs-freshness').textContent,/Reconnecting/);
 h.context.jobList=[base];h.context.state.wallets[0].name='<img src=x onerror=alert(1)>';h.node('job-filter').value='all';h.run('renderActivity()');
 assert.doesNotMatch(h.node('jobs-list').innerHTML,/<img src=x/);assert.match(h.node('jobs-list').innerHTML,/&lt;img/);
 h.run("openActivityDetails('saved-baseline')");assert.equal(h.node('activity-detail-title').textContent,'<img src=x onerror=alert(1)>');
});
