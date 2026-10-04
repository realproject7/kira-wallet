'use strict';
(function(root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  else root.KiraWatching = api;
})(typeof window === 'undefined' ? globalThis : window, function() {
  const addressPattern = /^0x[0-9a-fA-F]{40}$/;
  const invalidAccountsMessage = 'The wallet did not return valid EVM accounts. Try again or enter an address.';
  const uuidPattern = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
  function safeIcon(value) {
    // No remote images or inline SVG. The browser renders data icons in img.
    return typeof value === 'string' && value.length <= 32768 &&
      /^data:image\/(?:png|jpeg|webp|svg\+xml)(?:;base64)?,/i.test(value) ? value : null;
  }
  function displayText(value, fallback, limit = 80) {
    return typeof value === 'string' && value.trim() ?
      value.replace(/[\u0000-\u001f\u007f-\u009f\u202a-\u202e\u2066-\u2069]/g, '').slice(0, limit) || fallback : fallback;
  }
  function accounts(value) {
    if (!Array.isArray(value) || value.length > 100 || value.some(a => typeof a !== 'string' || !addressPattern.test(a)))
      throw new Error(invalidAccountsMessage);
    const seen = new Set();
    return value.filter(a => { const key = a.toLowerCase(); if (seen.has(key)) return false; seen.add(key); return true; });
  }
  function errorMessage(error) {
    let code;
    try { code = error?.code; if (!['number','string'].includes(typeof code)) code = undefined; } catch { /* Ignore hostile provider error objects. */ }
    const messages = {4001:'Account access was declined. Choose a wallet to try again.',
      4100:'Account access is not authorized. Open your wallet and try again.',
      4200:'This wallet does not support account access. Enter a public address instead.',
      4900:'The wallet is disconnected. Open it and try again.',
      4901:'The wallet network is unavailable. Open it or enter a public address.',
      '-32002':'An account request is already open in your wallet. Finish it or cancel here.'};
    return Object.hasOwn(messages, code) ? messages[code] :
      'Account access could not be completed. Open your wallet and try again, or enter an address.';
  }
  function create(onChange = () => {}) {
    const providers = new Map();
    let generation = 0, session = null;
    let state = {status:'idle', providerId:null, accounts:[], selected:null, chainId:null, message:''};
    const snapshot = () => ({...state, accounts:[...state.accounts], providers:[...providers.values()].map(p => ({id:p.id, name:p.name, icon:p.icon, rdns:p.rdns}))});
    const publish = () => onChange(snapshot());
    function detach() {
      const old = session; session = null;
      if (old) for (const [event, listener] of old.listeners) {
        try { old.provider.removeListener(event, listener); } catch { /* The generation guard also invalidates callbacks. */ }
      }
    }
    function disconnect(message = 'Kira disconnected. Saved Watching wallets stay in your notebook.') {
      generation++; detach();
      state = {status:'disconnected', providerId:null, accounts:[], selected:null, chainId:null, message};
      publish();
    }
    function announce(detail) {
      try {
        const {info, provider} = detail || {};
        if (!info || !uuidPattern.test(info.uuid) || !provider || typeof provider.request !== 'function' ||
            typeof provider.on !== 'function' || typeof provider.removeListener !== 'function' || providers.size >= 48 ||
            providers.has(info.uuid.toLowerCase()) || [...providers.values()].some(p => p.provider === provider)) return false;
        const entry = {id:info.uuid.toLowerCase(), provider, name:displayText(info.name,'Browser wallet'),
          rdns:displayText(info.rdns,'Unspecified provider',120), icon:safeIcon(info.icon)};
        providers.set(entry.id, entry); publish(); return true;
      } catch { return false; }
    }
    async function connect(id) {
      const entry = providers.get(id); if (!entry) return;
      generation++; detach(); const attempt = generation;
      state = {status:'requesting', providerId:id, accounts:[], selected:null, chainId:null,
        message:'Choose which accounts to share in your wallet. You can cancel here while it is open.'};
      const active = {provider:entry.provider, listeners:[]}; session = active;
      function listen(event, handler) {
        const listener = value => { if (session === active) handler(value); };
        // Record before calling untrusted on(), so partial installation is cleaned up.
        active.listeners.push([event,listener]); entry.provider.on(event,listener);
      }
      try {
        listen('accountsChanged', value => {
          generation++; state.selected = null;
          try {
            state.accounts = accounts(value);
            if (!state.accounts.length) { disconnect('No accounts are shared. Open your wallet or enter a public address.'); return; }
            state.status = 'accounts'; state.message = 'Shared accounts changed. Choose an account again before adding it.';
          } catch { state.accounts = []; state.status = 'error'; state.message = invalidAccountsMessage; }
          publish();
        });
        listen('chainChanged', value => {
          state.chainId = typeof value === 'string' && /^0x[0-9a-f]{1,16}$/i.test(value) ? value : null;
          publish();
        });
        listen('disconnect', () => disconnect('The wallet disconnected. Saved Watching wallets remain available.'));
        publish();
        if (generation !== attempt || session !== active) return;
        // Account access is the only provider request. Callers invoke this after a user choice.
        const result = await entry.provider.request({method:'eth_requestAccounts'});
        if (generation !== attempt || session !== active) return;
        const shared = accounts(result);
        if (!shared.length) { disconnect('No accounts are shared. Open your wallet or enter a public address.'); return; }
        state.accounts = shared; state.status = 'accounts'; state.message = 'Choose the public account to watch.'; publish();
      } catch (error) {
        if (generation !== attempt || session !== active) return;
        detach(); state.status = 'error'; state.providerId = null; state.accounts = []; state.selected = null;
        state.message = errorMessage(error); publish();
      }
    }
    function select(address) {
      const match = state.accounts.find(a => a.toLowerCase() === String(address).toLowerCase());
      if (!session || !match || !['accounts','selected'].includes(state.status)) return false;
      state.selected = match; state.status = 'selected'; state.message = 'Check the full address and wallet name below.'; publish(); return true;
    }
    function clearSelection() {
      if (state.status === 'requesting') { disconnect('Account request cancelled in Kira. The wallet may still show its request.'); return; }
      if (state.selected) { state.selected = null; state.status = 'accounts'; state.message = 'Choose the public account to watch.'; publish(); }
    }
    function registration(tag) {
      if (!session || state.status !== 'selected' || !state.accounts.includes(state.selected))
        throw new Error('Choose a current shared account before adding this wallet.');
      if (typeof tag !== 'string' || !tag.trim() || tag.length > 200) throw new Error('Enter a wallet name.');
      return {address:state.selected, tag};
    }
    return {announce, connect, select, disconnect, clearSelection, registration, snapshot};
  }
  function discover(target, connection) {
    const listener = event => connection.announce(event.detail);
    target.addEventListener('eip6963:announceProvider', listener);
    target.dispatchEvent(new Event('eip6963:requestProvider'));
    return () => target.removeEventListener('eip6963:announceProvider', listener);
  }
  return {create, discover, safeIcon, addressPattern};
});
