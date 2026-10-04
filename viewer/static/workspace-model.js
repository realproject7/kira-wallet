'use strict';
(function (root) {
  const pageSize = 50;
  function catalog(tokens, filters = {}) {
    const search = (filters.search || '').trim().toLowerCase();
    const rows = tokens.filter(t => (filters.testnets || t.environment !== 'testnet')
      && (!filters.network || filters.network === 'all' || String(t.chain_id) === String(filters.network))
      && (filters.pricing !== 'priced' || (t.value_usd != null && !t.unpriced_count))
      && (filters.pricing !== 'unpriced' || t.value_usd == null || t.unpriced_count > 0)
      && (!search || [t.symbol, t.name, t.address || 'native'].some(v => String(v || '').toLowerCase().includes(search))));
    const order = filters.sort || 'value';
    rows.sort((a, b) => (order === 'name' ? String(a.name || a.symbol).localeCompare(String(b.name || b.symbol))
      : order === 'wallets' ? b.wallet_count - a.wallet_count
      : (b.value_usd ?? -Infinity) - (a.value_usd ?? -Infinity)) || String(a.id).localeCompare(String(b.id)));
    const pages = Math.max(1, Math.ceil(rows.length / pageSize));
    const page = Math.min(Math.max(1, filters.page || 1), pages);
    return { rows: rows.slice((page - 1) * pageSize, page * pageSize), count: rows.length, page, pages };
  }
  const active = job => ['queued', 'running'].includes(job.state);
  function jobPresentation(job, now = Date.now(), connected = true) {
    const labels = { queued: 'Queued', running: 'Running', succeeded: 'Completed', partial: 'Saved with gaps', interrupted: 'Interrupted', failed: 'Failed', cancelled: 'Stopped' };
    const start = job.state === 'queued' ? job.updated_at || job.created_at : job.started_at || job.created_at;
    const end = active(job) ? now : Date.parse(job.updated_at);
    const elapsed = Math.max(0, Math.floor((end - Date.parse(start)) / 1000));
    const last = job.events?.at(-1)?.observed_at || job.updated_at;
    const quiet = job.state === 'running' && now - Date.parse(last) > 60000;
    return {
      label: job.cancel_requested && active(job) ? 'Stopping' : labels[job.state] || 'Unknown',
      active: active(job), spinner: connected && job.state === 'running', quiet,
      elapsed: Number.isFinite(elapsed) ? elapsed : null,
      timerLabel: job.state === 'queued' ? 'Waiting' : job.started_at ? 'Elapsed' : 'Since request',
      freshness: !connected ? 'Connection lost. Last recorded state shown.' : quiet ? 'Awaiting a new stage update. Still marked running.' : '',
    };
  }
  function duration(seconds) {
    if (seconds == null) return 'Unknown';
    const h = Math.floor(seconds / 3600), m = Math.floor(seconds % 3600 / 60), s = seconds % 60;
    return (h ? h + 'h ' : '') + m + 'm ' + s + 's';
  }
  const api = { catalog, pageSize, active, jobPresentation, duration };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else root.KiraView = api;
})(typeof globalThis !== 'undefined' ? globalThis : this);
