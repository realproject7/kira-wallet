import test from 'node:test';
import assert from 'node:assert/strict';
import {createWorker} from './kira_claude.mjs';

const tick = () => new Promise(resolve => setImmediate(resolve));
function fixture(extra = {}) {
  const events = [], native = [], waiting = [], prompts = [];
  let options, closed = false, iterator;
  const worker = createWorker(params => {
    options = params.options; iterator = params.prompt[Symbol.asyncIterator]();
    return {
      initializationResult: async () => ({}),
      [Symbol.asyncIterator]() { return this; },
      next() {
        if (native.length) return Promise.resolve({value:native.shift(),done:false});
        if (closed) return Promise.resolve({done:true});
        return new Promise(resolve => waiting.push(resolve));
      },
      close() {closed = true; for (const resolve of waiting.splice(0)) resolve({done:true});},
    };
  }, value => events.push(value));
  const initialize = () => worker.handle({type:'initialize',cli:'/synthetic/claude',cwd:'/synthetic/output',instructions:'Kira rules',python:'python3',mcp:'kira_native_mcp.py',bridge_url:'http://127.0.0.1:9000',bridge_token:'synthetic-token',model:'sonnet',retain_history:true,...extra});
  async function prompt(id='turn') {
    await worker.handle({type:'prompt',turn_id:id,message:'Work'});
    prompts.push((await iterator.next()).value);
  }
  function push(value) { const resolve = waiting.shift(); if (resolve) resolve({value,done:false}); else native.push(value); }
  const respond = (event,response,turn=event.turn_id) => worker.handle({type:'respond',request_id:event.request_id,turn_id:turn,response});
  return {worker,events,prompts,initialize,prompt,push,respond,get options(){return options;}};
}

test('SDK uses the installed CLI, native settings and preset without a restricted tool list',async()=>{
  const f=fixture({thread_id:'00000000-0000-4000-8000-000000000001'});
  try {
    await f.initialize();
    assert.equal(f.options.pathToClaudeCodeExecutable,'/synthetic/claude');
    assert.deepEqual(f.options.settingSources,['user','project','local']);
    assert.deepEqual(f.options.systemPrompt,{type:'preset',preset:'claude_code',append:'Kira rules'});
    assert.equal(f.options.permissionMode,'default');
    assert.equal(f.options.resume,'00000000-0000-4000-8000-000000000001');
    for (const key of ['tools','allowedTools','disallowedTools','maxTurns','maxBudgetUsd','strictMcpConfig']) assert.equal(f.options[key],undefined);
    assert.equal(f.options.env.KIRA_TOOL_TOKEN,'synthetic-token');
    assert.doesNotMatch(JSON.stringify(f.options.mcpServers),/synthetic-token/);
    assert.equal(f.options.mcpServers.kira_wallet.env.KIRA_TOOL_TOKEN,'${KIRA_TOOL_TOKEN}');
    assert.equal(f.events.at(-1).type,'ready');
  } finally {f.worker.close();}
});

test('approvals match the active turn and allow exactly one original input',async()=>{
  const f=fixture();try {
    await f.initialize();await f.prompt();
    const input={command:'printf hello'};const controller=new AbortController();
    let answer;
    const pending=f.options.canUseTool('Bash',input,{signal:controller.signal,suggestions:[{type:'allowAll'}]}).then(value=>{answer=value;return value;});
    const request=f.events.at(-1);assert.equal(request.request.kind,'approval');
    await f.respond(request,{decision:'accept'},'foreign');await tick();assert.equal(answer,undefined);
    await f.respond(request,{decision:'accept'});
    assert.deepEqual(await pending,{behavior:'allow',updatedInput:input});
    await f.respond(request,{decision:'decline'});
    const second=f.options.canUseTool('Write',{file_path:'report.csv',content:'DEMO,125'},{signal:controller.signal});
    await f.respond(f.events.at(-1),{decision:'acceptForSession'});
    assert.equal((await second).behavior,'deny');
  } finally {f.worker.close();}
});

