# Free RPC reads and token coverage

Kira contacts public providers directly from the local research process. No
Kira relay or shared credential is required. Free public services are best
effort and can throttle requests or omit historical state.

The reviewed default catalog adds alternatives on Ethereum, Base, BNB Chain,
Polygon, Arbitrum and Optimism. PublicNode is the initial preference. Reserves
are selected per chain rather than downloaded from an untrusted runtime list.
The other supported networks retain their existing endpoints.

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
The catalog has 57 chain/contract identities on eight mainnets. Issuer references
and selected Uniswap token-list records retain per-contract provenance. The
upstream list commit and its license are bundled; no untrusted runtime list is
loaded. Decimals and quantities come from on-chain reads. This remains a bounded
inventory, not a claim to discover every wrapped or arbitrary token.

Default research also uses Routescan without a key on individually verified
Ethereum, Avalanche and Blast routes. Its documented free access is limited to
two requests per second and 10,000 calls per day. Kira starts at most one call
per second, reads at most 20 pages of 100 candidates per chain and spends at most
25 seconds per enumeration. An isolated HTTP reader enforces a total deadline,
including DNS and response bodies. Unsafe pagination, outages, malformed data
and limits keep coverage partial. Provider quantities and prices never replace
RPC-verified balances. Other Routescan chains are not presumed supported.
Explicit keyless opt-outs and custom-only preferences remain respected.

Initial reports check Base, Ethereum and Blast, up to 128 candidates per chain.
Selected common contracts take priority. Remaining candidates and networks are
explicitly pending. A durable background continuation scans every configured
network, the full Mint Club registry and markets. Registry identity prefixes
are saved incrementally; balances are never shared between wallets. Batches
contain at most 128 reads, with splitting only for verified payload limits.
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
