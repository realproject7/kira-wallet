# Wallet capability direction

Agreed with the operator on 2026-10-04: begin with Watching wallet connection.
Transfers, swaps and OWS Managed wallets need separate design and verification
before implementation. This is a future direction, not a delivered capability.
The account/session and portfolio disclosure gates remain unchanged.

## Two wallet groups, distinct authority

Watching Wallets contains manually entered or explicitly selected external
addresses. An extension connection is an address source and a temporary signer
session, not permission for Kira to spend. Disconnection removes the session
while preserving the recorded watching address. A changing extension account
must not silently add or replace a registered wallet.

Kira Managed Wallets would identify local OWS wallets with explicitly delegated
capabilities. A group name alone does not imply that Kira can sign. A locked,
unconfigured, expired or revoked signer must remain visibly unavailable.
The portfolio model remains keyed by chain and contract; source and execution
capabilities are separate metadata.

## First implementation scope: Watching connection

The reviewed local `lptoken-fun` source was synced by fast-forward to
`b5782b507758f78b6b29e2571bcf1c48f458756b`. Its wallet stack uses Wagmi
3.7.6, `injected()`, EIP-6963 discovery and an explicit wallet chooser. This
means an injected browser provider, not the Injective chain. Its bounded
reconnect, explicit disconnect and separate network-switch behavior are useful
references. Kira's vanilla browser does not require copying its entire React
or RPC stack.

A proposed first ticket will discover providers, let the user choose one,
request accounts only from that choice and preview an address and exact name
before the existing add-and-research operation. No login message, transaction,
chain switch or permission expansion is needed to add a watching address.
Handle absent extensions, user rejection, multiple providers, account changes,
disconnect and late responses. Address registration and provider-consuming
research remain an explicit user action. Mobile handoff is separate from a
successful local connection. An embedded browser may have no extension.

Primary references: [EIP-6963](https://eips.ethereum.org/EIPS/eip-6963),
[EIP-1193](https://eips.ethereum.org/EIPS/eip-1193) and
[MetaMask connection documentation](https://docs.metamask.io/metamask-connect/).

## Transfers and swaps: design before implementation

Reuse mature transaction and protocol libraries instead of writing custody or
DEX contracts. Reuse does not remove integration, approval, slippage, RPC,
protocol or supply-chain risk. Start by considering an external protocol handoff
for swaps. A native transfer flow would still need a confirmed recipient,
chain, asset, amount and fee estimate, fresh simulation and final approval in
the external wallet. An agent cannot infer that approval from a conversation.

An embedded swap needs a separate threat model and pinned provider selection.
The quote's target, chain, calldata, allowance spender, amount, minimum output
and deadline need independent checks. Default to exact allowances, visible
price impact and slippage, no arbitrary unsigned calldata execution, and no
cross-chain bridges in an initial scope. Review protocol guarantees rather than
calling an intermediary UI risk-free.

## OWS Managed wallets: correction and proposed boundary

OWS is not seedless. Its current lifecycle derives accounts from a BIP-39
mnemonic and stores encrypted wallet secrets locally. Password encryption does
not remove backup and recovery responsibilities. The owner passphrase grants
full access without agent policy evaluation. Delegated API tokens instead
trigger policies and are themselves sensitive decryption capabilities.

The current reference architecture performs decryption and signing in-process.
It explicitly does not fully mitigate compromised process memory. A subprocess
enclave is described as future work. Local policies are code-path controls,
not an on-chain or hardware guarantee.

The proposed Kira boundary is a trusted local signer outside the model process.
The browser, model, prompts, research store, telemetry and Git never receive
the mnemonic, private key, owner passphrase or delegated token. OS-protected
credential access belongs to the signer. Model tools provide typed intents
only. The signer enforces wallet, chain, contract, method, recipient, token,
spending, fee, expiry and approval limits and rejects unsupported or undecoded
requests. Generic message signing and policy/credential modification must not
be exposed to the model. No environment credential inherited by an arbitrary
agent shell is acceptable as the boundary.

Before a Managed implementation, pin a specific OWS version and inspect its
actual APIs and policy behavior. Define creation, encrypted backup, restore,
revocation, audit retention, process isolation and OS-platform support. Begin
with synthetic/testnet verification and independent security review. A local
vault does not by itself justify unattended mainnet execution. Native secure
credential UX may require a companion application beyond this loopback viewer.

Primary references checked on 2026-10-04:
[OWS specification](https://docs.openwallet.sh/),
[wallet lifecycle](https://github.com/open-wallet-standard/core/blob/main/docs/06-wallet-lifecycle.md),
[policy access model](https://github.com/open-wallet-standard/core/blob/main/docs/03-policy-engine.md),
[current key isolation limits](https://github.com/open-wallet-standard/core/blob/main/docs/05-key-isolation.md).

No OWS package, wallet creation, signing, transfer or trade was used during this
research. These capabilities are not included in the workspace redesign PR.
