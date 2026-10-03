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
console.log('Workspace catalog and job-state checks passed with 5,002 synthetic tokens.');
