# Free RPC reads and token coverage

Kira contacts public providers directly from the local research process. No
Kira relay or shared credential is required. Free public services are best
effort and can throttle requests or omit historical state.

The reviewed default catalog adds alternatives on Ethereum, Base, BNB Chain,
Polygon, Arbitrum and Optimism. PublicNode is the initial preference. Reserves
are selected per chain rather than downloaded from an untrusted runtime list.
Shibarium and Puppynet use the current official Shib endpoints. Cyber mainnet
adds the official Superchain registry endpoint. Unverified replacements are
never accepted just because an endpoint returns HTTP 200. Some configured
networks can remain unavailable; their missing balances stay unknown.

## Request behavior

- Chain identity is verified once per endpoint session and again after recovery.
- One request runs per endpoint. Provider families share one queue and a
  conservative two-second interval across chains. Two chain scans run at once.
- A logical read has a twelve-second deadline including queues and verification.
  The preferred HTTP attempt has four seconds, reserves at most two seconds.
  Public attempts also have a total budget including verification and pacing,
  leaving half the deadline for a configured personal backup.
  Real fetches are aborted when a deadline expires. HTTP automatic retries are off.
- At most four endpoint attempts run for a read. Public-first configurations
  reserve an attempt for the personal backup after two public providers.
- HTTP 429 and JSON-RPC backpressure cool an endpoint for at least sixty seconds.
  Consecutive throttles increase this to at most thirty minutes. Retry-After
  can extend the wait. Other transport failures have a short cooldown.
- Unsupported methods have a method-specific penalty. Contract reverts do not
  cool an otherwise healthy endpoint. Oversized Multicalls can split; outages and
  throttling cannot create a burst of smaller calls.

These are application limits, not promises about a provider's quota or uptime.
Cooldown observations survive sequential research subprocesses in a bounded
local cache. Custom endpoints and credentialed URLs are not written there.
Status screens and onboarding checks do not probe RPC providers.

## Snapshot consistency

Each chain analysis records a block number and hash. Balance and contract reads
keep that block. Before a fallback provider reads it, Kira verifies its header
has the same hash. Every evidence read then uses an EIP-1898 block-hash selector
with canonical checking. Providers that do not support it cannot supply that
snapshot's evidence. Conflicting or unavailable evidence stays incomplete.
No fallback silently substitutes `latest` for a fixed block.

Identical concurrent reads share work. Successful fixed-block reads have a
bounded cache keyed by chain, pinned hash, method and complete parameters,
including the wallet address. Failed reads are evicted and never become zero.
Wallet balances are not reused across wallets or new research processes.
Registry identity caching remains separate from balances.

## Default token inventory

Native balances and the selected issuer/deployment-backed contracts in
`sources/known-tokens.json` are checked before cold Mint Club enumeration.
The catalog has 63 chain/contract identities on eight mainnets. Issuer references
and selected Uniswap token-list records retain per-contract provenance. The
upstream list commit and its license are bundled; no untrusted runtime list is
loaded. Decimals and quantities come from on-chain reads. This remains a bounded
inventory, not a claim to discover every wrapped or arbitrary token.

Default research also uses Routescan without a key on individually verified
Ethereum, Avalanche and Blast routes. Its documented free access is limited to
two requests per second and 10,000 calls per day. Kira starts at most one call
per second and reads at most 20 pages of 100 candidates per invocation. Its
cursor, candidate segments and quota retry deadline survive process restarts.
The standalone adapter defaults to a 25-second budget. An isolated HTTP reader enforces a total deadline,
including DNS and response bodies. Unsafe pagination, outages, malformed data
and limits keep coverage partial. Provider quantities and prices never replace
RPC-verified balances. Other Routescan chains are not presumed supported.
Explicit keyless opt-outs and custom-only preferences remain respected.

