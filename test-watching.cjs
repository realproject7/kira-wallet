'use strict';
const {test} = require('node:test');
const assert = require('node:assert/strict');
const {EventEmitter} = require('node:events');
const {create, discover, safeIcon} = require('./viewer/static/watching-model.js');
const A = '0x'+'1'.repeat(40), B = '0x'+'2'.repeat(40);
const ID = '11111111-1111-4111-8111-111111111111', OTHER = '22222222-2222-4222-8222-222222222222';
class Provider extends EventEmitter {
  calls = [];
  result = [A];
  request(input) { this.calls.push(input); return Promise.resolve(this.result); }
}
function detail(provider, uuid = ID, info = {}) {
  return {provider, info:{uuid, name:'Synthetic wallet', rdns:'test.synthetic', icon:'https://remote.invalid/icon.svg', ...info}};
}
function setup(result = [A]) {
  const provider = new Provider(); provider.result = result;
  const connection = create(); connection.announce(detail(provider));
  return {connection, provider};
}
function pending(provider) { let resolve; provider.result = new Promise(done => { resolve = done; }); return resolve; }
function assertReleased(provider) {
  for (const event of ['accountsChanged','chainChanged','disconnect']) assert.equal(provider.listenerCount(event), 0);
}
test('discovery installs its listener before requesting providers, survives late announcements, and never requests accounts', () => {
  const target = new EventTarget(), provider = new Provider(), connection = create();
  const announce = () => { const event = new Event('eip6963:announceProvider'); event.detail = detail(provider); target.dispatchEvent(event); };
  target.addEventListener('eip6963:requestProvider', announce);
  const dispose = discover(target, connection);
  assert.equal(connection.snapshot().providers.length, 1); assert.deepEqual(provider.calls, []);
  const late = new Provider(), event = new Event('eip6963:announceProvider'); event.detail = detail(late, OTHER); target.dispatchEvent(event);
  assert.equal(connection.snapshot().providers.length, 2); assert.deepEqual(late.calls, []);
  dispose();
});
test('repeated announcements, same object under another UUID and UUID collisions do not replace or reselect providers', () => {
  const {connection, provider} = setup();
  assert.equal(connection.announce(detail(provider)), false);
  assert.equal(connection.announce(detail(provider, OTHER)), false);
  assert.equal(connection.announce(detail(new Provider())), false);
  assert.equal(connection.snapshot().providers.length, 1);
  assert.equal(connection.snapshot().providerId, null);
  assert.equal(connection.announce(detail(new Provider(), 'not-a-uuid')), false);
});
test('provider metadata is bounded, not an authenticity signal, and remote icons are refused', () => {
  const {connection} = setup();
  const hostile = detail(new Provider(), OTHER, {name:'<img src=x onerror=alert(1)>', rdns:'\u202ereversed\u0000', icon:'javascript:alert(1)'});
  assert.equal(connection.announce(hostile), true);
  const row = connection.snapshot().providers[1];
  assert.equal(row.name, '<img src=x onerror=alert(1)>'); assert.equal(row.rdns, 'reversed'); assert.equal(row.icon, null);
  assert.equal(safeIcon('data:image/svg+xml,<svg onload="alert(1)"></svg>')?.startsWith('data:'), true);
  assert.equal(safeIcon('data:text/html,<script>'), null);
  assert.equal(safeIcon('data:image/png;base64,'+'A'.repeat(32769)), null);
  assert.equal(connection.announce({get info() {throw Error('untrusted');}}), false);
});
test('only an explicitly chosen provider receives account access, even for one account', async () => {
  const {connection, provider} = setup(), other = new Provider(); connection.announce(detail(other, OTHER));
  await connection.connect(OTHER);
  assert.deepEqual(provider.calls, []); assert.deepEqual(other.calls, [{method:'eth_requestAccounts'}]);
  assert.equal(connection.snapshot().selected, null);
  assert.throws(() => connection.registration('Synthetic exact name'));
  assert.equal(connection.select(A), true);
  assert.deepEqual(connection.registration('  Synthetic exact name  '), {address:A, tag:'  Synthetic exact name  '});
});
test('multiple accounts need a choice, invalid choices cannot register, and duplicate account casing is collapsed', async () => {
  const {connection} = setup([A, A.toUpperCase().replace('0X','0x'), B]);
  await connection.connect(ID); assert.equal(connection.snapshot().accounts.length, 2);
  assert.equal(connection.select('0x'+'3'.repeat(40)), false);
  assert.equal(connection.select(B), true); assert.equal(connection.registration('Synthetic').address, B);
  assert.throws(() => connection.registration('   ')); assert.throws(() => connection.registration('x'.repeat(201)));
});
test('accountsChanged invalidates the preview synchronously, including an identical account list', async () => {
  const {connection, provider} = setup(); await connection.connect(ID); connection.select(A);
  provider.emit('accountsChanged', [A]); assert.throws(() => connection.registration('Synthetic'));
  connection.select(A); provider.emit('accountsChanged', [B]);
  assert.equal(connection.snapshot().selected, null); assert.throws(() => connection.registration('Synthetic'));
  connection.select(B); assert.equal(connection.registration('Synthetic').address, B);
  assert.equal(provider.calls.length, 1);
});
test('late account response after cancellation cannot restore a session', async () => {
  const {connection, provider} = setup(), resolve = pending(provider), attempt = connection.connect(ID);
  connection.clearSelection(); assertReleased(provider); resolve([A]); await attempt;
  assert.equal(connection.snapshot().status, 'disconnected'); assert.equal(connection.snapshot().selected, null);
});
test('late response from an old provider cannot overwrite the newly chosen session', async () => {
  const {connection, provider} = setup(), resolve = pending(provider), old = connection.connect(ID);
  const other = new Provider(); other.result = [B]; connection.announce(detail(other, OTHER));
  await connection.connect(OTHER); connection.select(B); assertReleased(provider);
  resolve([A]); await old; assert.equal(connection.registration('Synthetic').address, B);
  provider.emit('accountsChanged', [A]); assert.equal(connection.snapshot().providerId, OTHER);
});
test('late provider rejection after disconnect does not restore an error or a registration candidate', async () => {
  const {connection, provider} = setup(); let reject;
  provider.request = () => new Promise((_, fail) => { reject = fail; });
  const attempt = connection.connect(ID); connection.disconnect();
  reject({code:4001}); await attempt;
  assert.equal(connection.snapshot().status, 'disconnected');
  assert.equal(connection.snapshot().message.includes('declined'), false);
  assert.throws(() => connection.registration('Synthetic')); assertReleased(provider);
});
test('an account event while access is pending wins over a stale request result', async () => {
  const {connection, provider} = setup(), resolve = pending(provider), attempt = connection.connect(ID);
  provider.emit('accountsChanged', [B]); connection.select(B); resolve([A]); await attempt;
  assert.equal(connection.registration('Synthetic').address, B);
});
test('empty shared accounts or disconnect releases the session and leaves no registration candidate', async () => {
  for (const event of ['accountsChanged','disconnect']) {
    const {connection, provider} = setup(); await connection.connect(ID); connection.select(A);
    provider.emit(event, []); assertReleased(provider); assert.throws(() => connection.registration('Synthetic'));
    assert.equal(connection.snapshot().providerId, null);
  }
});
test('chain context changes do not switch networks, request accounts again or change the selected public address', async () => {
  const {connection, provider} = setup(); await connection.connect(ID); connection.select(A);
  provider.emit('chainChanged','0x2105'); assert.equal(connection.snapshot().chainId, '0x2105');
  assert.equal(connection.registration('Synthetic').address, A);
  provider.emit('chainChanged','<script>'); assert.equal(connection.snapshot().chainId, null);
  assert.deepEqual(provider.calls, [{method:'eth_requestAccounts'}]);
});
test('closing a completed chooser clears its preview but retains the memory session until explicit disconnect', async () => {
  const {connection, provider} = setup(); await connection.connect(ID); connection.select(A);
  connection.clearSelection(); assert.equal(connection.snapshot().accounts[0], A); assert.throws(() => connection.registration('Synthetic'));
  assert.equal(provider.listenerCount('accountsChanged'), 1);
  connection.disconnect(); assertReleased(provider);
  const reloaded = create(); reloaded.announce(detail(provider));
  assert.equal(reloaded.snapshot().providerId, null); assert.equal(provider.calls.length, 1);
});
test('provider errors use bounded public messages without leaking arbitrary exception contents', async () => {
  for (const code of [4001,4100,4200,4900,4901,-32002,999,'__proto__','toString']) {
    const {connection, provider} = setup();
    provider.request = async input => { provider.calls.push(input); throw {code, message:'private untrusted provider details'}; };
    await connection.connect(ID); const current = connection.snapshot();
    assert.equal(current.status, 'error'); assert.equal(current.message.includes('private'), false);
    assert.equal(typeof current.message, 'string');
    assert.equal(current.message.length < 200, true); assertReleased(provider); assert.throws(() => connection.registration('Synthetic'));
  }
});
test('malformed accounts, locked wallets and partial event subscription cannot create a preview', async () => {
  for (const value of [null, 'bad', ['not-an-address'], Array(101).fill(A), []]) {
    const {connection, provider} = setup(value); await connection.connect(ID);
    assert.equal(connection.snapshot().selected, null); assertReleased(provider); assert.throws(() => connection.registration('Synthetic'));
  }
  const {connection, provider} = setup();
  provider.on = function(event, listener) { EventEmitter.prototype.on.call(this,event,listener); if (event === 'chainChanged') throw Error('subscription failed'); return this; };
  await connection.connect(ID); assert.deepEqual(provider.calls, []); assertReleased(provider);
});