test('user answers preserve the SDK question keys and cannot include secret input',async()=>{
  const f=fixture();try {
    await f.initialize();await f.prompt();const signal=new AbortController().signal;
    const original={questions:[{question:'Report format?',header:'Format',options:[{label:'CSV',description:'Spreadsheet'}]}]};
    const pending=f.options.canUseTool('AskUserQuestion',original,{signal});
    const request=f.events.at(-1);assert.equal(request.request.kind,'input');
    await f.respond(request,{answers:{'0':'CSV'}});
    assert.deepEqual(await pending,{behavior:'allow',updatedInput:{...original,answers:{'Report format?':'CSV'}}});
    const count=f.events.length;
    assert.equal((await f.options.canUseTool('AskUserQuestion',{questions:[{question:'Secret?',isSecret:true}]},{signal})).behavior,'deny');
    assert.equal(f.events.length,count);
  } finally {f.worker.close();}
});

test('cancelled approval callbacks deny late replies and notify the host',async()=>{
  const f=fixture();try {
    await f.initialize();await f.prompt();const controller=new AbortController();
    const pending=f.options.canUseTool('Bash',{command:'echo hello'},{signal:controller.signal});
    const request=f.events.at(-1);controller.abort();
    assert.equal((await pending).behavior,'deny');
    assert.equal(f.events.at(-1).type,'input_cancelled');
    await f.respond(request,{decision:'accept'});
    assert.equal(f.events.at(-1).request_id,request.request_id);
  } finally {f.worker.close();}
});

test('main results delimit turns while subagent results cannot finish the user task',async()=>{
  const f=fixture();try {
    await f.initialize();await f.prompt('first');
    f.push({type:'result',parent_tool_use_id:'child',subtype:'success',result:'Subtask'});await tick();
    assert.equal(f.events.some(event=>event.type==='completed'),false);
    f.push({type:'result',subtype:'success',is_error:false,session_id:'session',result:'Created report.csv'});await tick();
    assert.equal(f.events.at(-1).answer,'Created report.csv');assert.equal(f.events.at(-1).success,true);
    await f.prompt('second');
    f.push({type:'result',subtype:'error_during_execution',is_error:true,result:'Failed'});await tick();
    assert.equal(f.events.at(-1).success,false);
    assert.equal(f.prompts.length,2);
    assert.deepEqual(f.prompts[0].message,{role:'user',content:'Work'});
  } finally {f.worker.close();}
});

test('unsupported elicitation and shutdown cannot grant credentials or pending actions',async()=>{
  const f=fixture();await f.initialize();await f.prompt();const signal=new AbortController().signal;
  const elicitation=f.options.onElicitation({mode:'url',url:'https://example.test/login'},{signal});
  const request=f.events.at(-1);assert.equal(request.request.kind,'notice');
  await f.respond(request,{decision:'accept'});assert.deepEqual(await elicitation,{action:'decline'});
  const pending=f.options.canUseTool('Bash',{command:'echo hello'},{signal});
  f.worker.close();assert.equal((await pending).behavior,'deny');
});

test('a missing or disconnected wallet bridge fails closed at native initialization',async()=>{
  for (const mcp_servers of [[],[{name:'kira_wallet',status:'failed'}]]) {
    const f=fixture();await f.initialize();await f.prompt();
    f.push({type:'system',subtype:'init',mcp_servers});await tick();
    assert.equal(f.events.at(-1).type,'error');
    assert.equal(f.events.at(-1).code,'native_tools_unavailable');f.worker.close();
  }
  const f=fixture();await f.initialize();await f.prompt();
  f.push({type:'system',subtype:'init',mcp_servers:[{name:'kira_wallet',status:'connected'}]});await tick();
  assert.equal(f.events.some(event=>event.type==='error'),false);f.worker.close();
});
