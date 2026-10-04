'use strict';
// Extension state is memory only. Registration still uses the protected local job API in jobs.js.
let watchingMode = 'manual', watchingSubmitting = false, watchingLastStatus = 'idle';
let watchingSubmission = null;
const watchingConnection = KiraWatching.create(renderWatching);
KiraWatching.discover(window, watchingConnection);

function watchingCanAct() {
  return localSession?.controls === true && !!state && state.demo !== true;
}
function setWatchingMode(mode) {
  if (watchingSubmission) return;
  watchingMode = mode;
  watchingConnection.clearSelection();
  $('new-wallet-address').value = '';
  $('wallet-form-error').textContent = '';
  renderWatching();
}
function walletChoice(label, description, icon, action, pressed) {
  const button = document.createElement('button');
  button.type = 'button'; button.className = 'wallet-choice';
  button.setAttribute('aria-pressed', String(pressed));
  const image = document.createElement('img'); image.alt = ''; image.width = 32; image.height = 32;
  image.src = icon || '/kira-logo.png';
  image.addEventListener('error', () => { if (!image.src.endsWith('/kira-logo.png')) image.src = '/kira-logo.png'; });
  const text = document.createElement('span'), title = document.createElement('strong'), subtitle = document.createElement('small');
  title.textContent = label; subtitle.textContent = description; text.append(title, subtitle);
  const arrow = document.createElement('span'); arrow.className = 'wallet-choice-arrow'; arrow.setAttribute('aria-hidden','true');
  arrow.innerHTML = '<svg class="ui-icon" viewBox="0 0 24 24" fill="none" focusable="false"><path d="'+(pressed ? 'm5 12 4 4L19 6' : 'm9 6 6 6-6 6')+'"/></svg>';
  button.append(image, text, arrow);
  button.addEventListener('click', action); return button;
}
function replaceWatchingChoices(list, choices) {
  const activeLabel = list.contains(document.activeElement) ? document.activeElement.getAttribute('aria-label') : null;
  list.replaceChildren(...choices);
  if (activeLabel && $('wallet-dialog').open) {
    const replacement = choices.find(choice => choice.getAttribute('aria-label') === activeLabel);
    if (replacement && !replacement.disabled) replacement.focus({preventScroll:true});
    else $('wallet-connection-status').focus({preventScroll:true});
  }
}
function renderWatching() {
  const current = watchingConnection.snapshot(), browser = watchingMode === 'browser';
  const permitted = watchingCanAct();
  const submission = watchingSubmission;
  $('wallet-entry-modes').hidden = !!submission;
  $('wallet-submission').hidden = !submission;
  if (submission) {
    $('wallet-submission-title').textContent = watchingSubmitting ? 'Saving this Watching wallet' : 'We could not confirm this request';
    $('wallet-submission-address').textContent = submission.address;
    $('wallet-submission-name').textContent = submission.tag;
    $('wallet-submission-note').textContent = watchingSubmitting ? 'You can close this window. The submitted address and name stay here while the request finishes.' : 'Check Activity before choosing a wallet again. A connection error can occur after a request is accepted.';
  }
  $('wallet-choose-again').disabled = watchingSubmitting;
  $('wallet-manual-mode').setAttribute('aria-pressed', String(!browser));
  $('wallet-browser-mode').setAttribute('aria-pressed', String(browser));
  $('wallet-browser-panel').hidden = !!submission || !browser;
  $('wallet-dialog-title').textContent = submission ? 'Watching wallet request' : browser && current.selected ? 'Review your Watching wallet' : 'Add a Watching wallet';
  $('wallet-dialog').classList.toggle('is-review', !!submission || browser && !!current.selected);
  $('wallet-intro').hidden = !!submission || browser && !!current.selected;
  $('wallet-address-field').hidden = browser;
  $('wallet-session-note').hidden = !!current.selected;
  $('wallet-connection-status').hidden = !!current.selected;
  $('wallet-demo-note').hidden = state?.demo !== true;
  $('wallet-registration-fields').hidden = !!submission || browser && !current.selected;
  $('new-wallet-address').readOnly = browser;
  for (const id of ['wallet-manual-mode','wallet-browser-mode']) $(id).disabled = watchingSubmitting;
  for (const id of ['new-wallet-address','new-wallet-tag']) $(id).disabled = watchingSubmitting || browser && !current.selected;
  if (browser) $('new-wallet-address').value = current.selected || '';
  const selectedProvider = current.providers.find(p => p.id === current.providerId);
  $('wallet-providers-title').textContent = current.accounts.length ? 'Connected with '+selectedProvider.name : 'Choose a browser wallet';
  $('wallet-providers').hidden = current.accounts.length > 0;
  $('wallet-provider-note').hidden = current.accounts.length > 0;
  $('wallet-change-provider').hidden = !current.accounts.length;
  $('wallet-change-provider').disabled = watchingSubmitting;
  $('wallet-change-account').hidden = !current.selected;
  $('wallet-change-account').disabled = watchingSubmitting;
  const sessionButton = $('wallet-session');
  $('wallet-session-panel').hidden = !submission && !selectedProvider;
  sessionButton.textContent = submission ? watchingSubmitting ? 'Wallet registration pending' : 'Wallet request details' : current.status === 'requesting' ? 'Wallet request pending' : 'Browser wallet session';
  $('wallet-session-name').textContent = selectedProvider?.name || '';
  // Do not rebuild focusable lists on every poll or name input.
  const providerSignature = JSON.stringify([current.providers, current.providerId, current.status === 'requesting', permitted, watchingSubmitting]);
  if ($('wallet-providers').dataset.signature !== providerSignature) {
    $('wallet-providers').dataset.signature = providerSignature;
    replaceWatchingChoices($('wallet-providers'), current.providers.map(provider => {
      const choice = walletChoice(provider.name, provider.rdns, provider.icon, () => {
        if (watchingCanAct() && !watchingSubmitting) watchingConnection.connect(provider.id);
      }, provider.id === current.providerId);
      choice.setAttribute('aria-label', 'Connect to '+provider.name);
      choice.disabled = !permitted || watchingSubmitting || (provider.id === current.providerId && current.status === 'requesting');
      return choice;
    }));
  }
  $('wallet-no-providers').hidden = current.providers.length > 0;
  $('wallet-connection-status').textContent = current.message;
  $('wallet-chain-context').hidden = !current.chainId;
  $('wallet-chain-context').textContent = 'Wallet network: '+(current.chainId || '')+'. Research uses the saved network coverage.';
  $('wallet-disconnect').hidden = !current.providerId;
  $('wallet-disconnect').textContent = current.status === 'requesting' ? 'Cancel request' : 'Disconnect from Kira';
  $('wallet-disconnect').disabled = watchingSubmitting;
  const accountSignature = JSON.stringify([current.accounts, current.selected, watchingSubmitting]);
  if ($('wallet-accounts').dataset.signature !== accountSignature) {
    $('wallet-accounts').dataset.signature = accountSignature;
    replaceWatchingChoices($('wallet-accounts'), current.accounts.map((address, index) => {
      const choice = walletChoice('Account '+(index+1), address, null, () => {
        if (watchingConnection.select(address)) $('new-wallet-tag').focus();
      }, address === current.selected);
      choice.classList.add('wallet-account'); choice.setAttribute('aria-label', 'Select account '+address);
      choice.disabled = watchingSubmitting; return choice;
    }));
  }
  $('wallet-accounts-section').hidden = !current.accounts.length || !!current.selected;
  const address = $('new-wallet-address').value, tag = $('new-wallet-tag').value;
  const valid = KiraWatching.addressPattern.test(address) && tag.trim().length > 0 && tag.length <= 200 &&
    (!browser || current.status === 'selected' && address === current.selected);
  $('wallet-preview').hidden = !valid;
  $('wallet-preview-address').textContent = address;
  $('wallet-preview-name').textContent = tag;
  const existing = state?.wallets.find(wallet => wallet.key === address.toLowerCase());
  $('wallet-existing').hidden = !valid || !existing;
  $('wallet-existing-link').href = '#/wallet/'+address.toLowerCase();
  $('wallet-register').disabled = !!submission || !permitted || !valid || !!existing;
  $('wallet-register').textContent = watchingSubmitting ? 'Saving wallet…' : 'Add and research';
  if (browser && $('wallet-dialog').open && watchingLastStatus === 'requesting' && current.status === 'accounts')
    $('wallet-accounts').querySelector('button')?.focus();
  watchingLastStatus = current.status;
}
function watchingRegistrationInput() {
  if (!watchingCanAct()) throw new Error('A personal local control session is required to add a wallet.');
  const address = $('new-wallet-address').value, tag = $('new-wallet-tag').value;
  const input = watchingMode === 'browser' ? watchingConnection.registration(tag) : {address, tag};
  if (input.address !== address || !KiraWatching.addressPattern.test(address) || !tag.trim() || tag.length > 200)
    throw new Error('Check the public address and wallet name before adding this wallet.');
  if (state?.wallets.some(wallet => wallet.key === address.toLowerCase()))
    throw new Error('This Watching wallet is already saved. Open it below to keep its current names.');
  return input;
}
$('wallet-manual-mode').addEventListener('click', () => setWatchingMode('manual'));
$('wallet-browser-mode').addEventListener('click', () => setWatchingMode('browser'));
$('wallet-disconnect').addEventListener('click', () => {
  if (watchingConnection.snapshot().status === 'requesting') watchingConnection.clearSelection();
  else watchingConnection.disconnect();
});
$('wallet-change-provider').addEventListener('click', () => watchingConnection.disconnect('Choose a browser wallet.'));
$('wallet-change-account').addEventListener('click', () => {
  watchingConnection.clearSelection(); $('wallet-accounts').querySelector('button')?.focus();
});
$('wallet-session').addEventListener('click', () => {
  if (!localSession?.controls) return;
  if (!watchingSubmission) setWatchingMode('browser');
  renderWatching(); $('wallet-dialog').showModal();
});
$('wallet-submission-activity').addEventListener('click', () => {
  $('wallet-dialog').close(); navigate('#/activity');
});
$('wallet-choose-again').addEventListener('click', () => {
  if (watchingSubmitting) return;
  watchingSubmission = null; $('wallet-form-error').textContent = '';
  watchingConnection.clearSelection(); renderWatching();
  if (watchingMode === 'browser') $('wallet-accounts').querySelector('button')?.focus();
  else $('new-wallet-address').focus();
});
for (const id of ['new-wallet-address','new-wallet-tag']) $(id).addEventListener('input', renderWatching);
$('wallet-dialog').addEventListener('close', () => watchingConnection.clearSelection());
$('wallet-existing-link').addEventListener('click', () => $('wallet-dialog').close());
renderWatching();
