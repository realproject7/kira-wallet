'use strict';
let owsState = null, owsSelected = null, owsBusy = false, owsRequest = null;
try {
  const saved = JSON.parse(sessionStorage.getItem('kira-ows-request'));
  if (saved && /^[0-9a-f-]{36}$/.test(saved.key) && typeof saved.identity === 'string') owsRequest = saved;
} catch { /* Browser storage may be unavailable. The vault still retains owner receipts. */ }
function saveOwsRequest() {
  try {
    if (owsRequest) sessionStorage.setItem('kira-ows-request', JSON.stringify(owsRequest));
    else sessionStorage.removeItem('kira-ows-request');
  } catch { /* The in-memory request remains available in this page. */ }
}
function owsDisplayName(wallet) {
  const address = (wallet?.address || wallet?.accounts?.[0]?.address || '').toLowerCase();
  const registered = state?.wallets?.find(w => (w.key || w.address || '').toLowerCase() === address);
  const connection = owsState?.connection;
  const linked = connection && ((wallet?.id && wallet.id === connection.wallet_id) || (address && address === connection.address?.toLowerCase()));
  return registered?.name || wallet?.tag || (linked && connection.tag) || wallet?.name || '';
}
function renderOws() {
  const available = owsState?.available === true;
  $('ows-status').textContent = owsState?.note || 'Checking the local vault…';
  $('ows-connection').hidden = !owsState?.connection;
  $('ows-connected-name').textContent = owsDisplayName(owsState?.connection);
  $('ows-connected-address').textContent = owsState?.connection?.address || '';
  $('ows-create-section').hidden = false;
  $('ows-pending').hidden = !owsRequest;
  $('ows-connect-form').hidden = !owsSelected;
  if (owsSelected) { $('ows-selected-name').textContent = owsDisplayName(owsSelected); $('ows-selected-address').textContent = owsSelected.accounts[0].address; }
  for (const button of $('ows-dialog').querySelectorAll('button:not([data-close-dialog])')) button.disabled = owsBusy || (!available && button.id !== 'ows-disconnect');
  for (const input of $('ows-dialog').querySelectorAll('input')) input.disabled = owsBusy;
  if (!watchingConnection.snapshot().accounts.length && owsState?.connection) {
    $('open-connection').textContent = 'OWS · ' + shortAddress(owsState.connection.address);
    $('open-connection').title = 'View linked OWS account or disconnect';
  }
}
async function loadOws() {
  if (!localSession?.controls || state?.demo) return;
  owsState = await localAPI('/api/ows');
  if (owsRequest) {
    const [create, name, tag, id] = JSON.parse(owsRequest.identity);
    if (create) { $('ows-create-name').value = name; $('ows-create-section').open = true; }
    else { owsSelected = owsState.wallets.find(w => w.id === id) || null; $('ows-connect-tag').value = tag; }
  }
  $('ows-list').replaceChildren(...owsState.wallets.filter(w => w.accounts.length).map(wallet => walletChoice(owsDisplayName(wallet), shortAddress(wallet.accounts[0].address), '/kira-logo.png', () => {
    if (owsBusy) return;
    if (owsRequest) { $('ows-error').textContent = 'Recover the pending request or check your vault before starting another.'; return; }
    owsSelected = wallet; $('ows-connect-tag').value = owsDisplayName(wallet); renderOws(); $('ows-connect-tag').focus();
  }, wallet.id === owsSelected?.id)));
  renderOws();
}
async function openOws() {
  if (!watchingCanAct()) return;
  $('wallet-dialog').close(); $('ows-error').textContent = ''; $('ows-dialog').showModal();
  try { await loadOws(); } catch { $('ows-error').textContent = 'The local vault could not be checked. You can still use a browser wallet or public address.'; }
}
$('wallet-ows-mode').addEventListener('click', openOws);
$('wallet-copy-link').addEventListener('click', async () => {
  try { await navigator.clipboard.writeText(location.origin); $('wallet-copy-link').textContent = 'Copied'; }
  catch { toast('Open this app URL in a browser with a wallet extension: '+location.origin); }
});
$('ows-disconnect').addEventListener('click', async () => {
  if (owsBusy) return;
  try { await agentPost('/api/ows/disconnect', {}); owsState.connection = null; owsSelected = null; renderWatching(); renderOws(); }
  catch (error) { $('ows-error').textContent = error.message; }
});
async function submitOws(create, event) {
  event.preventDefault(); if (owsBusy || !owsState?.available || !watchingCanAct()) return;
  $('ows-error').textContent = '';
  const name = $('ows-create-name').value.trim(), tag = create ? name : $('ows-connect-tag').value.trim();
  if (create && $('ows-passphrase').value !== $('ows-passphrase-confirm').value) { $('ows-error').textContent = 'The passphrases do not match.'; return; }
  const identity = JSON.stringify([create, name, tag, create ? null : owsSelected?.id]);
  if (owsRequest && owsRequest.identity !== identity) { $('ows-error').textContent = 'This request may already have finished. Recover its original name or check the vault before starting another.'; return; }
  if (!owsRequest || owsRequest.identity !== identity) owsRequest = {identity, key: crypto.randomUUID()};
  saveOwsRequest();
  const request = create ? {name, tag, passphrase: $('ows-passphrase').value, idempotency_key: owsRequest.key} : {wallet_id: owsSelected.id, tag, idempotency_key: owsRequest.key};
  // Password fields are cleared before the asynchronous request. No browser storage.
  $('ows-passphrase').value = ''; $('ows-passphrase-confirm').value = '';
  owsBusy = true; renderOws(); $('ows-status').textContent = create ? 'Creating your encrypted local wallet…' : 'Linking the public account…';
  try {
    const result = await localAPI(create ? '/api/ows/create' : '/api/ows/connect', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(request), signal: AbortSignal.timeout(75000)});
    delete request.passphrase;
    owsRequest = null; saveOwsRequest(); owsSelected = null; await loadOws();
    $('ows-dialog').close(); navigate(result.job_id ? '#/activity' : '#/wallet/'+result.connection.address.toLowerCase());
    toast(result.note);
  } catch (error) { delete request.passphrase; $('ows-error').textContent = error.message; }
  finally { owsBusy = false; renderOws(); }
}
$('ows-connect-form').addEventListener('submit', event => submitOws(false, event));
$('ows-create-form').addEventListener('submit', event => submitOws(true, event));
$('ows-dialog').addEventListener('close', () => { $('ows-passphrase').value = ''; $('ows-passphrase-confirm').value = ''; });
$('ows-forget-request').addEventListener('click', async () => {
  if (owsBusy) return;
  await loadOws(); owsRequest = null; saveOwsRequest(); renderOws();
});
// The existing connection chooser stays useful with or without the optional SDK.

$('open-create-wallet').addEventListener('click', async () => { await openOws(); $('ows-create-section').open = true; if(owsState?.available)$('ows-create-name').focus(); });
