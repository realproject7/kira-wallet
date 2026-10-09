'use strict';
// Local read scheduling. No probes, background timers or provider credentials on disk.
const fs = require('node:fs'), path = require('node:path'), crypto = require('node:crypto');
const viem = require('viem');
const failure = (message, name = 'RpcUnavailableError') => Object.assign(new Error(message), {name});
function classify(error) {
  let quotaCode=false;
  for (let e = error, depth = 0; e && depth < 10; e = e.cause, depth++) {
    const text = e.shortMessage || e.message || '';
    if (e.status === 429 || /rate.?limit|too many requests|quota|backpressure|capacity exceeded/i.test(text)) return 'throttle';
    if (e.status === 413 || /(?:payload|batch|response|request body).*(?:large|size|exceed)|gas.*(?:cap|limit).*exceed/i.test(text)) return 'size';
    // viem wraps both quota and payload failures in generic -32005 errors.
    // Inspect the underlying cause before using that ambiguous code.
    if (e.code === -32005) quotaCode=true;
    if (e.code === -32601 || /method (?:not found|not supported)|historical state|missing trie|header not found/i.test(text)) return 'method';
    if (e.code === 3 || /execution reverted|revert opcode/i.test(text)) return 'contract';
  }
  return quotaCode?'throttle':'transport';
}
function retryAfter(error) {
  for (let e = error, depth = 0; e && depth < 10; e = e.cause, depth++) {
    const value = e.headers?.get?.('retry-after') || e.headers?.['retry-after'];
    if (value) { const seconds = Number(value); return Number.isFinite(seconds) ? Math.max(0, seconds * 1000) : Math.max(0, Date.parse(value) - Date.now()) || 0; }
  }
  return 0;
}
class Gate {
  constructor() { this.busy = false; this.queue = []; }
  acquire(signal) {
    return new Promise((resolve, reject) => {
      const ticket = {resolve, reject, signal, abort: null};
      ticket.abort = () => { const i = this.queue.indexOf(ticket); if (i >= 0) this.queue.splice(i, 1); reject(signal.reason); };
      if (signal.aborted) { reject(signal.reason); return; }
      signal.addEventListener('abort', ticket.abort, {once:true});
      this.queue.push(ticket); this.drain();
    });
  }
  drain() {
    if (this.busy || !this.queue.length) return;
    const ticket = this.queue.shift(); ticket.signal.removeEventListener('abort', ticket.abort);
    if (ticket.signal.aborted) { ticket.reject(ticket.signal.reason); this.drain(); return; }
    this.busy = true;
    ticket.resolve(() => { this.busy = false; this.drain(); });
  }
}
function wait(ms, signal) {
  if (signal.aborted) return Promise.reject(signal.reason);
  if (ms <= 0) return Promise.resolve();
  return new Promise((resolve, reject) => {
    const abort = () => { clearTimeout(timer); reject(signal.reason); };
    const timer = setTimeout(() => { signal.removeEventListener('abort', abort); resolve(); }, ms);
    signal.addEventListener('abort', abort, {once:true});
  });
}
function within(promise, signal) {
  if (signal.aborted) return Promise.reject(signal.reason);
  return new Promise((resolve, reject) => {
    const abort = () => reject(signal.reason);
    signal.addEventListener('abort', abort, {once:true});
    Promise.resolve(promise).then(resolve, reject).finally(() => signal.removeEventListener('abort', abort));
  });
}
function blockTag(request) {
  const tag = request.params?.[1];
  return ['eth_call','eth_getBalance','eth_getCode'].includes(request.method) && typeof tag === 'string' && /^0x[0-9a-f]+$/i.test(tag) ? tag.toLowerCase() : null;
}
class RouteRecorder {
  constructor() { this.rows=new Map();this.overflow=new Map(); }
  record(index, endpointClass, event) {
    if(!['public','custom'].includes(endpointClass)||!['succeeded','failed','skipped','queue_timeout'].includes(event.outcome))return;
    const row={endpoint_index:Number.isInteger(index)?index:null,endpoint_class:endpointClass,
      method:/^[a-zA-Z0-9_]{1,64}$/.test(event.method||'')?event.method:'other',outcome:event.outcome};
    if(['transport','throttle','size','method','contract','cooldown'].includes(event.reason))row.reason=event.reason;
    for(const name of ['http_status','rpc_code'])if(Number.isSafeInteger(event[name]))row[name]=event[name];
    const key=JSON.stringify(row);
    let saved=this.rows.get(key);
    if(!saved && this.rows.size<96){saved={...row,count:0};this.rows.set(key,saved);}
    if(!saved){
      const bucket=endpointClass+':'+event.outcome;
      saved=this.overflow.get(bucket);
      if(!saved){saved={endpoint_class:endpointClass,outcome:event.outcome,aggregated_overflow:true,count:0};this.overflow.set(bucket,saved);}
    }
    saved.count=Math.min(Number.MAX_SAFE_INTEGER,saved.count+1);
  }
  snapshot(){return [...this.rows.values(),...this.overflow.values()].map(row=>({...row}));}
}
class RpcPool {
  constructor({publicUrls = [], healthFile = null, interval = 2000, deadline = 12000, attemptTimeout = 4000, cooldown = 60000} = {}) {
    this.publicUrls = new Set(publicUrls); this.healthFile = healthFile;
    this.interval = interval; this.deadline = deadline; this.attemptTimeout = attemptTimeout; this.cooldown = cooldown;
    this.states = new Map(); this.families = new Map(); this.pins = new Map(); this.pending = new Map(); this.cache = new Map();
    this.saved = {};
    try { if (healthFile && fs.statSync(healthFile).size <= 65536) {
      const saved = JSON.parse(fs.readFileSync(healthFile));
      if (saved.schema_version === 1 && saved.entries && typeof saved.entries === 'object' && !Array.isArray(saved.entries)) {
        const now=Date.now();
        this.saved=Object.fromEntries(Object.entries(saved.entries).filter(([id,row])=>/^[a-f0-9]{64}$/.test(id) && row && Number.isFinite(row.until) && row.until>now && row.until<=now+1800000).slice(-128));
      }
    } } catch { /* Health is optional. Malformed or missing observations cannot block reads. */ }
  }
  state(chain, url, transport, options) {
    const key = chain + ':' + url;
    if (!this.states.has(key)) {
      const id = crypto.createHash('sha256').update(key).digest('hex');
      const saved = this.saved[id] || {}, now = Date.now();
      const until = Number.isFinite(saved.until) && saved.until > now && saved.until <= now + 1800000 ? saved.until : 0;
      let host; try { host = new URL(url).hostname; } catch { host = url; }
      const publicEndpoint = this.publicUrls.has(url);
      const family = publicEndpoint ? host.endsWith('publicnode.com') ? 'publicnode' : host.endsWith('drpc.org') ? 'drpc' : host.endsWith('1rpc.io') ? '1rpc' : host : host;
      if (!this.families.has(family)) this.families.set(family, {gate:new Gate(), next:0});
      this.states.set(key, {id, publicEndpoint, family, gate:new Gate(), until, strikes:until ? Math.min(Number(saved.strikes) || 1, 5) : 0,
        methods:new Map(), verified:false, blocks:new Set(), inner:transport(url,{timeout:this.attemptTimeout,retryCount:0})(options)});
    }
    return this.states.get(key);
  }
  persist() {
    if (!this.healthFile) return;
    const now = Date.now(), entries = Object.fromEntries(Object.entries(this.saved).filter(([,v]) => v && Number.isFinite(v.until) && v.until > now && v.until <= now + 1800000).slice(-128));
    for (const s of this.states.values()) if (s.publicEndpoint) {
      if (s.until > now) entries[s.id] = {until:s.until, strikes:s.strikes}; else delete entries[s.id];
    }
    this.saved = entries;
    try { fs.mkdirSync(path.dirname(this.healthFile), {recursive:true}); const temp = this.healthFile + '.' + process.pid + '.tmp';
      fs.writeFileSync(temp, JSON.stringify({schema_version:1,entries:Object.fromEntries(Object.entries(entries).slice(-128))}) + '\n', {mode:0o600}); fs.renameSync(temp, this.healthFile);
    } catch { /* Persistence is a performance hint, never an analysis failure. */ }
  }
  pin(chain, number, hash, state = null) {
    if (!/^0x[0-9a-f]{64}$/i.test(hash || '')) throw failure('Snapshot block hash is unavailable.', 'RpcConsistencyError');
    const tag = '0x' + BigInt(number).toString(16), key = chain + ':' + tag;
    const previous = this.pins.get(key);
    if (previous && previous !== hash.toLowerCase()) throw failure('Snapshot block changed. Start a new holdings analysis.', 'RpcConsistencyError');
    this.pins.set(key, hash.toLowerCase()); if (state) state.blocks.add(tag);
  }
  async send(state, request, signal, timeout = this.attemptTimeout) {
    const family = this.families.get(state.family), release = await family.gate.acquire(signal);
    try {
      await wait(family.next - Date.now(), signal);
      family.next = Date.now() + this.interval;
      const controller = new AbortController(), abort = () => controller.abort(signal.reason);
      signal.addEventListener('abort', abort, {once:true});
      const timer = setTimeout(() => controller.abort(failure('RPC read timed out.', 'TimeoutError')), timeout);
      try { return await within(state.inner.request(request, {signal:controller.signal}), controller.signal); }
      finally { clearTimeout(timer); signal.removeEventListener('abort', abort); }
    } finally { release(); }
  }
  async run(chain, choices, request, transport, options, onSuccess, signal, deadlineAt, onOutcome) {
    let last = failure('RPC providers are temporarily unavailable. Retry holdings shortly.');
    let attempts = 0;
    for (const [index, url] of choices.entries()) {
      if (signal.aborted) throw signal.reason;
      const state = this.state(chain, url, transport, options);
      if (state.until > Date.now() || (state.methods.get(request.method) || 0) > Date.now()) {onOutcome(index,{method:request.method,outcome:'skipped',reason:'cooldown'});last=state.error||last;continue;}
      // An endpoint attempt includes its queue, cold verification and family pacing.
      // Public outages must leave time for the personal backup's actual read.
      const remaining=deadlineAt-Date.now();
      const backupAhead=this.publicUrls.has(url) && choices.slice(index+1).some(next=>!this.publicUrls.has(next));
      const reserve=backupAhead?Math.min(this.deadline/2,2*this.interval+this.attemptTimeout):0;
      const budget=backupAhead?Math.max(1,Math.min(attempts===0?this.attemptTimeout:Math.min(this.attemptTimeout,2000),remaining-reserve)):remaining;
      const controller=new AbortController(), abort=()=>controller.abort(signal.reason);
      signal.addEventListener('abort',abort,{once:true});
      const timer=budget<remaining?setTimeout(()=>controller.abort(failure('RPC endpoint attempt timed out.', 'TimeoutError')),budget):null;
      let release;
      let attempted=false;
      try {
        release=await state.gate.acquire(controller.signal);
        // A request ahead of us may have cooled this endpoint while we waited.
        if (state.until > Date.now() || (state.methods.get(request.method) || 0) > Date.now()) {onOutcome(index,{method:request.method,outcome:'skipped',reason:'cooldown'});last=state.error||last;continue;}
        if (++attempts > 4) break;
        attempted=true;
        const timeout=attempts===1?this.attemptTimeout:Math.min(this.attemptTimeout,2000);
        if (!state.verified) {
          const id = await this.send(state, {method:'eth_chainId'}, controller.signal, timeout);
          if (Number(BigInt(id)) !== chain) throw failure('RPC chain identity mismatch');
          state.verified = true;
        }
        const tag = blockTag(request), hash = this.pins.get(chain + ':' + tag);
        if (hash && !state.blocks.has(tag)) {
          const header = await this.send(state, {method:'eth_getBlockByNumber',params:[tag,false]}, controller.signal, timeout);
          if (header?.hash?.toLowerCase() !== hash || BigInt(header.number) !== BigInt(tag)) throw failure('RPC snapshot block hash mismatch.', 'RpcConsistencyError');
          state.blocks.add(tag);
        }
        // A height can reorg after verification. Every evidence read names the hash.
        const pinned=hash?{...request,params:[request.params[0],{blockHash:hash,requireCanonical:true},...request.params.slice(2)]}:request;
        let result;
        try { result=request.method==='eth_chainId'?'0x'+chain.toString(16):await this.send(state,pinned,controller.signal,timeout); }
        catch(error) {
          if(hash && (error.code===-32602 || /cannot unmarshal object|block.?hash.*(?:unsupported|not supported)/i.test(error.shortMessage||error.message||''))) {
            throw Object.assign(failure('RPC does not support hash-qualified snapshot reads.'),{code:-32601,cause:error});
          }
          throw error;
        }
        onSuccess(index, state); state.strikes = 0;state.error=null;
        onOutcome(index,{method:request.method,outcome:'succeeded'});
        if (state.until) { state.until = 0; this.persist(); }
        return result;
      } catch (error) {
        last = error;state.error=error; const kind = classify(error);
        const event={method:request.method,outcome:attempted?'failed':'queue_timeout',reason:kind};
        for(let cause=error,depth=0;cause&&depth<10;cause=cause.cause,depth++){
          if(Number.isInteger(cause.status))event.http_status=cause.status;
          if(Number.isInteger(cause.code))event.rpc_code=cause.code;
        }
        onOutcome(index,event);
        if (signal.aborted) throw signal.reason;
        if (kind === 'contract' || kind === 'size') throw error;
        if (kind === 'method') state.methods.set(request.method, Date.now() + 300000);
        else {
          state.strikes = Math.min(state.strikes + 1, 5);
          state.until = Date.now() + (kind === 'throttle' ? Math.max(retryAfter(error), Math.min(this.cooldown * 2 ** (state.strikes - 1), 1800000)) : 5000);
          state.verified = false; state.blocks.clear(); this.persist();
        }
      } finally { clearTimeout(timer);signal.removeEventListener('abort',abort);release?.(); }
    }
    throw last;
  }
  transport(chain, urls, transport = viem.http, onSuccess = () => {}, onOutcome = () => {}) {
    if (!urls.length) throw failure('No configured RPC endpoint for this chain.');
    const pool = this;
    // Leave time for a personal backup after two public providers. Preserve explicit custom-first order.
    const choices=urls.map((url,index)=>({url,index}));
    const backup=choices.findIndex(row=>!pool.publicUrls.has(row.url));
    if(pool.publicUrls.has(urls[0])&&backup>2)choices.splice(2,0,...choices.splice(backup,1));
    return options => viem.createTransport({key:'kira-rpc',name:'Kira local RPC pool',type:'custom',retryCount:0,
      request: async (request, requestOptions = {}) => {
        const tag = blockTag(request), hash = pool.pins.get(chain + ':' + tag);
        const key = JSON.stringify([chain, urls, hash || null, request.method, request.params]);
        const cached = pool.cache.get(key);
        if (hash && cached && cached.expires > Date.now()) return cached.value;
        if (!requestOptions.signal && pool.pending.has(key)) return pool.pending.get(key);
        const controller = new AbortController(), external = requestOptions.signal;
        const abort = () => controller.abort(external.reason);
        if (external?.aborted) abort(); else external?.addEventListener('abort', abort, {once:true});
        const deadlineAt=Date.now()+pool.deadline;
        const timer = setTimeout(() => controller.abort(failure('RPC read deadline exceeded. Retry holdings.', 'TimeoutError')), pool.deadline);
        const promise = pool.run(chain, choices.map(row=>row.url), request, transport, options, (index,state)=>onSuccess(choices[index].index,state), controller.signal,deadlineAt,
          (index,event)=>onOutcome(choices[index].index,event)).then(value => {
          if (hash) { if (pool.cache.size >= 512) pool.cache.delete(pool.cache.keys().next().value); pool.cache.set(key, {value,expires:Date.now()+300000}); }
          return value;
        }).finally(() => { clearTimeout(timer); external?.removeEventListener('abort', abort); if (pool.pending.get(key) === promise) pool.pending.delete(key); });
        if (!external) pool.pending.set(key, promise);
        return promise;
      }
    });
  }
}
module.exports = {RpcPool, RouteRecorder, classify};
