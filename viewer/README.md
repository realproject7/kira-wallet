# Wallet research viewer

A read-only local browser view of the registered wallets and their latest analysis. The Kira interface uses warm ivory surfaces, ink text, a restrained violet accent, native system fonts and an adult webtoon research companion. Home introduces Kira; each view includes a factual note computed from the saved research, with an expandable explanation of valuation limits. The character does not imply a connected model chat. It has no wallet connection, edit action, or trading action.

## Open the viewer

Run from the project directory:

```sh
python3 viewer/start.py
```

Open [Wallets](http://127.0.0.1:8765). The launcher keeps the server running in the background and reuses it if already running. For a foreground server use `python3 viewer/server.py --port 8765`. The server binds only to this computer. It uses Python's standard library and needs no frontend build or package installation.

Home is the first sidebar item and the default view. It shows the estimated total value, registered wallet count, networks with holdings, position count, wallet shares, network allocations, and the five largest holdings. Click a wallet card or sidebar item to open its holdings. The selected view and value filter stay in the browser.

Click a token name or a largest-holding card to open its token overview. It sums the recorded balance and known value for that exact chain ID and contract, then shows every registered wallet, recorded prices, analysis times, market links, curve backing and recorded burn refunds where available. An absent holding remains a missing record rather than a fabricated zero. The price range can reflect different observation times. Shared curve backing is never added once per wallet.

Click a network name in Home or a wallet's chain heading to open its network overview. It shows aggregate known value, unique assets, positions, holding wallets, each wallet's coverage and allocation, and the combined token list. Search tokens by name, symbol or contract. The dollar filters apply to the combined token value across wallets; summary totals remain unfiltered. The network selector includes all configured mainnets and testnets, including networks without recorded holdings.

Detail views have local hash URLs such as `/#/network/8453` and `/#/token/8453/<contract>`. Direct links, browser Back/Forward and reload preserve the selected entity. Research file updates retain the selected detail view. These figures use existing snapshots; opening a detail does not refresh providers.

One compact breadcrumb in the topbar provides `Home / wallet`, `Home / network`, or `Home / network / token` navigation. Page headings follow directly below it. Mobile hides the redundant topbar research summary; observation times remain in the page content.

## Network images

Mint Club's current network selector uses static artwork under `https://mint.club/assets/networks/`, not a chain-logo API. Base uses `base.svg`; other visible mainnets use PNG files such as `ethereum@2x.png`. The mapping in `chain_images.py` was checked against the live selector and public frontend bundles on 2026-10-03. All 16 visible mainnet files return image content. Testnets inherit parent artwork, matching Mint Club's Sepolia treatment. Ham and Over files referenced by an internal bundle currently return HTML, so they retain the letter fallback. Image failures preserve the fallback without affecting research data. Images use the existing approved Mint Club origin.

Holdings are grouped by chain and sorted by estimated USD value. Use All, ≥ $5, or ≥ $10 to filter by the value of the whole held position. The default is ≥ $10. Unpriced positions appear in All and do not qualify for dollar filters.

Home sums direct mainnet positions across wallets. A position is one asset in one wallet. Unique assets use chain ID and contract address, so the same asset held by two wallets counts once as a unique asset and twice as positions. Unknown network values show a dash. Testnets, curve backing, and pool TVL are excluded from the total. Allocation percentages refer to priced value, and the footer shows the range of recorded price update times.

Market links open Mint Club or the observed DEX pool evidence. A DEX link can lead to DEX Screener or the pool contract explorer when that pool is absent from the market index. Research notes link to the complete recorded report.

## Add an analysis or refresh it

The source of truth is `wallets.json`. Each wallet's `latest_snapshot.result` points to a `results.json` with the recorded schema, and its `latest_snapshot.directory` points to that snapshot folder. Keep wallet addresses and operator tags in the registry. The viewer reads all registered wallets, with no hardcoded wallet list.

Save a new dated analysis and update that wallet's latest snapshot pointer. The open viewer checks the files every five seconds and updates the sidebar and holdings without a page reload. It keeps the selected wallet and filters. Files should be written through a temporary file and atomic rename. A partial JSON write briefly keeps the last valid response.

The agent can refresh market prices for existing analysed holdings:

```sh
python3 viewer/refresh_prices.py --wallet '<registered address or tag>'
```

Omit `--wallet` to refresh all analysed wallets. This reads public DEX prices and current Mint Club curve prices through RPC, then atomically writes `market-prices.json` next to each snapshot. The viewer updates automatically. This command refreshes prices only. A full holdings refresh requires a new wallet analysis. The analysis date and price date are shown separately.

The browser never contacts an RPC or price provider and never reads the RPC credentials. Token image requests use the approved Mint Club and Hunt image endpoints and image origins returned by Mint Club. Only the agent's refresh process uses the existing authorized RPC configuration. The viewer server exposes only its three static assets, favicon, derived data, and registered reports. It has no write endpoint.

## Token images

Mint Club holdings use `/api/tokens/logo?chainId=...&address=...`. Reserve assets use the image catalog collected from `/api/reserve-tokens/list`, `/api/reserve-tokens/stats`, `/api/reserve-tokens/popular`, and the `reserveToken` metadata in `/api/tokens/details/{chainId}/{address}`. Legacy 1inch URLs currently return HTTP 403 and are resolved through the Hunt token-image endpoint for the same chain and contract. Native assets retain their own symbol icons rather than adopting a wrapped token's logo.

The wallet analysis pipeline collects image metadata automatically and reuses successful metadata for 24 hours. The agent can refresh it independently:

```sh
python3 viewer/token_images.py --force
```

Add `--wallet <registered address or exact tag>` to collect details for one wallet. The shared catalog is `cache/token-images.json`; it contains public metadata and does not alter any research snapshot. Images load lazily with a fixed size and no referrer. Missing or failed images fall back to the existing symbol. API failures preserve previous logos and do not stop a wallet analysis.

## Valuation rules

Use a valid DEX market price when available. Mint Club positions without a DEX price use the current curve spot price multiplied by the reserve asset's USD price. Nested CHICKEN curves resolve through the price of CHICKEN. The resulting value is a spot estimate, not a full sell or burn quote. Curve reserves are never added to the wallet's position values.

Unknown prices and unfunded curves remain unpriced. A source-reported pool whose own token accounts for more than 98 percent of its reported TVL is excluded as a USD price reference because the quote side provides little support for that price. This is a conservative valuation rule, not a determination about the token. Testnet positions are excluded from dollar totals. Missing chain coverage remains incomplete rather than becoming a zero balance.

## Verification

```sh
python3 -m unittest discover -s viewer -p 'test_*.py'
node --check viewer/static/app.js
```

The checks cover reserve price conversion, unknown prices, testnet exclusion, multi-wallet aggregation, shared asset identities, image catalog updates, failed image metadata refreshes, approved image origins, price and registry changes, path boundaries, conditional HTTP responses, and blocked write endpoints. Desktop and mobile layout, Home navigation, images and the filters are also checked in the browser.

Detail checks also cover exact decimal balance aggregation, shared curve backing exclusion, same-contract separation across networks, and missing or unresearched wallet coverage. The token and network pages are checked at desktop, 390 px and 320 px widths.

## Design references

[lpTOKEN.fun](https://lptoken.fun) informed the restrained presentation. [Apple](https://www.apple.com) informed typography and spacing. [Selected Lazyweb references](https://www.lazyweb.com/agentic-search/5eed25a9-311b-4741-a717-8e16fb777b35) informed the sidebar and holdings hierarchy.

[Home dashboard references](https://www.lazyweb.com/agentic-search/1d5075aa-195b-4d2f-8ce9-e1d7bf8ac03e) informed the aggregate balance, account cards, and sidebar hierarchy. Image endpoints are documented in the [Mint Club API](https://sdk.mint.club/docs/api).

[Compact navigation references](https://www.lazyweb.com/agentic-search/b67b3f2d-9998-4da7-a42c-871ef9c88c82) informed the single topbar breadcrumb and reduced header spacing.

## Planned Kira Wallet product

The [product specification](../docs/KIRA_PRODUCT_SPEC.md) and [implementation plan](../docs/KIRA_IMPLEMENTATION_PLAN.md) describe portable public/custom RPC configuration, Kira's identity and original character, the future workspace redesign, direct job controls and optional agent chat. These are planned milestones beyond the current read-only viewer.

## Opt-in local controls

The legacy viewer start remains read-only. `kira start --controls` enables the
version 1 job API with same-origin Host/Origin checks and a rotating local
session. It offers research, exact names, connection references, cancel/resume
and saved analysis comparison. No signing or trading is exposed. Jobs continue
independently of the viewer and a disconnected model. The synthetic demo blocks
provider research. See [the job contract](../docs/JOB_CONTRACT.md) and
[continuation report](../docs/KIRA_JOBS_BUILD_REPORT.md).
