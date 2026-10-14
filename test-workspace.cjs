'use strict';
const assert = require('node:assert/strict');
const { catalog, jobPresentation, duration } = require('./viewer/static/workspace-model.js');
const tokens = Array.from({ length: 5000 }, (_, i) => ({ id: '8453:' + i, chain_id: 8453,
  address: 'contract-' + i, symbol: 'Token ' + i, name: 'Synthetic', environment: 'mainnet',
  value_usd: i % 5 ? i : null, unpriced_count: i % 5 ? 0 : 1, wallet_count: 2 }));
tokens.push({ ...tokens[1], id: '1:1', chain_id: 1, value_usd: 0, symbol: 'Same symbol' });
tokens.push({ ...tokens[1], id: '11155111:1', chain_id: 11155111, environment: 'testnet', value_usd: 900000 });
const result = catalog(tokens);
assert.equal(result.count, 5001); assert.equal(result.rows.length, 50);
assert.equal(result.rows[0].value_usd, 4999);
assert.equal(catalog(tokens, { page: 101 }).rows.length, 1);
assert.equal(catalog(tokens, { page: 999 }).page, 101);
assert.equal(catalog(tokens, { pricing: 'unpriced' }).count, 1000);
assert.equal(catalog(tokens, { network: '1', pricing: 'priced' }).rows[0].value_usd, 0);
assert.equal(catalog(tokens, { search: 'contract-1234' }).rows[0].id, '8453:1234');
assert.equal(catalog(tokens, { testnets: true }).count, 5002);
const partial = { ...tokens[1], id: '1:partial', value_usd: 20, unpriced_count: 1 };
assert.equal(catalog([partial], { pricing: 'unpriced' }).count, 1);
assert.equal(catalog([partial], { pricing: 'priced' }).count, 0);
assert.equal(tokens[0].id, '8453:0'); // Sorting must not reorder the shared evidence.
const named = [{ ...tokens[1], id: '1:alpha', symbol: 'ZZZ', name: 'Alpha' },
  { ...tokens[1], id: '1:beta', symbol: 'AAA', name: 'Beta' },
  { ...tokens[1], id: '1:gamma', symbol: 'Gamma', name: '' }];
assert.deepEqual(catalog(named, { sort: 'name' }).rows.map(t => t.id), ['1:alpha', '1:beta', '1:gamma']);
const time = Date.parse('2026-10-04T00:05:00Z');
const job = { state: 'running', created_at: '2026-10-04T00:00:00Z', updated_at: '2026-10-04T00:01:00Z', events: [] };
assert.equal(jobPresentation(job, time).elapsed, 300);
assert.equal(jobPresentation(job, time).label, 'Running'); // Quiet is not a terminal state.
assert.equal(jobPresentation(job, time).quiet, true);
assert.equal(jobPresentation(job, time, false).spinner, false);
assert.match(jobPresentation(job, time, false).freshness, /Connection lost/);
assert.equal(jobPresentation({ ...job, started_at: '2026-10-04T00:04:00Z' }, time).elapsed, 60);
assert.equal(jobPresentation({ ...job, state: 'succeeded' }, time).elapsed, 60);
assert.equal(jobPresentation({ ...job, state: 'queued', started_at: '2026-10-03T00:00:00Z' }, time).elapsed, 240);
assert.equal(jobPresentation({ ...job, cancel_requested: true }, time).label, 'Stopping');
assert.equal(jobPresentation({ ...job, created_at: 'invalid' }, time).elapsed, null);
assert.equal(duration(3661), '1h 1m 1s');
const {jobProgress}=require('./viewer/static/workspace-model.js');
const progressEvent=(checked,second,extra={})=>({stage:'onchain_progress',observed_at:new Date(time-30000+second*1000).toISOString(),
 counts:{checked,total:100},context:{operation:'balances',chain_id:8453,attempt:2},...extra});
const measured={...job,attempt:2,result:{status:'completed_with_coverage_gaps'},events:[progressEvent(10,0),progressEvent(20,10),progressEvent(30,20)]};
assert.match(jobProgress(measured,time).eta,/Current step estimate/);
assert.equal(jobProgress(measured,time).count,'30 / 100 balances');
assert.match(jobProgress(measured,time).saved,/Saved results/);
assert.match(jobProgress(measured,time+60000).eta,/unknown/);
assert.match(jobProgress(measured,time,false).eta,/unknown/);
assert.match(jobProgress({...measured,attempt:3},time).eta,/unknown/);
assert.match(jobProgress({...measured,events:[progressEvent(10,0),progressEvent(20,10),progressEvent(5,20)]},time).eta,/unknown/);
assert.match(jobProgress({...measured,events:[{...progressEvent(4,20),counts:{checked:4,pending_ranges:3},context:{operation:'history',attempt:2}}]},time).count,/history pages checked including saved work/);
assert.match(jobProgress({...measured,state:'queued',continuation:{not_before:time/1000+60}},time).eta,/Provider retry in 1m 0s/);
assert.equal(jobProgress({...measured,state:'partial'},time).eta,'');
console.log('Workspace catalog and job-state checks passed with 5,002 synthetic tokens.');

const {networkEmpty}=require('./viewer/static/workspace-model.js');
const coverage=(...states)=>({wallets:states.map(coverage=>({coverage}))});
assert.equal(networkEmpty(coverage('Research pending','Research pending'),0).activity,true);
assert.match(networkEmpty(coverage('Research pending'),0).title,/pending/);
assert.match(networkEmpty(coverage('Researched'),0).title,/No positive holdings/);
assert.equal(networkEmpty(coverage('Researched'),0).activity,false);
assert.match(networkEmpty(coverage('RPC unavailable','Researched'),0).message,/unknown/);
assert.match(networkEmpty(coverage('Incomplete discovery'),0).title,/incomplete/);
assert.match(networkEmpty(coverage('Research pending'),3).title,/filters/);
assert.equal(networkEmpty(coverage('Research pending'),3).activity,false);
const completeStale={analysed_at:'2026-10-11T00:00:00Z',chains:[{id:1,name:'Ethereum',environment:'mainnet',complete:true,rpc_available:true,registry_complete:true,head_status:'stale',head_age_seconds:172800}]};
assert(require('./viewer/static/workspace-model.js').discoveryNotice(completeStale),'A stale successful head must stay visible even when inventory coverage succeeds.');
const mixed={analysed_at:'2026-10-11T00:00:00Z',chains:[{name:'Ham',environment:'mainnet',complete:false,lifecycle:{status:'retirement_reported'}},{name:'Base',environment:'mainnet',complete:false,rpc_available:true,registry_complete:true,discovery_status:'history_pending'}]};
const mixedNotice=require('./viewer/static/workspace-model.js').discoveryNotice(mixed);
assert.equal(mixedNotice.action,'refresh');assert(mixedNotice.message.includes('Ham'));assert(mixedNotice.message.includes('unfinished'));
const retiredAndTestnet={analysed_at:'2026-10-11T00:00:00Z',chains:[{name:'Degen L3',environment:'mainnet',complete:true,rpc_available:true,lifecycle:{status:'retired'}},{name:'Sepolia',environment:'testnet',complete:false,rpc_pending:true}]};
assert(require('./viewer/static/workspace-model.js').discoveryNotice(retiredAndTestnet),'Testnet gaps cannot hide a mainnet retirement notice.');
