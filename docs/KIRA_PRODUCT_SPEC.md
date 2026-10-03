# Kira Wallet product specification

Kira Wallet will be an open-source application for researching holdings across registered wallets. Users will manage wallets through a local web interface with buttons and an optional Kira assistant. The CLI will install and launch the application and expose the same analysis tools to external agents. The public website at kirawallet.xyz is a proposed home for a sample demo, documentation and installation instructions.

This specification defines the next product version. The current viewer has been extended with chain artwork and token and network overviews. The local CLI, provider settings, adult webtoon base character and read-only Kira redesign are implemented in the development build. Browser write actions, persisted jobs and connected agent chat remain planned work. The first product release covers research and watch-only wallet records.

## Users and product outcomes

Start with users who manage several EVM wallets or hold small tokens and bonding-curve assets. The product should help them find holdings, understand recorded prices and available liquidity, and inspect the evidence. A useful result is a reproducible finding or a shorter research workflow. Broad demand and competitor coverage advantages remain hypotheses to test with external users.

The first release must support wallet registration, exact tags, full holdings analysis, price-only refresh, Home totals, wallet pages, token pages, network pages, search, minimum-value filters, source links and recorded analysis history. Model connection must be optional for these routine operations. Contextual chat adds investigation, comparison and explanation through the same tools.

## Distribution and application architecture

Use one local analysis engine and one local job service. The web interface, CLI and agent adapter call typed operations on that service. Preserve the working Python and Node engine during the first packaging milestone; evaluate runtime consolidation only after measuring installation friction and maintenance cost. Runtime versions and the supported platform matrix must be established by clean-machine checks.

A proposed `kira start` command launches a loopback service and opens the browser. A normal hosted web page cannot launch an arbitrary local CLI by itself. The local helper must be installed and running. kirawallet.xyz should offer an interactive sample dataset that demonstrates the experience before installation.

The service owns the wallet registry, jobs, immutable snapshots and price overlays. Financial facts come from the engine. The agent receives structured tool results and produces explanations with source links. It must not invent or overwrite balances, prices or completeness. Saved wallets and evidence must survive an agent restart, a disconnected model or a changed provider.

Planned operations are `wallet.add`, `wallet.setTags`, `analysis.run`, `prices.refresh`, `analysis.resume`, `job.cancel`, `portfolio.read`, `token.read`, `network.read`, `snapshots.compare` and `liquidity.inspect`. Each operation has validated identifiers, a defined output schema and structured errors. Buttons invoke routine jobs directly. Chat chooses among these tools for requests that need interpretation.

## Kira identity and character

Kira is a curious, careful research companion who remembers the user's registered wallets and explains what was checked. Her warmth should make complex research approachable. Her reports should remain factual when data is missing, prices change or an analysis fails.

Create an identity document covering role, voice, knowledge boundaries, supported tasks, evidence requirements and recovery behavior. Use short, calm explanations. Examples include “I checked Base. Two networks still need another connection” and “I found a price, but the recorded quote side is thin.” Do not imply that a rising balance is an achievement or that a mascot expression predicts returns.

The operator approved an adult webtoon research companion with a chic, quietly cute presence. Kira has espresso hair in a loose low bun, calm gray-violet eyes, an ivory shirt, charcoal blazer and a small lavender notebook. The generated base portrait is used by the development viewer. Toony's fixed character descriptions, palette separation and generation records guide consistency. The earlier mascot concepts remain a comparison study. Prepare an approved expression pack for idle, working, partial coverage, waiting and error before production agent integration.

Character states must map to actual job states. Kira may inspect a network badge while that network is being checked, explain an incomplete stage, and point to a useful next action. Avoid fake progress, repeated chat interruptions and continuous celebratory animations. Reduced-motion mode should use static poses and text.

## Kira interface redesign

Keep the light theme, careful typography, readable figures and generous spacing. Introduce warm off-white surfaces, soft corners, small illustrations and restrained pastel accents. The proposed starting palette is ink `#292733`, warm white `#FCFBF8`, violet `#6755CE` and apricot `#F3C89E`. Validate contrast and brand distinction during design development; the development viewer uses these tokens.

