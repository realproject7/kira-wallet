# Wallet research operating instructions

Read `session.json`, `wallets.json`, and `networks.json` before research. Only register wallet addresses supplied by the operator. Preserve operator tags and previous snapshots. Coin identity is chain ID plus contract address.

For an operator-supplied new wallet and tag, use the wallet.py add command with the exact address and --tag value. It runs discovery, chain reads, Mint Club registry scans, curve and DEX research, snapshot creation and viewer publication. Use wallet.py refresh with a registered address or exact tag for a holdings refresh. Do not copy a previous wallet's balances into a new wallet. If a run fails, use its printed snapshot path with --resume and finish the authorized analysis. Read README.md for the pipeline contract and coverage limits.

The browser app in `viewer/` displays saved research and provides human wallet, name, connection-reference, refresh and job controls. CLI, optional MCP and browser operations share the local application service. The external agent host owns conversation, models and approvals. Keep model runtimes out of Kira. Opening a page or querying saved records must never start provider research. Holdings and price refreshes require an explicit human or agent request.

For a new or refreshed analysis, save a new snapshot with the existing `results.json` schema and update `wallets.json` to point to it. Include timestamps, balances, prices, source links, chain coverage, and nulls for missing information. The viewer uses published-data revisions, bounded pages and active-job updates. Hidden tabs stop periodic API reads. Write updates atomically when possible. Do not overwrite prior analyses.

Price-only refresh: `python3 viewer/refresh_prices.py --wallet <registered address or tag>`. Full holdings refresh requires new research. Run `python3 viewer/server.py --port 8765` for the local viewer. Keep the server loopback-only. Never expose the credential file or credentialed RPC URLs in data served to the browser.

Verification for viewer changes: `python3 -m unittest discover -s viewer -p 'test_*.py'` and `node --check viewer/static/app.js`. Check responsive layout and meaningful interactions in the browser after UI changes. Financial figures must preserve unknown values and exclude testnets and unsupported price references from USD totals.
