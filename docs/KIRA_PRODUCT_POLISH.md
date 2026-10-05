# Kira product polish

The wallet page now has distinct icon actions, bounded market groups and a
full-height Kira dock. The floating composer has an opaque bottom surface and a
short gradient above it. The heading is "Manage your wallets. With your own AI."
Page title, social metadata, package description and sidebar follow that message.
Copy describes current research and local OWS creation without claiming chat can
sign or trade.

## Examples and artwork

The 42-second public showcase and its accessible transcript cover idle-token
questions, Blast exposure across wallets and an LP concept preview. Examples
include quantities, unit prices, spot values, venues, pairs and sale-output
assumptions. Public market references identify contracts and pools. Balances,
activity and financial figures are illustrative. Missing execution quotes remain
unknown; inactivity requires transfer-history evidence. LP discovery remains a
concept preview.

lpTOKEN.fun uses its market catalog's chain-specific `token.imageUrl`, including
DEX Screener CDN artwork. CASHCAT is the Robinhood contract in that catalog.
BLAST and USDB identities were checked against DEX Screener and CoinGecko.
Runtime metadata matching uses chain ID plus contract, approved HTTPS origins,
24-hour successful and empty-lookup caching, and retained images on failures.
The browser never performs new RPC or metadata research. Artwork provenance and
hashes are in `site/assets/token-artwork-sources.json`.

Research references:

- [Lazyweb portfolio and asset-list evidence](https://www.lazyweb.com/agentic-search/0f70ddb4-6888-4697-9908-5be6dad5e6a7)
- [lpTOKEN public catalog](https://lptoken.fun/api/markets?sort=volume&limit=100)
- [Blast markets](https://dexscreener.com/blast)
- [USDB metadata](https://api.coingecko.com/api/v3/coins/usdb)
- [BLAST metadata](https://api.coingecko.com/api/v3/coins/blast)

The operator's supplied Codex screenshot informed composer and dock geometry.

## Product acceptance, 2026-10-05

Tests used a disposable workspace with synthetic addresses and snapshots. Research
admissions were observable, but provider workers were disabled. The fixture's
HTML entry allows automation document navigation; production API, Origin and
session guards are unchanged. No operator records enter the fixture.

| Action | Observed result |
| --- | --- |
| Open wallet and token detail | Exact balance and unknown-value semantics preserved; pair artwork and venue visible |
| Expand four recorded pools | Two initially visible; remaining two available; detail shows addresses, time and liquidity |
| Ask an advanced question | Draft stays editable; Markdown table renders; absent sale output is unknown |
| Expand/collapse chat | Thread uses available height; composer remains at the bottom |
| Add a synthetic public address | Exact address/name submitted; a queued wallet job appears in Activity and chat |
| Open Create wallet | Local OWS form is visible, including human passphrase fields |
| Create in disposable OWS vault through local API | Actual pinned SDK created an encrypted wallet, linked only public EVM identity and admitted research; identical retry reused wallet and job |
| Installed Codex CLI with synthetic context | Described quantity, price, pool, unknown inactivity and sale proceeds; price-refresh tool created a real queued job and did not claim completion |
| 390 × 844 mobile | Portfolio/Kira switch and composer verified; no horizontal overflow in chat |
| Public video | Playback and pause work; full scenario transcript is accessible |

The real operator vault, extension approval and human passphrase flow were not
exercised. No signing or transaction was performed. The new fixture script can
repeat UI tests or run an installed supported CLI with synthetic context only.

## Findings fixed during acceptance and review

- A composer stacking rule exposed the screen-reader-only draft status and
  increased bottom space. It now excludes hidden status and hidden top controls.
- Duplicate pool evidence used balance time instead of market time. Newest market
  time now selects the shared route; missing time cannot replace known evidence.
- Full pool detail could exceed the chat limit even for one wallet. Shared market
  bytes are bounded, omitted records are counted, and `token_read` retrieves the
  selected token within the same approved scope. Holdings remain intact.
- Malformed paired-token symbols could stop rendering. Projection normalizes them
  and the actual icon renderer also handles invalid symbols.
- Repeated empty artwork lookups caused redundant requests. Successful empty
  results now share the 24-hour cache. A verified User-Agent permits public DEX
  metadata responses without forwarding credentials.
- Native chat initially suggested a separate wallet app for creation. Kira now
  points to its own sidebar Create wallet form and keeps passphrases out of chat.

## Verification

`npm test` passed 134 Python tests plus Node agent, holdings, Markdown, RPC, OWS,
workspace and watching suites. Clean installed-package acceptance passed,
including an encrypted disposable OWS wallet. Screenshots in `docs/screenshots/`
contain synthetic records only. Independent review findings were implemented
with regression tests; final review and packaging receipts accompany the PR.

npm latest was 0.1.0 and 0.1.1 returned E404. Installation guidance preserves that
distinction. Registry publication remains operator-only.
