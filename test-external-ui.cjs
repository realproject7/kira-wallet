'use strict';
const {test}=require('node:test');
const assert=require('node:assert/strict');
const vm=require('node:vm');
const fs=require('node:fs');
const KiraView=require('./viewer/static/workspace-model.js');
const A='0x'+'1'.repeat(40),B='0x'+'2'.repeat(40);
const plain=value=>JSON.parse(JSON.stringify(value));
const deferred=()=>{let resolve;const promise=new Promise(done=>{resolve=done;});return {promise,resolve};};
function dom(){
  const nodes=new Map(),listeners={},timers=[];
  const document={hidden:false,activeElement:null,querySelectorAll:()=>[],addEventListener:(type,fn)=>{listeners[type]=fn;}};
  function element(id){
    if(nodes.has(id))return nodes.get(id);
    const node={id,value:'all',textContent:'',innerHTML:'',hidden:false,disabled:false,checked:false,open:false,dataset:{},listeners:{},children:[],
      classList:{add(){},remove(){},toggle(){}},setAttribute(){},removeAttribute(){},querySelectorAll:()=>[],querySelector:()=>null,contains:()=>false,
      addEventListener(type,fn){this.listeners[type]=fn;},append(child){this.children.push(child);},focus(){document.activeElement=this;},
      setSelectionRange(start,end){this.selectionStart=start;this.selectionEnd=end;},showModal(){this.open=true;},close(){this.open=false;this.listeners.close?.();}};
    nodes.set(id,node);return node;
  }
  document.getElementById=element;document.createElement=()=>element('new-'+nodes.size);
  return {element,document,listeners,timers,setTimeout(fn,delay){timers.push({fn,delay});return timers.length;},clearTimeout(){}};
}
function routeHarness(){
  const d=dom(),requests=[],writes=[];
  const context=vm.createContext({...d,window:{},localStorage:{getItem:()=>null},location:{origin:'http://localhost'},URL,URLSearchParams,AbortSignal,AbortController,
    localSession:{controls:true,token:'synthetic'},localAPI:async(path,options)=>{writes.push({path,body:JSON.parse(options.body)});},
    fetch:async(path,options)=>{requests.push({path,options});return {ok:true,json:async()=>({assets:[],matched_count:0,offset:0,next_offset:null})};},
    renderView(){},refreshControlState(){},catalogFilters:()=>({page:3,network:'1',search:'saved token',minimum:5,sort:'wallets',pricing:'unpriced',testnets:true})
  });
  const run=code=>vm.runInContext(code,context);
  const source=fs.readFileSync('viewer/static/app.js','utf8');run(source.slice(0,source.indexOf('function currentWallet()')));
  Object.assign(context,{A,B});run("state={paged:true,data_revision:'r1',wallets:[]};selectedView='wallet';selectedWallet=A");
  return {...d,context,run,requests,writes};
}
function jobHarness(){
  const d=dom(),requests=[],notices=[];
  const context=vm.createContext({...d,$:d.element,window:{addEventListener(){}},KiraView,AbortSignal,crypto:{randomUUID:()=> 'test-id'},
    state:{data_revision:'r1',wallets:[],demo:false},selectedView:'home',selectedWallet:A,currentWallet:()=>null,
    setInterval:()=>0,escapeHTML:value=>String(value??'').replaceAll('<','&lt;'),stamp:value=>value,toast:value=>notices.push(value),navigate(){},
    fetch:async(path,options)=>{requests.push({path,options});return {ok:true,status:200,json:async()=>[]};},
    readAPI:async()=>({data_revision:'r1',jobs_revision:'j1',active_job_count:0,active_jobs:[]}),
    sessionStorage:{getItem:()=>null,setItem(){},removeItem(){}}
  });
  const run=code=>vm.runInContext(code,context);
  run(fs.readFileSync('viewer/static/jobs.js','utf8').replace(/\npollWorkspace\(\);\s*$/,''));
  run("localSession={controls:true,token:'synthetic'};renderJobs=()=>{};refreshControlState=()=>{};");
  return {...d,context,run,requests,notices};
}
test('wallet pages keep filters, cap rows and cache only the same revision',async()=>{
  const h=routeHarness();h.run("walletOffset=100;selectedChain='1';minimum=5");await h.run('loadRoute()');
  const first=new URL(h.requests[0].path,'http://localhost');assert.equal(first.pathname,'/api/wallet');
  assert.deepEqual(Object.fromEntries(first.searchParams),{wallet:A,offset:'100',limit:'100',chain_id:'1',minimum_value_usd:'5'});
  assert.equal(h.requests[0].options.headers['X-Kira-Session'],'synthetic');assert(h.requests[0].options.signal instanceof AbortSignal);
  await h.run('loadRoute()');assert.equal(h.requests.length,1);
  h.run("selectedWallet=B");await h.run('loadRoute()');h.run('selectedWallet=A');await h.run('loadRoute()');assert.equal(h.requests.length,2);
  h.run("state.data_revision='r2'");await h.run('loadRoute()');assert.equal(h.requests.length,3);
  assert(h.writes.every(write=>write.path==='/api/ui-context'));
  assert.deepEqual(h.writes.at(-1).body,{view:'wallet',wallet:A});
});
test('network, token, catalog and home load only their focused records and bounded holdings',async()=>{
  const h=routeHarness();h.run("selectedView='network';selectedNetwork=1;networkOffset=100;tokenSearch='ETH';minimum=10");await h.run('loadRoute()');
  const paths=h.requests.map(request=>new URL(request.path,'http://localhost'));
  assert.equal(paths[0].pathname,'/api/network');assert.deepEqual(Object.fromEntries(paths[1].searchParams),{chain_id:'1',offset:'100',limit:'100',query:'ETH',minimum_value_usd:'10',include_testnets:'1'});
  h.run("selectedView='token';selectedToken='1:native'");await h.run('loadRoute()');assert.equal(h.requests.at(-1).path,'/api/token?chain_id=1&address=native');
  h.run("selectedView='tokens'");await h.run('loadRoute()');
  assert.deepEqual(Object.fromEntries(new URL(h.requests.at(-1).path,'http://localhost').searchParams),{offset:'100',limit:'50',chain_id:'1',query:'saved token',minimum_value_usd:'5',sort:'wallets',pricing:'unpriced',include_testnets:'1'});
  h.run("selectedView='home'");await h.run('loadRoute()');assert.equal(h.requests.at(-1).path,'/api/holdings?offset=0&limit=5&sort=value');
  assert(h.requests.every(request=>!request.path.startsWith('/api/state')));
});
test('a late wallet response cannot replace the newly selected token',async()=>{
  const h=routeHarness(),pending=[];
  h.context.fetch=(path,options)=>{const next=deferred();pending.push({...next,path,options});return next.promise;};
  const wallet=h.run('loadRoute()');h.run("selectedView='token';selectedToken='1:native'");const token=h.run('loadRoute()');
  assert.equal(pending[0].options.signal.aborted,true);
  pending[1].resolve({ok:true,json:async()=>({id:'1:native'})});await token;
  pending[0].resolve({ok:true,json:async()=>({key:A,assets:[{symbol:'Late'}]})});await wallet;
  assert.deepEqual(plain(h.run('routeData')),{token:{id:'1:native'}});assert.equal(h.run('routeLoading'),false);
  assert.deepEqual(h.writes.map(write=>write.body),[{view:'token',token:'1:native',chain_id:1}]);
});
test('route failure exposes a retry and successful rerender preserves focused search selection',async()=>{
  const h=routeHarness(),field=h.element('network-token-search');field.selectionStart=2;field.selectionEnd=4;field.focus();
  h.context.fetch=async()=>({ok:false});await h.run('loadRoute()');assert.equal(h.run('routeLoading'),false);
  assert.match(h.element('route-status').textContent,/could not be loaded/);assert.equal(h.element('route-status').children[0].textContent,'Retry');
  h.context.fetch=async()=>({ok:true,json:async()=>({key:A,assets:[]})});await h.element('route-status').children[0].listeners.click();
  assert.equal(h.element('route-status').hidden,true);assert.equal(h.document.activeElement,field);assert.equal(field.selectionStart,2);assert.equal(field.selectionEnd,4);
});
test('idle checks load status only; revisions and active work select the bounded update cadence',async()=>{
  const h=jobHarness(),reads=[];let full=0;
  h.context.poll=async()=>{full++;h.context.state.data_revision='r2';};h.run('pollJobs=async()=>{globalThis.jobReads++;}');h.context.jobReads=0;
  h.context.readAPI=async path=>{reads.push(path);return {data_revision:h.context.state.data_revision,jobs_revision:'j1',active_job_count:0};};
  await h.run('pollWorkspace()');assert.equal(h.context.jobReads,1);assert.equal(full,0);assert.equal(h.timers.at(-1).delay,10000);
  await h.run('pollWorkspace()');assert.equal(h.context.jobReads,1);assert.equal(full,0);assert.deepEqual(reads,['/api/status','/api/status']);
  h.context.readAPI=async()=>({data_revision:'r2',jobs_revision:'j2',active_job_count:1});await h.run('pollWorkspace()');
  assert.equal(full,1);assert.equal(h.context.jobReads,2);assert.equal(h.timers.at(-1).delay,2500);
  h.document.hidden=true;const timers=h.timers.length;await h.run('pollWorkspace()');h.run('scheduleWorkspacePoll()');assert.equal(h.timers.length,timers);assert.equal(full,1);
});
test('read-only status checks never request privileged job history or local controls',async()=>{
  const h=jobHarness();h.run('localSession={controls:false};lastJobsRevision=null');h.context.poll=async()=>{};
  h.context.fetch=async()=>{throw Error('Unexpected privileged request');};await h.run('pollWorkspace()');assert.equal(h.requests.length,0);assert.equal(h.timers.at(-1).delay,10000);
});
test('Activity pages apply filters on the server and ignore late older pages',async()=>{
  const h=jobHarness(),pending=[];h.context.selectedView='activity';h.run("localAPI=path=>new Promise(resolve=>globalThis.pending.push({path,resolve}))");h.context.pending=pending;
  h.element('job-filter').value='attention';h.run('jobsPage=2');const first=h.run('loadActivity()');h.run('jobsPage=3');const second=h.run('loadActivity()');
  assert.equal(pending[0].path,'/api/job-history?offset=20&limit=20&state=attention');assert.equal(pending[1].path,'/api/job-history?offset=40&limit=20&state=attention');
  pending[1].resolve({jobs:[],total:41,offset:40});await second;pending[0].resolve({jobs:[],total:41,offset:20});await first;
  assert.equal(h.run('activityData.offset'),40);
});
test('an older active job outside recent history is fetched individually and remains actionable',async()=>{
  const h=jobHarness(),reads=[];
  h.run("workspaceStatus={active_jobs:[{job_id:'older-active'}]};localAPI=async path=>globalThis.fixtureRead(path)");
  h.context.fixtureRead=async path=>{reads.push(path);return path==='/api/jobs?limit=50'?[]:{job_id:'older-active',operation:'wallet.refresh',state:'running',input:{wallet:A},created_at:'2026-01-01',updated_at:'2026-01-01'};};
  await h.run('pollJobs()');assert.deepEqual(reads,['/api/jobs?limit=50','/api/jobs/older-active']);assert.equal(h.run('jobList[0].job_id'),'older-active');
});
test('RPC edits retain untouched references, reject secrets and write only a reviewed settings operation',async()=>{
  const h=jobHarness(),config={rpc:{mode:'custom',priority:'custom_first',allow_public_fallback:false,chains:{1:{url_env:'ETH_RPC'},8453:{url_env:'BASE_RPC'}}},rpc_networks:[{chain_id:1,name:'Ethereum'},{chain_id:8453,name:'Base'}]};
  h.context.config=config;h.run('loadRpcSettings(config)');assert.deepEqual(plain(h.run('rpcSettingsInput().chains')),[{chain_id:1,url_env:'ETH_RPC'},{chain_id:8453,url_env:'BASE_RPC'}]);
  h.element('rpc-rows').listeners.input({target:{dataset:{rpcReference:'0'},value:'REVISED_ETH_RPC'}});
  assert.deepEqual(plain(h.run('rpcSettingsInput().chains')),[{chain_id:1,url_env:'REVISED_ETH_RPC'},{chain_id:8453,url_env:'BASE_RPC'}]);
  h.run("rpcRows[0].url_env='https://example.invalid/key'");assert.throws(()=>h.run('rpcSettingsInput()'),/URLs and keys are not accepted/);
  h.run("rpcRows[0].url_env='REVISED_ETH_RPC';globalThis.saved=[];submitOperation=async(operation,input)=>saved.push({operation,input})");await h.run('saveRpcSettings()');
  assert.deepEqual(plain(h.run('saved')),[{operation:'settings.rpc',input:{mode:'custom',chains:[{chain_id:1,url_env:'REVISED_ETH_RPC'},{chain_id:8453,url_env:'BASE_RPC'}],allow_public_fallback:false,priority:'custom_first'}}]);
  assert.match(h.element('rpc-status').textContent,/Check Activity/);assert.equal(h.element('rpc-activity').hidden,false);
  h.run('rpcRows=[]');assert.throws(()=>h.run('rpcSettingsInput()'),/at least one/);
});
