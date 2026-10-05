'use strict';
let agentState = null, agentProvider = 'codex', agentStep = 1, setupRevision = 0, agentVerified = false;
let chatTurn = null, chatEpoch = 0, chatRequest = null, chatRetry = null, agentLoading = false, setupTesting = false, setupTurn = null, draftRevision = 0;
let chatSignature = '', agentReady = false, chatDraftRevision = 0;
const scopeNames = {none: 'No wallet context', wallet: 'One approved wallet', portfolio: 'Whole portfolio'};
const questionStarters = {
  liquidity: 'Which tokens in my wallets may have been sitting idle, and what could I receive if I sold my full balance? Show each token’s chain, contract, quantity, price and timestamp, pool pair and venue, spot value, and any recorded full-balance output. Use actual transfer-history evidence for inactivity; if it is unavailable, say so. Keep sale proceeds, price impact, fees and gas unknown when there is no current executable quote.',
  prices: 'Review my Blast holdings across all wallets. Show quantities, unit prices, valuation timestamps and recorded market routes for each token. Separate ETH for gas, assets with reliable market evidence, unpriced tokens and missing wallet coverage. Do not assume a trending token is one I hold. Tell me what to refresh before deciding my next move.',
  coverage: 'Which tokens or networks need another look? Show exact quantities and contract identities for unpriced holdings, explain missing or unreliable price and coverage evidence, and prioritise the next research actions. Keep unknown values distinct from zero.'
};
const agentPost = (path, body) => localAPI(path, {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)});
function currentSetup() {
  return {provider: agentProvider, model: $('agent-model').value.trim(), scope: document.querySelector('[name="agent-scope"]:checked').value,
    wallet: $('agent-wallet').value || null, retain_history: $('agent-retain').checked, trust_native_cli: $('agent-trust').checked, wallet_tools: $('agent-tools').checked};
}
function invalidateSetup() { setupRevision++; agentVerified = false; $('agent-save').disabled = true; $('agent-test-status').textContent = ''; }
function scopeLabel(config) {
  if (!config) return 'Wallet access is off';
  if (config.scope === 'wallet') return 'Context: ' + (state?.wallets.find(w => w.key === config.wallet)?.name || 'approved wallet');
  return config.scope === 'portfolio' ? 'Connected to your portfolio' : 'Wallet access is off';
}
function renderAgent() {
  const config = agentState?.config;
  $('chat-model-label').textContent = config ? (config.provider === 'codex' ? 'Codex' : 'Claude') + ' · ' + (config.model || 'CLI default') : 'Connect a model';
  $('chat-setup').classList.toggle('connected', Boolean(config));
  $('chat-context').textContent = scopeLabel(config);
  $('chat-choose-context').hidden = !config || !state?.wallets.length || !localSession?.controls;
  $('chat-form').dataset.working = String(Boolean(chatTurn));
  $('chat-status').textContent = chatTurn ? (agentState?.tool_status || 'Kira is working…') : config ? (config.retain_history ? 'History saved locally' : 'History in memory') : 'Connect your account';
  $('chat-send').hidden = Boolean(chatTurn); $('chat-stop').hidden = !chatTurn;
  $('chat-send').disabled = !config || !localSession?.controls || !$('kira-draft').value.trim() || Boolean(chatRequest);
  $('chat-suggestions').hidden = Boolean($('kira-draft').value.trim());
  if($('chat-welcome'))$('chat-welcome').hidden=Boolean((agentState?.messages||[]).length||chatTurn);
  if(typeof renderSetupPath==='function')renderSetupPath();
  if(typeof renderBriefing==='function')renderBriefing();
  const messages = agentState?.messages || [];
  $('kira-panel').classList.toggle('chatting', Boolean(messages.length || chatTurn));
  const signature = JSON.stringify([messages, chatTurn, chatRequest?.message, agentState?.tool_status]);
  if (signature !== chatSignature) {
    const scroller=$('conversation-scroll'), previousTop=scroller.scrollTop;
    const follow=scroller.scrollHeight-scroller.clientHeight-previousTop<80;
    chatSignature = signature;
    $('chat-messages').innerHTML = messages.map(message => `<article class="chat-message ${message.role === 'user' ? 'user' : 'assistant'}"><strong>${message.role === 'user' ? 'YOU' : 'KIRA'}</strong>${message.role === 'user' ? '<p>' + escapeHTML(message.text) + '</p>' : '<div class="kira-reply-identity"><img src="/kira-explain.png" width="48" height="60" alt=""><span>Kira</span></div><div class="markdown-body">' + KiraMarkdown.render(message.text) + '</div>'}</article>`).join('') + (chatTurn && chatRequest?.message ? `<article class="chat-message user"><strong>YOU</strong><p>${escapeHTML(chatRequest.message)}</p></article>` : '') + (chatTurn ? '<div class="chat-message pending"><img src="/kira-research.png" width="72" height="90" alt="Kira analysing your question"><div><strong>Kira</strong><p>' + escapeHTML(agentState?.tool_status || 'Let me take a look…') + '</p><span class="thinking-dots" aria-hidden="true"><i></i><i></i><i></i></span></div></div>' : '');
    scroller.scrollTop=follow?scroller.scrollHeight:previousTop;
  }
}
function renderProviders() {
  $('agent-providers').innerHTML = (agentState?.providers || []).map(row => {
    const ready = row.installed && row.supported && row.logged_in;
    const label = !row.installed ? 'Install CLI' : !row.supported ? 'Unsupported version' : !row.logged_in ? 'Login needed' : 'Account detected';
    return `<button class="provider-card" type="button" data-provider="${row.id}" aria-pressed="${agentProvider === row.id}"><strong>${escapeHTML(row.name)}</strong><small>${row.id === 'codex' ? 'Your ChatGPT account' : 'Your Claude account'}${row.version ? ' · ' + escapeHTML(row.version) : ''}</small><span class="provider-status ${ready ? 'ready' : ''}">${label}</span></button>`;
  }).join('');
  const selected = agentState?.providers.find(p => p.id === agentProvider);
  $('agent-cli-help').innerHTML = !selected ? '' : selected.installed && selected.supported && selected.logged_in ? 'Your native account is ready for a response check. Kira never copies its credentials.' :
    `<p>${!selected.installed ? 'Install the official CLI in your terminal, then sign in.' : !selected.supported ? 'Use a verified version: Codex 0.158.x or Claude Code 2.1.259–2.1.x.' : 'Sign in through the official CLI in your terminal.'} <a href="${selected.url}" target="_blank" rel="noreferrer">Official setup ↗</a></p>${(!selected.installed ? [selected.install, selected.login] : [selected.login]).map(command => `<div class="cli-command"><code>${escapeHTML(command)}</code><button type="button" data-copy-cli="${escapeHTML(command)}">Copy</button></div>`).join('')}`;
  updateStep();
}
function updateStep() {
  for (let step = 1; step <= 3; step++) {
    $('agent-step-' + step).hidden = step !== agentStep;
    const node = document.querySelector('.setup-progress [data-step="' + step + '"]');
    if (step === agentStep) node.setAttribute('aria-current', 'step'); else node.removeAttribute('aria-current');
  }
  $('agent-back').hidden = agentStep === 1; $('agent-next').hidden = agentStep === 3; $('agent-save').hidden = agentStep !== 3;
  const selected = agentState?.providers.find(p => p.id === agentProvider);
  $('agent-next').disabled = agentStep === 1 ? !(selected?.installed && selected.supported && selected.logged_in) : !$('agent-trust').checked || (currentSetup().scope === 'wallet' && !$('agent-wallet').value);
  $('agent-wallet-field').hidden = currentSetup().scope !== 'wallet';
  if (agentStep === 3) {
    const config = currentSetup();
    $('agent-review').innerHTML = '<dt>Account</dt><dd>' + escapeHTML(selected?.name || '') + '</dd><dt>Model</dt><dd>' + escapeHTML(config.model || 'CLI default') + '</dd><dt>Context</dt><dd>' + escapeHTML(scopeLabel(config)) + '</dd><dt>History</dt><dd>' + (config.retain_history ? 'Saved on this computer' : 'Memory only') + '</dd>';
  }
}
async function loadAgent(recheck = false) {
  if (!localSession?.controls) return;
  const epoch = chatEpoch;
  const status = await localAPI('/api/agent' + (recheck ? '?recheck=1' : ''));
  if (epoch !== chatEpoch) return;
  agentState = status; renderAgent();
  if (typeof loadOws === 'function' && !owsState) loadOws().catch(() => {});
  if (agentState.active_turn && !chatTurn && !chatRequest && !setupTesting) {
    const id = agentState.active_turn;
    // Keep Stop available even when the first recovery lookup loses its response.
    chatTurn = id; chatDraftRevision = draftRevision; renderAgent();
    let turn;
    try { turn = await localAPI('/api/chat/turn/' + encodeURIComponent(id)); }
    catch { if (epoch === chatEpoch) { recoverResponse(id, epoch); agentReady = true; } return; }
    if (epoch !== chatEpoch) return;
    if (turn.state === 'running') {
      chatTurn = turn.id; chatRequest = turn.test ? null : {message: turn.message, conversation_id: turn.conversation_id, idempotency_key: turn.id}; renderAgent();
      recoverResponse(turn.id, epoch);
    } else {
      await recoverResponse(id, epoch);
    }
  }
  agentReady = true;
}
async function openAgent() {
  if (state?.demo) { toast('The sample workspace does not contact model services. Run kira setup for your personal workspace.'); return; }
  if (!localSession?.controls) { toast('Start your local workspace with kira setup to enable connection settings.'); return; }
  $('agent-error').textContent = ''; $('agent-providers').innerHTML = '<p>Checking installed accounts…</p>';
  $('agent-dialog').showModal(); agentStep = 1; invalidateSetup();
  try {
    await loadAgent();
    const config = agentState.config;
    agentProvider = config?.provider || agentState.providers.find(p => p.installed && p.supported && p.logged_in)?.id || 'codex';
    $('agent-model').value = config?.model || '';
    document.querySelector('[name="agent-scope"][value="' + (config?.scope || 'portfolio') + '"]').checked = true;
    $('agent-wallet').innerHTML = '<option value="">Choose a wallet</option>' + (state?.wallets || []).map(w => `<option value="${escapeHTML(w.key)}">${escapeHTML(w.name)}</option>`).join('');
    $('agent-wallet').value = config?.wallet || ''; $('agent-retain').checked = config?.retain_history || false; $('agent-trust').checked = config?.trust_native_cli || false; $('agent-tools').checked = config ? config.wallet_tools === true : true;
    renderProviders();
  } catch (error) { $('agent-error').textContent = error.message; }
}
$('chat-setup').addEventListener('click', openAgent);
$('chat-choose-context').addEventListener('click', openAgent);
$('settings-agent').addEventListener('click', () => { $('settings-dialog').close(); openAgent(); });
$('agent-providers').addEventListener('click', event => {
  const button = event.target.closest('[data-provider]'); if (!button || setupTesting) return;
  if (agentProvider !== button.dataset.provider) { agentProvider = button.dataset.provider; $('agent-model').value = ''; invalidateSetup(); renderProviders(); }
});
$('agent-cli-help').addEventListener('click', async event => {
  const button = event.target.closest('[data-copy-cli]'); if (!button) return;
  try { await navigator.clipboard.writeText(button.dataset.copyCli); button.textContent = 'Copied'; } catch { toast('Select and copy the command in your terminal.'); }
});
for (const id of ['agent-model', 'agent-wallet', 'agent-retain', 'agent-trust', 'agent-tools']) $(id).addEventListener('input', () => { invalidateSetup(); updateStep(); });
document.querySelectorAll('[name="agent-scope"]').forEach(input => input.addEventListener('change', () => { invalidateSetup(); updateStep(); }));
$('agent-next').addEventListener('click', () => { if (!$('agent-next').disabled) { agentStep++; updateStep(); $('agent-dialog').scrollTop = 0; } });
$('agent-back').addEventListener('click', () => { agentStep--; updateStep(); });
$('agent-recheck').addEventListener('click', async () => {
  $('agent-recheck').disabled = true; $('agent-error').textContent = '';
  try { await loadAgent(true); invalidateSetup(); renderProviders(); } catch (error) { $('agent-error').textContent = error.message; }
  finally { $('agent-recheck').disabled = false; }
});
async function waitTurn(id, valid) {
  while (valid()) {
    const turn = await localAPI('/api/chat/turn/' + encodeURIComponent(id));
    if (turn.state !== 'running') return turn;
    if(chatTurn===id&&agentState){agentState.tool_status=turn.tool_status||null;renderAgent();}
    await new Promise(resolve => setTimeout(resolve, 700));
  }
  return null;
}
$('agent-test').addEventListener('click', async () => {
  if (setupTesting) return;
  setupTesting = true; const revision = setupRevision; $('agent-test').disabled = true; $('agent-back').disabled = true; $('agent-error').textContent = ''; $('agent-test-status').textContent = 'Checking a response with no wallet data…';
  const id = crypto.randomUUID(); setupTurn = id;
  try {
    const turn = await agentPost('/api/agent/test', {config: currentSetup(), idempotency_key: id});
    if (revision !== setupRevision) { await agentPost('/api/chat/cancel', {id: turn.id}); return; }
    const result = await waitTurn(turn.id, () => revision === setupRevision);
    if (!result) return;
    if (result.state !== 'succeeded') throw new Error(result.error?.message || 'Connection check stopped. Retry before saving.');
    if (revision === setupRevision) { agentVerified = true; $('agent-save').disabled = false; $('agent-test-status').textContent = 'Connected. Kira received a real response.'; }
  } catch (error) { await agentPost('/api/chat/cancel', {id}).catch(() => {}); if (revision === setupRevision) { $('agent-test-status').textContent = ''; $('agent-error').textContent = error.message; } }
  finally { setupTesting = false; setupTurn = null; $('agent-test').disabled = false; $('agent-back').disabled = false; }
});
$('agent-dialog').addEventListener('close', () => {
  invalidateSetup(); if (setupTurn) agentPost('/api/chat/cancel', {id: setupTurn}).catch(() => {});
});
$('agent-save').addEventListener('click', async () => {
  if (!agentVerified) return; $('agent-save').disabled = true; $('agent-error').textContent = '';
  try {
    await agentPost('/api/agent/settings', currentSetup()); chatEpoch++; chatTurn = null; chatRequest = null;
    await loadAgent(); $('agent-dialog').close(); $('kira-draft').focus();
  } catch (error) { $('agent-error').textContent = error.message; $('agent-save').disabled = false; }
});
$('kira-draft').addEventListener('input', () => { draftRevision++; $('draft-status').textContent = 'Draft stays in memory until sent.'; renderAgent(); });
$('chat-suggestions').addEventListener('click', event => {
  const key = event.target.closest('[data-prompt]')?.dataset.prompt;
  if (!Object.hasOwn(questionStarters, key) || $('kira-draft').value.trim()) return;
  $('kira-draft').value = questionStarters[key];
  draftRevision++;
  $('draft-status').textContent = 'Question added. Edit it before sending.';
  renderAgent();
  $('kira-draft').focus();
});
$('kira-draft').addEventListener('keydown', event => {
  if (event.key === 'Enter' && !event.shiftKey && !event.isComposing && event.keyCode !== 229) { event.preventDefault(); if (!$('chat-send').disabled) $('chat-form').requestSubmit(); }
});
async function sendChat(event) {
  event.preventDefault(); if (!agentState?.config || chatTurn || chatRequest) return;
  const message = $('kira-draft').value.trim(); if (!message) return;
  const epoch = chatEpoch, draftAtSend = draftRevision;
  chatDraftRevision = draftAtSend;
  chatRequest = chatRetry?.message === message && chatRetry.conversation_id === agentState.conversation_id ? chatRetry : {message, conversation_id: agentState.conversation_id, idempotency_key: crypto.randomUUID()}; chatRetry = chatRequest; renderAgent(); $('chat-error').textContent = '';
  try {
    const turn = await agentPost('/api/chat/send', chatRequest);
    if (epoch !== chatEpoch) return;
    chatTurn = turn.id; if (draftRevision === draftAtSend) $('kira-draft').value = ''; renderAgent(); $('conversation-scroll').scrollTop=$('conversation-scroll').scrollHeight;
    const result = await waitTurn(turn.id, () => epoch === chatEpoch);
    if (!result || epoch !== chatEpoch) return;
    if (result.state !== 'succeeded') { if (!$('kira-draft').value && draftRevision === draftAtSend) $('kira-draft').value = message; chatRetry = null; throw new Error(result.error?.message || 'Response stopped. You can edit and send your message again.'); }
    await loadAgent(); chatRetry = null;
  } catch (error) { if (epoch === chatEpoch) { $('chat-error').textContent = error.message; if (chatTurn && chatRetry) { recoverResponse(chatTurn, epoch); return; } } }
  finally { if (epoch === chatEpoch && !(chatTurn && chatRetry)) { chatTurn = null; chatRequest = null; renderAgent(); if (chatRetry) loadAgent().catch(() => {}); } }
}
async function recoverResponse(id, epoch) {
  try {
    const result = await waitTurn(id, () => epoch === chatEpoch);
    if (epoch !== chatEpoch || !result) return;
    if (result.state !== 'succeeded') {
      if (!$('kira-draft').value && !result.test && draftRevision === chatDraftRevision) $('kira-draft').value = chatRequest?.message || result.message || '';
      $('chat-error').textContent = result.error?.message || 'Response stopped. Research already queued stays in Activity, where you can stop it. You can edit and resend your message.';
    } else $('chat-error').textContent = '';
    const status = await localAPI('/api/agent');
    if (epoch !== chatEpoch || chatTurn !== id) return;
    agentState = status; chatTurn = null; chatRequest = null; chatRetry = null;
  } catch (error) { if (epoch === chatEpoch) { $('chat-error').textContent = 'Reconnecting. ' + error.message; setTimeout(() => { if (epoch === chatEpoch && chatTurn === id) recoverResponse(id, epoch); }, 1500); } }
  finally { if (epoch === chatEpoch) renderAgent(); }
}
$('chat-form').addEventListener('submit', sendChat);
$('chat-stop').addEventListener('click', async () => {
  const id = chatTurn; if (!id) return;
  $('chat-stop').disabled = true;
  try { const result = await agentPost('/api/chat/cancel', {id}); chatEpoch++; chatTurn = null; if (result.state !== 'succeeded' && chatRequest && !$('kira-draft').value) $('kira-draft').value = chatRequest.message; chatRequest = null; chatRetry = null; await loadAgent(); $('chat-error').textContent = result.state === 'succeeded' ? '' : 'Response stopped. Research already queued stays in Activity, where you can stop it. You can edit and resend your message.'; }
  catch (error) { $('chat-error').textContent = error.message; }
  finally { $('chat-stop').disabled = false; renderAgent(); }
});
$('chat-new').addEventListener('click', async () => {
  if (!localSession?.controls || chatRequest && !chatTurn) return;
  try { await agentPost('/api/chat/reset', {}); chatEpoch++; chatTurn = null; chatRequest = null; chatRetry = null; await loadAgent(); $('chat-error').textContent = ''; $('kira-draft').focus(); }
  catch (error) { $('chat-error').textContent = error.message; }
});
async function initialAgent() {
  if (agentLoading || agentReady || !localSession?.controls) return; agentLoading = true;
  try { await loadAgent(); if (new URLSearchParams(location.search).get('setup') === '1') { history.replaceState(null, '', '/#/home'); await loadSetupReadiness(); renderSetupPath(); } }
  catch { /* The normal local session polling can reconnect. */ }
  finally { agentLoading = false; }
}
renderAgent(); initialAgent(); const agentStartup = setInterval(() => { initialAgent(); if (agentReady) clearInterval(agentStartup); }, 1000);
