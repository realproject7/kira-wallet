'use strict';
// One Node process for a batch holdings refresh. Requests arrive as JSON lines on
// stdin and run concurrently, so every read in the batch shares one Alchemy budget,
// one endpoint health view and one read cache. Each answer is a JSON line carrying the
// request's helper_id; any other line is progress for the job named in it.
const fs = require('node:fs');
const readline = require('node:readline');
const h = require('./onchain.cjs');
const p = require('./pipeline-onchain.cjs');

const save = file => result => { fs.writeFileSync(file + '.tmp', h.serialize(result)); fs.renameSync(file + '.tmp', file); };
const scripts = {
  'factory-markets': (input, output) => require('./market-discovery.cjs').discover(JSON.parse(fs.readFileSync(input)), save(output)),
  'sell-quotes': (input, output) => require('./sell-quotes.cjs').collect(JSON.parse(fs.readFileSync(input)), save(output)),
};
const reply = value => process.stdout.write(JSON.stringify(value) + '\n');

p.setQuiet(true);
// A timed-out provider read can settle after its request has answered. It must not
// stop the helper while other wallets are still being read.
process.on('unhandledRejection', () => {});
readline.createInterface({input: process.stdin}).on('line', line => {
  let request;
  try { request = JSON.parse(line); } catch { return; }
  if (!request || typeof request.id !== 'number' || typeof request.mode !== 'string' || typeof request.input !== 'string') return;
  const run = scripts[request.mode] ? scripts[request.mode](request.input, request.output) : p.runMode(request.mode, request.input, request.output);
  Promise.resolve(run).then(() => reply({helper_id: request.id, ok: true}),
    error => reply({helper_id: request.id, ok: false, error: h.safeError(error)}));
}).on('close', () => process.exit(0));
