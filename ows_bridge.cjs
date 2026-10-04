'use strict';
// Only public descriptors and encrypted creation. This bridge never exports or signs.
const fs = require('node:fs');
function descriptor(wallet) {
  if (!wallet || typeof wallet.id !== 'string' || typeof wallet.name !== 'string' || !Array.isArray(wallet.accounts)) throw new Error('Invalid descriptor');
  return {id: wallet.id, name: wallet.name.slice(0, 120), created_at: wallet.createdAt,
    accounts: wallet.accounts.filter(a => /^eip155:[1-9][0-9]*$/.test(a.chainId) && /^0x[0-9a-fA-F]{40}$/.test(a.address)).map(a => ({chain_id: a.chainId, address: a.address}))};
}
function execute(request, sdk) {
  if (!request || !['list', 'create'].includes(request.action) || typeof request.vault !== 'string') throw new Error('Invalid operation');
  if (request.action === 'list') return {wallets: sdk.listWallets(request.vault).slice(0, 200).map(descriptor)};
  if (typeof request.name !== 'string' || !/^[A-Za-z0-9][A-Za-z0-9 ._-]{1,95}$/.test(request.name) || typeof request.passphrase !== 'string' || request.passphrase.trim().length < 12 || request.passphrase.length > 1024) throw new Error('Encrypted creation requires a name and passphrase');
  const existing = sdk.listWallets(request.vault).find(w => w.name === request.name);
  // A name is reserved by an owner-side idempotency receipt before this call.
  if (existing && request.allow_recovery !== true) throw new Error('Creation identity already exists');
  return {wallet: descriptor(existing || sdk.createWallet(request.name, request.passphrase, 12, request.vault)), recovered: Boolean(existing)};
}
if (require.main === module) {
  try {
    const input = fs.readFileSync(0, 'utf8');
    if (Buffer.byteLength(input) > 16384) throw new Error('Input too large');
    const sdk = require('@open-wallet-standard/core');
    process.stdout.write(JSON.stringify(execute(JSON.parse(input), sdk)));
  } catch { process.stdout.write(JSON.stringify({error: 'The local OWS SDK could not complete this operation.'})); process.exitCode = 1; }
}
module.exports = {descriptor, execute};