Use Kira in onboarding, a compact Home research summary, real analysis progress, empty states and contextual assistance. Keep the holdings table easy to scan. The character should help explain state and suggest an action without occupying the space needed for balances, timestamps and sources.

The primary workspace keeps Home, registered wallets and research detail pages. Add an assistant panel that knows the selected wallet, network or exact token identity. Show its scope before running a request. On mobile, open the assistant in a dedicated sheet or view instead of shrinking the data table beside a chat pane.

Required flows are first launch, public RPC setup, custom RPC setup, optional indexer setup, add wallet and tag, analysis in progress, partial success and retry, price-only refresh, token investigation, network overview, prior-snapshot comparison, model connection and model disconnection. A disconnected model must leave the ordinary research controls usable.

The current token page aggregates one chain ID and contract across wallets, including per-wallet recorded price and burn refund when available. Network pages aggregate direct holdings, with search and minimum combined-value filters. Preserve these semantics in the redesign. Do not merge same-symbol tokens across chains or contracts.

## RPC and token discovery

The current implementation uses an operator-specific Alchemy configuration and several public RPC endpoints. The product must remove machine-specific paths and work without the operator's key. Standard RPC reads and token discovery are separate capabilities. Ethereum JSON-RPC provides methods such as `eth_getBalance`, `eth_call` and `eth_getLogs`; Alchemy's token enumeration is a provider-specific API. A custom RPC URL alone does not guarantee an inventory of every token held by a wallet. [Ethereum JSON-RPC](https://ethereum.org/developers/docs/apis/json-rpc/), [Alchemy Token API](https://www.alchemy.com/docs/data/token-api/token-api-endpoints/alchemy-get-token-balances)

Offer the following independent settings:

| Setting | Required behavior |
| --- | --- |
| Public RPC | Start without an API key using a versioned catalog of reviewed public endpoints. Read native balances, known token contracts and reachable Mint Club registries. Report incomplete general token discovery. |
| Custom RPC | Accept user endpoints per chain, including a self-hosted node. Validate chain ID and required capabilities before use. Keep the endpoint and any headers in local private configuration. |
| Fallback policy | Public mode may use its declared public fallback list. Custom mode defaults to its user-defined endpoints. Switching from a custom endpoint to public infrastructure requires the user's explicit setting. |
| Indexed discovery | Optionally connect a user-owned indexer credential, with Alchemy as the first adapter candidate because the current pipeline already uses it. Keep discovery settings independent of RPC settings. |
| Extended log scan | Offer bounded, resumable transfer-log discovery when useful. Explain the requested range and limitations before starting a large scan. Do not describe a partial log scan as complete discovery. |

Public RPC mode must have an honest capability label such as “Known assets and Mint Club; broader discovery is incomplete.” An API response or catalog by itself cannot establish that a wallet has no Mint Club holdings. That claim requires a complete registry enumeration and balance scan at a recorded block, including ERC1155 ID 0 when in scope.

Connection checks should test `eth_chainId`, a recent block, native balance reads, required contract calls, multicall availability and bounded log access when requested. Record latency, block age, batch limits, historical-read support and sanitized failures. Classify an endpoint as usable, limited, unavailable or wrong network. A successful HTTP response is not sufficient evidence of the required capability.

Use bounded concurrency, adaptive multicall batches, pagination, incremental registry identity caches, retries with backoff and resumable stages. Pin a block per chain for a holdings stage. A fallback must serve that block, or the stage must restart explicitly and record the change. Do not silently combine inconsistent blocks. Viem provides ordered transport fallback; automatic ranking is optional and causes background probes, so the proposed default is ordered fallback without continuous ranking. [Viem fallback transport](https://viem.sh/docs/clients/transports/fallback)

Public endpoint suitability remains to be benchmarked on the actual registry workload. Do not promise identical coverage or speed between public and indexed configurations. Use the current verified Mint Club deployment registry as the starting scope, and check current deployments before release. Testnets have separate presentation and do not contribute to financial USD totals.

## Local settings and credentials

Store non-secret settings in a user-specific Kira directory. Prefer credential references backed by an OS credential store or a private local file. Support environment-variable overrides and explicit configuration paths. Treat a custom URL containing a key as a secret. Migrate the existing operator configuration through an explicit local import path; do not place its values in the source package or a demo dataset.

Serve browser settings as redacted summaries. Keep RPC URLs, headers and model tokens out of agent context, snapshots, reports, logs, exports and the browser state API. Test redaction against path keys, query parameters, userinfo and headers. Local storage means the application controls its saved records; RPC and model providers can still receive requests sent to them.

The future local service needs session authentication, allowed-origin checks and protection against unrelated web pages triggering writes or reading secrets. The model adapter exposes research tools rather than unrestricted shell or filesystem access. Validate tool arguments independently of model instructions and token metadata.

## Agent and model integration

Prototype Codex app-server as the first session adapter. Use the official authentication path suitable for local open-source applications and inspect account/model eligibility and usage limits. OpenAI documents ChatGPT plan use for local open-source clients and a path for Codex app-server, with preview restrictions. Subscription access is not universal unlimited API access. [ChatGPT plan use](https://developers.openai.com/siwc/token-sharing-open-source), [Codex app-server](https://developers.openai.com/siwc/token-sharing-open-source/codex-app-server), [Preview limitations](https://developers.openai.com/siwc/token-sharing-open-source/preview-limitations)

Implement structured session events, reconnect, cancellation, local conversation persistence and resumed jobs. Keep agent-turn state separate from analysis-job state. Retrying a connection must not duplicate wallet registration or rerun a completed refresh.

Define a provider interface so other integrations can be added later. Anthropic currently requires approval to offer claude.ai login or subscription limits in third-party products; otherwise use its documented API-key path. Do not advertise arbitrary existing CLI subscriptions as interchangeable. [Claude Agent SDK](https://code.claude.com/docs/en/agent-sdk/overview)

## Financial data and research quality

Store token quantities as decimal strings and raw on-chain units as integer strings. Distinguish spot value, reported pool TVL, verified active liquidity, shared curve reserves and wallet-sized sell or burn estimates. Quotes must retain their observation time, fees and omitted costs. None is a guarantee of execution.

A full holdings refresh creates a new immutable snapshot. A price-only refresh keeps its separate time and scope. Missing prices, failed chains and incomplete discovery remain unknown rather than zero. Portfolio totals sum direct mainnet holdings only. Nested reserves and shared pool backing must not be added as independent wallet value.

Add snapshot comparison with separate explanations for balance changes, price changes, coverage changes and valuation-method changes. Broader wallet-sized DEX quotes are a later capability to implement and validate; current recorded Mint Club burn quotes are not general DEX execution estimates.

## Release evidence

Use sanitized fixtures and an opt-in sample portfolio. The operator's existing wallet registry, tags, snapshots and credentials are not default public package contents. Provide a protocol adapter guide, contribution instructions, supported-network capability matrix, license and reproducible verification commands. Check artwork licenses and trademark attribution before including third-party token or network images in a distributable asset bundle.

Run an external pilot with approximately 10 to 15 users spanning the initial segments. Measure unaided installation, first useful result, reproducible additional findings, failures, repeat use and maintenance cost. This is a proposed pilot size, not a demand forecast. Publish comparisons only after testing the same wallet scope and observation period, including data the other tool does cover.

## Design and source references

Research checked on 2026-10-03. [Selected UI references](https://www.lazyweb.com/agentic-search/d4bd1497-9716-4312-95b7-f3834ebf2481) inform token context, honest progress and companion onboarding. They do not establish demand or conversion impact. Character artwork must be original.

[Mint Club Explore](https://mint.club/explore) uses network artwork under `/assets/networks/`. The live selector and public bundles supplied the mapping used in the current viewer. Ham and Over references currently resolve to HTML, so the viewer uses its fallback. API token artwork and reserve metadata remain separate from network artwork. [Mint Club API](https://sdk.mint.club/docs/api)