Initial reports check Base, Ethereum and Blast, up to 128 candidates per chain.
Selected common contracts take priority. Remaining candidates and networks are
explicitly pending. A durable background continuation scans every configured
network, the full Mint Club registry and markets. Pinned registry counts,
successful identities, failed indices and the next index are saved after each
batch. Each chain receives at most four registry and four balance batches per
category in a scheduling round before unfinished chains receive another turn.
Successful balances retain their original block and observation time. A failed
registry reread cannot remove a previously saved positive observation from the
same research run. Batches contain at most 128 reads, with splitting only for
verified payload limits. Three consecutive unchanged rounds leave work explicitly
incomplete. Registry identities can be reused; wallet balances stay wallet-specific.
New initial work takes priority over detailed research. Older same-wallet
continuations cannot replace newer evidence.

Public RPC cannot enumerate all arbitrary ERC20 contracts. Alchemy is an
optional broader candidate source and backup RPC. Discovery calls made through
the wallet engine have a 25-second initial or 60-second detailed per-chain
budget. Native balances, free candidates and Mint Club research remain usable
without it. Missing or deferred evidence stays unknown. Persistent coverage
notices distinguish pending work from failed reads and offer retry or optional
[Alchemy setup](ALCHEMY_SETUP.md).

Keyless sources: [Routescan addresses](https://routescan.io/docs/api/addresses),
[API access](https://routescan.io/docs/plans-and-limits/api-keys-and-pricing),
[rate limits](https://routescan.io/docs/plans-and-limits/rate-limits).

## Read preferences

Public first is the default even when a custom connection is configured.
Advanced settings provide custom first and custom only. Configurations without
the new priority field use public first; an existing explicit custom-only choice
continues to exclude public endpoints. RPC priority does not change the dedicated
Alchemy discovery request.

CLI example using an existing local endpoint variable:

```sh
kira rpc set --chain 8453 --url-env KIRA_BASE_RPC --priority public_first
```

Primary references: [EIP-1898](https://eips.ethereum.org/EIPS/eip-1898),
[PublicNode](https://www.publicnode.com/),
[dRPC limits](https://drpc.org/docs/howitworks/ratelimiting),
[1RPC networks](https://docs.1rpc.io/overview/supported-networks),
[Circle contracts](https://developers.circle.com/stablecoins/usdc-contract-addresses),
[Tether contracts](https://tether.to/en/supported-protocols/),
[Uniswap Arbitrum deployments](https://developers.uniswap.org/docs/protocols/v3/deployments/v3-arbitrum-deployments).

## Recorded route evidence and remaining limits

Chain coverage includes `rpc_routes`: bounded aggregate logical endpoint outcomes
with public/custom class, endpoint index, method, outcome and count. Failures
can include HTTP or RPC error codes. A successful read can follow failed public
attempts; configuring public first does not prove every read was public.
Cooldown skips, queue timeouts and successes are distinct. The receipt contains
no endpoint URLs, keys, request arguments or balances. Cached checkpoints retain
their original evidence and routes; a resume is not a fresh observation.

A live October 10 check identified DNS failures on the old Shib endpoints,
Ham, Over and Cyber testnet. Current official Shib endpoints returned the correct
chain identities and supported hash-qualified balance reads. Cyber mainnet's
registry endpoint also passed. The official Cyber testnet replacement failed
certificate validation, so it was not added. Ham and Over have no verified
replacement in this catalog. This is an observation, not a claim that their
chains permanently stopped. Their failed checks remain visible.

Base public balance reads work independently of arbitrary token discovery.
In published 0.1.9, the keyless Base inventory was selected common contracts and Mint Club. The next candidate adds the Etherscan transfer path below.
Blockscout's current documentation deprecates per-instance APIs in favor of its
keyed PRO API. Kira does not promise keyless Base enumeration through that route.
The former 1RPC Base reserve returned HTTP 410 during block lookup and was
removed. PublicNode and dRPC remain verified Base candidates. The official Base
public endpoint returned HTTP 403 in this test and was not silently substituted.

Sources: [Shib network setup](https://docs.shib.io/get-started/deploy-contracts),
[Superchain registry](https://github.com/ethereum-optimism/superchain-registry/blob/main/chainList.toml),
[Ham network information](https://docs.ham.fun/docs/network-information/),
[Blockscout API migration](https://docs.blockscout.com/devs/apis).


## Keyless transfer candidates

Kira uses [Etherscan keyless MCP](https://docs.etherscan.io/build-with-ai/mcp)
for ERC20 transfer identities on Ethereum, Base, Optimism, Arbitrum, Polygon,
BNB Smart Chain, Unichain, ApeChain, Robinhood, Sepolia, Base Sepolia and Fuji.
This backend adapter needs no model MCP configuration,
API key, paid relay or shared credentials. Routescan remains available on
Ethereum, Avalanche and Blast. Where sources overlap, candidates are unioned
and each source keeps its own completion evidence and checkpoint. Standard RPC verifies each candidate at a canonical
pinned block. Transfer amounts never become wallet balances.

The optional `explorers` setting adds paginated hosted explorer reads for
Shibarium, Cyber, HashKey and Puppynet, using their admitted official hosts.
It remains off by default and respects custom-only preferences. Per-instance
Blockscout APIs are deprecated upstream, so these paths remain best effort.
Ham, Over, Zora, Kaia, Blast Sepolia and Cyber testnet have no admitted keyless
general-token route in this catalog. Their native and Mint Club RPC checks are
independent. An empty accepted page does not prove representative asset coverage.
Robinhood's ordinary API has a published October 16, 2026 paid-tier change;
its effect on keyless MCP remains unconfirmed. This adapter does not promise
permanent free access or silently switch to paid credentials.

Each request scans at most three 100-record pages within the research budget.
A window ends at a block before a timestamp two minutes behind the local clock,
allowing for explorer indexing lag. Its block bounds and next page are saved
per wallet and chain. A later refresh continues unfinished history. Once a
window finishes, subsequent refreshes recheck a 2,048-block overlap, scan new
blocks and retain earlier candidate identities. A deeper reorg or older indexer
backfill can still omit identities. Fresh intervals discovered while older
history is pending are also saved as unfinished ranges. A continuation can keep
the existing window fixed instead of continually chasing a new chain head.
At 100 full pages, an unfinished range splits into two inclusive, disjoint block
ranges. Both children must finish; parent candidates are deduplicated by contract.
A single block that exceeds the page limit remains explicitly unresolved.
Candidate segments contain at most 512 identities and are durable before the
frontier manifest advances. The former 10,000-contract limit no longer prevents
large histories from finishing. Provider backfills, history limits, indexing lag and
unsupported networks can still omit tokens. A finished window is not proof
of a complete inventory. No majority-coverage promise is made.

The shared local request lane conservatively paces tool calls every two seconds.
HTTP 429 pauses that lane and saves its retry deadline with an established
frontier. It does not rotate accounts or evade provider limits.
Sessions stay in process memory. Saved evidence contains candidate contracts
and window facts, never MCP session IDs, credentials or transfer-derived balances.
No liquidity or dollar-value filter removes candidate identities. Spam transfers
can introduce irrelevant candidates. Only positive RPC balances enter holdings.

Earlier positive holdings, common known contracts and Mint Club identities
supplement candidate discovery. Targeted suspicious zeros receive up to eight
direct and qualified peer checks per chain slice, at the same pinned hash. Saved
successful checks do not consume the next slice's allowance. Conflicting
or unavailable checks remain unknown. Ordinary zero-heavy registry scans do
not receive an unbounded peer fan-out.

## Network lifecycle

A verified retirement notice removes a network from new default research and
current valuation. Historical assets and timestamps remain available.
Connectivity, stale observed heads, token discovery and provider support loss
remain separate facts. Ham has an operator retirement report with no verified
primary closure notice. It is labelled explicitly, without recommending
Alchemy as a verified recovery path. Degen L3 is absent from the current catalog;
its reviewed Alchemy notice is separate from Base DEGEN. A responding archive
endpoint does not make a retired chain current. No bridge or migration outcome
is promised.
