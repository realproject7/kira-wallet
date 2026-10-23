/** Public Agent SDK adapter. The SDK owns Claude's native control protocol. */
import {createInterface} from 'node:readline';
import {randomUUID} from 'node:crypto';
import {pathToFileURL} from 'node:url';

export function createWorker(query, emit) {
  let session, active = null, ready = false, stopped = false, wake;
  const prompts = [], pending = new Map();
  async function* input() {
    while (!stopped) {
      if (!prompts.length) await new Promise(resolve => { wake = resolve; });
      while (prompts.length) yield prompts.shift();
    }
  }
  function publish(value) {
    if (!stopped) emit({...value, turn_id: value.turn_id ?? active});
  }
  function request(value, signal) {
    if (!active || stopped || signal?.aborted) return Promise.resolve({decision:'decline'});
    const id = randomUUID(), turn = active;
    return new Promise(resolve => {
      const abort = () => {
        if (!pending.delete(id)) return;
        publish({type:'input_cancelled', request_id:id, turn_id:turn});
        resolve({decision:'decline'});
      };
      pending.set(id, {turn, resolve:response => {
        signal?.removeEventListener('abort', abort); resolve(response);
      }});
      signal?.addEventListener('abort', abort, {once:true});
      publish({type:'request', request_id:id, request:value, turn_id:turn});
    });
  }
  async function permission(tool, original, context) {
    if (tool === 'AskUserQuestion') {
      const questions = original.questions;
      if (!Array.isArray(questions) || !questions.length || questions.length > 8 || questions.some(q => typeof q.question !== 'string' || q.isSecret)) {
        return {behavior:'deny', message:'This input form is unsupported. Complete secret entry in the native client.'};
      }
      const result = await request({kind:'input', details:{questions:questions.map((q,i) => ({id:String(i), question:q.question, options:q.options}))}}, context.signal);
      if (context.signal.aborted || stopped || !result.answers || questions.some((_,i) => typeof result.answers[String(i)] !== 'string' || !result.answers[String(i)].trim() || result.answers[String(i)].length > 8000)) {
        return {behavior:'deny', message:'The question was cancelled or did not receive an answer.'};
      }
      return {behavior:'allow', updatedInput:{...original, answers:Object.fromEntries(questions.map((q,i) => [q.question, result.answers[String(i)]]))}};
    }
    const result = await request({kind:'approval', details:{tool, input:original, command:tool === 'Bash' ? original.command : undefined, reason:context.decisionReason || tool}}, context.signal);
    if (result.decision !== 'accept' || context.signal.aborted || stopped) return {behavior:'deny', message:'User declined this tool request.'};
    // Approve exactly this input. Never persist permission suggestions or session grants.
    return {behavior:'allow', updatedInput:original};
  }
  async function consume() {
    try {
      for await (const event of session) {
        if (event.parent_tool_use_id) continue;
        if (event.type === 'system' && event.subtype === 'init' && !event.mcp_servers?.some(server => server.name === 'kira_wallet' && server.status === 'connected')) {
          publish({type:'error', code:'native_tools_unavailable'});
          session.close(); return;
        }
        if (event.session_id) publish({type:'session', thread_id:event.session_id});
        if (event.type === 'result') {
          if (!active) continue;
          publish({type:'completed', success:event.subtype === 'success' && event.is_error !== true, answer:event.result || ''});
          active = null;
        } else if (event.type === 'assistant') {
          const tools = event.message?.content?.filter(block => block.type === 'tool_use').map(block => block.name) || [];
          publish({type:'progress', text:tools.length ? 'Using '+tools.join(', ')+'…' : 'Writing a response…'});
        } else if (event.type === 'tool_progress' || event.type === 'system') {
          publish({type:'progress', text:'Kira is working…'});
        }
      }
      if (!stopped) publish({type:'error', code:'native_stopped'});
    } catch {
      if (!stopped) publish({type:'error', code:'native_claude_failed'});
    }
  }
  async function handle(message) {
    if (message.type === 'initialize') {
      if (session || stopped) throw Error('Already initialized');
      const options = {
        pathToClaudeCodeExecutable:message.cli,
        cwd:message.cwd,
        settingSources:['user','project','local'],
        systemPrompt:{type:'preset', preset:'claude_code', append:message.instructions},
        permissionMode:'default',
        persistSession:message.retain_history,
        canUseTool:permission,
        onElicitation:async (form, context) => {
          await request({kind:'notice', details:{message:'This integration needs an external input form. Use its native client to complete setup.'}}, context.signal);
          return {action:'decline'};
        },
        onUserDialog:async () => ({behavior:'cancelled'}),
        mcpServers:{kira_wallet:{command:message.python, args:[message.mcp], env:{KIRA_TOOL_URL:'${KIRA_TOOL_URL}', KIRA_TOOL_TOKEN:'${KIRA_TOOL_TOKEN}'}}},
        env:{...process.env, KIRA_TOOL_URL:message.bridge_url, KIRA_TOOL_TOKEN:message.bridge_token},
      };
      if (message.model) options.model = message.model;
      if (message.thread_id) options.resume = message.thread_id;
      session = query({prompt:input(), options});
      void consume();
      await session.initializationResult();
      ready = true; publish({type:'ready'});
    } else if (message.type === 'prompt') {
      if (!ready || stopped || active || typeof message.message !== 'string' || typeof message.turn_id !== 'string') throw Error('Unavailable turn');
      active = message.turn_id;
      prompts.push({type:'user', message:{role:'user',content:message.message}, parent_tool_use_id:null});
      wake?.(); wake = undefined;
    } else if (message.type === 'respond') {
      const item = pending.get(message.request_id);
      if (item && item.turn === message.turn_id && active === item.turn) {
        pending.delete(message.request_id); item.resolve(message.response || {});
      }
    } else if (message.type === 'close') close();
    else throw Error('Unsupported host message');
  }
  function close() {
    if (stopped) return;
    stopped = true;
    for (const item of pending.values()) item.resolve({decision:'decline'});
    pending.clear(); wake?.(); session?.close();
  }
  return {handle, close};
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  const {query} = await import('@anthropic-ai/claude-agent-sdk');
  const worker = createWorker(query, value => process.stdout.write(JSON.stringify(value)+'\n'));
  const lines = createInterface({input:process.stdin, crlfDelay:Infinity});
  lines.on('line', line => {
    try {
      if (Buffer.byteLength(line) > 2_000_000) throw Error('Oversized host message');
      void worker.handle(JSON.parse(line)).catch(() => {
        process.stdout.write(JSON.stringify({type:'error',code:'native_claude_failed'})+'\n'); worker.close();
      });
    } catch {worker.close();}
  });
  lines.on('close', () => worker.close());
  process.on('SIGTERM', () => {worker.close(); lines.close();});
}
