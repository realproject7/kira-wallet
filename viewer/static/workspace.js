'use strict';
let catalogPage = 1;
let catalogTimer;
function catalogFilters() {
  return { search: $('all-token-search').value, network: $('all-token-network').value,
    pricing: $('all-token-pricing').value, sort: $('all-token-sort').value,
    testnets: $('all-token-testnets').checked, page: catalogPage };
}
function catalogRow(a) {
  const network = state.details.networks.find(n => n.id === a.chain_id);
  return `<tr><td><a class="token-name token-link" href="${tokenHref(a.id)}">${coinIcon(a)}<div class="coin-title"><div class="symbol">${escapeHTML(a.symbol)}</div><div class="token-description">${escapeHTML(a.is_native ? 'Native asset' : a.name)}</div></div></a></td><td class="catalog-chain"><span class="mobile-label">Chain</span><a class="chain-link" href="${networkHref(a.chain_id)}">${escapeHTML(network?.name || 'Chain ' + a.chain_id)}</a>${a.environment === 'testnet' ? '<small>Testnet</small>' : ''}</td><td><span class="mobile-label">Total balance</span><span class="amount" title="${escapeHTML(a.balance)}">${quantity(a.balance)}</span></td><td><span class="mobile-label">Wallets</span>${a.wallet_count}</td><td><span class="token-value">${a.environment === 'testnet' ? 'Testnet' : money(a.value_usd)}</span>${a.unpriced_count ? '<div class="price-basis">' + a.unpriced_count + ' unpriced</div>' : ''}</td></tr>`;
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
  $('all-token-body').innerHTML = result.rows.map(catalogRow).join('');
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
    $('all-token-network').innerHTML = '<option value="all">All chains</option>' + state.details.networks.filter(n => recordedChains.has(n.id)).map(n => `<option value="${n.id}">${escapeHTML(n.name)}${n.environment === 'testnet' ? ' · Testnet' : ''}</option>`).join('');
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
  if (typeof renderResearchChat === 'function') renderResearchChat();
}
function resetRouteFilters() {
  for (const [id,value] of Object.entries({'all-token-network':'all','all-token-pricing':'all','all-token-sort':'value','all-token-search':'','job-filter':'all'})) $(id).value=value;
  $('all-token-testnets').checked=false;catalogPage=1;
  if(typeof jobsPage!=='undefined')jobsPage=1;
  if(typeof KiraSelect!=='undefined')KiraSelect.refresh();
}
for (const id of ['all-token-network', 'all-token-pricing', 'all-token-sort', 'all-token-testnets']) $(id).addEventListener('change', () => { catalogPage = 1; renderCatalog(); });
$('all-token-search').addEventListener('input', () => { clearTimeout(catalogTimer); catalogTimer = setTimeout(() => { catalogPage = 1; renderCatalog(); }, 120); });
$('tokens-prev').addEventListener('click', () => { catalogPage--; renderCatalog(); });
$('tokens-next').addEventListener('click', () => { catalogPage++; renderCatalog(); });
$('home-view-all').addEventListener('click', () => {
  $('all-token-search').value = '';
  $('all-token-network').value = 'all';
  $('all-token-pricing').value = 'all';
  $('all-token-sort').value = 'value';
  $('all-token-testnets').checked = false;
  catalogPage = 1;
});
function setWorkspacePane(pane) {
  document.querySelector('.workspace').dataset.pane = pane;
  document.body.classList.toggle('chat-pane',pane==='kira');
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
window.addEventListener('hashchange', () => { setWorkspacePane('portfolio'); renderWorkspace(); });
try { localStorage.removeItem('kira-draft'); } catch { /* Drafts are now memory-only. */ }
renderWorkspace();
