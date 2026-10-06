'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const source = fs.readFileSync('viewer/static/agent.js', 'utf8');
const deferred = () => { let resolve, reject; const promise = new Promise((yes,no) => {resolve=yes;reject=no;}); return {promise,resolve,reject}; };
const tick = () => new Promise(resolve => setImmediate(resolve));
function harness(api) {
  const elements = new Map();
  function el(id) {
    if (!elements.has(id)) elements.set(id,{id,value:'',checked:false,hidden:false,disabled:false,open:false,opens:0,textContent:'',html:'',writes:0,dataset:{},listeners:{},classList:{toggle(){}},
      set innerHTML(value){this.html=value;this.writes++;},get innerHTML(){return this.html;},
      addEventListener(type,listener){this.listeners[type]=listener;},setAttribute(){},removeAttribute(){},focus(){},showModal(){this.open=true;this.opens++;},close(){this.open=false;this.listeners.close?.();}});
    return elements.get(id);
  }
  const scope = el('scope');scope.value='none';
  const context = vm.createContext({KiraMarkdown:require('./viewer/static/markdown.js'),$:el,localSession:{controls:false},state:{wallets:[]},localAPI:api,toast(){},escapeHTML:s=>String(s).replaceAll('<','&lt;'),
    document:{querySelector:selector=>selector.includes('agent-scope')?scope:el(selector),querySelectorAll:()=>[]},
    navigator:{clipboard:{writeText:async()=>{}}},location:{pathname:'/',hash:'#/home',search:''},history:{replaceState(_state,_title,url){const next=new URL(url,'http://localhost');context.location.pathname=next.pathname;context.location.hash=next.hash;context.location.search=next.search;}},URLSearchParams,crypto:require('node:crypto').webcrypto,
    readRoute(){context.renderedRoute=context.location.hash;},
    setInterval:()=>1,clearInterval(){},setTimeout});
  vm.runInContext(source,context);
  vm.runInContext("localSession.controls=true; agentState={config:{provider:'codex',model:'',scope:'none',retain_history:false},providers:[],conversation_id:'conversation',messages:[],active_turn:null};renderAgent();",context);
  return {el,run:code=>vm.runInContext(code,context),context};
}
const status = () => ({config:{provider:'codex',model:'',scope:'none',retain_history:false},providers:[],conversation_id:'conversation',messages:[],active_turn:null});
test('setup opens the existing account modal once without submitting model or wallet operations',async()=>{
  const calls=[];const h=harness(async(path,options)=>{calls.push({path,options});return {...status(),config:null};});
  h.run("location.search='?setup=1';location.hash='#/activity'");
  await h.run('initialAgent()');
  assert.equal(h.el('agent-dialog').open,true);assert.equal(h.el('agent-dialog').opens,1);
  assert.equal(h.run('agentStep'),1);assert.equal(h.run('location.search'),'');
  assert.equal(h.context.renderedRoute,'#/home');
  assert.ok(calls.length>0);assert.ok(calls.every(call=>call.path==='/api/agent'&&!call.options));
  h.el('agent-dialog').close();await h.run('initialAgent()');
  assert.equal(h.el('agent-dialog').open,false);assert.equal(h.el('agent-dialog').opens,1);
});
test('setup waits for controls and workspace even when another status load is already ready',async()=>{
  const h=harness(async()=>status());
  h.run("location.search='?setup=1';localSession.controls=false;state=null");
  await h.run('initialAgent()');assert.equal(h.el('agent-dialog').opens,0);
  h.run('localSession.controls=true');await h.run('loadAgent()');await h.run('initialAgent()');
  assert.equal(h.el('agent-dialog').opens,0);assert.equal(h.run('location.search'),'?setup=1');
  h.run('state={wallets:[]}');await h.run('initialAgent()');
  assert.equal(h.el('agent-dialog').opens,1);assert.equal(h.run('location.search'),'');
});
test('setup retries a failed initial status lookup without losing its intent',async()=>{
  let fail=true;const h=harness(async()=>{if(fail)throw Error('Unavailable');return status();});
  h.run("location.search='?setup=1'");await h.run('initialAgent()');
  assert.equal(h.el('agent-dialog').opens,0);assert.equal(h.run('location.search'),'?setup=1');
  fail=false;await h.run('initialAgent()');assert.equal(h.el('agent-dialog').opens,1);
});
test('ordinary startup leaves navigation and the modal unchanged',async()=>{
  const h=harness(async()=>status());h.run("location.hash='#/activity'");
  await h.run('initialAgent()');await h.run('initialAgent()');
  assert.equal(h.el('agent-dialog').opens,0);assert.equal(h.run('location.hash'),'#/activity');
});
test('setup reloads saved Claude account and permission choices instead of fresh defaults',async()=>{
  const config={provider:'claude',model:'saved-model',scope:'wallet',wallet:'sample',retain_history:true,trust_native_cli:true,wallet_tools:false};
  const h=harness(async()=>({...status(),config}));
  h.run("location.search='?setup=1';state.wallets=[{key:'sample',name:'Sample wallet'}]");await h.run('initialAgent()');
  assert.equal(h.run('agentProvider'),'claude');assert.equal(h.el('agent-model').value,'saved-model');
  assert.equal(h.el('agent-wallet').value,'sample');assert.equal(h.el('agent-retain').checked,true);
  assert.equal(h.el('agent-tools').checked,false);assert.equal(h.el('agent-trust').checked,true);
});
test('setup does not reset choices in a modal already opened by the user',async()=>{
  const h=harness(async()=>status());h.el('agent-dialog').showModal();h.el('agent-model').value='unsaved-choice';
  h.run("location.search='?setup=1';agentStep=2");await h.run('initialAgent()');
  assert.equal(h.el('agent-dialog').opens,1);assert.equal(h.el('agent-model').value,'unsaved-choice');
  assert.equal(h.run('agentStep'),2);
});
test('dismissing a manually opened modal cancels pending startup intent without changing the current route',async()=>{
  const first=deferred(),calls=[];
  const h=harness(async(path,options)=>{calls.push({path,options});return calls.length===1?first.promise:status();});
  h.run("location.search='?setup=1&view=local';location.hash='#/activity'");
  const initial=h.run('initialAgent()');
  await h.run('openAgent()');h.el('agent-dialog').close();
  assert.equal(h.run('location.search'),'?view=local');assert.equal(h.run('location.hash'),'#/activity');
  first.resolve(status());await initial;await h.run('initialAgent()');
  assert.equal(h.el('agent-dialog').open,false);assert.equal(h.el('agent-dialog').opens,1);
  assert.equal(h.run('location.hash'),'#/activity');
  assert.ok(calls.every(call=>call.path==='/api/agent'&&!call.options));
});
test('question starters fill an editable draft without a model call or permission change',()=>{
  let calls=0;const h=harness(async()=>{calls++;return status();});
  let submits=0;h.el('chat-form').requestSubmit=()=>submits++;
  h.el('chat-suggestions').listeners.click({target:{closest:()=>({dataset:{prompt:'liquidity'}})}});
  assert.match(h.el('kira-draft').value,/full balance/);
  assert.equal(h.el('chat-suggestions').hidden,true);
  assert.equal(h.run('agentState.config.scope'),'none');
  assert.equal(h.run('draftRevision'),1);assert.equal(calls,0);assert.equal(submits,0);
  const draft=h.el('kira-draft').value;
  h.el('chat-suggestions').listeners.click({target:{closest:()=>({dataset:{prompt:'coverage'}})}});
  assert.equal(h.el('kira-draft').value,draft); // Existing work is never overwritten.
});
test('a starter drafted during a pending send survives its successful receipt',async()=>{
  const receipt=deferred();const h=harness(async path=>path==='/api/chat/send'?receipt.promise:path.startsWith('/api/chat/turn/')?{state:'succeeded'}:status());
  h.el('kira-draft').value='Earlier question';h.el('kira-draft').listeners.input();
  const pending=h.run('sendChat({preventDefault(){}})');
  h.el('kira-draft').value='';h.el('kira-draft').listeners.input();
  h.el('chat-suggestions').listeners.click({target:{closest:()=>({dataset:{prompt:'prices'}})}});
  const draft=h.el('kira-draft').value;receipt.resolve({id:'turn'});await pending;
  assert.equal(h.el('kira-draft').value,draft);assert.match(draft,/Blast holdings/);
});
test('a next draft typed before the send receipt survives successful completion', async () => {
  const receipt=deferred();
  const h=harness(async (path)=>path==='/api/chat/send'?receipt.promise:path.startsWith('/api/chat/turn/')?{state:'succeeded'}:status());
  h.el('kira-draft').value='First question';h.el('kira-draft').listeners.input();
  const pending=h.run('sendChat({preventDefault(){}})');
  h.el('kira-draft').value='Next draft';h.el('kira-draft').listeners.input();
  receipt.resolve({id:'turn'});await pending;
  assert.equal(h.el('kira-draft').value,'Next draft');
});
test('later draft survives failed response and cancel completion race',async()=>{
  const result=deferred();const h=harness(async path=>path==='/api/chat/send'?{id:'turn'}:path.startsWith('/api/chat/turn/')?result.promise:path==='/api/chat/cancel'?{state:'succeeded'}:status());
  h.el('kira-draft').value='First';const pending=h.run('sendChat({preventDefault(){}})');await tick();
  h.el('kira-draft').value='Keep this';h.el('kira-draft').listeners.input();result.resolve({state:'failed',error:{message:'Failed'}});await pending;
  assert.equal(h.el('kira-draft').value,'Keep this');
  h.run("chatTurn='completed';chatRequest={message:'First'}");await h.el('chat-stop').listeners.click();
  assert.equal(h.el('kira-draft').value,'Keep this');assert.equal(h.el('chat-error').textContent,'');
});
test('ambiguous send retry uses the same key for the same message',async()=>{
  const keys=[];let attempt=0;
  const h=harness(async(path,options)=>{
    if(path==='/api/chat/send'){keys.push(JSON.parse(options.body).idempotency_key);if(attempt++===0)throw Error('Transport unavailable');return {id:'turn'};}
    if(path.startsWith('/api/chat/turn/'))return {state:'succeeded'};return status();
  });
  h.el('kira-draft').value='Retry exactly';await h.run('sendChat({preventDefault(){}})');await tick();
  await h.run('sendChat({preventDefault(){}})');assert.equal(keys.length,2);assert.equal(keys[0],keys[1]);
});
test('reconnect exposes Stop and resumes the backend active turn',async()=>{
  const result=deferred();const h=harness(async path=>path==='/api/agent'?{...status(),active_turn:'active'}:path==='/api/chat/turn/active'?result.promise:status());
  const loading=h.run('loadAgent()');result.resolve({id:'active',state:'running',test:false,message:'Earlier message',conversation_id:'conversation'});
  await loading;assert.equal(h.el('chat-stop').hidden,false);assert.equal(h.el('chat-status').textContent,'Kira is working…');
  h.run('chatEpoch++');
});
test('draft input does not rebuild the live conversation log and IME Enter does not send',()=>{
  const h=harness(async()=>status());const writes=h.el('chat-messages').writes;
  h.el('kira-draft').value='draft';h.el('kira-draft').listeners.input();assert.equal(h.el('chat-messages').writes,writes);
  let submits=0;h.el('chat-form').requestSubmit=()=>submits++;
  h.el('kira-draft').listeners.keydown({key:'Enter',isComposing:true,keyCode:229,preventDefault(){throw Error('IME was intercepted');}});
  assert.equal(submits,0);
});
test('a turn completed between status and reconnect read refreshes its answer',async()=>{
  let reads=0;
  const h=harness(async path=>path==='/api/agent'?++reads===1?{...status(),active_turn:'active'}:{...status(),messages:[{role:'assistant',text:'Completed answer'}]}:{id:'active',state:'succeeded'});
  await h.run('loadAgent()');assert.equal(reads,2);assert.match(h.el('chat-messages').html,/Completed answer/);assert.equal(h.el('chat-stop').hidden,true);
});
test('a lost reconnect lookup keeps Stop and recovers the exact terminal turn',async()=>{
  const response=deferred();let reads=0;
  const h=harness(async path=>path==='/api/agent'?statusActive():++reads===1?Promise.reject(Error('Lost lookup')):response.promise);
  function statusActive(){return {...status(),active_turn:reads?'': 'active'};}
  await h.run('loadAgent()');assert.equal(h.el('chat-stop').hidden,false);
  response.resolve({id:'active',state:'failed',test:false,message:'Recover this question',error:{message:'Failed'}});await tick();await tick();
  assert.equal(h.el('kira-draft').value,'Recover this question');assert.equal(h.el('chat-stop').hidden,true);
});
test('lost setup receipt still cancels its known idempotency key',async()=>{
  let sent,cancelled;
  const h=harness(async(path,options)=>{const body=options?JSON.parse(options.body):{};if(path==='/api/agent/test'){sent=body.idempotency_key;throw Error('Lost receipt');}if(path==='/api/chat/cancel'){cancelled=body.id;return {state:'cancelled'};}return status();});
  await h.el('agent-test').listeners.click();assert.ok(sent);assert.equal(cancelled,sent);
});
test('poll failure recovers its exact known turn after it has stopped being active',async()=>{
  let lookups=0;const h=harness(async path=>path==='/api/chat/send'?{id:'known'}:path==='/api/chat/turn/known'?++lookups===1?Promise.reject(Error('Lost poll')):{id:'known',state:'failed',message:'Keep the failed question',test:false}:status());
  h.el('kira-draft').value='Keep the failed question';await h.run('sendChat({preventDefault(){}})');await tick();await tick();
  assert.equal(h.el('kira-draft').value,'Keep the failed question');assert.equal(lookups,2);assert.equal(h.el('chat-stop').hidden,true);
});
test('a failed final status read retains recovery ownership until messages arrive',async()=>{
  let reads=0;const h=harness(async path=>path.startsWith('/api/chat/turn/')?{id:'active',state:'succeeded'}:++reads===1?Promise.reject(Error('Lost final status')):{...status(),messages:[{role:'assistant',text:'Recovered answer'}]});
  h.run("chatTurn='active';chatRequest={message:'Question'};renderAgent()");await h.run("recoverResponse('active',chatEpoch)");
  assert.equal(h.el('chat-stop').hidden,false);await h.run("recoverResponse('active',chatEpoch)");
  assert.equal(h.el('chat-stop').hidden,true);assert.match(h.el('chat-messages').html,/Recovered answer/);
});
test('an old reconnect lookup cannot clear a new conversation turn',async()=>{
  const old=deferred();const h=harness(async path=>path==='/api/agent'?{...status(),active_turn:'old'}:old.promise);
  const loading=h.run('loadAgent()');await tick();h.run("chatEpoch++;chatTurn='new';chatRequest={message:'New question'};renderAgent()");
  old.resolve({id:'old',state:'succeeded'});await loading;assert.equal(h.run('chatTurn'),'new');assert.equal(h.el('chat-stop').hidden,false);
});

test('no-context wallet chat offers settings without changing disclosure', () => {
  const h = harness(async () => status());
  h.run("state.wallets=[{key:'sample',name:'Sample wallet'}];renderAgent()");
  assert.equal(h.el('chat-choose-context').hidden, false);
  assert.equal(h.run('agentState.config.scope'), 'none');
  h.run("agentState.config.scope='portfolio';renderAgent()");
  assert.equal(h.el('chat-choose-context').hidden, false);
  h.run("agentState.config.scope='none';state.wallets=[];renderAgent()");
  assert.equal(h.el('chat-choose-context').hidden, true);
});
test('working status updates preserve a reader position and follow the bottom when pinned',()=>{
  const h=harness(async()=>status()),scroll=h.el('conversation-scroll');
  scroll.scrollHeight=1200;scroll.clientHeight=400;scroll.scrollTop=150;
  h.run("chatTurn='active';chatRequest={message:'Synthetic question'};agentState.tool_status='Checking token records';renderAgent();");
  assert.equal(scroll.scrollTop,150);
  scroll.scrollTop=795;h.run("agentState.tool_status='Analysing the results';renderAgent();");
  assert.equal(scroll.scrollTop,1200);
  assert.match(h.el('chat-messages').innerHTML,/kira-research/);
});
