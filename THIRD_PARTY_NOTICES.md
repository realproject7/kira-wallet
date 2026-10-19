# Third-party reference material

Kira's original code and character assets are provided under the root MIT
license. Third-party reference files retain their original terms. The root
license does not relicense them.

- `sources/mintclub-multitoken.sol` retains its `BUSL-1.1` SPDX identifier.
  It is a research reference, not a contract deployed by Kira.
- `sources/uniswap-state-view.sol` retains its MIT SPDX identifier.
- Mint Club ABI and contract metadata are research references to
  [Mint Club](https://github.com/Steemhunt/mint.club-v2-contract).
- Installed dependencies retain their package licenses. Remote token and chain
  artwork is referenced from its provider; the app does not claim ownership.
- Native coin prices and artwork reference [CoinGecko market metadata](https://docs.coingecko.com/reference/coins-markets).
  Provider availability and rate limits apply. Artwork belongs to the respective projects.

Open Wallet Standard Node SDK (`@open-wallet-standard/core` 1.4.3) and its
optional platform bindings are distributed under MIT by their upstream owner.
The SDK is an optional dependency used for human-submitted encrypted wallet
creation and public account listing. See
[Open Wallet Standard](https://github.com/open-wallet-standard/core).

The official Open Wallet Standard wordmark in `viewer/static/ows-logo.svg` and
`site/assets/ows-logo.svg` is copied unchanged from
[openwallet.sh](https://openwallet.sh/footer-logo.svg). CSS displays its original
white artwork in black on light backgrounds. The mark belongs to its owner and
identifies the OWS wallet-creation integration without implying endorsement.
Its retrieval date and source digest are in `site/assets/ows-artwork-source.json`.

CASHCAT, BLAST and USDB artwork in the public reconstructed demo comes from lpTOKEN.fun token metadata, DEX Screener and CoinGecko. Token marks belong to their respective owners and identify the assets without implying affiliation or endorsement. The source URLs and chain-specific contract identities are recorded in `site/assets/token-artwork-sources.json`.

The factual token inventory in `sources/known-tokens.json` includes selected
chain/contract identities from Uniswap default-token-list at commit
583cb696cc15778536fe0ddd416de5bd81be2023. The upstream references retain
GPL-3.0 terms in `sources/TOKEN_LIST_LICENSE.txt`. Per-contract provenance is
recorded in the catalog. No upstream executable code or artwork is included.


Free token discovery uses [Etherscan keyless MCP](https://docs.etherscan.io/build-with-ai/mcp)
and [Routescan](https://routescan.io/docs). Data is provided by those services,
subject to their availability and usage limits. Their data does not establish
token safety, current balance, value or an exhaustive inventory. No service SDK
or credential is distributed. Selected new known identities use issuer documents,
PancakeSwap integration references and freshly verified on-chain metadata; their
per-contract provenance is in the catalog.

## Alchemy setup illustration

`viewer/static/alchemy-create-app.png` is an unmodified example screenshot from Alchemy’s public API key walkthrough, used to explain app setup. Source: https://www.alchemy.com/docs/create-an-api-key . The image contains no Kira operator account or credential. Alchemy retains rights to its interface and illustration.

## Market platform marks

The local market cards identify their sources using the official marks retrieved
on October 19, 2026: [Mint Club app icon](https://mint.club/apple-touch-icon.png),
[Uniswap logo](https://github.com/Uniswap/interface/blob/main/packages/ui/src/assets/icons/uniswap-logo.svg),
and [Aerodrome favicon](https://aerodrome.finance/svg/AERO/favicon.svg).
These marks identify external services and remain their respective owners' marks.
Kira does not claim affiliation or endorsement. The original files are served
locally from `viewer/static/venues/`.

## Explorer mark

The Etherscan icon in `viewer/static/explorers/` identifies links to Etherscan.
It was retrieved unchanged on October 19, 2026 from
[Etherscan documentation](https://docs.etherscan.io/mintlify-assets/_mintlify/favicons/etherscan/PMbbZQeU1A_1WqNP/_generated/favicon/android-chrome-192x192.png).
The mark belongs to its owner and does not imply affiliation or endorsement.
