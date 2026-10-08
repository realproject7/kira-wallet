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
The small list includes USDC on seven supported mainnets, USDT on Ethereum and
Avalanche, and WETH on Arbitrum. Decimals and quantities come from on-chain
reads. This list does not cover all common tokens or all wrapped/bridged variants.

The full Mint Club registry is still scanned. Public RPC cannot enumerate all
arbitrary ERC20 contracts held by an address. Discovery remains incomplete
without a working indexer on that network. Incomplete holdings show a persistent
notice on Home and the wallet page, with a path to
[Alchemy setup](ALCHEMY_SETUP.md) and an explicit holdings refresh.

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
