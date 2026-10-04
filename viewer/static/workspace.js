'use strict';
let catalogPage = 1;
let briefingMode = 'view';
let catalogTimer;
function catalogFilters() {
  return { search: $('all-token-search').value, network: $('all-token-network').value,
    pricing: $('all-token-pricing').value, sort: $('all-token-sort').value,
    testnets: $('all-token-testnets').checked, page: catalogPage };
}
function renderCatalog() {
  if (!state) return;
  const result = KiraView.catalog(state.details.tokens, catalogFilters());
  catalogPage = result.page;
  $('all-token-result').textContent = result.count + (result.count === 1 ? ' token · ' : ' tokens · ') + (result.count ? ((result.page - 1) * 50 + 1) + '–' + Math.min(result.page * 50, result.count) + ' shown' : 'none shown');
  $('tokens-page').textContent = result.page + ' / ' + result.pages;
  $('tokens-prev').disabled = result.page === 1;
  $('tokens-next').disabled = result.page === result.pages;
  $('all-token-empty').hidden = result.count > 0;
  $('all-token-body').innerHTML = result.rows.map(a => {
    const network = state.details.networks.find(n => n.id === a.chain_id);
    return `<tr><td><a class="token-name token-link" href="${tokenHref(a.id)}">${coinIcon(a)}<div class="coin-title"><div class="symbol">${escapeHTML(a.symbol)}</div><div class="token-description">${escapeHTML(network?.name || 'Chain ' + a.chain_id)}${a.environment === 'testnet' ? ' · Testnet' : ''}</div></div></a></td><td><span class="mobile-label">Total balance</span><span class="amount" title="${escapeHTML(a.balance)}">${quantity(a.balance)}</span></td><td><span class="mobile-label">Wallets</span>${a.wallet_count}</td><td><span class="token-value">${a.environment === 'testnet' ? 'Testnet' : money(a.value_usd)}</span>${a.unpriced_count ? '<div class="price-basis">' + a.unpriced_count + ' unpriced</div>' : ''}</td></tr>`;
  }).join('');
  bindImages();
}
function renderWorkspace() {
  if (!state) return;
  $('tokens-view').hidden = selectedView !== 'tokens';
  $('activity-view').hidden = selectedView !== 'activity';
  document.querySelectorAll('[data-view]').forEach(link => {
    const current = link.dataset.view === selectedView || (link.dataset.view === 'home' && ['wallet', 'token', 'network'].includes(selectedView));
    if (current) link.setAttribute('aria-current', 'page'); else link.removeAttribute('aria-current');
  });
  if (selectedView === 'home') $('brand-home').setAttribute('aria-current', 'page'); else $('brand-home').removeAttribute('aria-current');
  $('all-token-count').textContent = state.details.tokens.filter(t => t.environment !== 'testnet').length;
  if (selectedView === 'tokens') {
    renderBreadcrumb([{ label: 'Home', href: '#/home' }, { label: 'All tokens' }]);
    document.title = 'All tokens · Kira Wallet';
    const network = $('all-token-network').value;
    const recordedChains = new Set(state.details.tokens.map(t => t.chain_id));
    $('all-token-network').innerHTML = '<option value="all">All networks</option>' + state.details.networks.filter(n => recordedChains.has(n.id)).map(n => `<option value="${n.id}">${escapeHTML(n.name)}${n.environment === 'testnet' ? ' · Testnet' : ''}</option>`).join('');
    $('all-token-network').value = [...$('all-token-network').options].some(o => o.value === network) ? network : 'all';
    $('sync-label').textContent = 'Latest recorded holdings'; renderCatalog();
  } else if (selectedView === 'activity') {
    renderBreadcrumb([{ label: 'Home', href: '#/home' }, { label: 'Activity' }]);
    document.title = 'Activity · Kira Wallet'; $('sync-label').textContent = 'Local research history';
  }
  renderBriefing();
}
function renderBriefing() {
  if (!state) return;
  renderKiraNote();
  const active = typeof jobList !== 'undefined' && jobList.some(KiraView.active);
  const gaps = state.wallets.reduce((sum, w) => sum + w.chains.filter(c => c.environment === 'mainnet' && (!c.complete || !c.rpc_available)).length, 0);
  let art = 'welcome', caption = 'Your wallet assistant', note = 'Connect your AI to ask about your holdings.';
  if (active) { art = 'research'; caption = 'Research in progress'; note = 'Follow the recorded stages in Activity.'; }
  else if (gaps && briefingMode === 'coverage') { art = 'attention'; caption = 'Coverage needs attention'; note = 'Some holdings may still be missing.'; }
  else if (selectedView === 'activity') { art = 'review'; caption = 'Research history'; note = 'Review saved results and unfinished work.'; }
  else if (['token', 'network', 'tokens', 'wallet'].includes(selectedView)) { art = 'explain'; caption = 'Explore your holdings'; note = 'Balances, prices and coverage from saved research.'; }
  const config = typeof agentState !== 'undefined' ? agentState?.config : null;
  const thinking = typeof chatTurn !== 'undefined' && Boolean(chatTurn);
  if (thinking) { art = 'research'; caption = 'Preparing your answer'; }
  else if (config && !active && briefingMode !== 'coverage') { art = 'explain'; caption = 'Ask Kira about your wallets'; }
  if (config && (thinking || !active && briefingMode !== 'coverage')) note = config.scope === 'none' ? 'General chat · No wallet context shared' : config.scope === 'wallet' ? 'Chat uses one approved wallet' : 'Chat uses your approved portfolio';
  $('kira-panel').dataset.speaking = String(thinking);
  const src = art === 'welcome' ? '/kira.png' : '/kira-' + art + '.png';
  if ($('kira-scene-art').getAttribute('src') !== src) $('kira-scene-art').src = src;
  $('kira-scene-art').alt = { welcome: 'Kira holding her research notebook', research: 'Kira writing while researching', explain: 'Kira explaining a finding', review: 'Kira reviewing saved notes', attention: 'Kira carefully checking incomplete evidence' }[art];
  $('kira-mood').textContent = caption; $('kira-scene-note').textContent = note;
  $('kira-context').textContent = selectedView === 'wallet' ? currentWallet()?.name || 'Wallet' : selectedView === 'token' ? state.details.tokens.find(t => t.id === selectedToken)?.symbol || 'Token' : selectedView === 'network' ? state.details.networks.find(n => n.id === selectedNetwork)?.name || 'Network' : { home: 'Portfolio overview', tokens: 'All tokens', activity: 'Research activity' }[selectedView];
  if (briefingMode === 'coverage') {
    const selected = selectedView === 'wallet' ? [currentWallet()].filter(Boolean) : state.wallets;
    const missing = selected.flatMap(w => w.chains.filter(c => c.environment === 'mainnet' && (!c.complete || !c.rpc_available)).map(c => w.name + ' · ' + c.name + (!c.rpc_available ? ': RPC unavailable' : ': incomplete discovery')));
    $('kira-note-text').textContent = missing.length ? 'These recorded coverage gaps need a closer look: ' + missing.slice(0, 6).join('; ') + (missing.length > 6 ? '; and ' + (missing.length - 6) + ' more.' : '.') + ' Missing data does not mean zero holdings.' : 'No mainnet coverage gaps are flagged in this recorded view. This does not prove that every possible token has been discovered.';
  } else if (selectedView === 'tokens') {
    const tokens = state.details.tokens.filter(t => t.environment !== 'testnet');
    $('kira-note-text').textContent = `There are ${tokens.length} recorded mainnet tokens. ${tokens.filter(t => t.value_usd == null || t.unpriced_count > 0).length} have unpriced amounts. I keep tokens on different networks separate, even when their symbols match.`;
  } else if (selectedView === 'activity') {
    const running = typeof jobList === 'undefined' ? 0 : jobList.filter(KiraView.active).length;
    $('kira-note-text').textContent = running ? `${running} local research ${running === 1 ? 'job is' : 'jobs are'} in progress. The timeline shows the last recorded stage, elapsed time and freshness. A quiet stage is not proof that a worker stopped.` : 'There is no recorded job in progress. Completed work stays in the timeline, along with partial results, interruptions and failed attempts.';
  }
}
for (const id of ['all-token-network', 'all-token-pricing', 'all-token-sort', 'all-token-testnets']) $(id).addEventListener('change', () => { catalogPage = 1; renderCatalog(); });
$('all-token-search').addEventListener('input', () => { clearTimeout(catalogTimer); catalogTimer = setTimeout(() => { catalogPage = 1; renderCatalog(); }, 120); });
$('tokens-prev').addEventListener('click', () => { catalogPage--; renderCatalog(); });
$('tokens-next').addEventListener('click', () => { catalogPage++; renderCatalog(); });
function setWorkspacePane(pane) {
  document.querySelector('.workspace').dataset.pane = pane;
  document.querySelectorAll('.mobile-pane-control [data-pane]').forEach(button => button.setAttribute('aria-pressed', String(button.dataset.pane === pane)));
}
document.querySelectorAll('.mobile-pane-control [data-pane]').forEach(button => button.addEventListener('click', () => {
  setWorkspacePane(button.dataset.pane);
  if (button.dataset.pane === 'kira' && matchMedia('(max-width: 980px)').matches) {
    document.querySelector('.workspace').scrollIntoView({ block: 'start', behavior: 'instant' });
  }
}));
// Explicit navigation must reveal the selected evidence, including same-route clicks.
document.addEventListener('click', event => {
  if (event.target.closest('a[href^="#/"]')) setWorkspacePane('portfolio');
});
document.querySelectorAll('[data-brief]').forEach(button => button.addEventListener('click', () => {
  if (button.dataset.brief === 'coverage') { briefingMode = 'coverage'; renderBriefing(); }
  else if (button.dataset.brief === 'unpriced') { briefingMode = 'view'; $('all-token-pricing').value = 'unpriced'; catalogPage = 1; navigate('#/tokens'); renderCatalog(); }
  else { briefingMode = 'view'; navigate('#/activity'); }
  if (button.dataset.brief !== 'coverage') document.querySelector('.mobile-pane-control [data-pane="portfolio"]').click();
}));
window.addEventListener('hashchange', () => { briefingMode = 'view'; setWorkspacePane('portfolio'); renderWorkspace(); });
try { localStorage.removeItem('kira-draft'); } catch { /* Drafts are now memory-only. */ }
renderWorkspace();
