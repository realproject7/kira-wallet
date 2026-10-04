'use strict';
const assert = require('node:assert/strict'), fs = require('node:fs'), os = require('node:os'), path = require('node:path');
const {execute} = require('./ows_bridge.cjs');
const root = fs.mkdtempSync(path.join(os.tmpdir(), 'kira-ows-sdk-'));
try {
  let sdk;
  try { sdk = require('@open-wallet-standard/core'); } catch { console.log('OWS SDK acceptance skipped: optional native SDK is unavailable on this platform.'); process.exit(0); }
  assert.throws(() => execute({action:'create', vault:root, name:'Synthetic wallet', passphrase:''}, sdk));
  const request = {action:'create', vault:root, name:'Synthetic-wallet-acceptance', passphrase:'synthetic-fixture-encryption-only'};
  const created = execute(request, sdk).wallet;
  assert(created.accounts.some(a => a.chain_id === 'eip155:1'));
  assert(!JSON.stringify(created).includes('mnemonic'));
  assert.throws(() => sdk.exportWallet(created.id, 'wrong-fixture-passphrase', root));
  const mnemonic = sdk.exportWallet(created.id, request.passphrase, root);
  assert.equal(mnemonic.trim().split(/\s+/).length,12);
  assert.throws(() => execute(request,sdk), /already exists/);
  const retry = execute({...request,allow_recovery:true}, sdk);
  assert.equal(retry.recovered,true);
  const again = retry.wallet;
  assert.equal(created.id, again.id);
  assert.equal(execute({action:'list', vault:root}, sdk).wallets.length, 1);
  const files = [];
  function walk(dir) { for (const name of fs.readdirSync(dir)) { const file=path.join(dir,name); if(fs.statSync(file).isDirectory())walk(file);else files.push(file); } }
  walk(root);
  assert(files.length > 0);
  assert(!files.some(file => fs.readFileSync(file).includes(Buffer.from(request.passphrase))));
  assert(!files.some(file => fs.readFileSync(file).includes(Buffer.from(mnemonic))));
  console.log('Pinned OWS SDK creates an encrypted disposable wallet and returns public EVM descriptors; repeat recovery reuses it.');
} finally { fs.rmSync(root, {recursive:true,force:true}); }
